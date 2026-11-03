import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from app.models.booking import BookingStatus
from app.schemas.customer import CustomerResponse
from app.schemas.vehicle import VehicleResponse


class BookingResponse(BaseModel):
    id: uuid.UUID
    garage_id: uuid.UUID
    customer_id: Optional[uuid.UUID] = None
    vehicle_id: Optional[uuid.UUID] = None
    status: BookingStatus
    booking_date: Optional[date] = None
    owner_accepted_at: Optional[datetime] = None
    scheduled_date: Optional[date] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    notes: Optional[str] = None
    customer_name: Optional[str] = None
    customer_mobile: Optional[str] = None
    service_requested: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BookingDetailResponse(BookingResponse):
    customer: Optional[CustomerResponse] = None
    vehicle: Optional[VehicleResponse] = None

    model_config = {"from_attributes": True}
