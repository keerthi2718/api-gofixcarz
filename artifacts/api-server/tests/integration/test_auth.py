"""Integration tests for the auth flow."""
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import httpx

BASE_URL = "http://localhost:8080"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_mobile() -> str:
    return str(uuid.uuid4().int % 10**10).zfill(10)


def _signup_payload(mobile: str, suffix: str = "") -> dict:
    """Return a valid sign-up payload for the given mobile.
    
    Uses the full mobile as the email tag to guarantee cross-test uniqueness.
    """
    tag = suffix or mobile  # full mobile avoids last-6-digit collisions
    return {
        "first_name": "Test",
        "workshop_name": f"Test Workshop {mobile}",
        "email": f"t{tag}@authtest.com",
        "country_code": "91",
        "mobile": mobile,
        "terms_accepted": True,
    }


async def _read_otp_from_db(mobile: str) -> str:
    """Open a fresh DB connection (own engine) to read the OTP, then dispose."""
    from app.database.session import _build_async_url
    from app.core.config import settings
    from app.models.user import User
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy import select

    url, connect_args = _build_async_url(settings.DATABASE_URL)
    engine = create_async_engine(url, connect_args=connect_args, pool_size=1, max_overflow=0)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            user = (await session.execute(select(User).where(User.mobile == mobile))).scalar_one()
            return user.otp
    finally:
        await engine.dispose()


async def _signup_and_get_tokens(mobile: str) -> dict:
    """Sign up a fresh user, read OTP from DB, verify it, return token data."""
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/sign-up", json=_signup_payload(mobile))
        assert r.status_code == 201, r.text

    otp = await _read_otp_from_db(mobile)

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/verify-otp", json={"mobile": mobile, "otp": otp})
        assert r.status_code == 200, r.text
        return r.json()["data"]


# ---------------------------------------------------------------------------
# Basic endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_endpoint():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["data"]["database"] == "connected"


@pytest.mark.asyncio
async def test_version_endpoint():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.get("/api/version")
    assert r.status_code == 200
    assert r.json()["data"]["app_name"] == "Garage Management API"


# ---------------------------------------------------------------------------
# Sign-up tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sign_up_new_user():
    mobile = _unique_mobile()
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/sign-up", json=_signup_payload(mobile))
    assert r.status_code == 201
    assert r.json()["success"] is True
    data = r.json()["data"]
    assert data["mobile"] == mobile
    assert data["country_code"] == "91"


@pytest.mark.asyncio
async def test_sign_up_duplicate_mobile_fails():
    mobile = _unique_mobile()
    payload = _signup_payload(mobile)
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        await client.post("/api/v1/auth/sign-up", json=payload)
        # Second attempt with same mobile, different email
        payload2 = {**payload, "email": f"other_{mobile}@authtest.com"}
        r = await client.post("/api/v1/auth/sign-up", json=payload2)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_sign_up_duplicate_email_fails():
    mobile_a = _unique_mobile()
    mobile_b = _unique_mobile()
    payload = _signup_payload(mobile_a)
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        await client.post("/api/v1/auth/sign-up", json=payload)
        payload2 = {**payload, "mobile": mobile_b}  # same email, different mobile
        r = await client.post("/api/v1/auth/sign-up", json=payload2)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_sign_up_mobile_equals_mobile2_fails():
    mobile = _unique_mobile()
    payload = {
        **_signup_payload(mobile),
        "country_code_2": "91",
        "mobile_2": mobile,  # same as primary
    }
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/sign-up", json=payload)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_sign_up_invalid_zipcode_fails():
    mobile = _unique_mobile()
    payload = {**_signup_payload(mobile), "zipcode": "ABCDE"}
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/sign-up", json=payload)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_sign_up_invalid_country_code_fails():
    mobile = _unique_mobile()
    payload = {**_signup_payload(mobile), "country_code": "999"}
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/sign-up", json=payload)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_sign_up_terms_not_accepted_fails():
    mobile = _unique_mobile()
    payload = {**_signup_payload(mobile), "terms_accepted": False}
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/sign-up", json=payload)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Sign-in tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sign_in_with_mobile():
    """Sign-in with 10-digit mobile — no country code required."""
    mobile = _unique_mobile()
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        await client.post("/api/v1/auth/sign-up", json=_signup_payload(mobile))
        r = await client.post("/api/v1/auth/sign-in", json={"mobile": mobile})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["mobile"] == mobile
    assert "country_code" in data


@pytest.mark.asyncio
async def test_sign_in_with_email_rejected():
    """Email is no longer accepted for sign-in — must return 422."""
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/sign-in", json={"mobile": "test@example.com"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_sign_in_unregistered_mobile_returns_400():
    # Use a mobile with leading zeros that will never appear in seed data
    unregistered = "0" + str(uuid.uuid4().int % 10**9).zfill(9)
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/sign-in", json={"mobile": unregistered})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_sign_in_invalid_format_returns_422():
    """Non-numeric, non-10-digit values must be rejected before hitting the service."""
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/sign-in", json={"mobile": "nobody@nowhere.com"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Send-OTP tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_otp_registered_mobile():
    mobile = _unique_mobile()
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        await client.post("/api/v1/auth/sign-up", json=_signup_payload(mobile))
        r = await client.post("/api/v1/auth/send-otp", json={"mobile": mobile})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["mobile"] == mobile
    assert "country_code" in data


@pytest.mark.asyncio
async def test_send_otp_unregistered_mobile_returns_400():
    unregistered = "0" + str(uuid.uuid4().int % 10**9).zfill(9)
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/send-otp", json={"mobile": unregistered})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_send_otp_invalid_mobile_format():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/send-otp", json={"mobile": "123"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Verify-OTP tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_otp_returns_jwt(auth_token):
    assert auth_token and len(auth_token) > 20


@pytest.mark.asyncio
async def test_verify_otp_wrong_otp_returns_401():
    mobile = _unique_mobile()
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        await client.post("/api/v1/auth/sign-up", json=_signup_payload(mobile))
        r = await client.post("/api/v1/auth/verify-otp", json={"mobile": mobile, "otp": "000000"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_verify_otp_unregistered_mobile_returns_400():
    unregistered = "0" + str(uuid.uuid4().int % 10**9).zfill(9)
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/verify-otp", json={"mobile": unregistered, "otp": "123456"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Protected endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_protected_endpoint_requires_auth():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.get("/api/v1/customers")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_profile_accessible_with_token(auth_token):
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.get(
            "/api/v1/profile",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
    assert r.status_code == 200
    assert r.json()["success"] is True


# ---------------------------------------------------------------------------
# Refresh token flow tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_verify_otp_returns_both_tokens():
    """OTP verification must return both access_token and refresh_token."""
    mobile = _unique_mobile()
    tokens = await _signup_and_get_tokens(mobile)
    assert tokens.get("access_token"), "access_token missing from verify-otp response"
    assert tokens.get("refresh_token"), "refresh_token missing from verify-otp response"
    assert tokens["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_refresh_returns_new_access_token_keeps_same_refresh():
    """POST /refresh issues a new access token but keeps the same refresh token (no rotation).

    No rotation means the same refresh token can be reused indefinitely until it
    expires or is explicitly revoked — safe against network-loss on mobile.
    """
    mobile = _unique_mobile()
    tokens = await _signup_and_get_tokens(mobile)
    refresh = tokens["refresh_token"]
    original_access = tokens["access_token"]

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200, r.text
    new_tokens = r.json()["data"]
    assert new_tokens.get("access_token"), "new access_token missing"
    # Note: tokens issued in the same second are byte-for-byte identical (same sub+exp);
    # we verify the token is present and the refresh token was not rotated.
    assert new_tokens["refresh_token"] == refresh, "refresh token must NOT be rotated"

    # Same token still usable — no revocation happened
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 200, "same refresh token should still be accepted"


@pytest.mark.asyncio
async def test_revoked_refresh_token_returns_401():
    """A refresh token that has been explicitly revoked must be rejected."""
    mobile = _unique_mobile()
    tokens = await _signup_and_get_tokens(mobile)
    refresh = tokens["refresh_token"]
    access = tokens["access_token"]

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh},
            headers={"Authorization": f"Bearer {access}"},
        )
    assert r.status_code == 200, r.text

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 401, "revoked token should be rejected"


@pytest.mark.asyncio
async def test_expired_refresh_token_returns_401():
    """A refresh token whose expires_at is in the past must be rejected."""
    mobile = _unique_mobile()
    tokens = await _signup_and_get_tokens(mobile)
    refresh = tokens["refresh_token"]

    from app.database.session import _build_async_url
    from app.core.config import settings
    from app.models.refresh_token import RefreshToken
    from app.core.security import hash_refresh_token
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy import update

    token_hash = hash_refresh_token(refresh)
    past = datetime(2000, 1, 1, tzinfo=timezone.utc)
    url, connect_args = _build_async_url(settings.DATABASE_URL)
    engine = create_async_engine(url, connect_args=connect_args, pool_size=1, max_overflow=0)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            await session.execute(
                update(RefreshToken)
                .where(RefreshToken.token_hash == token_hash)
                .values(expires_at=past)
            )
            await session.commit()
    finally:
        await engine.dispose()

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401, "expired token should be rejected"


@pytest.mark.asyncio
async def test_logout_with_token_revokes_that_token():
    """Logout with a refresh token must revoke it; the access token remains valid until expiry."""
    mobile = _unique_mobile()
    tokens = await _signup_and_get_tokens(mobile)
    access = tokens["access_token"]
    refresh = tokens["refresh_token"]

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh},
            headers={"Authorization": f"Bearer {access}"},
        )
    assert r.status_code == 200, r.text

    # Refresh token is now revoked
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 401, "logged-out refresh token should be rejected"

    # Existing access token still works (it lives until its own expiry)
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r_profile = await client.get(
            "/api/v1/profile",
            headers={"Authorization": f"Bearer {access}"},
        )
    assert r_profile.status_code == 200, "access token should still be valid after logout"


@pytest.mark.asyncio
async def test_logout_without_token_revokes_all_sessions():
    """Logout without a refresh token must revoke every refresh token for the user."""
    mobile = _unique_mobile()
    tokens = await _signup_and_get_tokens(mobile)
    refresh = tokens["refresh_token"]
    access = tokens["access_token"]

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post(
            "/api/v1/auth/logout",
            json={},
            headers={"Authorization": f"Bearer {access}"},
        )
    assert r.status_code == 200, r.text

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 401, "all refresh tokens should be revoked after full logout"
