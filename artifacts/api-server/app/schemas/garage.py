import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class GarageUpdate(BaseModel):
    name: Optional[str] = None
    owner: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    country: Optional[str] = None
    alternate_number: Optional[str] = None
    wheelers: Optional[List[str]] = None
    working_hours: Optional[Dict[str, Any]] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None

    @field_validator("name", "owner")
    @classmethod
    def not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("Field must not be empty")
        return v.strip() if v else v

    @field_validator("latitude")
    @classmethod
    def validate_lat(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and not (-90 <= float(v) <= 90):
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_lng(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and not (-180 <= float(v) <= 180):
            raise ValueError("Longitude must be between -180 and 180")
        return v


class GarageCreate(BaseModel):
    name: str
    owner: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    country: Optional[str] = None
    alternate_number: Optional[str] = None
    wheelers: Optional[List[str]] = None
    working_hours: Optional[Dict[str, Any]] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None


class GarageResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    owner: str
    operational_status: str = "ACTIVE"
    verification_status: str = "UNVERIFIED"
    version: int = Field(default=1, validation_alias="admin_version")
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    country: Optional[str] = None
    alternate_number: Optional[str] = None
    wheelers: Optional[List[str]] = None
    working_hours: Optional[Dict[str, Any]] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    # `logo_object_key` is persisted; `logo_url` is a short-lived signed read URL.
    logo_object_key: Optional[str] = None
    logo_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
