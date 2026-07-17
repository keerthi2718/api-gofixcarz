from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, UnauthorizedException
from app.core.security import create_access_token, generate_otp, get_otp_expiry
from app.repositories.user_repository import UserRepository
from app.schemas.auth import SignUpRequest, SignInRequest, SendOTPRequest, VerifyOTPRequest, TokenResponse, UserResponse
from app.utils.msg91 import send_otp_sms


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def sign_up(self, data: SignUpRequest) -> dict:
        existing = await self.user_repo.get_by_mobile(data.mobile)
        if existing:
            raise BadRequestException("Mobile number already registered. Please sign in.")
        user = await self.user_repo.create(
            mobile=data.mobile, name=data.name, email=str(data.email) if data.email else None
        )
        # Auto-send OTP after sign-up
        otp = generate_otp()
        expires_at = get_otp_expiry()
        await self.user_repo.set_otp(user, otp, expires_at)
        await send_otp_sms(data.mobile, otp)
        return {
            "message": "Account created. OTP sent to your mobile number.",
            "mobile": data.mobile,
        }

    async def sign_in(self, data: SignInRequest) -> dict:
        user = await self.user_repo.get_by_mobile(data.mobile)
        if not user:
            raise BadRequestException("Mobile number not registered. Please sign up first.")
        if not user.is_active:
            raise UnauthorizedException("Account is inactive.")
        # Send OTP for sign-in
        otp = generate_otp()
        expires_at = get_otp_expiry()
        await self.user_repo.set_otp(user, otp, expires_at)
        await send_otp_sms(data.mobile, otp)
        return {
            "message": "OTP sent to your mobile number.",
            "mobile": data.mobile,
        }

    async def send_otp(self, data: SendOTPRequest) -> dict:
        user = await self.user_repo.get_by_mobile(data.mobile)
        if not user:
            raise BadRequestException("Mobile number not registered.")
        otp = generate_otp()
        expires_at = get_otp_expiry()
        await self.user_repo.set_otp(user, otp, expires_at)
        await send_otp_sms(data.mobile, otp)
        return {"message": "OTP sent successfully.", "mobile": data.mobile}

    async def verify_otp(self, data: VerifyOTPRequest) -> TokenResponse:
        user = await self.user_repo.get_by_mobile(data.mobile)
        if not user:
            raise BadRequestException("Mobile number not registered.")
        if not user.otp or not user.otp_expires_at:
            raise BadRequestException("No OTP found. Please request a new OTP.")
        now = datetime.now(timezone.utc)
        otp_expires = user.otp_expires_at
        if otp_expires.tzinfo is None:
            from datetime import timezone as tz
            otp_expires = otp_expires.replace(tzinfo=tz.utc)
        if now > otp_expires:
            raise BadRequestException("OTP has expired. Please request a new OTP.")
        if user.otp != data.otp:
            raise UnauthorizedException("Invalid OTP.")
        await self.user_repo.clear_otp(user)
        token = create_access_token(subject=str(user.id))
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )

    async def logout(self, user_id: str) -> dict:
        # JWT is stateless; client discards the token
        return {"message": "Logged out successfully."}
