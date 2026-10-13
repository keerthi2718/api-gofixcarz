"""Real SQL signup + MFA with connection-local throwaway tables; no live writes."""
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.v1.admin_auth import limiter
from app.core.admin_security import verify_admin_password
from app.core.admin_totp import totp
from app.core.config import settings
from app.database.connection_url import build_async_url
from app.database.session import get_session
from app.main import app
from app.models.admin_account import AdminAccount, AdminSession
from app.models.admin_audit_log import AdminAuditLog

KEY = "fixture-only-admin-setup-key-long-enough"
PASSWORD = "fixture-only-long-admin-password"
BASE = "/api/v1/admin-auth"


@pytest_asyncio.fixture
async def isolated_signup(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_SIGNUP_ENABLED", True)
    monkeypatch.setattr(settings, "ADMIN_SETUP_KEY", SecretStr(KEY))
    monkeypatch.setattr(settings, "ALLOW_LEGACY_ADMIN_TOKENS", False)
    limiter.reset()
    app.state.limiter.reset()
    url, connect_args = build_async_url(settings.DATABASE_URL)
    assert make_url(url).host == "helium", "Tests refuse non-internal-development targets."
    test_engine = create_async_engine(url, connect_args=connect_args, poolclass=NullPool)
    original = app.dependency_overrides.copy()
    try:
        async with test_engine.connect() as connection:
            transaction = await connection.begin()
            # PostgreSQL temp tables shadow the public names on this connection.
            # LIKE copies column/index checks, not foreign keys to real accounts.
            for table in (
                "admin_accounts", "admin_audit_logs", "admin_sessions",
                "admin_mfa_challenges", "admin_revoked_session_families",
            ):
                await connection.execute(text(
                    f"CREATE TEMP TABLE {table} (LIKE public.{table} INCLUDING ALL) ON COMMIT DROP",
                ))
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint",
            ) as session:
                async def override_session():
                    yield session
                    await session.flush()
                app.dependency_overrides[get_session] = override_session
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app), base_url="http://test",
                ) as client:
                    yield {"client": client, "session": session}
            await transaction.rollback()
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)
        limiter.reset()
        app.state.limiter.reset()
        await test_engine.dispose()


async def signup(d, **changes):
    return await d["client"].post(BASE + "/sign-up", headers={"X-Admin-Setup-Key": KEY}, json={
        "email": "First.Admin@EXAMPLE.com", "name": " First admin ", "password": PASSWORD, **changes,
    })


async def test_signup_hash_audit_and_required_mfa_journey(isolated_signup, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)
    d = isolated_signup
    response = await signup(d)
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    result = response.json()["data"]
    assert result["email"] == "first.admin@example.com" and result["name"] == "First admin"
    assert result["role_ids"] == ["role_ceo"] and result["mfa_required"] is True
    assert result["next_step"] == "SIGN_IN_AND_COMPLETE_MFA"
    assert all(secret not in response.text for secret in (KEY, PASSWORD, "password_hash", "access_token", "refresh_token"))
    account = (await d["session"].execute(select(AdminAccount))).scalar_one()
    assert account.garage_scope is None and verify_admin_password(PASSWORD, account.password_hash)
    event = (await d["session"].execute(select(AdminAuditLog))).scalar_one()
    assert event.admin_account_id == account.id and event.action == "account.first_admin_signup"
    assert KEY not in str(event.details) and PASSWORD not in str(event.details)
    assert not (await d["session"].execute(select(AdminSession))).scalars().all()
    login = await d["client"].post(BASE + "/sign-in", json={
        "email": result["email"], "password": PASSWORD,
    })
    assert login.status_code == 200
    challenge = login.json()["data"]
    assert challenge["mfa_required"] and challenge["enrollment_required"]
    assert "access_token" not in challenge
    factor = parse_qs(urlparse(challenge["provisioning_uri"]).query)["secret"][0]
    proof = await d["client"].post(BASE + "/mfa", json={
        "challenge_id": challenge["challenge_id"], "code": totp(factor),
    })
    assert proof.status_code == 200, proof.text
    token = proof.json()["data"]["access_token"]
    me = await d["client"].get("/api/v1/admin/me", headers={"Authorization": "Bearer " + token})
    assert me.status_code == 200
    assert "admin-auth" not in str(app.openapi()["paths"])


async def test_signup_and_sign_in_work_without_mfa_by_default(isolated_signup):
    d = isolated_signup
    response = await signup(d)
    assert response.status_code == 201, response.text
    result = response.json()["data"]
    assert result["mfa_required"] is False
    assert result["next_step"] == "SIGN_IN"
    assert "Sign in with your password" in response.json()["message"]

    login = await d["client"].post(BASE + "/sign-in", json={
        "email": result["email"], "password": PASSWORD,
    })
    assert login.status_code == 200
    data = login.json()["data"]
    assert "access_token" in data and "refresh_token" in data
    assert "challenge_id" not in data and "provisioning_uri" not in data
    me = await d["client"].get(
        "/api/v1/admin/me",
        headers={"Authorization": "Bearer " + data["access_token"]},
    )
    assert me.status_code == 200


async def test_repeat_and_inactive_accounts_cannot_be_overwritten(isolated_signup):
    d = isolated_signup
    assert (await signup(d)).status_code == 201
    account = (await d["session"].execute(select(AdminAccount))).scalar_one()
    original_hash = account.password_hash
    for active in (True, False):
        account.is_active = active
        await d["session"].flush()
        response = await signup(d, email=f"another-{uuid4()}@example.com")
        assert response.status_code == 409
        assert response.headers["cache-control"] == "no-store"
        assert account.password_hash == original_hash
        assert len((await d["session"].execute(select(AdminAccount))).scalars().all()) == 1


async def test_guards_and_input_errors_do_not_create_accounts(isolated_signup, monkeypatch):
    d = isolated_signup
    for headers in ({}, {"X-Admin-Setup-Key": "incorrect-fixture-key-long-enough"}):
        response = await d["client"].post(BASE + "/sign-up", headers=headers, json={
            "email": "admin@example.com", "name": "Admin", "password": PASSWORD,
        })
        assert response.status_code == 403
        assert KEY not in response.text and PASSWORD not in response.text
        assert response.headers["cache-control"] == "no-store"
    assert (await signup(d, role_ids=["role_ceo"])).status_code == 422
    assert (await signup(d, password="too-short")).status_code == 422
    monkeypatch.setattr(settings, "ADMIN_SIGNUP_ENABLED", False)
    assert (await signup(d)).status_code == 404
    assert not (await d["session"].execute(select(AdminAccount))).scalars().all()


async def test_signup_attempts_are_rate_limited(isolated_signup):
    d = isolated_signup
    for _ in range(5):
        response = await d["client"].post(BASE + "/sign-up", json={
            "email": "admin@example.com", "name": "Admin", "password": PASSWORD,
        })
        assert response.status_code == 403
    response = await d["client"].post(BASE + "/sign-up", json={
        "email": "admin@example.com", "name": "Admin", "password": PASSWORD,
    })
    assert response.status_code == 429
    assert not (await d["session"].execute(select(AdminAccount))).scalars().all()
