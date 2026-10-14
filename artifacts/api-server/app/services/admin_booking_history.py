import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from fastapi import HTTPException
from app.models.garage import Garage
from app.models.admin_operations import SourceRecord
from app.models.booking import Booking


async def lock_booking(session, garage_id, booking_id):
    await session.execute(select(Booking.id).where(
        Booking.id == booking_id, Booking.garage_id == garage_id).with_for_update())


async def ensure_new_work(session, garage_id):
    garage = (await session.execute(select(Garage).where(Garage.id == garage_id).with_for_update())).scalar_one_or_none()
    if not garage or garage.operational_status != "ACTIVE":
        raise HTTPException(409, "GARAGE_SUSPENDED: existing work remains accessible")


async def record_booking_event(session, booking, status):
    garage = await session.get(Garage, booking.garage_id)
    session.add(SourceRecord(
        id=uuid.uuid4(), kind="BOOKING_EVENT", source="garage-owner-api",
        external_id=f"{booking.id}:{status}", garage_id=booking.garage_id,
        booking_id=booking.id, status=status, occurred_at=datetime.now(timezone.utc),
        payload={"actor_id": str(garage.user_id)} if garage else {},
    ))
    await session.flush()
    from app.models.customer_workspace import CustomerBookingLink
    from app.services.customer_workspace_base import CustomerWorkspaceBase
    link = await session.get(CustomerBookingLink, booking.id)
    if link:
        await CustomerWorkspaceBase(session, link.customer_id).notify(
            "BOOKINGS", f"Booking status: {status}", booking.id, f"booking:{booking.id}:{status}")
