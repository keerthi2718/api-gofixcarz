"""Customer quote and booking response contracts; monetary amounts are paise."""
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.booking import BookingStatus


class BookingGarage(BaseModel):
    id: UUID
    name: str
    address: str | None = None


class BookingVehicle(BaseModel):
    id: UUID
    registration_number: str
    brand: str | None = None
    model: str | None = None
    year: int | None = None


class BookingSelectedService(BaseModel):
    id: UUID
    name: str
    amount: int
    duration_minutes: int | None = None


class CustomerAppointmentDetails(BaseModel):
    garage: BookingGarage
    vehicle: BookingVehicle
    services: list[BookingSelectedService]
    slot_id: UUID | None = None
    scheduled_date: date | None = None
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    notes: str | None = None
    attachment_ids: list[UUID]
    estimated_total: int
    currency: str


class CustomerQuoteResponse(CustomerAppointmentDetails):
    quote_id: UUID
    expires_at: datetime
    slot_reserved: bool


class CustomerBookingResponse(CustomerAppointmentDetails):
    id: UUID
    booking_id: UUID
    quote_id: UUID
    status: BookingStatus
    can_cancel: bool
    cancel_reason: str | None = None
    linked_job_id: UUID | None = None
    linked_job_status: str | None = None
    created_at: datetime
