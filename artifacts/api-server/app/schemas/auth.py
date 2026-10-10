import re
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, StrictBool, field_validator, model_validator

from app.core.constants import DEFAULT_COUNTRY_CODE, VALID_COUNTRY_CODES
from app.models.user import AccountStatus, UserRole

_VALID_WHEELERS = {"2W", "3W", "4W", "6W"}

# Regex for a plain 10-digit mobile
_MOBILE_RE = re.compile(r"^\d{10}$")
# Regex for a valid email (rough check — Pydantic EmailStr handles the real one)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Regex for zipcode: digits only, 4–10 chars
_ZIPCODE_RE = re.compile(r"^\d{4,10}$")


def _validate_country_code(v: str) -> str:
    """Strip leading '+', check against the allowed list."""
    v = v.strip().lstrip("+")
    if v not in VALID_COUNTRY_CODES:
        raise ValueError(
            f"'{v}' is not a recognised country code. "
            "Use a valid E.164 numeric country code (e.g. '91' for India, '1' for USA)."
        )
    return v


def _validate_mobile_10(v: str) -> str:
    """Exactly 10 digits, no spaces."""
    v = v.strip()
    if not _MOBILE_RE.fullmatch(v):
        raise ValueError("Mobile number must be exactly 10 digits")
    return v


# ──────────────────────────────────────────────────────────
# Sign-up
# ──────────────────────────────────────────────────────────

class SignUpRequest(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def reject_role_assignment(cls, data):
        if isinstance(data, dict) and ("role" in data or "is_active" in data):
            raise ValueError("Account role and activation cannot be set during signup")
        return data

    first_name: str
    last_name: Optional[str] = None
    workshop_name: str
    email: EmailStr
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    country: Optional[str] = None
    # Country codes — validated against the allowed list; default is India "91"
    country_code: str = DEFAULT_COUNTRY_CODE
    mobile: str                              # exactly 10 digits
    country_code_2: Optional[str] = None    # for second phone
    mobile_2: Optional[str] = None          # exactly 10 digits
    wheelers: Optional[List[str]] = None
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

    @field_validator("zipcode")
    @classmethod
    def validate_zipcode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not _ZIPCODE_RE.fullmatch(v):
            raise ValueError("Zipcode must be 4–10 digits (numbers only)")
        return v

    @field_validator("wheelers")
    @classmethod
    def validate_wheelers(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        invalid = [w for w in v if w not in _VALID_WHEELERS]
        if invalid:
            raise ValueError(
                f"Invalid wheeler options: {invalid}. Must be one of {sorted(_VALID_WHEELERS)}"
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

    @model_validator(mode="after")
    def mobiles_must_differ(self) -> "SignUpRequest":
        if self.mobile_2 and self.mobile == self.mobile_2:
            raise ValueError(
                "Primary mobile and alternate mobile must be different numbers"
            )
        return self

    @property
    def full_mobile(self) -> str:
        """Combined number for MSG91: country_code + mobile (e.g. '919876543210')."""
        return f"{self.country_code}{self.mobile}"

    @property
    def full_mobile_2(self) -> Optional[str]:
        if self.mobile_2 and self.country_code_2:
            return f"{self.country_code_2}{self.mobile_2}"
        return None


# ──────────────────────────────────────────────────────────
# Sign-in  (10-digit mobile only)
# ──────────────────────────────────────────────────────────

class SignInRequest(BaseModel):
    """
    Sign in with a plain 10-digit mobile number.
    No country code required — resolved from the stored user record.
    """
    mobile: str

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("mobile is required")
        if not _MOBILE_RE.fullmatch(v):
            raise ValueError("mobile must be a 10-digit number")
        return v


# ──────────────────────────────────────────────────────────
# Send OTP  (just mobile — no country code)
# ──────────────────────────────────────────────────────────

class SendOTPRequest(BaseModel):
    """
    Request a fresh OTP. Supply the plain 10-digit mobile number only.
    The backend looks up the registered country code and builds the full
    number before calling MSG91.
    """
    mobile: str

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        return _validate_mobile_10(v)


# ──────────────────────────────────────────────────────────
# Verify OTP  (just mobile + otp — no country code)
# ──────────────────────────────────────────────────────────

class VerifyOTPRequest(BaseModel):
    """
    Verify an OTP. Supply the plain 10-digit mobile and the OTP code.
    Country code is resolved from the stored user record.
    """
    mobile: str
    otp: str

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


# ──────────────────────────────────────────────────────────
# Response schemas
# ──────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    id: uuid.UUID
    first_name: Optional[str]
    last_name: Optional[str]
    name: Optional[str]
    mobile: str
    country_code: str = DEFAULT_COUNTRY_CODE
    country_code_2: Optional[str] = None
    email: Optional[str]
    is_active: bool
    account_status: AccountStatus
    role: UserRole = UserRole.GARAGE_OWNER
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


class AccountDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: StrictBool

    @field_validator("confirm")
    @classmethod
    def require_confirmation(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Set confirm to true to mark your account deleted")
        return value
