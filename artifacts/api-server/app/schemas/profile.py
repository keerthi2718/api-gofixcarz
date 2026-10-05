import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator
from app.models.user import UserRole


class ProfileResponse(BaseModel):
    id: uuid.UUID
    name: Optional[str]
    mobile: str
    email: Optional[str]
    is_active: bool
    role: UserRole = UserRole.GARAGE_OWNER
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def reject_role_assignment(cls, data):
        if isinstance(data, dict) and ("role" in data or "is_active" in data):
            raise ValueError("Account role and activation cannot be changed through profile")
        return data

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
