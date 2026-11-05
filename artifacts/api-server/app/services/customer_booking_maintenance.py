"""Expire unattended pending appointments without claiming accepted work expired."""
from sqlalchemy import select, and_, or_
from zoneinfo import ZoneInfo
from app.core.customer_security import now
from app.models.booking import Booking, BookingStatus
from app.models.customer_workspace import CustomerBookingLink, AppointmentSlot
from app.services.admin_booking_history import record_booking_event


async def expire_pending_bookings(db):
    today = now().astimezone(ZoneInfo("Asia/Kolkata")).date()
    bookings = (await db.execute(select(Booking).join(CustomerBookingLink).outerjoin(
        AppointmentSlot, AppointmentSlot.id == CustomerBookingLink.slot_id
    ).where(Booking.status == BookingStatus.PENDING, Booking.deleted_at.is_(None),
            or_(and_(CustomerBookingLink.slot_id.is_not(None), AppointmentSlot.starts_at <= now()),
                and_(CustomerBookingLink.slot_id.is_(None), Booking.booking_date < today))).with_for_update(
                of=Booking, skip_locked=True).limit(100))).scalars().all()
    for booking in bookings:
        booking.status = BookingStatus.EXPIRED
        await record_booking_event(db, booking, "EXPIRED")
    return len(bookings)
