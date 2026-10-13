"""Dedicated auth journeys against real SQL, rolled back without SMS."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest_asyncio
from jose import jwt
from sqlalchemy import select

from app.core.admin_security import AUDIENCE, ISSUER, hash_admin_password
from app.core.config import settings
from app.models.admin_account import AdminAccount, AdminSession
from app.models.admin_audit_log import AdminAuditLog
from app.services.admin_auth_service import AdminAuthService
from tests.integration.test_admin import setup_admin_api, ADMIN_PATHS

# Test-only credential; never the real admin's password.
PASSWORD = "test-only-password-long-enough"
PRIVATE_BASE = "/api/v1/admin-auth"


@pytest_asyncio.fixture
async def dedicated(setup_admin_api, monkeypatch):
    from app.api.v1.admin_auth import limiter
    limiter.reset()
    monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)
    d = setup_admin_api
    account = AdminAccount(
        id=uuid4(), email=f"admin-{uuid4()}@fixture.com", name="Dedicated fixture",
        password_hash=hash_admin_password(PASSWORD),
        role_ids=["role_ceo"],
    )
    d["session"].add(account)
    await d["session"].flush()
    d["account"] = account
    yield d
    limiter.reset()


async def login(d):
    r = await d["client"].post(PRIVATE_BASE + "/sign-in", json={
        "email": d["account"].email.upper(), "password": PASSWORD,
    })
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert PASSWORD not in r.text and "password_hash" not in r.text
    data = r.json()["data"]
    assert data["mfa_required"] and "access_token" not in data
    from urllib.parse import urlparse, parse_qs
    from app.core.admin_totp import decrypt_secret, totp
    secret = (parse_qs(urlparse(data["provisioning_uri"]).query)["secret"][0] if data["enrollment_required"]
              else decrypt_secret(d["account"].mfa_secret_encrypted))
    proof = await d["client"].post(PRIVATE_BASE + "/mfa", json={
        "challenge_id": data["challenge_id"], "code": totp(secret),
    })
    assert proof.status_code == 200
    return proof.json()["data"]


def bearer(token):
    return {"Authorization": "Bearer " + token}


async def test_password_only_login_when_mfa_is_optional(dedicated, monkeypatch):
    d = dedicated
    monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", False)
    response = await d["client"].post(PRIVATE_BASE + "/sign-in", json={
        "email": d["account"].email, "password": PASSWORD,
    })
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()["data"]
    assert "access_token" in data and "refresh_token" in data
    assert "challenge_id" not in data and "provisioning_uri" not in data
    menus = await d["client"].get(
        "/api/v1/admin/menus", headers=bearer(data["access_token"]),
    )
    assert menus.status_code == 200


async def test_dedicated_login_all_menus_and_dashboard_access(dedicated):
    d = dedicated
    data = await login(d)
    claims = jwt.decode(data["access_token"], settings.SECRET_KEY,
                        algorithms=[settings.ALGORITHM], audience=AUDIENCE, issuer=ISSUER)
    assert claims["type"] == "admin_access"
    assert data["expires_in"] == 900
    paths = ["/me", "/menus", "/dashboard", "/users", f"/users/{d['owner'].id}",
             "/garages", f"/garages/{d['garage'].id}", "/jobs", f"/jobs/{d['completed'].id}",
             "/bookings", "/analytics", "/billing/issues", "/audit-logs"]
    for path in paths:
        r = await d["client"].get("/api/v1/admin" + path, headers=bearer(data["access_token"]))
        assert r.status_code == 200
        assert "password_hash" not in r.text and "refresh_token_hash" not in r.text
    menus = await d["client"].get("/api/v1/admin/menus", headers=bearer(data["access_token"]))
    assert len(menus.json()["data"]["menus"]) == 15
    assert (await d["client"].get("/api/v1/profile", headers=bearer(data["access_token"]))).status_code == 401
    logs = (await d["session"].execute(select(AdminAuditLog).where(
        AdminAuditLog.admin_account_id == d["account"].id,
    ))).scalars().all()
    assert logs and all(entry.actor_id is None for entry in logs)
    assert all(PASSWORD not in str(entry.details) for entry in logs)


async def test_refresh_rotation_logout_and_replay_denial(dedicated):
    d = dedicated
    original = await login(d)
    r = await d["client"].post(PRIVATE_BASE + "/refresh",
                              json={"refresh_token": original["refresh_token"]})
    assert r.status_code == 200
    rotated = r.json()["data"]
    assert rotated["refresh_token"] != original["refresh_token"]
    assert (await d["client"].get("/api/v1/admin/menus",
            headers=bearer(original["access_token"]))).status_code == 401
    assert (await d["client"].post(PRIVATE_BASE + "/refresh",
            json={"refresh_token": original["refresh_token"]})).status_code == 401
    # Replay revokes the whole family, including the rotated successor.
    assert (await d["client"].post(PRIVATE_BASE + "/logout",
            headers=bearer(rotated["access_token"]))).status_code == 401
    assert (await d["client"].get("/api/v1/admin/menus",
            headers=bearer(rotated["access_token"]))).status_code == 401
    assert (await d["client"].post(PRIVATE_BASE + "/refresh",
            json={"refresh_token": rotated["refresh_token"]})).status_code == 401


async def test_lockout_and_generic_errors(dedicated):
    d = dedicated
    service = AdminAuthService(d["session"])
    for _ in range(5):
        assert await service.login(d["account"].email, "wrong") is None
    assert d["account"].failed_attempts == 5
    assert d["account"].locked_until > datetime.now(timezone.utc)
    assert await service.login(d["account"].email, PASSWORD) is None
    known = await d["client"].post(PRIVATE_BASE + "/sign-in",
                                 json={"email": d["account"].email, "password": PASSWORD})
    unknown = await d["client"].post(PRIVATE_BASE + "/sign-in",
                                   json={"email": "missing@fixture.com", "password": PASSWORD})
    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json()
    d["account"].locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert await service.login(d["account"].email, PASSWORD)
    assert d["account"].failed_attempts == 0


async def test_disabled_rotated_credentials_expiry_and_forgery(dedicated):
    d = dedicated
    data = await login(d)
    auth = bearer(data["access_token"])
    d["account"].is_active = False
    assert (await d["client"].get("/api/v1/admin/menus", headers=auth)).status_code == 401
    assert (await d["client"].post(PRIVATE_BASE + "/refresh",
            json={"refresh_token": data["refresh_token"]})).status_code == 401
    d["account"].is_active = True
    d["account"].credential_version += 1
    assert (await d["client"].get("/api/v1/admin/menus", headers=auth)).status_code == 401
    d["account"].credential_version -= 1
    claims = jwt.decode(data["access_token"], settings.SECRET_KEY,
                        algorithms=[settings.ALGORITHM], audience=AUDIENCE, issuer=ISSUER)
    for override in [
        {"exp": 1}, {"aud": "garage-owner"}, {"iss": "untrusted"},
        {"type": "access"}, {"sid": 123}, {"sid": "invalid"},
        {"ver": 999}, {"sub": str(uuid4())},
    ]:
        token = jwt.encode({**claims, **override}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        assert (await d["client"].get("/api/v1/admin/menus", headers=bearer(token))).status_code == 401
    forged = jwt.encode(claims, "not-the-signing-key", algorithm=settings.ALGORITHM)
    for path in ADMIN_PATHS:
        assert (await d["client"].get("/api/v1/admin" + path, headers=bearer(forged))).status_code == 401
    session = (await d["session"].execute(select(AdminSession).where(
        AdminSession.admin_account_id == d["account"].id,
    ))).scalar_one()
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert (await d["client"].get("/api/v1/admin/menus", headers=auth)).status_code == 401


async def test_ip_throttle_and_private_auth_not_in_public_schema(dedicated):
    d = dedicated
    for _ in range(5):
        assert (await d["client"].post(PRIVATE_BASE + "/sign-in",
            json={"email": "missing@fixture.com", "password": "bad"})).status_code == 401
    assert (await d["client"].post(PRIVATE_BASE + "/sign-in",
        json={"email": "missing@fixture.com", "password": "bad"})).status_code == 429
    r = await d["client"].get("/api/openapi.json")
    assert r.status_code == 200
    assert all(PRIVATE_BASE not in path for path in r.json()["paths"])
    assert "/api/v1/admin/menus" in r.json()["paths"]
