"""Customer account/session lifecycle; no contact-record auto-linking."""
import uuid
from datetime import timedelta

from sqlalchemy import select, update

from app.core.customer_security import access_token, decode_customer_access, now
from app.core.security import generate_refresh_token, hash_refresh_token
from app.models.admin_operations import CustomerAccount
from app.models.customer_auth import (
    CustomerIdentity, CustomerOTPChallenge, CustomerRefreshCredential, CustomerSession,
)
from app.services.customer_otp_service import CustomerOTPService, fail


class CustomerAuthService(CustomerOTPService):
    @staticmethod
    def profile(account, identity):
        return {
            "id": account.id, "name": account.name, "mobile": identity.mobile,
            "email": None, "mobile_verified": True, "email_verified": False,
            "photo": None, "address": identity.address,
        }

    async def principal(self, token, *, allow_revoked=False):
        payload = decode_customer_access(token)
        try:
            if not payload:
                raise ValueError()
            customer_id, session_id = uuid.UUID(payload["sub"]), uuid.UUID(payload["sid"])
        except (ValueError, KeyError, TypeError):
            fail("AUTH_REQUIRED", 401)
        await self.lock("account", customer_id)
        login_session = await self.db.get(CustomerSession, session_id, populate_existing=True)
        account = await self.active(customer_id)
        identity = await self.db.get(CustomerIdentity, customer_id)
        if (
            not login_session or not account or not identity
            or login_session.customer_id != customer_id or login_session.expires_at <= now()
            or (login_session.revoked_at is not None and not allow_revoked)
        ):
            fail("SESSION_REVOKED", 401)
        return account, identity, login_session, payload

    async def issue_tokens(self, account, identity, login_session):
        raw = generate_refresh_token()
        self.db.add(CustomerRefreshCredential(
            token_hash=hash_refresh_token(raw), session_id=login_session.id,
        ))
        return {
            "customer": self.profile(account, identity),
            "access_token": access_token(account.id, login_session.id),
            "refresh_token": raw, "token_type": "Bearer", "expires_in_seconds": 900,
            "session_id": login_session.id,
        }

    async def complete_login(self, data):
        challenge = await self.verify(data, {"REGISTER", "LOGIN"})
        instant = now()
        if challenge.purpose == "REGISTER":
            if await self.identity_by_mobile(challenge.identifier):
                await self.db.commit()
                fail("ACCOUNT_ALREADY_EXISTS", 409)
            account = CustomerAccount(
                id=uuid.uuid4(), name=challenge.pending_registration["name"],
                mobile=challenge.identifier, email=None, account_status="ACTIVE",
                source="customer_app", last_activity_at=instant,
            )
            self.db.add(account)
            await self.db.flush()
            identity = CustomerIdentity(
                customer_id=account.id, mobile=challenge.identifier, verified_at=instant,
                terms_version=challenge.pending_registration["terms_version"],
                terms_accepted_at=instant,
            )
            self.db.add(identity)
            await self.db.flush()
        else:
            account = await self.active(challenge.customer_id)
            identity = await self.db.get(CustomerIdentity, challenge.customer_id)
            account.last_activity_at = instant
        login_session = CustomerSession(
            id=uuid.uuid4(), customer_id=account.id, authenticated_at=instant,
            expires_at=instant + timedelta(days=30), device_name=data.device_name,
        )
        self.db.add(login_session)
        await self.db.flush()
        return await self.issue_tokens(account, identity, login_session)

    async def refresh(self, raw):
        await self.rate_limit("refresh")
        credential = await self.db.get(CustomerRefreshCredential, hash_refresh_token(raw))
        if not credential:
            await self.db.commit()
            fail("REFRESH_TOKEN_INVALID", 401)
        login_session = await self.db.get(CustomerSession, credential.session_id)
        await self.lock("account", login_session.customer_id)
        credential = await self.db.get(
            CustomerRefreshCredential, credential.token_hash, populate_existing=True)
        login_session = await self.db.get(
            CustomerSession, credential.session_id, populate_existing=True)
        if credential.used_at is not None:
            # Every credential ever issued for this stable session stays in the
            # ledger until session expiry, allowing replay to revoke successors.
            login_session.revoked_at = now()
            await self.db.commit()
            fail("SESSION_REVOKED", 401)
        account = await self.active(login_session.customer_id)
        if not account or login_session.revoked_at or login_session.expires_at <= now():
            await self.db.commit()
            fail("SESSION_REVOKED", 401)
        identity = await self.db.get(CustomerIdentity, account.id)
        credential.used_at = now()
        account.last_activity_at = now()
        return await self.issue_tokens(account, identity, login_session)

    async def update_profile(self, data, principal):
        account, identity = principal[:2]
        if "name" in data.model_fields_set:
            account.name = data.name
        if "address" in data.model_fields_set:
            identity.address = data.address.model_dump(exclude_none=True) if data.address else None
        return self.profile(account, identity)

    async def start_contact_change(self, data, principal):
        self.require_recent(principal)
        return await self.start(
            data.new_identifier, "CONTACT_CHANGE",
            customer_id=principal[0].id, session_id=principal[2].id,
        )

    async def complete_contact_change(self, data, principal):
        self.require_recent(principal)
        challenge = await self.verify(data, {"CONTACT_CHANGE"}, principal)
        if await self.identity_by_mobile(challenge.identifier):
            await self.db.commit()
            fail("CONTACT_ALREADY_IN_USE", 409)
        account, identity, login_session = principal[:3]
        identity.mobile = account.mobile = challenge.identifier
        identity.verified_at = now()
        await self.db.execute(update(CustomerOTPChallenge).where(
            CustomerOTPChallenge.customer_id == account.id,
            CustomerOTPChallenge.consumed_at.is_(None),
        ).values(consumed_at=now()))
        # Retain the recently verified initiating session; revoke all others.
        await self.db.execute(update(CustomerSession).where(
            CustomerSession.customer_id == account.id, CustomerSession.id != login_session.id,
            CustomerSession.revoked_at.is_(None),
        ).values(revoked_at=now()))
        return {"mobile": identity.mobile, "mobile_verified": True}
