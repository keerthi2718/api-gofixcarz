"""JWT and real SQL endpoint checks; fixtures always roll back; no SMS is sent."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.security import create_access_token, hash_refresh_token
from app.database.connection_url import build_async_url
from app.database.session import get_session
from app.main import app
from app.models.admin_audit_log import AdminAuditLog
from app.models.booking import Booking, BookingStatus
from app.models.garage import Garage
from app.models.job import Job, JobStatus
from app.models.refresh_token import RefreshToken
from app.models.user import User


ADMIN_PATHS = [
    "/me", "/menus", "/dashboard", "/users", f"/users/{uuid4()}",
    "/garages", f"/garages/{uuid4()}", "/jobs", f"/jobs/{uuid4()}",
    "/bookings", "/analytics", "/billing/issues", "/audit-logs",
]


@pytest_asyncio.fixture
async def setup_admin_api():
    url, connect_args = build_async_url(settings.DATABASE_URL)
    # These tests may only write throwaway rows in the internal development DB.
    from sqlalchemy.engine import make_url
    assert make_url(url).host == "helium"
    test_engine = create_async_engine(url, connect_args=connect_args, poolclass=NullPool)
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(bind=connection, expire_on_commit=False) as session:
            def user(role):
                return User(
                    id=uuid4(), mobile=str(uuid4().int % 10**10).zfill(10),
                    name="Admin regression fixture", is_active=True, role=role,
                    otp="123456", otp_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                )
            admin, owner, other_owner = user("admin"), user("garage_owner"), user("garage_owner")
            session.add_all([admin, owner, other_owner])
            await session.flush()
            garage = Garage(id=uuid4(), user_id=owner.id, name="Admin test A", owner="Fixture A")
            other_garage = Garage(id=uuid4(), user_id=other_owner.id, name="Admin test B", owner="Fixture B")
            session.add_all([garage, other_garage])
            await session.flush()
            billing = {
                "services_total": "100.00", "labour_total": "0.00", "subtotal": "100.00",
                "gst_amount": "18.00", "grand_total": "118.00",
            }
            completed = Job(
                id=uuid4(), garage_id=garage.id, job_number="ADMIN-FIXTURE-1",
                status=JobStatus.COMPLETED, final_amount=118, billing=billing,
                completed_at=datetime.now(timezone.utc),
            )
            missing = Job(
                id=uuid4(), garage_id=other_garage.id, job_number="ADMIN-FIXTURE-2",
                status=JobStatus.COMPLETED,
            )
            json_null_bill = Job(
                id=uuid4(), garage_id=other_garage.id, job_number="ADMIN-FIXTURE-3",
                status=JobStatus.COMPLETED, final_amount=0, billing=None,
                completed_at=datetime.now(timezone.utc),
            )
            ready = Job(id=uuid4(), garage_id=garage.id, job_number="ADMIN-FIXTURE-4", status=JobStatus.READY)
            booking = Booking(id=uuid4(), garage_id=garage.id, status=BookingStatus.PENDING)
            refresh = RefreshToken(
                id=uuid4(), user_id=owner.id, token_hash=hash_refresh_token("fixture-refresh"),
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                created_at=datetime.now(timezone.utc),
            )
            session.add_all([completed, missing, ready, json_null_bill, booking, refresh])
            await session.flush()

            async def override_session():
                async with session.begin_nested():
                    yield session
                    await session.flush()

            original = app.dependency_overrides.copy()
            app.dependency_overrides[get_session] = override_session
            transport = httpx.ASGITransport(app=app)
            try:
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    yield {
                        "client": client, "session": session, "admin": admin, "owner": owner,
                        "garage": garage, "other_garage": other_garage, "completed": completed,
                        "missing": missing, "ready": ready, "booking": booking, "refresh": refresh,
                        "json_null_bill": json_null_bill,
                    }
            finally:
                app.dependency_overrides.clear()
                app.dependency_overrides.update(original)
        await transaction.rollback()
    await test_engine.dispose()


def headers(user, role=None):
    return {"Authorization": f"Bearer {create_access_token(user.id, role=role or user.role)}"}


async def test_every_admin_route_is_guarded(setup_admin_api):
    data = setup_admin_api
    client = data["client"]
    for path in ADMIN_PATHS:
        response = await client.get("/api/v1/admin" + path)
        assert response.status_code == 401, (path, response.text)
        response = await client.get("/api/v1/admin" + path, headers=headers(data["owner"], role="admin"))
        assert response.status_code == 403, (path, response.text)
    for auth_headers, expected in [({}, 401), (headers(data["owner"]), 403)]:
        response = await client.patch(
            f"/api/v1/admin/users/{data['owner'].id}/status",
            headers=auth_headers, json={"is_active": False},
        )
        assert response.status_code == expected


async def test_admin_without_garage_can_read_all_dashboard_apis(setup_admin_api):
    d = setup_admin_api
    paths = [
        "/me", "/menus", "/dashboard", "/users", f"/users/{d['owner'].id}",
        "/garages", f"/garages/{d['garage'].id}", "/jobs", f"/jobs/{d['completed'].id}",
        "/bookings", "/analytics", "/billing/issues", "/audit-logs",
    ]
    for path in paths:
        response = await d["client"].get("/api/v1/admin" + path, headers=headers(d["admin"]))
        assert response.status_code == 200, (path, response.text)
        assert response.json()["success"] is True
        text = response.text
        assert '"otp"' not in text
        assert '"token_hash"' not in text
    logs = (await d["session"].execute(
        select(AdminAuditLog).where(AdminAuditLog.actor_id == d["admin"].id)
    )).scalars().all()
    assert len(logs) == len(paths)


async def test_cross_garage_filters_pagination_and_billing_review(setup_admin_api):
    d = setup_admin_api
    auth = headers(d["admin"])
    for garage, expected in [(d["garage"], 2), (d["other_garage"], 2)]:
        response = await d["client"].get(
            "/api/v1/admin/jobs", params={"garage_id": str(garage.id), "page_size": 1}, headers=auth,
        )
        result = response.json()["data"]
        assert result["total"] == expected
        assert result["pages"] == 2
        assert len(result["items"]) == 1
        assert result["items"][0]["garage_id"] == str(garage.id)
    response = await d["client"].get(
        "/api/v1/admin/billing/issues", params={"garage_id": str(d["other_garage"].id)}, headers=auth,
    )
    result = response.json()["data"]
    assert result["total"] == 2
    assert {r["id"] for r in result["items"]} == {str(d["missing"].id), str(d["json_null_bill"].id)}
    # Reviews must not turn unknown bills into zero or fabricate completion dates.
    assert d["missing"].final_amount is None
    assert d["missing"].completed_at is None


async def test_owner_endpoints_stay_tenant_scoped(setup_admin_api):
    d = setup_admin_api
    response = await d["client"].get(
        f"/api/v1/jobs/{d['missing'].id}", headers=headers(d["owner"]),
    )
    assert response.status_code == 404
    response = await d["client"].get("/api/v1/jobs", headers=headers(d["owner"]))
    assert response.status_code == 200
    assert all(r["garage_id"] == str(d["garage"].id) for r in response.json()["data"]["items"])


async def test_user_deactivation_revokes_tokens_and_is_audited(setup_admin_api):
    d = setup_admin_api
    old_token = headers(d["owner"])
    response = await d["client"].patch(
        f"/api/v1/admin/users/{d['owner'].id}/status",
        headers=headers(d["admin"]), json={"is_active": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["is_active"] is False
    assert d["owner"].otp is None
    await d["session"].refresh(d["refresh"])
    assert d["refresh"].revoked_at is not None
    assert (await d["client"].get("/api/v1/profile", headers=old_token)).status_code == 401
    assert (await d["client"].post(
        "/api/v1/auth/refresh", json={"refresh_token": "fixture-refresh"},
    )).status_code == 401
    audit = (await d["session"].execute(select(AdminAuditLog).where(
        AdminAuditLog.actor_id == d["admin"].id, AdminAuditLog.action == "users.status",
    ))).scalar_one()
    assert audit.details == {"previous_is_active": True, "is_active": False}
    response = await d["client"].patch(
        f"/api/v1/admin/users/{d['owner'].id}/status",
        headers=headers(d["admin"]), json={"is_active": True},
    )
    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is True


async def test_admin_deactivation_and_role_injection_are_denied(setup_admin_api):
    d = setup_admin_api
    for body, expected in [
        ({"is_active": False}, 400), ({"is_active": True, "role": "admin"}, 422),
    ]:
        response = await d["client"].patch(
            f"/api/v1/admin/users/{d['admin'].id}/status",
            headers=headers(d["admin"]), json=body,
        )
        assert response.status_code == expected, response.text


async def test_role_removal_immediately_denies_old_admin_jwt(setup_admin_api):
    d = setup_admin_api
    auth = headers(d["admin"])
    d["admin"].role = "garage_owner"
    await d["session"].flush()
    response = await d["client"].get("/api/v1/admin/dashboard", headers=auth)
    assert response.status_code == 403


async def test_otp_login_and_refresh_return_admin_role(setup_admin_api):
    d = setup_admin_api
    response = await d["client"].post(
        "/api/v1/auth/verify-otp", json={"mobile": d["admin"].mobile, "otp": "123456"},
    )
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["user"]["role"] == "admin"
    auth = {"Authorization": "Bearer " + result["access_token"]}
    assert (await d["client"].get("/api/v1/admin/me", headers=auth)).status_code == 200
    response = await d["client"].post(
        "/api/v1/auth/refresh", json={"refresh_token": result["refresh_token"]},
    )
    assert response.status_code == 200
    assert response.json()["data"]["user"]["role"] == "admin"


async def test_analytics_keeps_revenue_and_job_dates_distinct(setup_admin_api):
    d = setup_admin_api
    d["completed"].created_at = datetime.now(timezone.utc) - timedelta(days=30)
    await d["session"].flush()
    today = datetime.now(timezone.utc).date().isoformat()
    response = await d["client"].get(
        "/api/v1/admin/analytics", headers=headers(d["admin"]),
        params={"garage_id": str(d["garage"].id), "period": "custom",
                "start_date": today, "end_date": today},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["total_jobs"] == 1
    assert data["total_revenue"] == 118.0
    assert data["status_counts"]["READY"] == 1
    assert data["graph_data"][0]["completed_count"] == 1


async def test_validation_and_missing_records(setup_admin_api):
    d = setup_admin_api
    for path, expected in [
        ("/jobs?page_size=101", 422),
        ("/jobs?status=INVALID", 422),
        ("/jobs?date_from=2026-10-05&date_to=2026-10-01", 400),
        ("/analytics?period=custom", 400),
        ("/analytics?period=invalid", 422),
        (f"/users/{uuid4()}", 404),
        (f"/garages/{uuid4()}", 404),
        (f"/jobs/{uuid4()}", 404),
    ]:
        response = await d["client"].get("/api/v1/admin" + path, headers=headers(d["admin"]))
        assert response.status_code == expected, response.text
