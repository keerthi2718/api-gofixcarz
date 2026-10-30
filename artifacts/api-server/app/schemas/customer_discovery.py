"""Customer-safe discovery contracts. Locations travel in bodies, not URLs."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.customer_app import StrictInput
from app.schemas.response import PaginatedData


class LocationInput(StrictInput):
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    accuracy_meters: float | None = Field(default=None, ge=0, le=100000, allow_inf_nan=False)
    captured_at: datetime | None = None

    @model_validator(mode="after")
    def complete_location(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Supply both latitude and longitude")
        if self.latitude is None and (self.accuracy_meters is not None or self.captured_at is not None):
            raise ValueError("Location metadata requires coordinates")
        return self


class GarageSearch(LocationInput):
    q: str = Field(default="", max_length=100)
    search_by: Literal["all", "service", "garage"] = "all"
    radius_km: float | None = Field(default=None, gt=0, le=200, allow_inf_nan=False)
    page: int = Field(default=1, ge=1, le=100000)
    page_size: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_search(self):
        if self.radius_km is not None and self.latitude is None:
            raise ValueError("Radius requires coordinates")
        if not self.q and self.latitude is None:
            raise ValueError("Supply search text or a location")
        return self


class DiscoveryService(BaseModel):
    id: UUID
    name: str
    description: str | None
    price_inr: Decimal
    amount: int = Field(description="INR minor units (paise), matching quote service amounts")
    currency: Literal["INR"] = "INR"
    duration_minutes: int | None
    booking_eligible: bool
    unavailable_reason: str | None


class DiscoveryGarage(BaseModel):
    id: UUID
    name: str
    address: str | None
    city: str | None
    state: str | None
    zipcode: str | None
    country: str | None
    distance_km: float | None
    distance_type: Literal["STRAIGHT_LINE"] = "STRAIGHT_LINE"
    matched_by: list[Literal["garage", "service"]]
    active_service_count: int
    matching_service_count: int
    services: list[DiscoveryService]
    services_has_more: bool
    services_path: str
    booking_eligible: bool
    booking_prerequisites: list[str]


class GarageSearchResults(PaginatedData[DiscoveryGarage]):
    radius_km: float | None
    distance_type: Literal["STRAIGHT_LINE"] = "STRAIGHT_LINE"
