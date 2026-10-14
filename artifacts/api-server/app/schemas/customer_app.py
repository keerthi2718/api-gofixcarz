"""First-phase customer contracts; reject server-owned and unknown fields."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MobileInput(StrictInput):
    channel: Literal["mobile"]
    # This phase uses the existing Indian MSG91 sender/template.
    identifier: str = Field(pattern=r"^\+91[6-9][0-9]{9}$")


class RegisterRequest(MobileInput):
    name: str = Field(min_length=1, max_length=255)
    terms_version: str = Field(min_length=1, max_length=50)
    terms_accepted: Literal[True]


class LoginOTPRequest(MobileInput):
    purpose: Literal["LOGIN"]


class ChallengeRequest(StrictInput):
    challenge_id: UUID


class VerifyRequest(ChallengeRequest):
    otp: str = Field(pattern=r"^[0-9]{6}$", strict=True)


class LoginVerifyRequest(VerifyRequest):
    device_name: str | None = Field(default=None, max_length=100)


class RefreshRequest(StrictInput):
    refresh_token: str = Field(min_length=32, max_length=256)


class Address(StrictInput):
    line1: str = Field(min_length=1, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    postal_code: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9 -]{1,11}$")
    country: str = Field(pattern=r"^[A-Z]{2}$")


class ProfilePatch(StrictInput):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: Address | None = None

    @model_validator(mode="after")
    def supported_fields(self):
        if not self.model_fields_set:
            raise ValueError("At least one supported field is required")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Name cannot be null")
        return self


class ContactChangeRequest(StrictInput):
    channel: Literal["mobile"]
    new_identifier: str = Field(pattern=r"^\+91[6-9][0-9]{9}$")


class ChallengeResponse(BaseModel):
    challenge_id: UUID
    purpose: str
    expires_in_seconds: int = 300
    resend_after_seconds: int = 30


class ProfileResponse(BaseModel):
    id: UUID
    name: str
    mobile: str
    email: str | None = None
    mobile_verified: bool = True
    email_verified: bool = False
    photo: None = None
    address: Address | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in_seconds: int = 900
    session_id: UUID
    customer: ProfileResponse


class SessionResponse(BaseModel):
    session_id: UUID
    customer_id: UUID
    authenticated: bool = True
    expires_at: datetime


class LogoutResponse(BaseModel):
    logged_out: bool = True


class ContactResponse(BaseModel):
    mobile: str
    mobile_verified: bool = True
