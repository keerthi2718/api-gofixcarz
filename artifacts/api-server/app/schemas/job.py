import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, field_validator

from app.models.job import JobStatus
from app.schemas.customer import CustomerResponse
from app.schemas.vehicle import VehicleResponse


class JobTimelineResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    status: str
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class JobCreate(BaseModel):
    customer_id: uuid.UUID
    vehicle_id: uuid.UUID
    booking_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    estimated_amount: Optional[Decimal] = None

    @field_validator("estimated_amount")
    @classmethod
    def validate_amount(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < 0:
            raise ValueError("Amount must be non-negative")
        return v


class JobUpdate(BaseModel):
    customer_id: Optional[uuid.UUID] = None
    vehicle_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    estimated_amount: Optional[Decimal] = None
    final_amount: Optional[Decimal] = None

    @field_validator("estimated_amount", "final_amount")
    @classmethod
    def validate_amount(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < 0:
            raise ValueError("Amount must be non-negative")
        return v


class JobStatusUpdate(BaseModel):
    status: JobStatus
    notes: Optional[str] = None


class JobCompleteUpdate(BaseModel):
    final_amount: Optional[Decimal] = None
    notes: Optional[str] = None

    @field_validator("final_amount")
    @classmethod
    def validate_amount(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < 0:
            raise ValueError("Amount must be non-negative")
        return v


class JobResponse(BaseModel):
    id: uuid.UUID
    job_number: str
    garage_id: uuid.UUID
    customer_id: uuid.UUID
    vehicle_id: uuid.UUID
    booking_id: Optional[uuid.UUID] = None
    status: JobStatus
    description: Optional[str] = None
    estimated_amount: Optional[Decimal] = None
    final_amount: Optional[Decimal] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobDetailResponse(JobResponse):
    """Job with nested customer, vehicle, and timeline."""
    customer: Optional[CustomerResponse] = None
    vehicle: Optional[VehicleResponse] = None
    timelines: list[JobTimelineResponse] = []

    model_config = {"from_attributes": True}
