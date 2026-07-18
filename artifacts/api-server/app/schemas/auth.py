import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, field_validator, model_validator
import re

_VALID_WEEKS = {"2W", "3W", "4W", "6W"}


def _validate_mobile(v: str) -> str:
    v = v.strip()
    if not re.fullmatch(r"\d{10,15}", v):
        raise ValueError("Mobile number must be 10–15 digits")
    return v


class SignUpRequest(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    workshop_name: str
    email: EmailStr
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    country: Optional[str] = None
    mobile: str
    mobile_2: Optional[str] = None
    weeks: Optional[List[str]] = None
    terms_accepted: bool

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("First name is required")
        return v

    @field_validator("workshop_name")
    @classmethod
    def validate_workshop_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Workshop name is required")
        return v

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        return _validate_mobile(v)

    @field_validator("mobile_2")
    @classmethod
    def validate_mobile_2(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_mobile(v)

    @field_validator("weeks")
    @classmethod
    def validate_weeks(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        invalid = [w for w in v if w not in _VALID_WEEKS]
        if invalid:
            raise ValueError(f"Invalid week options: {invalid}. Must be one of {sorted(_VALID_WEEKS)}")
        return v

    @model_validator(mode="after")
    def terms_must_be_accepted(self) -> "SignUpRequest":
        if not self.terms_accepted:
            raise ValueError("You must accept the terms and conditions to sign up")
        return self


class SignInRequest(BaseModel):
    mobile: str

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        return _validate_mobile(v)


class SendOTPRequest(BaseModel):
    mobile: str

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        return _validate_mobile(v)


class VerifyOTPRequest(BaseModel):
    mobile: str
    otp: str

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        return _validate_mobile(v)

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or not (4 <= len(v) <= 8):
            raise ValueError("OTP must be 4–8 digits")
        return v


class UserResponse(BaseModel):
    id: uuid.UUID
    first_name: Optional[str]
    last_name: Optional[str]
    name: Optional[str]
    mobile: str
    email: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None
    user: UserResponse


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None
