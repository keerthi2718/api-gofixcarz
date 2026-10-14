"""Expire unattended pending appointments without claiming accepted work expired."""
from sqlalchemy import select
from app.core.customer_security import now
from app.models.booking import Booking, BookingStatus
from app.models.customer_workspace import CustomerBookingLink, AppointmentSlot
from app.services.admin_booking_history import record_booking_event


async def expire_pending_bookings(db):
    bookings = (await db.execute(select(Booking).join(CustomerBookingLink).join(
        AppointmentSlot, AppointmentSlot.id == CustomerBookingLink.slot_id
    ).where(Booking.status == BookingStatus.PENDING, Booking.deleted_at.is_(None),
            AppointmentSlot.starts_at <= now()).with_for_update(
                of=Booking, skip_locked=True).limit(100))).scalars().all()
    for booking in bookings:
        booking.status = BookingStatus.EXPIRED
        await record_booking_event(db, booking, "EXPIRED")
    return len(bookings)
