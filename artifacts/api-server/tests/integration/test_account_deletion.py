"""Account archival is authenticated, owner-only, transactional and non-destructive."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.security import hash_refresh_token
from app.models.admin_audit_log import AdminAuditLog
from app.models.booking import Booking
from app.models.garage import Garage
from app.models.job import Job
from app.models.refresh_token import RefreshToken
from app.models.user import User
from tests.integration.test_admin import headers, setup_admin_api  # noqa: F401


async def test_account_archival_requires_auth(setup_admin_api):
    d = setup_admin_api
    response = await d["client"].request("DELETE", "/api/v1/auth/account", json={"confirm": True})
    assert response.status_code == 401
    assert d["owner"].deleted_at is None


@pytest.mark.parametrize("payload", [
    {}, {"confirm": False}, {"confirm": "true"}, {"confirm": 1},
    {"confirm": True, "account_id": str(uuid4())},
    {"confirm": True, "account_status": "ACTIVE"},
])
async def test_account_archival_requires_strict_confirmation(setup_admin_api, payload):
    d = setup_admin_api
    response = await d["client"].request(
        "DELETE", "/api/v1/auth/account", json=payload, headers=headers(d["owner"]),
    )
    assert response.status_code == 422
    assert d["owner"].is_active
    assert d["owner"].deleted_at is None


async def test_admin_cannot_use_owner_archival(setup_admin_api):
    d = setup_admin_api
    response = await d["client"].request(
        "DELETE", "/api/v1/auth/account", json={"confirm": True}, headers=headers(d["admin"]),
    )
    assert response.status_code == 403
    assert d["admin"].is_active
    assert d["admin"].deleted_at is None


async def test_owner_archival_revokes_all_sessions_and_preserves_history(setup_admin_api):
    d = setup_admin_api
    session = d["session"]
    owner = d["owner"]
    owner_headers = headers(owner)
    owner.email = f"deleted-{owner.id}@fixture.com"
    await session.flush()
    original = {"name": owner.name, "mobile": owner.mobile, "email": owner.email}
    now = datetime.now(timezone.utc)
    extra = RefreshToken(
        id=uuid4(), user_id=owner.id, token_hash=hash_refresh_token(str(uuid4())),
        expires_at=now+timedelta(days=1), created_at=now,
    )
    other = RefreshToken(
        id=uuid4(), user_id=d["other_garage"].user_id, token_hash=hash_refresh_token(str(uuid4())),
        expires_at=now+timedelta(days=1), created_at=now,
    )
    session.add_all([extra, other])
    await session.flush()
    response = await d["client"].request(
        "DELETE", "/api/v1/auth/account", json={"confirm": True}, headers=owner_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["account_id"] == str(owner.id)
    assert data["account_status"] == "DELETED"
    assert data["is_active"] is False
    assert data["sessions_revoked"] is True
    assert data["data_retained"] is True
    assert data["deleted_at"]
    await session.refresh(owner)
    assert not owner.is_active
    assert owner.deleted_at is not None
    assert owner.otp is None and owner.otp_expires_at is None
    assert {k:getattr(owner,k) for k in original} == original
    for token in [d["refresh"], extra]:
        await session.refresh(token)
        assert token.revoked_at is not None
    await session.refresh(other)
    assert other.revoked_at is None
    for cls, record in [(User,owner),(Garage,d["garage"]),(Job,d["completed"]),(Booking,d["booking"])]:
        assert await session.get(cls, record.id) is not None
    await session.refresh(d["completed"])
    assert d["completed"].billing["grand_total"] == "118.00"
    assert d["garage"].deleted_at is None
    for path in ["/api/v1/profile","/api/v1/garage","/api/v1/jobs"]:
        assert (await d["client"].get(path, headers=owner_headers)).status_code == 401
    assert (await d["client"].post(
        "/api/v1/auth/refresh", json={"refresh_token":"fixture-refresh"},
    )).status_code == 401
    for path in ["/api/v1/auth/sign-in","/api/v1/auth/send-otp"]:
        response = await d["client"].post(path, json={"mobile": original["mobile"]})
        assert response.status_code == 410
        assert response.json()["error_code"] == "ACCOUNT_DELETED"
        assert "deleted" in response.json()["message"].lower()
    verify_response = await d["client"].post(
        "/api/v1/auth/verify-otp",json={"mobile":original["mobile"],"otp":"123456"},
    )
    assert verify_response.status_code == 410
    assert verify_response.json()["error_code"] == "ACCOUNT_DELETED"
    signup_by_mobile = await d["client"].post("/api/v1/auth/sign-up", json={
        "first_name": "Test", "workshop_name": "Retry Garage",
        "email": f"retry_{uuid4().hex}@example.com", "country_code": owner.country_code,
        "mobile": original["mobile"], "terms_accepted": True,
    })
    signup_by_email = await d["client"].post("/api/v1/auth/sign-up", json={
        "first_name": "Test", "workshop_name": "Retry Garage",
        "email": original["email"], "country_code": "91",
        "mobile": str(uuid4().int % 10**10).zfill(10), "terms_accepted": True,
    })
    for response in (signup_by_mobile, signup_by_email):
        assert response.status_code == 410
        assert response.json()["error_code"] == "ACCOUNT_DELETED"
        assert "deleted" in response.json()["message"].lower()
    assert (await d["client"].request(
        "DELETE","/api/v1/auth/account",json={"confirm":True},headers=owner_headers,
    )).status_code == 401
    audit = (await session.execute(select(AdminAuditLog).where(
        AdminAuditLog.action=="users.account_deleted",AdminAuditLog.resource_id==owner.id,
    ))).scalar_one()
    assert audit.actor_id == owner.id
    assert audit.details == {"account_status":"DELETED","data_retained":True}
    # Defaults exclude archives; only administrators may request retained history.
    admin_headers = headers(d["admin"])
    assert (await d["client"].get(f"/api/v1/admin/users/{owner.id}",headers=admin_headers)).status_code == 404
    detail = await d["client"].get(
        f"/api/v1/admin/users/{owner.id}?include_deleted=true",headers=admin_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["data"]["account_status"] == "DELETED"
    assert detail.json()["data"]["mobile"] == original["mobile"]
    default_list = (await d["client"].get("/api/v1/admin/users",headers=admin_headers)).json()["data"]["items"]
    assert str(owner.id) not in {item["id"] for item in default_list}
    retained = await d["client"].get(
        "/api/v1/admin/users?include_deleted=true&is_active=false",headers=admin_headers,
    )
    assert retained.status_code == 200
    assert any(item["id"]==str(owner.id) and item["account_status"]=="DELETED"
               for item in retained.json()["data"]["items"])
    assert (await d["client"].patch(
        f"/api/v1/admin/users/{owner.id}/status",headers=admin_headers,json={"is_active":True},
    )).status_code == 404


async def test_failed_archival_rolls_back_flags_tokens_and_audit(setup_admin_api, monkeypatch):
    from app.repositories.refresh_token_repository import RefreshTokenRepository
    d = setup_admin_api

    async def fail_revoke(self, user_id):
        raise RuntimeError("simulated failure before archive commit")

    monkeypatch.setattr(RefreshTokenRepository, "revoke_all_for_user", fail_revoke)
    # HTTP transport raises server exceptions; savepoint must roll back every change.
    with pytest.raises(RuntimeError, match="simulated failure"):
        await d["client"].request(
            "DELETE","/api/v1/auth/account",json={"confirm":True},headers=headers(d["owner"]),
        )
    await d["session"].refresh(d["owner"])
    await d["session"].refresh(d["refresh"])
    assert d["owner"].is_active and d["owner"].deleted_at is None
    assert d["owner"].otp == "123456"
    assert d["refresh"].revoked_at is None
    audit = (await d["session"].execute(select(AdminAuditLog).where(
        AdminAuditLog.action=="users.account_deleted",AdminAuditLog.resource_id==d["owner"].id,
    ))).scalar_one_or_none()
    assert audit is None
