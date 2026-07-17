import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator
import re


class SignUpRequest(BaseModel):
    mobile: str
    name: Optional[str] = None
    email: Optional[EmailStr] = None

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"\d{10,15}", v):
            raise ValueError("Mobile number must be 10–15 digits")
        return v


class SignInRequest(BaseModel):
    mobile: str

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"\d{10,15}", v):
            raise ValueError("Mobile number must be 10–15 digits")
        return v


class SendOTPRequest(BaseModel):
    mobile: str

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"\d{10,15}", v):
            raise ValueError("Mobile number must be 10–15 digits")
        return v


class VerifyOTPRequest(BaseModel):
    mobile: str
    otp: str

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(r"\d{10,15}", v):
            raise ValueError("Mobile number must be 10–15 digits")
        return v

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or not (4 <= len(v) <= 8):
            raise ValueError("OTP must be 4–8 digits")
        return v


class UserResponse(BaseModel):
    id: uuid.UUID
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
