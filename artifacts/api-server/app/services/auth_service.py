from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, UnauthorizedException
from app.core.security import (
    create_access_token,
    generate_otp,
    generate_refresh_token,
    get_otp_expiry,
    get_refresh_token_expiry,
    hash_refresh_token,
)
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import SignUpRequest, SignInRequest, SendOTPRequest, VerifyOTPRequest, TokenResponse, UserResponse
from app.utils.msg91 import send_otp_sms


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.refresh_token_repo = RefreshTokenRepository(session)

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

        # Issue access token + refresh token
        access_token = create_access_token(subject=str(user.id))
        raw_refresh = generate_refresh_token()
        refresh_hash = hash_refresh_token(raw_refresh)
        refresh_expires = get_refresh_token_expiry()
        await self.refresh_token_repo.create(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=refresh_expires,
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )

    async def refresh(self, raw_refresh_token: str) -> TokenResponse:
        """Exchange a valid refresh token for a new access token (+ rotated refresh token)."""
        token_hash = hash_refresh_token(raw_refresh_token)
        stored = await self.refresh_token_repo.get_by_hash(token_hash)

        if not stored:
            raise UnauthorizedException("Invalid refresh token.")
        if stored.revoked_at is not None:
            raise UnauthorizedException("Refresh token has been revoked.")
        now = datetime.now(timezone.utc)
        expires = stored.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if now > expires:
            raise UnauthorizedException("Refresh token has expired. Please sign in again.")

        user = await self.user_repo.get_by_id(stored.user_id)
        if not user or not user.is_active:
            raise UnauthorizedException("Account not found or inactive.")

        # Revoke the used token (rotation — one-time use)
        await self.refresh_token_repo.revoke(stored)

        # Issue a new pair
        access_token = create_access_token(subject=str(user.id))
        raw_new_refresh = generate_refresh_token()
        new_hash = hash_refresh_token(raw_new_refresh)
        new_expires = get_refresh_token_expiry()
        await self.refresh_token_repo.create(
            user_id=user.id,
            token_hash=new_hash,
            expires_at=new_expires,
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_new_refresh,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )

    async def logout(self, user_id: str, raw_refresh_token: Optional[str] = None) -> dict:
        """Revoke the supplied refresh token (or all tokens if none provided)."""
        if raw_refresh_token:
            token_hash = hash_refresh_token(raw_refresh_token)
            stored = await self.refresh_token_repo.get_by_hash(token_hash)
            if stored and stored.revoked_at is None:
                await self.refresh_token_repo.revoke(stored)
        else:
            # Revoke all sessions for the user
            import uuid as _uuid
            await self.refresh_token_repo.revoke_all_for_user(_uuid.UUID(user_id))
        return {"message": "Logged out successfully."}
