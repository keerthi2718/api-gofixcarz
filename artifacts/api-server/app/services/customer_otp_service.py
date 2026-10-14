"""Durable, purpose-bound OTP challenges, resend chains and abuse limits."""
import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, async_sessionmaker

from app.core.config import settings
from app.core.customer_security import now, otp_digest
from app.core.exceptions import AppException
from app.models.customer_auth import (
    CustomerAuthRateBucket, CustomerIdentity, CustomerOTPChallenge,
)
from app.models.admin_operations import CustomerAccount
from app.services.sms_delivery_service import SMSDeliveryService
from app.utils.msg91 import submit_otp_sms


def fail(code, status=400):
    raise AppException(code, status_code=status, errors=[{"code": code}])


class CustomerOTPService:
    def __init__(self, session, request=None):
        self.db = session
        self.request = request

    async def lock(self, namespace, value):
        # Transaction-scoped across workers; never store raw IP/device identifiers.
        digest = hashlib.sha256(f"customer:{namespace}:{value}".encode()).digest()
        key = int.from_bytes(digest[:8], "big", signed=True)
        await self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    async def rate_limit(self, operation, identifier=None):
        ip = self.request.client.host if self.request and self.request.client else "unknown"
        device = self.request.headers.get("X-Device-ID", "")[:200] if self.request else ""
        scopes = [(f"ip:{ip}", 20 if operation == "send" else 60)]
        if device:
            scopes.append((f"device:{device}", 10 if operation == "send" else 30))
        if identifier:
            scopes.append((f"mobile:{identifier}", 5))
        # Sort lock acquisition to avoid bucket deadlocks between requests.
        keys = sorted(
            (hashlib.sha256(f"{operation}:{scope}".encode()).hexdigest(), limit)
            for scope, limit in scopes
        )
        window = int(now().timestamp()) // 900 * 900
        exceeded = False
        # Independent short transaction: counters must survive rejected requests
        # without committing unrelated account changes or holding bucket locks
        # while a caller acquires an identity/session lock.
        bind = self.db.bind
        engine = bind.engine if isinstance(bind, AsyncConnection) else bind
        async with async_sessionmaker(engine)() as counters:
            for key, limit in keys:
                stmt = insert(CustomerAuthRateBucket).values(key=key, window_start=window, count=1)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["key", "window_start"],
                    set_={"count": CustomerAuthRateBucket.count + 1},
                ).returning(CustomerAuthRateBucket.count)
                exceeded |= (await counters.execute(stmt)).scalar_one() > limit
            await counters.commit()
        if exceeded:
            fail("RATE_LIMITED", 429)

    async def identity_by_mobile(self, mobile):
        return (await self.db.execute(select(CustomerIdentity).where(
            CustomerIdentity.mobile == mobile))).scalar_one_or_none()

    async def active(self, customer_id):
        account = await self.db.get(CustomerAccount, customer_id, populate_existing=True)
        return account if account and account.account_status == "ACTIVE" else None

    async def start(self, identifier, purpose, *, registration=None, customer_id=None, session_id=None,
                    prior=None):
        await self.rate_limit("send", identifier)
        # Authenticated/contact and login sends acquire customer lock BEFORE identifier lock.
        if customer_id:
            await self.lock("account", customer_id)
        await self.lock("mobile", identifier)
        identity = await self.identity_by_mobile(identifier)
        if purpose == "REGISTER":
            if identity:
                await self.db.commit()
                fail("ACCOUNT_ALREADY_EXISTS", 409)
            if registration["terms_version"] != settings.CUSTOMER_TERMS_VERSION:
                await self.db.commit()
                fail("TERMS_VERSION_INVALID", 422)
        elif purpose == "CONTACT_CHANGE":
            if identity:
                await self.db.commit()
                fail("CONTACT_ALREADY_IN_USE", 409)
        latest = (await self.db.execute(select(CustomerOTPChallenge).where(
            CustomerOTPChallenge.identifier == identifier,
            CustomerOTPChallenge.purpose == purpose,
        ).order_by(CustomerOTPChallenge.created_at.desc()).limit(1))).scalar_one_or_none()
        if latest and (now() - latest.created_at).total_seconds() < 30:
            await self.db.commit()
            fail("RESEND_COOLDOWN", 429)
        if prior:
            prior = await self.db.get(CustomerOTPChallenge, prior.id, populate_existing=True)
            if prior.consumed_at or prior.expires_at <= now():
                await self.db.commit()
                fail("CHALLENGE_INVALID")
            root = await self.db.get(CustomerOTPChallenge, prior.root_id)
            if root.attempts >= 5:
                await self.db.commit()
                fail("OTP_ATTEMPTS_EXCEEDED", 429)
        elif latest and latest.consumed_at is None and latest.expires_at > now():
            # Starting again is not an attempt-limit bypass for a live chain.
            root = await self.db.get(CustomerOTPChallenge, latest.root_id)
            if root.attempts >= 5:
                await self.db.commit()
                fail("OTP_ATTEMPTS_EXCEEDED", 429)
        else:
            root = None
        # Only a resend continues pending registration metadata. A fresh start
        # invalidates older live challenges without inheriting their name/terms.
        challenge_id = uuid.uuid4()
        code = f"{secrets.randbelow(1_000_000):06d}"
        instant = now()
        challenge = CustomerOTPChallenge(
            id=challenge_id, root_id=root.id if root else challenge_id,
            identifier=identifier, purpose=purpose,
            otp_hash=otp_digest(challenge_id, identifier, purpose, code),
            customer_id=customer_id, session_id=session_id,
            pending_registration=registration,
            created_at=instant, expires_at=instant + timedelta(minutes=5), attempts=0,
        )
        # All previous challenges of this purpose/contact become unusable.
        await self.db.execute(update(CustomerOTPChallenge).where(
            CustomerOTPChallenge.identifier == identifier,
            CustomerOTPChallenge.purpose == purpose,
            CustomerOTPChallenge.consumed_at.is_(None),
        ).values(consumed_at=instant))
        self.db.add(challenge)
        await self.db.flush()
        # Submit the same message for unknown login identifiers as well: no
        # account is created and verification can never establish their session.
        # Provider rejection is explicit, never a successful fake OTP response.
        request_id = await submit_otp_sms(identifier.lstrip("+"), code)
        if not request_id:
            challenge.consumed_at = now()
            await self.db.commit()
            fail("OTP_DELIVERY_UNAVAILABLE", 503)
        await SMSDeliveryService(self.db).register_submission(request_id)
        return {
            "challenge_id": challenge.id, "purpose": purpose,
            "expires_in_seconds": 300, "resend_after_seconds": 30,
        }

    async def login(self, data):
        identity = await self.identity_by_mobile(data.identifier)
        return await self.start(data.identifier, "LOGIN",
                                customer_id=identity.customer_id if identity else None)

    async def resend(self, challenge_id, principal=None):
        challenge = await self.db.get(CustomerOTPChallenge, challenge_id)
        if not challenge or challenge.consumed_at or challenge.expires_at <= now():
            fail("CHALLENGE_INVALID")
        if challenge.purpose == "CONTACT_CHANGE":
            if not principal or challenge.customer_id != principal[0].id or challenge.session_id != principal[2].id:
                fail("CHALLENGE_INVALID")
            self.require_recent(principal)
        return await self.start(
            challenge.identifier, challenge.purpose, registration=challenge.pending_registration,
            customer_id=challenge.customer_id, session_id=challenge.session_id, prior=challenge,
        )

    @staticmethod
    def require_recent(principal):
        if (now() - principal[2].authenticated_at).total_seconds() > 900:
            fail("RECENT_AUTH_REQUIRED", 403)

    async def verify(self, data, purposes, principal=None):
        await self.rate_limit("verify")
        challenge = await self.db.get(CustomerOTPChallenge, data.challenge_id)
        if not challenge or challenge.purpose not in purposes:
            await self.db.commit()
            fail("CHALLENGE_INVALID")
        if challenge.purpose == "CONTACT_CHANGE" and (
            not principal or challenge.customer_id != principal[0].id
            or challenge.session_id != principal[2].id
        ):
            await self.db.commit()
            fail("CHALLENGE_INVALID")
        if challenge.customer_id:
            await self.lock("account", challenge.customer_id)
        await self.lock("mobile", challenge.identifier)
        challenge = await self.db.get(CustomerOTPChallenge, challenge.id, populate_existing=True)
        if challenge.consumed_at:
            await self.db.commit()
            fail("CHALLENGE_INVALID")
        if challenge.expires_at <= now():
            await self.db.commit()
            fail("OTP_EXPIRED")
        if challenge.purpose == "CONTACT_CHANGE":
            if not principal or challenge.customer_id != principal[0].id or challenge.session_id != principal[2].id:
                await self.db.commit()
                fail("CHALLENGE_INVALID")
            self.require_recent(principal)
        root = await self.db.get(CustomerOTPChallenge, challenge.root_id, populate_existing=True)
        if root.attempts >= 5:
            await self.db.commit()
            fail("OTP_ATTEMPTS_EXCEEDED", 429)
        root.attempts += 1
        valid = hmac.compare_digest(
            challenge.otp_hash, otp_digest(challenge.id, challenge.identifier, challenge.purpose, data.otp),
        )
        # Account existence/status never turns an unknown login into registration.
        if challenge.purpose == "LOGIN":
            identity = await self.db.get(CustomerIdentity, challenge.customer_id) if challenge.customer_id else None
            valid = valid and bool(
                identity and identity.mobile == challenge.identifier
                and await self.active(challenge.customer_id)
            )
        if not valid:
            await self.db.commit()
            fail("OTP_ATTEMPTS_EXCEEDED" if root.attempts >= 5 else "OTP_INVALID",
                 429 if root.attempts >= 5 else 400)
        challenge.consumed_at = now()
        return challenge
