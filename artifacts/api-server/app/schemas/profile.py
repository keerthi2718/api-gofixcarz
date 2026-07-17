import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class ProfileResponse(BaseModel):
    id: uuid.UUID
    name: Optional[str]
    mobile: str
    email: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    mobile: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Name must not be empty")
        return v

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        digits = v.strip().replace(" ", "").replace("-", "")
        if not digits.isdigit() or not (10 <= len(digits) <= 15):
            raise ValueError("Mobile must be 10–15 digits")
        return digits
