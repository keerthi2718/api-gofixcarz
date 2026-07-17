import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from app.schemas.customer import CustomerResponse


class VehicleCreate(BaseModel):
    customer_id: uuid.UUID
    make: str
    model: str
    year: Optional[int] = None
    registration_plate: str
    vin: Optional[str] = None
    colour: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("make", "model", "registration_plate")
    @classmethod
    def not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Field must not be empty")
        return v

    @field_validator("year")
    @classmethod
    def validate_year(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1886 <= v <= 2100):
            raise ValueError("Year must be between 1886 and 2100")
        return v


class VehicleUpdate(BaseModel):
    customer_id: Optional[uuid.UUID] = None
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    registration_plate: Optional[str] = None
    vin: Optional[str] = None
    colour: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("year")
    @classmethod
    def validate_year(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and not (1886 <= v <= 2100):
            raise ValueError("Year must be between 1886 and 2100")
        return v


class VehicleResponse(BaseModel):
    id: uuid.UUID
    garage_id: uuid.UUID
    customer_id: uuid.UUID
    make: str
    model: str
    year: Optional[int] = None
    registration_plate: str
    vin: Optional[str] = None
    colour: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VehicleDetailResponse(VehicleResponse):
    """Vehicle with nested customer info."""
    customer: Optional[CustomerResponse] = None

    model_config = {"from_attributes": True}
