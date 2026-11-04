"""Read-only location triage through real SQL, JWTs, and rollback-only fixtures."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio

from app.core.admin_security import hash_admin_password
from app.models.admin_account import AdminAccount
from app.models.garage import Garage
from app.services.admin_auth_service import AdminAuthService
from tests.integration.test_admin import headers, setup_admin_api

BASE = "/api/v1/admin/garages"


@pytest_asyncio.fixture
async def locations(setup_admin_api):
    d = setup_admin_api
    account = AdminAccount(
        id=uuid4(), email=f"location-{uuid4()}@fixture.test", name="Location fixture",
        password_hash=hash_admin_password("fixture-only-long-password"), role_ids=["role_ceo"],
    )
    d["session"].add(account)
    city = "Location-" + str(uuid4())
    cases = [
        ("null", None, None, "MISSING"),
        ("lat-only", 18, None, "MISSING"),
        ("lng-only", None, 73, "MISSING"),
        ("partial-invalid", None, 181, "MISSING"),
        ("lat-high", "90.0000001", 73, "INVALID"),
        ("lat-low", "-90.0000001", 73, "INVALID"),
        ("lng-high", 18, "180.0000001", "INVALID"),
        ("lng-low", 18, "-180.0000001", "INVALID"),
        ("normal", 18, 73, "VALID"),
        ("zero", 0, 0, "VALID"),
        ("lower-bound", -90, -180, "VALID"),
        ("upper-bound", 90, 180, "VALID"),
    ]
    rows = []
    for name, lat, lng, status in cases:
        row = Garage(
            id=uuid4(), user_id=d["owner"].id, name=f"Pin {name}", owner="Pin fixture",
            city=city, latitude=None if lat is None else Decimal(str(lat)),
            longitude=None if lng is None else Decimal(str(lng)),
            verification_status="UNVERIFIED",
        )
        d["session"].add(row)
        rows.append((row, status))
    suspended = Garage(user_id=d["owner"].id, name="Pin suspended", owner="Pin fixture",
                       city=city, operational_status="SUSPENDED")
    deleted = Garage(user_id=d["owner"].id, name="Pin deleted", owner="Pin fixture",
                     city=city, deleted_at=datetime.now(timezone.utc))
    d["session"].add_all([suspended, deleted])
    await d["session"].flush()
    issued = await AdminAuthService(d["session"]).issue(account)
    d.update(location_rows=rows, city=city, account=account, suspended=suspended,
             auth={"Authorization": "Bearer " + issued["access_token"]})
    return d


async def test_location_filter_matrix_pagination_and_no_repairs(locations):
    d = locations
    base = {"city": d["city"], "operational_status": "ACTIVE",
            "verification_status": "UNVERIFIED", "user_id": str(d["owner"].id), "search": "Pin"}
    before = [(g.latitude, g.longitude, g.verification_status, g.operational_status,
               g.admin_version, g.updated_at) for g, _ in d["location_rows"]]
    for issue in [None, "true", "false"]:
        params = {**base, "page_size": 3}
        if issue is not None:
            params["location_issue"] = issue
        expected = {
            str(g.id): status for g, status in d["location_rows"]
            if issue is None or (status != "VALID") == (issue == "true")
        }
        found = {}
        for page in range(1, (len(expected) + 2) // 3 + 1):
            response = await d["client"].get(BASE, params={**params, "page": page}, headers=d["auth"])
            assert response.status_code == 200, response.text
            result = response.json()["data"]
            assert result["total"] == len(expected)
            assert result["pages"] == (len(expected) + 2) // 3
            for item in result["items"]:
                assert item["id"] not in found
                found[item["id"]] = item["location_status"]
                assert item["job_card_count"] == 0
        assert found == expected
    # No implicit ACTIVE restriction: suspended garages still appear unless filtered out.
    response = await d["client"].get(BASE, params={"city": d["city"], "location_issue": True},
                                    headers=d["auth"])
    assert response.json()["data"]["total"] == 9
    assert str(d["suspended"].id) in {g["id"] for g in response.json()["data"]["items"]}
    for g, _ in d["location_rows"]:
        await d["session"].refresh(g)
    assert before == [(g.latitude, g.longitude, g.verification_status, g.operational_status,
                       g.admin_version, g.updated_at) for g, _ in d["location_rows"]]
    empty = await d["client"].get(BASE, params={**base, "location_issue": True, "page": 100},
                                 headers=d["auth"])
    assert empty.json()["data"]["items"] == []
    assert empty.json()["data"]["total"] == 8


async def test_location_filter_validation_and_authorization(locations):
    d = locations
    for auth, expected in [({}, 401), (headers(d["owner"], role="admin"), 403)]:
        response = await d["client"].get(BASE, params={"location_issue": True}, headers=auth)
        assert response.status_code == expected, response.text
    for params in [{"location_issue": "invalid"}, {"location_issue": True, "page": 0},
                   {"location_issue": True, "page_size": 101}]:
        response = await d["client"].get(BASE, params=params, headers=d["auth"])
        assert response.status_code == 422, response.text


async def test_location_filter_respects_live_admin_scope_and_permissions(locations):
    d = locations
    visible = d["location_rows"][0][0]
    # Simulate a live role/scope assignment without exercising unrelated write APIs.
    d["account"].role_ids = ["role_support"]
    d["account"].garage_scope = [str(visible.id)]
    await d["session"].flush()
    for issue, total in [("true", 1), ("false", 0)]:
        response = await d["client"].get(BASE, params={"location_issue": issue}, headers=d["auth"])
        assert response.status_code == 200, response.text
        assert response.json()["data"]["total"] == total
        assert all(g["id"] == str(visible.id) for g in response.json()["data"]["items"])
    # The same token loses access as soon as its live role loses garages.read.
    d["account"].role_ids = []
    await d["session"].flush()
    response = await d["client"].get(BASE, params={"location_issue": True}, headers=d["auth"])
    assert response.status_code == 403, response.text
