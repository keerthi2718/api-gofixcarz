from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, BadRequestException, ConflictException, ForbiddenException, UnauthorizedException
from app.models.user import AccountStatus, User, UserRole
from app.models.admin_audit_log import AdminAuditLog
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
from app.utils.msg91 import submit_otp_sms
from app.services.sms_delivery_service import SMSDeliveryService


DELETED_ACCOUNT_ERROR_CODE = "ACCOUNT_DELETED"
DELETED_ACCOUNT_MESSAGE = "This account has been deleted. Please contact support for help."


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.garage_repo = GarageRepository(session)
        self.refresh_token_repo = RefreshTokenRepository(session)

    async def _submit_otp(self, mobile: str, otp: str) -> str | None:
        request_id = await submit_otp_sms(mobile, otp)
        if request_id:
            await SMSDeliveryService(self.session).register_submission(request_id)
        return request_id

    @staticmethod
    def _raise_deleted_account() -> None:
        raise AppException(
            DELETED_ACCOUNT_MESSAGE,
            status_code=410,
            error_code=DELETED_ACCOUNT_ERROR_CODE,
        )

    # ──────────────────────────────────────────────────────
    # Sign-up
    # ──────────────────────────────────────────────────────

    async def sign_up(self, data: SignUpRequest) -> dict:
        # Unique mobile check (plain 10-digit)
        existing = await self.user_repo.get_by_mobile_including_deleted(data.mobile)
        if existing:
            if existing.deleted_at is not None:
                self._raise_deleted_account()
            raise ConflictException("Mobile number already registered. Please sign in.")

        # Unique email check
        existing_email = await self.user_repo.get_by_email_including_deleted(str(data.email))
        if existing_email:
            if existing_email.deleted_at is not None:
                self._raise_deleted_account()
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
        request_id = await self._submit_otp(full_mobile, otp)
        if not request_id:
            raise AppException(
                "Account created, but the SMS provider could not accept the OTP request. "
                "Please sign in or resend the OTP later.",
                status_code=503,
            )

        return {
            "message": "Account created. OTP accepted by SMS provider; delivery pending.",
            "sms_request_id": request_id,
            "sms_delivery_status": "pending",
            "mobile": data.mobile,
            "country_code": data.country_code,
        }

    # ──────────────────────────────────────────────────────
    # Sign-in  (mobile only — no country code from client)
    # ──────────────────────────────────────────────────────

    async def sign_in(self, data: SignInRequest) -> dict:
        user = await self.user_repo.get_by_mobile_including_deleted(data.mobile)
        if user and user.deleted_at is not None:
            self._raise_deleted_account()
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
        request_id = await self._submit_otp(full_mobile, otp)
        if not request_id:
            raise AppException(
                "The SMS provider could not accept the OTP request. Please try again later.",
                status_code=503,
            )

        return {
            "message": "OTP accepted by SMS provider; delivery pending.",
            "sms_request_id": request_id,
            "sms_delivery_status": "pending",
            "mobile": user.mobile,
            "country_code": user.country_code,
        }

    # ──────────────────────────────────────────────────────
    # Send OTP  (just mobile — country code from user record)
    # ──────────────────────────────────────────────────────

    async def send_otp(self, data: SendOTPRequest) -> dict:
        user = await self.user_repo.get_by_mobile_including_deleted(data.mobile)
        if user and user.deleted_at is not None:
            self._raise_deleted_account()
        if not user:
            raise BadRequestException("Mobile number not registered.")
        if not user.is_active:
            raise UnauthorizedException("Account is inactive.")
        full_mobile = f"{user.country_code}{user.mobile}"
        otp = generate_otp()
        expires_at = get_otp_expiry()
        await self.user_repo.set_otp(user, otp, expires_at)
        request_id = await self._submit_otp(full_mobile, otp)
        if not request_id:
            raise AppException(
                "The SMS provider could not accept the OTP request. Please try again later.",
                status_code=503,
            )
        return {
            "message": "OTP accepted by SMS provider; delivery pending.",
            "sms_request_id": request_id,
            "sms_delivery_status": "pending",
            "mobile": user.mobile,
            "country_code": user.country_code,
        }

    # ──────────────────────────────────────────────────────
    # Verify OTP  (just mobile + otp — country code from user record)
    # ──────────────────────────────────────────────────────

    async def verify_otp(self, data: VerifyOTPRequest) -> TokenResponse:
        user = await self.user_repo.get_by_mobile_including_deleted(data.mobile)
        if user and user.deleted_at is not None:
            self._raise_deleted_account()
        if not user:
            raise BadRequestException("Mobile number not registered.")
        if not user.is_active:
            raise UnauthorizedException("Account is inactive.")
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

        access_token = create_access_token(subject=str(user.id), role=user.role)
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
        access_token = create_access_token(subject=str(user.id), role=user.role)

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

    async def delete_account(self, user_id: uuid.UUID) -> dict:
        """Owner-requested archival, never a cascading physical deletion."""
        user = (await self.session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )).scalar_one_or_none()
        if not user or not user.is_active or user.deleted_at is not None:
            raise UnauthorizedException("Account not found or inactive.")
        if user.role != UserRole.GARAGE_OWNER.value:
            raise ForbiddenException("Only garage owners can delete their account here.")
        now = datetime.now(timezone.utc)
        user.is_active = False
        user.deleted_at = now
        user.updated_at = now
        user.otp = None
        user.otp_expires_at = None
        await self.refresh_token_repo.revoke_all_for_user(user.id)
        self.session.add(AdminAuditLog(
            actor_id=user.id, action="users.account_deleted", resource_id=user.id,
            details={"account_status": AccountStatus.DELETED.value, "data_retained": True},
        ))
        await self.session.flush()
        return {
            "account_id": str(user.id),
            "account_status": AccountStatus.DELETED.value,
            "is_active": False,
            "deleted_at": now.isoformat(),
            "sessions_revoked": True,
            "data_retained": True,
        }
