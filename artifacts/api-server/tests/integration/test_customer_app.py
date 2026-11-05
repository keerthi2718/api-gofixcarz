"""Customer API regression tests against real dev SQL, with no real SMS."""
import hashlib
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from jose import jwt
from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.customer_security import AUDIENCE, ISSUER, now, otp_digest
from app.core.security import create_access_token, decode_access_token
from app.database.connection_url import build_async_url
from app.database.session import get_session
from app.main import app
from app.models.admin_operations import CustomerAccount
from app.models.customer_auth import (
    CustomerAuthRateBucket, CustomerIdentity, CustomerOTPChallenge,
    CustomerRefreshCredential, CustomerSession,
)
from app.services.customer_auth_service import CustomerAuthService

BASE = "/api/v1/customer-app"


def mobile():
    return "+919" + str(uuid4().int % 10**9).zfill(9)


def bearer(tokens):
    return {"Authorization": "Bearer " + tokens["access_token"]}


@pytest_asyncio.fixture
async def customer_api(monkeypatch):
    url, args = build_async_url(settings.DATABASE_URL)
    assert make_url(url).host == "helium", "Only the internal development database may be tested."
    engine = create_async_engine(url, connect_args=args, poolclass=NullPool)
    sent = {}
    ip = "customer-test-" + uuid4().hex
    device = uuid4().hex
    sms_ok = [True]

    async def sms(number, code):
        sent["+" + number] = code
        return uuid4().hex[:24] if sms_ok[0] else None

    monkeypatch.setattr("app.services.customer_otp_service.submit_otp_sms", sms)
    async with engine.connect() as connection:
        outer = await connection.begin()

        async def override():
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint",
            ) as session:
                try:
                    # The outer transaction is already active. Prevent the
                    # existing admin GET dependency from changing isolation.
                    await session.connection()
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        originals = app.dependency_overrides.copy()
        app.dependency_overrides[get_session] = override
        transport = httpx.ASGITransport(app=app, client=(ip, 1))
        try:
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test",
                headers={"X-Device-ID": device},
            ) as client:
                async with AsyncSession(bind=connection, expire_on_commit=False) as inspect:
                    yield {"client": client, "db": inspect, "sent": sent, "sms_ok": sms_ok}
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(originals)
            await outer.rollback()
    # Counters intentionally persist outside the request transaction; remove
    # only this fixture's uniquely hashed keys, never real users' counters.
    keys = [
        hashlib.sha256(f"{operation}:{scope}".encode()).hexdigest()
        for operation in ("send", "verify", "refresh")
        for scope in [f"ip:{ip}", f"device:{device}"] + [f"mobile:{number}" for number in sent]
    ]
    async with engine.begin() as connection:
        await connection.execute(delete(CustomerAuthRateBucket).where(CustomerAuthRateBucket.key.in_(keys)))
    await engine.dispose()


async def register(d, number=None):
    number = number or mobile()
    response = await d["client"].post(BASE + "/auth/register", json={
        "name": "Customer API fixture", "channel": "mobile", "identifier": number,
        "terms_accepted": True, "terms_version": settings.CUSTOMER_TERMS_VERSION,
    })
    assert response.status_code == 202, response.text
    return number, response.json()["data"]["challenge_id"]


async def verify(d, number, challenge):
    response = await d["client"].post(BASE + "/auth/otp/verify", json={
        "challenge_id": challenge, "otp": d["sent"][number], "device_name": "Fixture phone",
    })
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def account(d):
    number, challenge = await register(d)
    return number, await verify(d, number, challenge)


async def age_challenge(d, challenge):
    await d["db"].execute(update(CustomerOTPChallenge).where(
        CustomerOTPChallenge.id == UUID(challenge),
    ).values(created_at=now() - timedelta(seconds=31)))
    await d["db"].flush()


async def test_registration_creates_account_only_after_verification(customer_api):
    d = customer_api
    number, challenge = await register(d)
    assert not (await d["db"].execute(select(CustomerIdentity).where(
        CustomerIdentity.mobile == number))).scalar_one_or_none()
    row = await d["db"].get(CustomerOTPChallenge, UUID(challenge))
    assert row.otp_hash != d["sent"][number]
    assert row.otp_hash == otp_digest(row.id, number, "REGISTER", d["sent"][number])
    tokens = await verify(d, number, challenge)
    assert tokens["customer"]["mobile"] == number
    assert tokens["expires_in_seconds"] == 900
    assert decode_access_token(tokens["access_token"]) is None
    identity = await d["db"].get(CustomerIdentity, UUID(tokens["customer"]["id"]))
    assert identity.terms_version == settings.CUSTOMER_TERMS_VERSION
    session = await d["db"].get(CustomerSession, UUID(tokens["session_id"]))
    assert 29 < (session.expires_at - session.authenticated_at).total_seconds() / 86400 <= 30
    repeat = await d["client"].post(BASE + "/auth/otp/verify", json={
        "challenge_id": challenge, "otp": d["sent"][number],
    })
    assert repeat.status_code == 400


async def test_unknown_login_does_not_create_account(customer_api):
    d = customer_api
    number = mobile()
    r = await d["client"].post(BASE + "/auth/otp/send", json={
        "channel": "mobile", "identifier": number, "purpose": "LOGIN",
    })
    assert r.status_code == 202
    r = await d["client"].post(BASE + "/auth/otp/verify", json={
        "challenge_id": r.json()["data"]["challenge_id"], "otp": d["sent"][number],
    })
    assert r.status_code == 400
    assert not (await d["db"].execute(select(CustomerIdentity).where(
        CustomerIdentity.mobile == number))).scalar_one_or_none()


async def test_login_existing_customer_and_expiry(customer_api):
    d = customer_api
    number, initial = await account(d)
    r = await d["client"].post(BASE + "/auth/otp/send", json={
        "channel": "mobile", "identifier": number, "purpose": "LOGIN",
    })
    assert r.status_code == 202
    tokens = await verify(d, number, r.json()["data"]["challenge_id"])
    assert tokens["customer"]["id"] == initial["customer"]["id"]
    assert tokens["session_id"] != initial["session_id"]
    session = await d["db"].get(CustomerSession, UUID(tokens["session_id"]))
    session.expires_at = now() - timedelta(seconds=1)
    await d["db"].flush()
    assert (await d["client"].get(BASE + "/me", headers=bearer(tokens))).status_code == 401


async def test_wrong_attempts_persist_and_resend_does_not_reset(customer_api):
    d = customer_api
    number, challenge = await register(d)
    wrong = "000000" if d["sent"][number] != "000000" else "111111"
    for _ in range(2):
        assert (await d["client"].post(BASE + "/auth/otp/verify", json={
            "challenge_id": challenge, "otp": wrong,
        })).status_code == 400
    await age_challenge(d, challenge)
    r = await d["client"].post(BASE + "/auth/otp/resend", json={"challenge_id": challenge})
    assert r.status_code == 202
    new_challenge = r.json()["data"]["challenge_id"]
    old = await d["client"].post(BASE + "/auth/otp/verify", json={
        "challenge_id": challenge, "otp": wrong,
    })
    assert old.status_code == 400
    wrong = "000000" if d["sent"][number] != "000000" else "111111"
    for expected in (400, 400, 429):
        r = await d["client"].post(BASE + "/auth/otp/verify", json={
            "challenge_id": new_challenge, "otp": wrong,
        })
        assert r.status_code == expected
    r = await d["client"].post(BASE + "/auth/otp/verify", json={
        "challenge_id": new_challenge, "otp": d["sent"][number],
    })
    assert r.status_code == 429
    await age_challenge(d, new_challenge)
    r = await d["client"].post(BASE + "/auth/otp/resend", json={"challenge_id": new_challenge})
    assert r.status_code == 429


async def test_expired_otp_and_cooldown(customer_api):
    d = customer_api
    number, challenge = await register(d)
    r = await d["client"].post(BASE + "/auth/otp/resend", json={"challenge_id": challenge})
    assert r.status_code == 429
    await d["db"].execute(update(CustomerOTPChallenge).where(
        CustomerOTPChallenge.id == UUID(challenge),
    ).values(expires_at=now() - timedelta(seconds=1)))
    await d["db"].flush()
    r = await d["client"].post(BASE + "/auth/otp/verify", json={
        "challenge_id": challenge, "otp": d["sent"][number],
    })
    assert r.status_code == 400 and r.json()["message"] == "OTP_EXPIRED"


async def test_provider_rejection_is_explicit(customer_api):
    d = customer_api
    d["sms_ok"][0] = False
    number = mobile()
    r = await d["client"].post(BASE + "/auth/register", json={
        "name": "Fixture", "channel": "mobile", "identifier": number,
        "terms_accepted": True, "terms_version": settings.CUSTOMER_TERMS_VERSION,
    })
    assert r.status_code == 503
    assert r.json()["message"] == "OTP_DELIVERY_UNAVAILABLE"
    challenge = (await d["db"].execute(select(CustomerOTPChallenge).where(
        CustomerOTPChallenge.identifier == number))).scalar_one()
    assert challenge.consumed_at is not None


async def test_refresh_rotation_replay_revokes_successors(customer_api):
    d = customer_api
    _, tokens = await account(d)
    r = await d["client"].post(BASE + "/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    newer = r.json()["data"]
    assert newer["refresh_token"] != tokens["refresh_token"]
    assert newer["session_id"] == tokens["session_id"]
    r = await d["client"].post(BASE + "/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401
    assert (await d["client"].get(BASE + "/me", headers=bearer(newer))).status_code == 401
    assert (await d["client"].post(BASE + "/auth/refresh", json={
        "refresh_token": newer["refresh_token"],
    })).status_code == 401


async def test_logout_is_idempotent_and_revokes_access_and_refresh(customer_api):
    d = customer_api
    _, tokens = await account(d)
    r = await d["client"].get(BASE + "/auth/session", headers=bearer(tokens))
    assert r.status_code == 200 and r.json()["data"]["authenticated"]
    for _ in range(2):
        assert (await d["client"].post(BASE + "/auth/logout", headers=bearer(tokens))).status_code == 200
    assert (await d["client"].get(BASE + "/auth/session", headers=bearer(tokens))).status_code == 401
    assert (await d["client"].post(BASE + "/auth/refresh", json={
        "refresh_token": tokens["refresh_token"],
    })).status_code == 401


async def test_profile_patch_preserves_omissions_and_rejects_privilege_fields(customer_api):
    d = customer_api
    _, tokens = await account(d)
    address = {"line1": "Fixture Street", "city": "Hyderabad", "postal_code": "500001", "country": "IN"}
    r = await d["client"].patch(BASE + "/me", headers=bearer(tokens), json={"address": address})
    assert r.status_code == 200 and r.json()["data"]["address"]["city"] == "Hyderabad"
    r = await d["client"].patch(BASE + "/me", headers=bearer(tokens), json={"name": "Updated fixture"})
    assert r.status_code == 200 and r.json()["data"]["address"]["city"] == "Hyderabad"
    for payload in ({}, {"name": None}, {"name": " "}, {"mobile": mobile()}, {"role": "admin"},
                    {"mobile_verified": False}, {"address": {"city": "Only city"}}):
        assert (await d["client"].patch(BASE + "/me", headers=bearer(tokens), json=payload)).status_code == 422
    r = await d["client"].patch(BASE + "/me", headers=bearer(tokens), json={"address": None})
    assert r.status_code == 200 and r.json()["data"]["address"] is None
    r = await d["client"].get(BASE + "/me", headers=bearer(tokens))
    assert r.json()["data"]["name"] == "Updated fixture"


async def test_customer_cannot_access_garage_and_garage_cannot_access_customer(customer_api):
    d = customer_api
    _, tokens = await account(d)
    for path in ("/api/v1/customers", "/api/v1/profile", "/api/v1/admin/me"):
        assert (await d["client"].get(path, headers=bearer(tokens))).status_code == 401
    garage_token = create_access_token(uuid4())
    assert (await d["client"].get(BASE + "/me", headers={
        "Authorization": "Bearer " + garage_token,
    })).status_code == 401
    payload = {
        "sub": tokens["customer"]["id"], "sid": tokens["session_id"], "role": "customer",
        "type": "customer_access", "iss": ISSUER, "aud": "wrong",
        "iat": now(), "exp": now() + timedelta(minutes=15),
    }
    forged = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert (await d["client"].get(BASE + "/me", headers={
        "Authorization": "Bearer " + forged,
    })).status_code == 401


async def test_mobile_change_is_verified_and_session_bound(customer_api):
    d = customer_api
    old, tokens = await account(d)
    # An earlier login challenge must not work after the mobile changes.
    r = await d["client"].post(BASE + "/auth/otp/send", json={
        "channel": "mobile", "identifier": old, "purpose": "LOGIN",
    })
    pending_old_login = r.json()["data"]["challenge_id"]
    second = await verify(d, old, pending_old_login)
    await age_challenge(d, pending_old_login)
    r = await d["client"].post(BASE + "/auth/otp/send", json={
        "channel": "mobile", "identifier": old, "purpose": "LOGIN",
    })
    assert r.status_code == 202
    pending_old_login = r.json()["data"]["challenge_id"]
    old_code = d["sent"][old]
    new = mobile()
    r = await d["client"].post(BASE + "/me/contact-change", headers=bearer(tokens), json={
        "channel": "mobile", "new_identifier": new,
    })
    assert r.status_code == 202
    challenge = r.json()["data"]["challenge_id"]
    assert (await d["client"].get(BASE + "/me", headers=bearer(tokens))).json()["data"]["mobile"] == old
    # A contact-change OTP cannot be used to log in.
    r = await d["client"].post(BASE + "/auth/otp/verify", json={
        "challenge_id": challenge, "otp": d["sent"][new],
    })
    assert r.status_code == 400
    # Nor may another session complete it.
    r = await d["client"].post(BASE + "/me/contact-change/verify", headers=bearer(second), json={
        "challenge_id": challenge, "otp": d["sent"][new],
    })
    assert r.status_code == 400
    r = await d["client"].post(BASE + "/me/contact-change/verify", headers=bearer(tokens), json={
        "challenge_id": challenge, "otp": d["sent"][new],
    })
    assert r.status_code == 200 and r.json()["data"]["mobile"] == new
    assert (await d["client"].get(BASE + "/me", headers=bearer(tokens))).json()["data"]["mobile"] == new
    assert (await d["client"].get(BASE + "/me", headers=bearer(second))).status_code == 401
    r = await d["client"].post(BASE + "/auth/otp/verify", json={
        "challenge_id": pending_old_login, "otp": old_code,
    })
    assert r.status_code == 400


async def test_contact_conflict_and_recent_auth(customer_api):
    d = customer_api
    _, tokens = await account(d)
    other, _ = await account(d)
    r = await d["client"].post(BASE + "/me/contact-change", headers=bearer(tokens), json={
        "channel": "mobile", "new_identifier": other,
    })
    assert r.status_code == 409
    await d["db"].execute(update(CustomerSession).where(
        CustomerSession.id == UUID(tokens["session_id"]),
    ).values(authenticated_at=now() - timedelta(minutes=16)))
    await d["db"].flush()
    r = await d["client"].post(BASE + "/me/contact-change", headers=bearer(tokens), json={
        "channel": "mobile", "new_identifier": mobile(),
    })
    assert r.status_code == 403


@pytest.mark.parametrize("status", ["INACTIVE", "DELETED"])
async def test_account_status_blocks_access_refresh_and_login(customer_api, status):
    d = customer_api
    number, tokens = await account(d)
    row = await d["db"].get(CustomerAccount, UUID(tokens["customer"]["id"]))
    row.account_status = status
    await d["db"].flush()
    assert (await d["client"].get(BASE + "/me", headers=bearer(tokens))).status_code == 401
    assert (await d["client"].post(BASE + "/auth/refresh", json={
        "refresh_token": tokens["refresh_token"],
    })).status_code == 401
    r = await d["client"].post(BASE + "/auth/otp/send", json={
        "channel": "mobile", "identifier": number, "purpose": "LOGIN",
    })
    assert r.status_code == 202
    r = await d["client"].post(BASE + "/auth/otp/verify", json={
        "challenge_id": r.json()["data"]["challenge_id"], "otp": d["sent"][number],
    })
    assert r.status_code == 400


async def test_send_limits_are_durable_across_rejected_requests(customer_api):
    d = customer_api
    number, challenge = await register(d)
    for _ in range(4):
        r = await d["client"].post(BASE + "/auth/otp/resend", json={"challenge_id": challenge})
        assert r.status_code == 429 and r.json()["message"] == "RESEND_COOLDOWN"
    await age_challenge(d, challenge)
    r = await d["client"].post(BASE + "/auth/otp/resend", json={"challenge_id": challenge})
    assert r.status_code == 429 and r.json()["message"] == "RATE_LIMITED"


async def test_mobile_only_contract_and_no_store_errors(customer_api):
    d = customer_api
    for payload in (
        {"name": "Fixture", "channel": "email", "identifier": "test@example.test",
         "terms_accepted": True, "terms_version": settings.CUSTOMER_TERMS_VERSION},
        {"name": "Fixture", "channel": "mobile", "identifier": "9000000001",
         "terms_accepted": True, "terms_version": settings.CUSTOMER_TERMS_VERSION},
        {"name": "Fixture", "channel": "mobile", "identifier": mobile(),
         "terms_accepted": False, "terms_version": settings.CUSTOMER_TERMS_VERSION},
    ):
        r = await d["client"].post(BASE + "/auth/register", json=payload)
        assert r.status_code == 422
        assert r.headers["cache-control"] == "no-store"
    r = await d["client"].get(BASE + "/me")
    assert r.status_code == 401 and r.headers["cache-control"] == "no-store"
    assert (await d["client"].post(BASE + "/auth/password/login", json={})).status_code == 404


async def test_wrong_terms_version_and_duplicate_registration(customer_api):
    d = customer_api
    r = await d["client"].post(BASE + "/auth/register", json={
        "name": "Fixture", "channel": "mobile", "identifier": mobile(),
        "terms_accepted": True, "terms_version": "not-current",
    })
    assert r.status_code == 422 and r.json()["message"] == "TERMS_VERSION_INVALID"
    number, _ = await account(d)
    r = await d["client"].post(BASE + "/auth/register", json={
        "name": "Fixture", "channel": "mobile", "identifier": number,
        "terms_accepted": True, "terms_version": settings.CUSTOMER_TERMS_VERSION,
    })
    assert r.status_code == 409


async def test_cleanup_keeps_live_sessions_and_removes_expired_credentials(customer_api):
    from app.services.customer_auth_maintenance import delete_expired_customer_credentials
    d = customer_api
    _, live = await account(d)
    _, expired = await account(d)
    await d["db"].execute(update(CustomerSession).where(
        CustomerSession.id == UUID(expired["session_id"]),
    ).values(expires_at=now() - timedelta(days=2)))
    old = CustomerOTPChallenge(
        id=uuid4(), root_id=uuid4(), identifier=mobile(), purpose="LOGIN",
        otp_hash="0" * 64, attempts=0,
        created_at=now() - timedelta(days=3), expires_at=now() - timedelta(days=2),
    )
    d["db"].add(old)
    await d["db"].flush()
    await delete_expired_customer_credentials(d["db"])
    await d["db"].flush()
    assert (await d["db"].execute(select(CustomerSession.id).where(
        CustomerSession.id == UUID(expired["session_id"])))).scalar_one_or_none() is None
    assert (await d["db"].execute(select(CustomerRefreshCredential.token_hash).where(
        CustomerRefreshCredential.session_id == UUID(expired["session_id"])))).scalar_one_or_none() is None
    assert (await d["db"].execute(select(CustomerSession.id).where(
        CustomerSession.id == UUID(live["session_id"])))).scalar_one()
    assert (await d["db"].execute(select(CustomerIdentity.customer_id).where(
        CustomerIdentity.customer_id == UUID(expired["customer"]["id"])))).scalar_one()


async def test_garage_imported_customer_records_are_not_auto_linked(customer_api):
    d = customer_api
    number = mobile()
    imported = CustomerAccount(
        id=uuid4(), name="Imported contact", mobile=number,
        account_status="ACTIVE", source="fixture_import",
    )
    d["db"].add(imported)
    await d["db"].flush()
    _, challenge = await register(d, number)
    tokens = await verify(d, number, challenge)
    assert tokens["customer"]["id"] != str(imported.id)
    assert imported.source == "fixture_import"
    assert (await d["db"].execute(select(func.count()).select_from(CustomerAccount).where(
        CustomerAccount.mobile == number))).scalar_one() == 2


def test_openapi_has_approved_customer_operations_without_password_routes():
    spec = app.openapi()
    paths = {path: value for path, value in spec["paths"].items() if path.startswith(BASE)}
    import json
    from pathlib import Path
    inventory = json.loads((Path(__file__).resolve().parents[4] /
                            "documents/customer-only-api-specification-source.json").read_text())
    expected = {(BASE + e["path"], e["method"].lower()) for group in inventory
                for e in group["endpoints"] if e["id"] not in {"API-08", "API-09", "API-10", "API-11"}}
    # The approved date-only flow supersedes the historical slot/quote draft.
    expected.discard((BASE + "/bookings/quote", "post"))
    expected.add((BASE + "/bookings/summary", "post"))
    actual = {(path, method) for path, operations in paths.items() for method in operations}
    discovery = {
        (BASE + "/garages/search", "post"),
        (BASE + "/garages/{garage_id}", "get"),
        (BASE + "/garages/{garage_id}/details", "post"),
        (BASE + "/garages/{garage_id}/services", "get"),
    }
    assert actual == expected | discovery | {(BASE + "/jobs/{job_id}/photos/{photo_index}", "get")}
    assert spec["components"]["schemas"]["RegisterRequest"]["additionalProperties"] is False
    booking_input = spec["components"]["schemas"]["BookingSubmit"]
    assert {"garage_id", "vehicle_id", "service_ids", "booking_date"} <= set(booking_input["required"])
    assert not {"slot_id", "quote_id", "booking_fee"} & set(booking_input["properties"])
