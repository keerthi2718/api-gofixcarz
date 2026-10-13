"""Opt-in, operator-authorized creation of the first dedicated administrator."""
import hashlib
import hmac
import uuid

from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.admin_security import hash_admin_password
from app.core.config import settings
from app.core.exceptions import (
    AppException, ConflictException, ForbiddenException, NotFoundException,
)
from app.models.admin_account import AdminAccount
from app.models.admin_audit_log import AdminAuditLog
from app.schemas.admin_auth import AdminIdentity, AdminSignupRequest


def authorize_admin_setup(key: SecretStr | None) -> None:
    expected = settings.ADMIN_SETUP_KEY.get_secret_value()
    if not settings.ADMIN_SIGNUP_ENABLED or not 32 <= len(expected) <= 256:
        raise NotFoundException("Admin signup is not enabled.")
    supplied = key.get_secret_value() if key else ""
    if not 32 <= len(supplied) <= 256 or not hmac.compare_digest(
        hashlib.sha256(supplied.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    ):
        raise ForbiddenException("Invalid admin setup authorization.")


class AdminSignupService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def signup(self, data: AdminSignupRequest, key: SecretStr | None) -> dict:
        # Check authorization before hashing or touching the database.
        authorize_admin_setup(key)
        password_hash = await run_in_threadpool(
            hash_admin_password, data.password.get_secret_value(),
        )
        # A transaction-scoped TABLE lock also coordinates with trusted CLI and
        # staff creation paths, not only other instances of this endpoint.
        try:
            await self.session.execute(text("SET LOCAL lock_timeout = '5s'"))
            await self.session.execute(text(
                "LOCK TABLE admin_accounts IN SHARE ROW EXCLUSIVE MODE",
            ))
        except DBAPIError:
            # Avoid driver output/connection details in responses and logs.
            await self.session.rollback()
            raise AppException("Admin setup is busy. Try again later.", status_code=503) from None
        existing = (await self.session.execute(
            select(AdminAccount.id).limit(1),
        )).scalar_one_or_none()
        # Inactive accounts also close first-admin registration.
        if existing is not None:
            raise ConflictException("An admin account already exists. First-admin signup is closed.")
        account = AdminAccount(
            id=uuid.uuid4(), email=str(data.email).lower(), name=data.name,
            password_hash=password_hash, is_active=True,
            role_ids=["role_ceo"], garage_scope=None, mfa_required=True,
        )
        self.session.add(account)
        await self.session.flush()
        self.session.add(AdminAuditLog(
            admin_account_id=account.id, action="account.first_admin_signup",
            resource_id=account.id, details={"source": "operator_setup_api"},
        ))
        # Commit while holding the lock and before sending a success response.
        # No session is issued here. The operator must sign in separately.
        result = AdminIdentity.model_validate(account).model_dump(mode="json")
        result.update(
            role_ids=["role_ceo"],
            mfa_required=settings.ADMIN_MFA_REQUIRED,
            next_step=(
                "SIGN_IN_AND_COMPLETE_MFA" if settings.ADMIN_MFA_REQUIRED else "SIGN_IN"
            ),
        )
        await self.session.commit()
        return result
