import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.admin_security import (
    ACCESS_SECONDS, admin_access_token, hash_admin_password, verify_admin_password,
)
from app.core.config import settings
from app.core.exceptions import UnauthorizedException
from app.core.security import hash_refresh_token
from app.models.admin_account import AdminAccount, AdminSession, AdminMfaChallenge, AdminRevokedFamily
from app.core.admin_totp import new_secret, encrypt_secret, decrypt_secret, verify_totp
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


def authorized_menus(permissions):
    catalog = [(m.key, m.label, m.api, {
        "dashboard": "dashboard.read", "users": "users.read", "garages": "garages.read",
        "jobs": "jobs.read", "bookings": "bookings.read", "analytics": "dashboard.read",
        "billing_issues": "finance.read", "audit_logs": "audit.read",
    }[m.key]) for m in MENUS]
    catalog.extend((key, label, f"/api/v1/admin/{path}", permission) for key, label, path, permission in [
        ("security", "Security", "staff", "security.read"),
        ("customers", "Customers", "customers", "customers.read"),
        ("finance", "Finance", "finance/summary", "finance.read"),
        ("notifications", "Notifications", "notifications", "notifications.read"),
        ("support", "Support", "support/tickets", "support.read"),
        ("owners", "Owner performance", "garage-owner-statistics", "owner_statistics.read"),
        ("reports", "Reports", "reports/exports", "reports.export"),
    ])
    return [{"key": key, "label": label, "api": path} for key, label, path, permission in catalog
            if permission in permissions]


class AdminAuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    def audit(self, account, action):
        self.session.add(AdminAuditLog(
            admin_account_id=account.id, action=action, resource_id=account.id, details={},
        ))

    async def issue(self, account, mfa_verified_at=None, family_id=None, expires_at=None):
        raw = secrets.token_urlsafe(48)
        login_session = AdminSession(
            id=uuid.uuid4(), admin_account_id=account.id,
            credential_version=account.credential_version,
            refresh_token_hash=hash_refresh_token(raw),
            expires_at=expires_at or datetime.now(timezone.utc) + timedelta(days=7),
            mfa_verified_at=mfa_verified_at, family_id=family_id or uuid.uuid4(),
        )
        self.session.add(login_session)
        await self.session.flush()
        from app.core.admin_policy import resolve_permissions
        identity = AdminIdentity.model_validate(account).model_dump(mode="json")
        identity.update(role_ids=account.role_ids, permissions=sorted(await resolve_permissions(self.session, account)),
                        data_scope={"type": "PLATFORM" if account.garage_scope is None else "GARAGES",
                                    "garage_ids": account.garage_scope or []})
        return {
            "access_token": admin_access_token(account, login_session),
            "refresh_token": raw, "token_type": "bearer", "expires_in": ACCESS_SECONDS,
            "user": identity,
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
        if not (settings.ADMIN_MFA_REQUIRED and account.mfa_required):
            # Password-only login is an explicit platform policy, not a client choice.
            self.audit(account, "auth.login")
            return await self.issue(account)
        challenge = AdminMfaChallenge(
            id=uuid.uuid4(), admin_account_id=account.id,
            expires_at=now + timedelta(minutes=5),
            credential_version=account.credential_version,
        )
        result = {
            "challenge_id": str(challenge.id), "mfa_required": True, "mfa_method": "TOTP",
            "expires_in_seconds": 300, "enrollment_required": not bool(account.mfa_secret_encrypted),
        }
        if not account.mfa_secret_encrypted:
            secret = new_secret()
            challenge.pending_secret_encrypted = encrypt_secret(secret)
            # Only returned following password verification, on a private no-store route.
            from urllib.parse import quote
            result["provisioning_uri"] = (
                f"otpauth://totp/{quote('GoFixCarz:' + account.email)}?secret={secret}&issuer=GoFixCarz"
            )
        self.session.add(challenge)
        self.audit(account, "auth.mfa_challenge")
        await self.session.flush()
        return result

    async def complete_mfa(self, challenge_id, code):
        challenge = (await self.session.execute(select(AdminMfaChallenge).where(
            AdminMfaChallenge.id == challenge_id,
        ).with_for_update())).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if not challenge or challenge.consumed_at or challenge.expires_at <= now or challenge.attempts >= 5:
            return None
        account = (await self.session.execute(select(AdminAccount).where(
            AdminAccount.id == challenge.admin_account_id,
        ).with_for_update())).scalar_one()
        challenge.attempts += 1
        if not account.is_active or challenge.credential_version != account.credential_version or (
            account.locked_until and account.locked_until > now):
            return None
        encrypted = account.mfa_secret_encrypted or challenge.pending_secret_encrypted
        # An old enrollment proof must never replace a factor already enrolled elsewhere.
        if not encrypted or (account.mfa_secret_encrypted and challenge.pending_secret_encrypted):
            return None
        counter = verify_totp(decrypt_secret(encrypted), code, account.last_totp_counter)
        if counter is None:
            account.failed_attempts += 1
            if account.failed_attempts >= 5:
                account.locked_until = now + timedelta(minutes=15)
            self.audit(account, "auth.mfa_failed")
            return None
        account.mfa_secret_encrypted = encrypted
        account.last_totp_counter = counter
        account.failed_attempts = 0
        challenge.consumed_at = now
        self.audit(account, "auth.mfa_verified")
        return await self.issue(account, mfa_verified_at=now)

    async def refresh(self, raw):
        # Lock the old session so a refresh token can only be consumed once.
        previous = (await self.session.execute(select(AdminSession).where(
            AdminSession.refresh_token_hash == hash_refresh_token(raw),
        ).with_for_update())).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if previous and previous.revoked_at:
            from sqlalchemy.dialects.postgresql import insert
            await self.session.execute(insert(AdminRevokedFamily).values(
                family_id=previous.family_id, revoked_at=now,
            ).on_conflict_do_nothing())
            await self.session.execute(update(AdminSession).where(
                AdminSession.family_id == previous.family_id, AdminSession.revoked_at.is_(None),
            ).values(revoked_at=now))
            # Return instead of raising so family revocation commits on failure.
            return None
        if not previous or previous.expires_at <= now:
            raise UnauthorizedException("Invalid or expired session.")
        if await self.session.get(AdminRevokedFamily, previous.family_id):
            return None
        account = await self.session.get(AdminAccount, previous.admin_account_id)
        if not account or not account.is_active or account.credential_version != previous.credential_version:
            raise UnauthorizedException("Invalid or expired session.")
        previous.revoked_at = now
        self.audit(account, "auth.refresh")
        return await self.issue(account, mfa_verified_at=previous.mfa_verified_at,
                                family_id=previous.family_id, expires_at=previous.expires_at)
