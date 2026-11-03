"""Garage actions must not revive expired customer appointments."""
from app.models.customer_workspace import CustomerBookingLink, AppointmentSlot
from app.core.customer_security import now
from app.core.exceptions import BadRequestException


async def validate_customer_appointment(db, booking):
    link = await db.get(CustomerBookingLink, booking.id)
    if link:
        if link.cancelled_at:
            raise BadRequestException("Customer appointment is expired or cancelled")
        if link.slot_id:
            slot = await db.get(AppointmentSlot, link.slot_id)
            if not slot or slot.starts_at <= now():
                raise BadRequestException("Customer appointment is expired or cancelled")
