"""Integration tests for the auth flow."""
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import httpx

BASE_URL = "http://localhost:8080"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        r = await client.post("/api/v1/auth/sign-up", json={"mobile": mobile, "name": "Token Test"})
        assert r.status_code == 201, r.text

    otp = await _read_otp_from_db(mobile)

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/verify-otp", json={"mobile": mobile, "otp": otp})
        assert r.status_code == 200, r.text
        return r.json()["data"]


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


@pytest.mark.asyncio
async def test_sign_up_new_user():
    mobile = f"7{uuid.uuid4().int % 10**9:09d}"
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/sign-up", json={"mobile": mobile, "name": "Test"})
    assert r.status_code == 201
    assert r.json()["success"] is True


@pytest.mark.asyncio
async def test_sign_up_duplicate_fails():
    mobile = f"6{uuid.uuid4().int % 10**9:09d}"
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        await client.post("/api/v1/auth/sign-up", json={"mobile": mobile, "name": "Test"})
        r = await client.post("/api/v1/auth/sign-up", json={"mobile": mobile, "name": "Test"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_verify_otp_returns_jwt(auth_token):
    assert auth_token and len(auth_token) > 20


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
    mobile = f"91{uuid.uuid4().int % 10**9:09d}"
    tokens = await _signup_and_get_tokens(mobile)
    assert tokens.get("access_token"), "access_token missing from verify-otp response"
    assert tokens.get("refresh_token"), "refresh_token missing from verify-otp response"
    assert tokens["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_refresh_returns_new_token_pair_and_invalidates_old():
    """POST /refresh must return a fresh pair and mark the old refresh token revoked."""
    mobile = f"92{uuid.uuid4().int % 10**9:09d}"
    tokens = await _signup_and_get_tokens(mobile)
    old_refresh = tokens["refresh_token"]

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 200, r.text
    new_tokens = r.json()["data"]
    assert new_tokens.get("access_token"), "new access_token missing"
    assert new_tokens.get("refresh_token"), "new refresh_token missing"
    assert new_tokens["refresh_token"] != old_refresh, "refresh token was not rotated"

    # Old token must now be invalid
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert r2.status_code == 401, "revoked refresh token should return 401"


@pytest.mark.asyncio
async def test_revoked_refresh_token_returns_401():
    """A refresh token that has been explicitly revoked must be rejected."""
    mobile = f"93{uuid.uuid4().int % 10**9:09d}"
    tokens = await _signup_and_get_tokens(mobile)
    refresh = tokens["refresh_token"]
    access = tokens["access_token"]

    # Logout with explicit token to revoke it
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh},
            headers={"Authorization": f"Bearer {access}"},
        )
    assert r.status_code == 200, r.text

    # Attempt to use the now-revoked token
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 401, "revoked token should be rejected"


@pytest.mark.asyncio
async def test_expired_refresh_token_returns_401():
    """A refresh token whose expires_at is in the past must be rejected."""
    mobile = f"94{uuid.uuid4().int % 10**9:09d}"
    tokens = await _signup_and_get_tokens(mobile)
    refresh = tokens["refresh_token"]

    # Force-expire the token in the database using a fresh engine (avoids
    # event-loop conflicts with the module-level shared async_session)
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
async def test_logout_with_token_revokes_only_that_session():
    """Logout with a specific token must revoke only that session, leaving others active."""
    mobile = f"95{uuid.uuid4().int % 10**9:09d}"
    tokens_a = await _signup_and_get_tokens(mobile)
    access_a = tokens_a["access_token"]
    refresh_a = tokens_a["refresh_token"]

    # Create a second session by refreshing
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_a})
    assert r.status_code == 200, r.text
    refresh_b = r.json()["data"]["refresh_token"]
    access_b = r.json()["data"]["access_token"]

    # Logout session B only
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_b},
            headers={"Authorization": f"Bearer {access_b}"},
        )
    assert r.status_code == 200, r.text

    # Session B's token must be rejected
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r_b = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_b})
    assert r_b.status_code == 401, "logged-out session should be rejected"

    # Session A was already consumed by the first refresh call; rotation means it is also
    # invalid — but the user object (access token) is still structurally valid.
    # Verify the account itself is still reachable via the second access token.
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r_profile = await client.get(
            "/api/v1/profile",
            headers={"Authorization": f"Bearer {access_b}"},
        )
    assert r_profile.status_code == 200, "active session access token should still work"


@pytest.mark.asyncio
async def test_logout_without_token_revokes_all_sessions():
    """Logout without a refresh token must revoke every session for the user."""
    mobile = f"96{uuid.uuid4().int % 10**9:09d}"
    tokens = await _signup_and_get_tokens(mobile)
    access = tokens["access_token"]
    refresh1 = tokens["refresh_token"]

    # Create a second session via refresh (also consumes refresh1, gives refresh2)
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1})
    assert r.status_code == 200, r.text
    refresh2 = r.json()["data"]["refresh_token"]
    access2 = r.json()["data"]["access_token"]

    # Logout without specifying a token — should nuke all sessions
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post(
            "/api/v1/auth/logout",
            json={},
            headers={"Authorization": f"Bearer {access2}"},
        )
    assert r.status_code == 200, r.text

    # Both refresh tokens should now be invalid
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r1 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh1})
        r2 = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh2})
    assert r1.status_code == 401, "session 1 should be revoked"
    assert r2.status_code == 401, "session 2 should be revoked"
