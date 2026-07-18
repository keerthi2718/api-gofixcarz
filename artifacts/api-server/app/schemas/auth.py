import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, field_validator, model_validator
import re

_VALID_WEEKS = {"2W", "3W", "4W", "6W"}


def _validate_country_code(v: str) -> str:
    """Accept formats like '91', '+91', '1', '+1' — strip leading '+' and whitespace."""
    v = v.strip().lstrip("+")
    if not re.fullmatch(r"\d{1,4}", v):
        raise ValueError("Country code must be 1–4 digits (e.g. '91' or '+91')")
    return v


def _validate_mobile_10(v: str) -> str:
    """Exactly 10 digits, no spaces."""
    v = v.strip()
    if not re.fullmatch(r"\d{10}", v):
        raise ValueError("Mobile number must be exactly 10 digits")
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
    country_code: str                       # e.g. "91" or "+91"
    mobile: str                             # exactly 10 digits
    country_code_2: Optional[str] = None   # for second phone
    mobile_2: Optional[str] = None         # exactly 10 digits
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

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, v: str) -> str:
        return _validate_country_code(v)

    @field_validator("country_code_2")
    @classmethod
    def validate_country_code_2(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_country_code(v)

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        return _validate_mobile_10(v)

    @field_validator("mobile_2")
    @classmethod
    def validate_mobile_2(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_mobile_10(v)

    @field_validator("weeks")
    @classmethod
    def validate_weeks(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        invalid = [w for w in v if w not in _VALID_WEEKS]
        if invalid:
            raise ValueError(
                f"Invalid week options: {invalid}. Must be one of {sorted(_VALID_WEEKS)}"
            )
        return v

    @model_validator(mode="after")
    def terms_must_be_accepted(self) -> "SignUpRequest":
        if not self.terms_accepted:
            raise ValueError("You must accept the terms and conditions to sign up")
        return self

    @model_validator(mode="after")
    def mobile_2_requires_country_code(self) -> "SignUpRequest":
        if self.mobile_2 and not self.country_code_2:
            raise ValueError("country_code_2 is required when mobile_2 is provided")
        return self

    @property
    def full_mobile(self) -> str:
        """Combined number stored in DB and used for SMS: e.g. '919876543210'."""
        return f"{self.country_code}{self.mobile}"

    @property
    def full_mobile_2(self) -> Optional[str]:
        if self.mobile_2 and self.country_code_2:
            return f"{self.country_code_2}{self.mobile_2}"
        return None


class SignInRequest(BaseModel):
    country_code: str   # e.g. "91"
    mobile: str         # exactly 10 digits

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, v: str) -> str:
        return _validate_country_code(v)

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        return _validate_mobile_10(v)

    @property
    def full_mobile(self) -> str:
        return f"{self.country_code}{self.mobile}"


class SendOTPRequest(BaseModel):
    country_code: str
    mobile: str

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, v: str) -> str:
        return _validate_country_code(v)

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        return _validate_mobile_10(v)

    @property
    def full_mobile(self) -> str:
        return f"{self.country_code}{self.mobile}"


class VerifyOTPRequest(BaseModel):
    country_code: str
    mobile: str
    otp: str

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, v: str) -> str:
        return _validate_country_code(v)

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        return _validate_mobile_10(v)

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or not (4 <= len(v) <= 8):
            raise ValueError("OTP must be 4–8 digits")
        return v

    @property
    def full_mobile(self) -> str:
        return f"{self.country_code}{self.mobile}"


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
