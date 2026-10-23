"""Rollback-only checks: permissions, actual aggregates and proof lifecycles."""
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from sqlalchemy import select
from app.core.config import settings
from app.core.admin_security import hash_admin_password
from app.models.admin_account import AdminAccount
from app.models.admin_operations import AdminResource
from app.models.job import Job, JobStatus
from app.services.admin_auth_service import AdminAuthService
from tests.integration.test_admin_remaining import suite, setup_admin_api, BASE

EXAMPLES = {}


def sanitized(value):
    if isinstance(value, dict):
        return {k: ("<one_time_invitation_token>" if k == "invitation_token" else
                    "<chosen_strong_password>" if k == "password" else sanitized(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitized(v) for v in value]
    return value


async def call(d, method, path, body=None, **kwargs):
    response = await d["client"].request(method, BASE + path, headers=d["auth"], json=body, **kwargs)
    key = method + " " + path
    EXAMPLES.setdefault(key, []).append({"request": sanitized(body), "query": kwargs.get("params", {}),
                                        "status": response.status_code, "response": sanitized(response.json())})
    return response


@pytest.fixture(scope="module", autouse=True)
def save_examples():
    yield
    if path := os.environ.get("ADMIN_MANAGEMENT_EXAMPLES"):
        Path(path).write_text(json.dumps(EXAMPLES, indent=2))


async def test_metrics_count_and_paginated_inventory(suite):
    d = suite
    garage = str(d["garage"].id)
    metric = await call(d, "GET", f"/garages/{garage}/metrics")
    assert metric.status_code == 200, metric.text
    assert metric.json()["data"]["job_card_count"] == 2
    assert metric.json()["data"]["status_counts"]["COMPLETED"] == 1
    assert metric.json()["data"]["booking_count"] == 1
    count = await call(d, "GET", f"/garages/{garage}/job-card-count", params={"status": "READY"})
    assert count.json()["data"]["job_card_count"] == 1
    listing = await call(d, "GET", "/garages", params={"user_id": str(d["owner"].id)})
    assert listing.status_code == 200, listing.text
    assert listing.json()["data"]["items"][0]["job_card_count"] == 2
    removed = Job(garage_id=d["garage"].id, job_number="DELETED", status=JobStatus.OPEN,
                  deleted_at=datetime.now(timezone.utc))
    d["session"].add(removed)
    await d["session"].flush()
    assert (await call(d, "GET", f"/garages/{garage}/metrics")).json()["data"]["job_card_count"] == 2
    assert (await call(d, "GET", f"/garages/{uuid4()}/metrics")).status_code == 404


async def test_filtered_report_and_existing_details(suite):
    d = suite
    report = await call(d, "GET", "/reports/garage-performance", params={
        "garage_id": str(d["garage"].id), "status": "COMPLETED",
        "date_from": (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat(),
        "date_to": datetime.now(timezone.utc).date().isoformat(), "timezone": "Asia/Kolkata"})
    assert report.status_code == 200, report.text
    assert report.json()["data"]["items"][0]["job_card_count"] == 1
    assert report.json()["data"]["total"] == 1
    for params in [{"status": "FAKE"}, {"timezone": "No/Where"}, {"unknown": "filter"}]:
        assert (await call(d, "GET", "/reports/garage-performance", params=params)).status_code == 422
    assert (await call(d, "GET", "/reports/garage-performance", params={
        "date_from": "2026-12-01", "date_to": "2026-01-01"})).status_code == 400
    details = await call(d, "GET", f"/jobs/{d['completed'].id}")
    assert details.status_code == 200
    support = await call(d, "GET", "/support-tickets", params={"garage_id": str(d["garage"].id)})
    canonical = await call(d, "GET", "/support/tickets", params={"garage_id": str(d["garage"].id)})
    assert support.status_code == canonical.status_code == 200
    assert support.json()["data"] == canonical.json()["data"]
    assert (await call(d, "GET", "/notifications")).status_code == 200


async def test_general_garage_patch_atomic_version_and_validation(suite):
    d = suite
    path = f"/garages/{d['garage'].id}"
    body = {"name": "Updated fixture garage", "city": "Pune", "operational_status": "SUSPENDED",
            "verification_status": "VERIFIED", "reason": "Documents checked", "expected_version": 1}
    result = await call(d, "PATCH", path, body)
    assert result.status_code == 200, result.text
    assert result.json()["data"]["name"] == body["name"]
    assert result.json()["data"]["version"] == 2
    assert result.json()["data"]["operational_status"] == "SUSPENDED"
    listing = await call(d, "GET", "/garages", params={"user_id": str(d["owner"].id)})
    assert listing.json()["data"]["items"][0]["version"] == 2
    detail = await call(d, "GET", path)
    assert detail.json()["data"]["version"] == 2
    assert (await call(d, "PATCH", path, body)).status_code == 409
    for extra in [{"user_id": str(uuid4())}, {"name": None}, {"name": "  "}, {"latitude": 95}]:
        invalid = {"reason": "Invalid change", "expected_version": 2, **extra}
        assert (await call(d, "PATCH", path, invalid)).status_code == 422
    assert (await call(d, "PATCH", path, {"reason": "Empty", "expected_version": 2})).status_code == 422


async def make_role(d, name=None, permissions=None):
    r = await call(d, "POST", "/roles", {"name": name or "Custom " + uuid4().hex,
                   "permissions": permissions or ["garages.read"], "reason": "Delegate garage review"})
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def invitation(d, roles=None):
    r = await call(d, "POST", "/invitations", {
        "email": f"invite-{uuid4().hex}@example.com", "name": "Invited Test Admin",
        "role_ids": roles or ["role_support"], "data_scope": {"type": "PLATFORM"},
        "reason": "Approved staff invitation"})
    assert r.status_code == 201, r.text
    assert len(r.json()["data"]["invitation_token"]) >= 40
    assert r.headers["cache-control"] == "no-store"
    return r.json()["data"]


async def test_custom_roles_live_permissions_assignment_and_delete_guard(suite):
    d = suite
    role = await make_role(d)
    assert role["is_system"] is False
    account = AdminAccount(id=uuid4(), email=f"role-{uuid4()}@example.test", name="Role fixture",
                           password_hash=hash_admin_password("long-fixture-password"), role_ids=["role_support"])
    d["session"].add(account)
    await d["session"].flush()
    assign = await call(d, "PUT", f"/staff/{account.id}/roles", {
        "role_ids": [role["id"]], "data_scope": {"type": "GARAGES", "garage_ids": [str(d["garage"].id)]},
        "reason": "Limit to assigned garage"})
    assert assign.status_code == 200, assign.text
    issued = await AdminAuthService(d["session"]).issue(account)
    auth = {"Authorization": "Bearer " + issued["access_token"]}
    own = await d["client"].get(BASE + f"/garages/{d['garage'].id}/metrics", headers=auth)
    assert own.status_code == 200
    assert (await d["client"].get(BASE + f"/garages/{d['other_garage'].id}/metrics", headers=auth)).status_code == 404
    assert (await d["client"].get(BASE + "/reports/garage-performance", headers=auth)).status_code == 403
    assert (await call(d, "DELETE", f"/roles/{role['id']}", {
        "expected_version": 1, "reason": "Cannot delete in-use role"})).status_code == 409
    changed = await call(d, "PATCH", f"/roles/{role['id']}", {
        "permissions": ["jobs.read"], "expected_version": 1, "reason": "Change scope of duties"})
    assert changed.status_code == 200
    assert (await d["client"].get(BASE + f"/garages/{d['garage'].id}/metrics", headers=auth)).status_code == 403
    me = await d["client"].get(BASE + "/me", headers=auth)
    assert me.json()["data"]["permissions"] == ["jobs.read"]


async def test_custom_role_errors_and_unused_deletion(suite):
    d = suite
    role = await make_role(d, "Unique custom fixture")
    duplicate = await call(d, "POST", "/roles", {"name": "unique custom fixture",
        "permissions": ["garages.read"], "reason": "Duplicate"})
    assert duplicate.status_code == 409
    for permissions in [["invented.permission"], ["garages.read", "garages.read"]]:
        r = await call(d, "POST", "/roles", {"name": "Invalid", "permissions": permissions, "reason": "Test"})
        assert r.status_code == 422
    assert (await call(d, "PATCH", "/roles/role_ceo", {
        "name": "Changed", "expected_version": 1, "reason": "Test"})).status_code == 409
    assert (await call(d, "PATCH", f"/roles/{role['id']}", {
        "name": "Changed", "expected_version": 9, "reason": "Stale"})).status_code == 409
    result = await call(d, "DELETE", f"/roles/{role['id']}", {"expected_version": 1, "reason": "No longer needed"})
    assert result.status_code == 200
    listing = (await call(d, "GET", "/roles")).json()["data"]["items"]
    assert not any(r["id"] == role["id"] for r in listing)


async def test_invite_acceptance_expiry_and_single_use(suite):
    d = suite
    invite = await invitation(d)
    stored = await d["session"].get(AdminResource, invite["id"])
    assert invite["invitation_token"] not in json.dumps(stored.payload)
    listed = await call(d, "GET", "/invitations", params={"status": "PENDING"})
    assert "invitation_token" not in listed.text and "proof_hash" not in listed.text
    payload = {"invitation_id": invite["id"], "invitation_token": invite["invitation_token"],
               "password": "fixture-only-strong-password"}
    wrong = await d["client"].post("/api/v1/admin-invitations/accept", json={**payload, "invitation_token": "x" * 64})
    assert wrong.status_code == 400
    accepted = await d["client"].post("/api/v1/admin-invitations/accept", json=payload)
    assert accepted.status_code == 201, accepted.text
    EXAMPLES["POST /admin-invitations/accept"] = [{
        "request": sanitized(payload), "status": accepted.status_code, "response": accepted.json()}]
    assert (await d["client"].post("/api/v1/admin-invitations/accept", json=payload)).status_code == 400
    account = await d["session"].get(AdminAccount, accepted.json()["data"]["account_id"])
    issued = await AdminAuthService(d["session"]).issue(account)
    assert issued["user"]["permissions"] and "security.manage" not in issued["user"]["permissions"]
    assert stored.status == "ACCEPTED"


async def test_invite_resend_revocation_and_pending_role_delete_guard(suite):
    d = suite
    role = await make_role(d)
    inv = await invitation(d, [role["id"]])
    path = f"/invitations/{inv['id']}"
    body = {"expected_version": 1, "reason": "New proof requested"}
    assert (await call(d, "POST", path + "/resend", body)).status_code == 429
    row = await d["session"].get(AdminResource, inv["id"])
    row.updated_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    await d["session"].flush()
    resent = await call(d, "POST", path + "/resend", body)
    assert resent.status_code == 200, resent.text
    assert resent.json()["data"]["invitation_token"] != inv["invitation_token"]
    assert (await call(d, "DELETE", f"/roles/{role['id']}", {
        "expected_version": 1, "reason": "In use"})).status_code == 409
    old = await d["client"].post("/api/v1/admin-invitations/accept", json={
        "invitation_id": inv["id"], "invitation_token": inv["invitation_token"],
        "password": "fixture-only-strong-password"})
    assert old.status_code == 400
    revoked = await call(d, "DELETE", path, {"expected_version": 2, "reason": "Invitation withdrawn"})
    assert revoked.status_code == 200 and revoked.json()["data"]["status"] == "REVOKED"
    assert (await call(d, "POST", path + "/resend", {
        "expected_version": 3, "reason": "Test"})).status_code == 409
    assert (await call(d, "DELETE", f"/roles/{role['id']}", {
        "expected_version": 1, "reason": "No longer used"})).status_code == 200


async def test_expired_proofs_and_invalid_invitation_grants(suite):
    d = suite
    inv = await invitation(d)
    row = await d["session"].get(AdminResource, inv["id"])
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await d["session"].flush()
    result = await d["client"].post("/api/v1/admin-invitations/accept", json={
        "invitation_id": inv["id"], "invitation_token": inv["invitation_token"],
        "password": "fixture-only-strong-password"})
    assert result.status_code == 400
    listing = (await call(d, "GET", "/invitations", params={"status": "EXPIRED"})).json()["data"]
    assert any(x["id"] == inv["id"] for x in listing["items"])
    bad = {"email": "bad-role@example.com", "name": "Invalid Test", "role_ids": ["missing-role"],
           "data_scope": {"type": "PLATFORM"}, "reason": "Test"}
    assert (await call(d, "POST", "/invitations", bad)).status_code == 422
    for roles in [["role_ceo"], ["role_support", "role_support"]]:
        assert (await call(d, "POST", "/invitations", {
            **bad, "role_ids": roles, "data_scope": {"type": "GARAGES", "garage_ids": [str(d["garage"].id)]}
        })).status_code == 422


async def test_security_mutations_require_platform_ceo_and_mfa(suite, monkeypatch):
    d = suite
    monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", True)
    old = await AdminAuthService(d["session"]).issue(d["account"], mfa_verified_at=datetime.now(timezone.utc)-timedelta(minutes=6))
    d["auth"] = {"Authorization": "Bearer " + old["access_token"]}
    response = await call(d, "POST", "/roles", {"name": "Forbidden", "permissions": ["garages.read"], "reason": "Test"})
    assert response.status_code == 403
    monkeypatch.setattr(settings, "ADMIN_MFA_REQUIRED", False)
    role = await make_role(d, permissions=["security.read", "security.manage"])
    delegate = AdminAccount(id=uuid4(), email=f"delegate-{uuid4()}@example.test", name="Delegate",
                            password_hash=hash_admin_password("fixture-only-strong-password"), role_ids=[role["id"]])
    d["session"].add(delegate)
    await d["session"].flush()
    issued = await AdminAuthService(d["session"]).issue(delegate)
    d["auth"] = {"Authorization": "Bearer " + issued["access_token"]}
    assert (await call(d, "POST", "/roles", {"name": "No escalation", "permissions": ["finance.read"], "reason": "Test"})).status_code == 403
    assert (await call(d, "GET", "/invitations")).status_code == 403


async def test_new_routes_require_real_admin_sessions(suite):
    d = suite
    for path in [f"/garages/{d['garage'].id}/metrics", f"/garages/{d['garage'].id}/job-card-count",
                 "/invitations", "/reports/garage-performance", "/support-tickets"]:
        assert (await d["client"].get(BASE+path)).status_code == 401


async def test_support_alias_mutations_and_existing_garage_actions(suite):
    d = suite
    ticket = f"/support-tickets/{d['ticket']}"
    assert (await call(d, "GET", ticket)).status_code == 200
    result = await call(d, "PATCH", ticket + "/assignment", {
        "assignee_id": str(d["account"].id), "reason": "Assign support", "expected_version": 1})
    assert result.status_code == 200
    assert (await call(d, "PATCH", ticket + "/priority", {
        "priority": "HIGH", "reason": "Escalate", "expected_version": 2})).status_code == 200
    assert (await call(d, "POST", ticket + "/messages", {
        "client_message_id": "alias-message-one", "text": "We are reviewing this request."})).status_code == 201
    assert (await call(d, "GET", ticket + "/messages")).status_code == 200
    assert (await call(d, "PATCH", ticket + "/status", {
        "status": "RESOLVED", "resolution": "Clarification sent", "expected_version": 3})).status_code == 200
    notifications = (await call(d, "GET", "/notifications")).json()["data"]["items"]
    assert notifications
    assert (await call(d, "GET", f"/notifications/{notifications[0]['id']}")).status_code == 200
    garage = f"/garages/{d['garage'].id}"
    assert (await call(d, "PATCH", garage + "/status", {
        "operational_status": "SUSPENDED", "reason": "Review", "expected_version": 1})).status_code == 200
    assert (await call(d, "PATCH", garage + "/verification", {
        "verification_status": "VERIFIED", "reason": "Documents checked", "expected_version": 2})).status_code == 200
