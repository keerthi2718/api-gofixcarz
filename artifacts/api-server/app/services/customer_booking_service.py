"""Date-only customer bookings, immutable service snapshots and safe retries."""
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
from app.models.admin_operations import AccountGarage, CustomerAccount
from app.models.job import Job
from app.services.customer_attachment_service import CustomerAttachmentService
from app.services.customer_otp_service import fail


class CustomerBookingService(CustomerAttachmentService):
    async def garage(self, identifier):
        garage = await self.db.get(Garage, identifier)
        if not garage or garage.deleted_at:
            fail("GARAGE_NOT_FOUND", 404)
        if garage.operational_status != "ACTIVE" or garage.verification_status != "VERIFIED":
            fail("GARAGE_UNAVAILABLE", 409)
        return garage

    async def services(self, garage_id, identifiers):
        if not identifiers or len(set(identifiers)) != len(identifiers):
            fail("SERVICE_INACTIVE", 422)
        rows = (await self.db.execute(select(ServicePackage).where(
            ServicePackage.id.in_(identifiers), ServicePackage.garage_id == garage_id,
            ServicePackage.deleted_at.is_(None), ServicePackage.is_active.is_(True)))).scalars().all()
        if len(rows) != len(identifiers) or any(row.price < 0 for row in rows):
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
        duration = sum(row.duration_minutes or 0 for row in services)
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

    async def booking_selection(self, data):
        if data.booking_date < now().astimezone(ZoneInfo("Asia/Kolkata")).date():
            fail("INVALID_APPOINTMENT_DATE", 422)
        garage = await self.garage(data.garage_id)
        vehicle = await self.vehicle(data.vehicle_id)
        services = await self.services(garage.id, data.service_ids)
        await self.validate_attachments(data.attachment_ids, "BOOKING_PHOTO")
        items = [{"id": str(s.id), "name": s.name,
                  "description": s.description, "price_inr": str(s.price),
                  "amount": int((Decimal(s.price) * 100).quantize(Decimal("1"))),
                  "duration_minutes": s.duration_minutes} for s in services]
        total = sum(s["amount"] for s in items)
        if data.expected_total is not None and data.expected_total != total:
            fail("PRICE_CHANGED", 409)
        return {
            "garage": {"id": str(garage.id), "name": garage.name},
            "vehicle": {"id": str(vehicle.id), "registration_number": vehicle.registration_number},
            "services": items, "booking_date": data.booking_date.isoformat(),
            "notes": data.notes, "attachment_ids": [str(i) for i in data.attachment_ids],
            "estimated_total": total, "currency": "INR",
        }

    async def submit(self, data, key, account, identity):
        # Serialize per-account creation so concurrent retries and bridge creation
        # cannot create duplicate bookings or per-garage customer records.
        await self.db.execute(select(CustomerAccount.id).where(
            CustomerAccount.id == self.customer_id).with_for_update())
        request = data.model_dump(mode="json")
        original = (await self.db.execute(self.query("BOOKING_REQUEST").where(
            CustomerResource.dedupe_key == key))).scalar_one_or_none()
        if original:
            if original.payload.get("request") != request:
                fail("IDEMPOTENCY_CONFLICT", 409)
            booking, link = await self.booking(UUID(original.payload["booking_id"]))
            return await self.booking_row(booking, link)
        # Freeze the garage's eligibility while committing new work.
        await self.db.execute(select(Garage.id).where(
            Garage.id == data.garage_id).with_for_update())
        # Freeze selected prices/status until the immutable snapshot is saved.
        await self.db.execute(select(ServicePackage.id).where(
            ServicePackage.garage_id == data.garage_id,
            ServicePackage.id.in_(data.service_ids)).order_by(ServicePackage.id).with_for_update())
        selection = await self.booking_selection(data)
        # Retain existing snapshot storage and legacy foreign keys. This internal
        # identifier is never an input/output of the new customer contract.
        quote = await self.add("QUOTE", selection, garage_id=data.garage_id, status="SUBMITTED")
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
                          booking_date=data.booking_date,
                          notes=data.notes, customer_name=account.name, customer_mobile=identity.mobile,
                          service_requested=", ".join(s["name"] for s in selection["services"]))
        self.db.add(booking)
        await self.db.flush()
        link = CustomerBookingLink(booking_id=booking.id, customer_id=self.customer_id,
                                   vehicle_id=data.vehicle_id, slot_id=None, quote_id=quote.id)
        self.db.add(link)
        await self.db.flush()
        quote.status = "SUBMITTED"
        result = await self.booking_row(booking, link)
        await self.add("BOOKING_REQUEST", {"request": request, "booking_id": str(booking.id)}, key=key)
        await self.notify("BOOKINGS", "Booking request submitted", booking.id, f"booking:{booking.id}:PENDING")
        return result

    async def booking_row(self, booking, link):
        slot = await self.db.get(AppointmentSlot, link.slot_id) if link.slot_id else None
        quote = await self.resource(link.quote_id, "QUOTE")
        jobs = (await self.db.execute(select(Job).where(Job.booking_id == booking.id,
                                                       Job.deleted_at.is_(None)))).scalars().all()
        status = booking.status.value
        future = slot.starts_at > now() if slot else (
            booking.booking_date is not None
            and booking.booking_date >= now().astimezone(ZoneInfo("Asia/Kolkata")).date())
        can_cancel = status == "PENDING" and future and not jobs
        return {"id": booking.id, "status": status, "garage": quote.payload["garage"],
                "vehicle": quote.payload["vehicle"], "services": quote.payload["services"],
                "booking_date": booking.booking_date,
                "starts_at": slot.starts_at if slot else None, "ends_at": slot.ends_at if slot else None,
                "notes": quote.payload.get("notes"),
                "attachment_ids": quote.payload.get("attachment_ids", []),
                "estimated_total": quote.payload["estimated_total"], "currency": "INR",
                "can_cancel": can_cancel, "cancel_reason": None if can_cancel else "Only current/future PENDING bookings without jobs may be cancelled",
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
