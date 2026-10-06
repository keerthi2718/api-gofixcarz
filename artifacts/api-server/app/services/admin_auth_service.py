import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.admin_security import (
    ACCESS_SECONDS, admin_access_token, hash_admin_password, verify_admin_password,
)
from app.core.exceptions import UnauthorizedException
from app.core.security import hash_refresh_token
from app.models.admin_account import AdminAccount, AdminSession
from app.models.admin_audit_log import AdminAuditLog
from app.schemas.admin_auth import AdminIdentity, AdminMenu

# Unknown accounts perform the same expensive password check.
_DUMMY_HASH = hash_admin_password(secrets.token_urlsafe(32))

MENUS = [
    AdminMenu(key=key, label=label, api=f"/api/v1/admin/{path}")
    for key, label, path in [
        ("dashboard", "Dashboard", "dashboard"), ("users", "Users", "users"),
        ("garages", "Garages", "garages"), ("jobs", "Jobs", "jobs"),
        ("bookings", "Bookings", "bookings"), ("analytics", "Analytics", "analytics"),
        ("billing_issues", "Billing issues", "billing/issues"),
        ("audit_logs", "Audit logs", "audit-logs"),
    ]
]


class AdminAuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    def audit(self, account, action):
        self.session.add(AdminAuditLog(
            admin_account_id=account.id, action=action, resource_id=account.id, details={},
        ))

    async def issue(self, account):
        raw = secrets.token_urlsafe(48)
        login_session = AdminSession(
            id=uuid.uuid4(), admin_account_id=account.id,
            credential_version=account.credential_version,
            refresh_token_hash=hash_refresh_token(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        self.session.add(login_session)
        await self.session.flush()
        return {
            "access_token": admin_access_token(account, login_session),
            "refresh_token": raw, "token_type": "bearer", "expires_in": ACCESS_SECONDS,
            "user": AdminIdentity.model_validate(account).model_dump(mode="json"),
        }

    async def login(self, email, password):
        account = (await self.session.execute(select(AdminAccount).where(
            AdminAccount.email == email.strip().lower(),
        ).with_for_update())).scalar_one_or_none()
        valid = await run_in_threadpool(
            verify_admin_password, password, account.password_hash if account else _DUMMY_HASH,
        )
        now = datetime.now(timezone.utc)
        if account and account.locked_until and account.locked_until <= now:
            account.failed_attempts = 0
            account.locked_until = None
        locked = bool(account and account.locked_until and account.locked_until > now)
        if not account or not valid or not account.is_active or locked:
            if account and not locked:
                account.failed_attempts += 1
                if account.failed_attempts >= 5:
                    account.locked_until = now + timedelta(minutes=15)
            if account:
                self.audit(account, "auth.login_failed")
                await self.session.flush()
            # Return, don't raise: get_session commits lockout counters on 401.
            return None
        account.failed_attempts = 0
        account.locked_until = None
        self.audit(account, "auth.login")
        return await self.issue(account)

    async def refresh(self, raw):
        # Lock the old session so a refresh token can only be consumed once.
        previous = (await self.session.execute(select(AdminSession).where(
            AdminSession.refresh_token_hash == hash_refresh_token(raw),
        ).with_for_update())).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if not previous or previous.revoked_at or previous.expires_at <= now:
            raise UnauthorizedException("Invalid or expired session.")
        account = await self.session.get(AdminAccount, previous.admin_account_id)
        if not account or not account.is_active or account.credential_version != previous.credential_version:
            raise UnauthorizedException("Invalid or expired session.")
        previous.revoked_at = now
        self.audit(account, "auth.refresh")
        return await self.issue(account)
