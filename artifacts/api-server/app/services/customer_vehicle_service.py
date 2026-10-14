"""Customer vehicles, atomic default selection and archival."""
from sqlalchemy import select
from app.core.customer_security import now
from app.models.customer_workspace import CustomerVehicle, CustomerBookingLink
from app.models.booking import Booking
from app.models.job import Job
from app.services.customer_workspace_base import CustomerWorkspaceBase
from app.services.customer_otp_service import fail


class CustomerVehicleService(CustomerWorkspaceBase):
    @staticmethod
    def vehicle_row(row):
        return {name: getattr(row, name) for name in (
            "id", "registration_number", "brand", "model", "fuel_type", "year",
            "odometer_km", "is_default")}

    def vehicles(self):
        return select(CustomerVehicle).where(CustomerVehicle.customer_id == self.customer_id,
                                              CustomerVehicle.archived_at.is_(None))

    async def duplicate(self, registration, exclude=None):
        query = self.vehicles().where(CustomerVehicle.registration_number == registration)
        if exclude:
            query = query.where(CustomerVehicle.id != exclude)
        if (await self.db.execute(query)).scalar_one_or_none():
            fail("VEHICLE_ALREADY_EXISTS", 409)

    async def choose_default(self, identifier):
        row = await self.vehicle(identifier)
        # Flush clearing the old default before setting the new one (partial index).
        for old in (await self.db.execute(self.vehicles())).scalars().all():
            old.is_default = False
        await self.db.flush()
        row.is_default = True
        await self.db.flush()
        return {"default_vehicle_id": row.id}

    async def create_vehicle(self, data):
        await self.duplicate(data.registration_number)
        first = not (await self.db.execute(self.vehicles().limit(1))).scalar_one_or_none()
        row = CustomerVehicle(customer_id=self.customer_id, **data.model_dump(exclude={"is_default"}))
        self.db.add(row)
        await self.db.flush()
        if first or data.is_default:
            await self.choose_default(row.id)
        return self.vehicle_row(row)

    async def patch_vehicle(self, identifier, data):
        row = await self.vehicle(identifier)
        if data.registration_number:
            await self.duplicate(data.registration_number, identifier)
        for name, value in data.model_dump(exclude_unset=True).items():
            setattr(row, name, value)
        await self.db.flush()
        return self.vehicle_row(row)

    async def remove_vehicle(self, identifier):
        row = await self.vehicle(identifier)
        links = (await self.db.execute(select(CustomerBookingLink).where(
            CustomerBookingLink.customer_id == self.customer_id,
            CustomerBookingLink.vehicle_id == identifier))).scalars().all()
        for link in links:
            booking = await self.db.get(Booking, link.booking_id)
            jobs = (await self.db.execute(select(Job).where(Job.booking_id == link.booking_id,
                                                           Job.deleted_at.is_(None)))).scalars().all()
            if (not link.cancelled_at and booking.status.value in {"PENDING", "ACCEPTED"}) or any(
                job.status.value not in {"COMPLETED", "CANCELLED"} for job in jobs
            ):
                fail("VEHICLE_HAS_ACTIVE_WORK", 409)
        was_default = row.is_default
        row.is_default, row.archived_at = False, now()
        await self.db.flush()
        if was_default:
            replacement = (await self.db.execute(self.vehicles().order_by(
                CustomerVehicle.created_at, CustomerVehicle.id).limit(1))).scalar_one_or_none()
            if replacement:
                replacement.is_default = True
        return {"id": row.id, "removed": True}
