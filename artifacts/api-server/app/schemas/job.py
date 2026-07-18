import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, field_validator, model_validator

from app.models.job import JobStatus
from app.schemas.customer import CustomerResponse
from app.schemas.vehicle import VehicleResponse


# ── Sub-schemas for JSONB data blobs ─────────────────────────────────────────

class ServiceItem(BaseModel):
    """One line-item in the services list."""
    name: str
    price: Decimal
    qty: int = 1

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Service price must be non-negative")
        return v

    @field_validator("qty")
    @classmethod
    def validate_qty(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Quantity must be at least 1")
        return v


class InspectionData(BaseModel):
    """Inspection findings recorded during the job."""
    findings: Optional[str] = None
    parts_needed: Optional[List[str]] = None


class LabourData(BaseModel):
    """Labour work details and charge."""
    description: Optional[str] = None
    charge: Decimal = Decimal("0.00")

    @field_validator("charge")
    @classmethod
    def validate_charge(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Labour charge must be non-negative")
        return v


class BillingData(BaseModel):
    """Calculated billing breakdown (populated by /complete)."""
    services_total: Decimal
    labour_total: Decimal
    subtotal: Decimal
    gst_amount: Decimal   # 18% of subtotal
    grand_total: Decimal


# ── Timeline ─────────────────────────────────────────────────────────────────

class JobTimelineResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    status: str
    notes: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Job Create ────────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    """Create a job.

    Two creation paths:
    - Direct: customer_name, customer_mobile, registration_number, brand,
              vehicle_model, fuel_type, odometer_km are required.
    - Booking: customer_id + vehicle_id supplied (existing FK records used).
    """
    # ── Direct creation fields ──────────────────────────────────────────────
    customer_name: Optional[str] = None
    customer_mobile: Optional[str] = None
    registration_number: Optional[str] = None
    brand: Optional[str] = None
    vehicle_model: Optional[str] = None
    fuel_type: Optional[str] = None
    odometer_km: Optional[int] = None
    photos: Optional[List[str]] = None

    # ── Booking / legacy FK fields ──────────────────────────────────────────
    customer_id: Optional[uuid.UUID] = None
    vehicle_id: Optional[uuid.UUID] = None
    booking_id: Optional[uuid.UUID] = None

    # ── Shared optional fields ──────────────────────────────────────────────
    description: Optional[str] = None
    estimated_amount: Optional[Decimal] = None

    @field_validator("estimated_amount")
    @classmethod
    def validate_amount(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < 0:
            raise ValueError("Amount must be non-negative")
        return v

    @field_validator("customer_mobile")
    @classmethod
    def validate_mobile(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.isdigit():
            raise ValueError("Customer mobile must contain digits only")
        return v

    @field_validator("odometer_km")
    @classmethod
    def validate_odometer(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("Odometer reading must be non-negative")
        return v

    @model_validator(mode="after")
    def check_creation_path(self) -> "JobCreate":
        has_fk = self.customer_id is not None and self.vehicle_id is not None
        has_direct = all(
            f is not None
            for f in (
                self.customer_name,
                self.customer_mobile,
                self.registration_number,
                self.brand,
                self.vehicle_model,
                self.fuel_type,
                self.odometer_km,
            )
        )
        if not has_fk and not has_direct:
            raise ValueError(
                "Either provide customer_id + vehicle_id (booking path) or "
                "all of: customer_name, customer_mobile, registration_number, "
                "brand, vehicle_model, fuel_type, odometer_km (direct path)."
            )
        return self


# ── Job Update ────────────────────────────────────────────────────────────────

class JobUpdate(BaseModel):
    """Partial update for inspection, services, labour, photos, or description.

    Only supplied fields are written; unset fields are left untouched.
    JSONB fields are fully replaced (not merged) when provided.
    """
    description: Optional[str] = None
    estimated_amount: Optional[Decimal] = None
    photos: Optional[List[str]] = None
    inspection: Optional[InspectionData] = None
    services: Optional[List[ServiceItem]] = None
    labour: Optional[LabourData] = None

    @field_validator("estimated_amount")
    @classmethod
    def validate_amount(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < 0:
            raise ValueError("Amount must be non-negative")
        return v


# ── Status Update ─────────────────────────────────────────────────────────────

class JobStatusUpdate(BaseModel):
    status: JobStatus
    notes: Optional[str] = None


# ── Complete ──────────────────────────────────────────────────────────────────

class JobCompleteUpdate(BaseModel):
    """Trigger billing calculation and mark job as COMPLETED.

    Billing is derived from the job's services + labour JSONB.
    An optional notes field is added to the timeline entry.
    """
    notes: Optional[str] = None


# ── Responses ─────────────────────────────────────────────────────────────────

class JobResponse(BaseModel):
    id: uuid.UUID
    job_number: str
    garage_id: uuid.UUID

    # FK refs (nullable)
    customer_id: Optional[uuid.UUID] = None
    vehicle_id: Optional[uuid.UUID] = None
    booking_id: Optional[uuid.UUID] = None

    # Inline details
    customer_name: Optional[str] = None
    customer_mobile: Optional[str] = None
    registration_number: Optional[str] = None
    brand: Optional[str] = None
    vehicle_model: Optional[str] = None
    fuel_type: Optional[str] = None
    odometer_km: Optional[int] = None

    # JSONB blobs
    photos: Optional[List[Any]] = None
    inspection: Optional[Any] = None
    services: Optional[List[Any]] = None
    labour: Optional[Any] = None
    billing: Optional[Any] = None

    # Core fields
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
