"""Slot capacity, immutable quotes and idempotent customer booking submission."""
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import func, select
from app.core.customer_security import now
from app.models.booking import Booking, BookingStatus
from app.models.customer import Customer
from app.models.vehicle import Vehicle
from app.models.garage import Garage
from app.models.service_package import ServicePackage
from app.models.customer_workspace import AppointmentSlot, CustomerBookingLink, CustomerResource
from app.models.admin_operations import AccountGarage
from app.models.job import Job
from app.schemas.customer_workspace import QuoteRequest
from app.services.customer_attachment_service import CustomerAttachmentService
from app.services.customer_otp_service import fail


class CustomerBookingService(CustomerAttachmentService):
    async def garage(self, identifier):
        garage = await self.db.get(Garage, identifier)
        if not garage or garage.deleted_at:
            fail("GARAGE_NOT_FOUND", 404)
        if garage.operational_status != "ACTIVE":
            fail("GARAGE_UNAVAILABLE", 409)
        return garage

    async def services(self, garage_id, identifiers):
        if not identifiers or len(set(identifiers)) != len(identifiers):
            fail("SERVICE_INACTIVE", 422)
        rows = (await self.db.execute(select(ServicePackage).where(
            ServicePackage.id.in_(identifiers), ServicePackage.garage_id == garage_id,
            ServicePackage.deleted_at.is_(None), ServicePackage.is_active.is_(True)))).scalars().all()
        if len(rows) != len(identifiers) or any(
            row.duration_minutes is None or row.duration_minutes <= 0 for row in rows
        ):
            fail("SERVICE_INACTIVE", 422)
        by_id = {row.id: row for row in rows}
        return [by_id[identifier] for identifier in identifiers]

    async def slot_free(self, slot):
        count = (await self.db.execute(select(func.count()).select_from(CustomerBookingLink).join(
            Booking, Booking.id == CustomerBookingLink.booking_id).where(
                CustomerBookingLink.slot_id == slot.id, Booking.deleted_at.is_(None),
                Booking.status.in_([BookingStatus.PENDING, BookingStatus.ACCEPTED, BookingStatus.CONVERTED])
            ))).scalar_one()
        return slot.active and slot.starts_at > now() and count < slot.capacity

    async def availability(self, garage_id, day, service_ids):
        await self.garage(garage_id)
        services = await self.services(garage_id, service_ids)
        duration = sum(row.duration_minutes for row in services)
        rows = (await self.db.execute(select(AppointmentSlot).where(
            AppointmentSlot.garage_id == garage_id, AppointmentSlot.active.is_(True)
        ).order_by(AppointmentSlot.starts_at))).scalars().all()
        timezone = rows[0].timezone if rows else "Asia/Kolkata"
        if day < now().astimezone(ZoneInfo(timezone)).date():
            fail("INVALID_APPOINTMENT_DATE", 422)
        slots = []
        for row in rows:
            if row.starts_at.astimezone(ZoneInfo(row.timezone)).date() != day:
                continue
            if (row.ends_at - row.starts_at).total_seconds() < duration * 60:
                continue
            slots.append({"id": row.id, "starts_at": row.starts_at, "ends_at": row.ends_at,
                          "available": await self.slot_free(row)})
        return {"date": day, "timezone": timezone, "slots": slots}

    async def quote_selection(self, data):
        garage = await self.garage(data.garage_id)
        vehicle = await self.vehicle(data.vehicle_id)
        services = await self.services(garage.id, data.service_ids)
        await self.validate_attachments(data.attachment_ids, "BOOKING_PHOTO")
        slot = await self.db.get(AppointmentSlot, data.slot_id)
        if not slot or slot.garage_id != garage.id or not await self.slot_free(slot):
            fail("SLOT_UNAVAILABLE", 409)
        if (slot.ends_at - slot.starts_at).total_seconds() < sum(s.duration_minutes for s in services) * 60:
            fail("SLOT_UNAVAILABLE", 409)
        items = [{"id": str(s.id), "name": s.name,
                  "amount": int((Decimal(s.price) * 100).quantize(Decimal("1"))),
                  "duration_minutes": s.duration_minutes} for s in services]
        return {
            "garage": {"id": str(garage.id), "name": garage.name},
            "vehicle": {"id": str(vehicle.id), "registration_number": vehicle.registration_number},
            "services": items, "starts_at": slot.starts_at.isoformat(), "ends_at": slot.ends_at.isoformat(),
            "notes": data.notes, "attachment_ids": [str(i) for i in data.attachment_ids],
            "estimated_total": sum(s["amount"] for s in items), "currency": "INR",
            "expires_at": (now() + timedelta(minutes=10)).isoformat(), "slot_reserved": False,
            "slot_id": str(slot.id),
        }

    async def create_quote(self, data):
        payload = await self.quote_selection(data)
        row = await self.add("QUOTE", payload, garage_id=data.garage_id)
        return {"quote_id": row.id, **payload}

    async def submit(self, quote_id, key, account, identity):
        original = (await self.db.execute(self.query("BOOKING_REQUEST").where(
            CustomerResource.dedupe_key == key))).scalar_one_or_none()
        if original:
            if original.payload["quote_id"] != str(quote_id):
                fail("IDEMPOTENCY_CONFLICT", 409)
            return original.payload["response"]
        quote = await self.resource(quote_id, "QUOTE")
        if quote.status != "ACTIVE" or datetime.fromisoformat(quote.payload["expires_at"]) <= now():
            fail("QUOTE_EXPIRED", 409)
        slot_id = UUID(quote.payload["slot_id"])
        # Row lock serializes capacity checks across customers/workers.
        await self.db.execute(select(AppointmentSlot.id).where(
            AppointmentSlot.id == slot_id).with_for_update())
        data = QuoteRequest(
            garage_id=quote.garage_id, vehicle_id=quote.payload["vehicle"]["id"],
            service_ids=[s["id"] for s in quote.payload["services"]], slot_id=slot_id,
            notes=quote.payload["notes"], attachment_ids=quote.payload["attachment_ids"],
        )
        selection = await self.quote_selection(data)
        for name in ("services", "vehicle", "starts_at", "ends_at", "estimated_total"):
            if selection[name] != quote.payload[name]:
                fail("QUOTE_STALE", 409)
        # Create deliberate per-account/vehicle garage records for NEW work.
        # Never match historical contacts/vehicles by phone or registration.
        bridge_key = f"{quote.garage_id}:{data.vehicle_id}"
        bridge = (await self.db.execute(self.query("GARAGE_BRIDGE").where(
            CustomerResource.dedupe_key == bridge_key))).scalar_one_or_none()
        if not bridge:
            vehicle = await self.vehicle(data.vehicle_id)
            contact = Customer(id=uuid4(), garage_id=quote.garage_id, name=account.name, mobile=identity.mobile)
            self.db.add(contact)
            await self.db.flush()
            garage_vehicle = Vehicle(id=uuid4(), garage_id=quote.garage_id, customer_id=contact.id,
                                    make=vehicle.brand, model=vehicle.model, year=vehicle.year,
                                    registration_plate=vehicle.registration_number)
            self.db.add(garage_vehicle)
            await self.db.flush()
            bridge = await self.add("GARAGE_BRIDGE", {"contact_id": contact.id, "vehicle_id": garage_vehicle.id},
                                    garage_id=quote.garage_id, key=bridge_key)
        if not await self.db.get(AccountGarage, (self.customer_id, quote.garage_id)):
            self.db.add(AccountGarage(account_id=self.customer_id, garage_id=quote.garage_id))
        # Only these deliberately created bridge records are refreshed. Never
        # search or claim a historical garage record using contact details.
        vehicle = await self.vehicle(data.vehicle_id)
        contact = await self.db.get(Customer, UUID(bridge.payload["contact_id"]))
        garage_vehicle = await self.db.get(Vehicle, UUID(bridge.payload["vehicle_id"]))
        if not contact or contact.deleted_at or not garage_vehicle or garage_vehicle.deleted_at:
            fail("GARAGE_BRIDGE_UNAVAILABLE", 409)
        contact.name, contact.mobile = account.name, identity.mobile
        garage_vehicle.make, garage_vehicle.model = vehicle.brand, vehicle.model
        garage_vehicle.year, garage_vehicle.registration_plate = vehicle.year, vehicle.registration_number
        booking = Booking(id=uuid4(), garage_id=quote.garage_id,
                          customer_id=UUID(bridge.payload["contact_id"]), vehicle_id=UUID(bridge.payload["vehicle_id"]),
                          status=BookingStatus.PENDING,
                          booking_date=datetime.fromisoformat(selection["starts_at"]).date(),
                          notes=data.notes, customer_name=account.name, customer_mobile=identity.mobile,
                          service_requested=", ".join(s["name"] for s in selection["services"]))
        self.db.add(booking)
        await self.db.flush()
        link = CustomerBookingLink(booking_id=booking.id, customer_id=self.customer_id,
                                   vehicle_id=data.vehicle_id, slot_id=slot_id, quote_id=quote.id)
        self.db.add(link)
        await self.db.flush()
        quote.status = "SUBMITTED"
        result = await self.booking_row(booking, link)
        await self.add("BOOKING_REQUEST", {"quote_id": quote_id, "response": result}, key=key)
        await self.notify("BOOKINGS", "Booking request submitted", booking.id, f"booking:{booking.id}:PENDING")
        return result

    async def booking_row(self, booking, link):
        slot = await self.db.get(AppointmentSlot, link.slot_id)
        quote = await self.resource(link.quote_id, "QUOTE")
        jobs = (await self.db.execute(select(Job).where(Job.booking_id == booking.id,
                                                       Job.deleted_at.is_(None)))).scalars().all()
        status = booking.status.value
        can_cancel = status == "PENDING" and slot.starts_at > now() and not jobs
        return {"id": booking.id, "status": status, "garage": quote.payload["garage"],
                "vehicle": quote.payload["vehicle"], "services": quote.payload["services"],
                "starts_at": slot.starts_at, "ends_at": slot.ends_at, "notes": quote.payload["notes"],
                "attachment_ids": quote.payload["attachment_ids"],
                "estimated_total": quote.payload["estimated_total"], "currency": "INR",
                "can_cancel": can_cancel, "cancel_reason": None if can_cancel else "Only future PENDING bookings may be cancelled",
                "linked_job_id": jobs[0].id if jobs else None,
                "linked_job_status": jobs[0].status.value if jobs else None,
                "created_at": booking.created_at}

    async def list_bookings(self, page, page_size, status=None, vehicle_id=None, garage_id=None,
                            linked_job_status=None):
        query = select(Booking).join(CustomerBookingLink).where(
            CustomerBookingLink.customer_id == self.customer_id, Booking.deleted_at.is_(None))
        if status:
            query = query.where(Booking.status == status)
        if vehicle_id:
            query = query.where(CustomerBookingLink.vehicle_id == vehicle_id)
        if garage_id:
            query = query.where(Booking.garage_id == garage_id)
        if linked_job_status:
            query = query.where(select(Job.id).where(Job.booking_id == Booking.id,
                Job.status == linked_job_status, Job.deleted_at.is_(None)).exists())
        async def render(booking):
            return await self.booking_row(booking, await self.db.get(CustomerBookingLink, booking.id))
        return await self.page(query.order_by(Booking.created_at.desc(), Booking.id), page, page_size, render)

    async def cancel(self, identifier, reason):
        booking, link = await self.booking(identifier)
        await self.db.execute(select(Booking.id).where(Booking.id == identifier).with_for_update())
        await self.db.refresh(booking)
        if not (await self.booking_row(booking, link))["can_cancel"]:
            fail("BOOKING_CANNOT_CANCEL", 409)
        booking.status = BookingStatus.CANCELLED
        link.cancelled_at, link.cancellation_reason = now(), reason
        from app.services.admin_booking_history import record_booking_event
        await record_booking_event(self.db, booking, "CANCELLED")
        await self.notify("BOOKINGS", "Booking cancelled", booking.id, f"booking:{booking.id}:CANCELLED")
        return {"id": booking.id, "status": "CANCELLED", "cancelled_at": link.cancelled_at}
