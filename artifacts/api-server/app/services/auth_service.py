from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, ConflictException, UnauthorizedException
from app.core.security import (
    create_access_token,
    generate_otp,
    generate_refresh_token,
    get_otp_expiry,
    get_refresh_token_expiry,
    hash_refresh_token,
)
from app.repositories.garage_repository import GarageRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    SendOTPRequest,
    SignInRequest,
    SignUpRequest,
    TokenResponse,
    UserResponse,
    VerifyOTPRequest,
)
from app.schemas.garage import GarageCreate
from app.utils.msg91 import send_otp_sms


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.garage_repo = GarageRepository(session)
        self.refresh_token_repo = RefreshTokenRepository(session)

    # ──────────────────────────────────────────────────────
    # Sign-up
    # ──────────────────────────────────────────────────────

    async def sign_up(self, data: SignUpRequest) -> dict:
        # Unique mobile check (plain 10-digit)
        existing = await self.user_repo.get_by_mobile(data.mobile)
        if existing:
            raise ConflictException("Mobile number already registered. Please sign in.")

        # Unique email check
        existing_email = await self.user_repo.get_by_email(str(data.email))
        if existing_email:
            raise ConflictException("Email address already registered.")

        # Build full name
        full_name = data.first_name.strip()
        if data.last_name and data.last_name.strip():
            full_name = f"{full_name} {data.last_name.strip()}"

        # Create user — mobile stored as plain 10 digits; country code separate
        try:
            user = await self.user_repo.create(
                mobile=data.mobile,
                country_code=data.country_code,
                country_code_2=data.country_code_2 if data.mobile_2 else None,
                first_name=data.first_name,
                last_name=data.last_name,
                name=full_name,
                email=str(data.email),
                terms_accepted=data.terms_accepted,
            )
        except IntegrityError:
            # Race condition: another request inserted the same mobile/email
            # between our read-check and this write — treat as conflict.
            raise ConflictException("Mobile number or email already registered.")

        # Create garage/workshop
        garage_data = GarageCreate(
            name=data.workshop_name,
            owner=full_name,
            address=data.address,
            city=data.city,
            state=data.state,
            zipcode=data.zipcode,
            country=data.country,
            # alternate_number stored as full international number for the garage
            alternate_number=data.full_mobile_2,
            wheelers=data.wheelers,
        )
        await self.garage_repo.create(user_id=user.id, data=garage_data)

        # Auto-send OTP — combine country_code + mobile for MSG91
        otp = generate_otp()
        expires_at = get_otp_expiry()
        await self.user_repo.set_otp(user, otp, expires_at)
        full_mobile = f"{data.country_code}{data.mobile}"
        await send_otp_sms(full_mobile, otp)

        return {
            "message": "Account created. OTP sent to your mobile number.",
            "mobile": data.mobile,
            "country_code": data.country_code,
        }

    # ──────────────────────────────────────────────────────
    # Sign-in  (mobile only — no country code from client)
    # ──────────────────────────────────────────────────────

    async def sign_in(self, data: SignInRequest) -> dict:
        user = await self.user_repo.get_by_mobile(data.mobile)
        if not user:
            raise BadRequestException(
                "Mobile number not registered. Please sign up first."
            )

        if not user.is_active:
            raise UnauthorizedException("Account is inactive.")

        # Build full international number from stored country_code
        full_mobile = f"{user.country_code}{user.mobile}"
        otp = generate_otp()
        expires_at = get_otp_expiry()
        await self.user_repo.set_otp(user, otp, expires_at)
        await send_otp_sms(full_mobile, otp)

        return {
            "message": "OTP sent to your registered mobile number.",
            "mobile": user.mobile,
            "country_code": user.country_code,
        }

    # ──────────────────────────────────────────────────────
    # Send OTP  (just mobile — country code from user record)
    # ──────────────────────────────────────────────────────

    async def send_otp(self, data: SendOTPRequest) -> dict:
        user = await self.user_repo.get_by_mobile(data.mobile)
        if not user:
            raise BadRequestException("Mobile number not registered.")
        full_mobile = f"{user.country_code}{user.mobile}"
        otp = generate_otp()
        expires_at = get_otp_expiry()
        await self.user_repo.set_otp(user, otp, expires_at)
        await send_otp_sms(full_mobile, otp)
        return {
            "message": "OTP sent successfully.",
            "mobile": user.mobile,
            "country_code": user.country_code,
        }

    # ──────────────────────────────────────────────────────
    # Verify OTP  (just mobile + otp — country code from user record)
    # ──────────────────────────────────────────────────────

    async def verify_otp(self, data: VerifyOTPRequest) -> TokenResponse:
        user = await self.user_repo.get_by_mobile(data.mobile)
        if not user:
            raise BadRequestException("Mobile number not registered.")
        if not user.otp or not user.otp_expires_at:
            raise BadRequestException("No OTP found. Please request a new OTP.")
        now = datetime.now(timezone.utc)
        otp_expires = user.otp_expires_at
        if otp_expires.tzinfo is None:
            otp_expires = otp_expires.replace(tzinfo=timezone.utc)
        if now > otp_expires:
            raise BadRequestException("OTP has expired. Please request a new OTP.")
        if user.otp != data.otp:
            raise UnauthorizedException("Invalid OTP.")
        await self.user_repo.clear_otp(user)

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

    # ──────────────────────────────────────────────────────
    # Refresh token
    # ──────────────────────────────────────────────────────

    async def refresh(self, raw_refresh_token: str) -> TokenResponse:
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

        # No rotation: the refresh token stays valid until it expires naturally.
        # Rotating on every use causes "revoked" errors on mobile when a network
        # hiccup or app backgrounding prevents the new token from being saved.
        access_token = create_access_token(subject=str(user.id))

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )

    # ──────────────────────────────────────────────────────
    # Logout
    # ──────────────────────────────────────────────────────

    async def logout(self, user_id: str, raw_refresh_token: Optional[str] = None) -> dict:
        if raw_refresh_token:
            token_hash = hash_refresh_token(raw_refresh_token)
            stored = await self.refresh_token_repo.get_by_hash(token_hash)
            if stored and stored.revoked_at is None:
                await self.refresh_token_repo.revoke(stored)
        else:
            import uuid as _uuid
            await self.refresh_token_repo.revoke_all_for_user(_uuid.UUID(user_id))
        return {"message": "Logged out successfully."}
