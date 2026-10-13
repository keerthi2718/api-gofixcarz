"""All remaining route groups using rollback-isolated, authentic typed source fixtures."""
import io
import zipfile
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
import pytest_asyncio
from sqlalchemy import select
from app.core.config import settings
from app.core.admin_security import hash_admin_password
from app.models.admin_account import AdminAccount
from app.models.admin_operations import SourceRecord, AdminResource
from app.models.job import JobStatus
from app.schemas.admin_operations import SourceBatch
from app.services.admin_auth_service import AdminAuthService
from app.services.admin_source_import import import_sources
from app.services.admin_export_service import AdminExportService
from tests.integration.test_admin import setup_admin_api, headers

BASE = "/api/v1/admin"


@pytest_asyncio.fixture
async def suite(setup_admin_api, monkeypatch):
    d = setup_admin_api
    monkeypatch.setattr(settings, "ALLOW_LEGACY_ADMIN_TOKENS", False)
    account = AdminAccount(id=uuid4(), email=f"remaining-{uuid4()}@fixture.test", name="Admin source fixture",
                           password_hash=hash_admin_password("fixture-only-long-password"), role_ids=["role_ceo"])
    d["session"].add(account)
    await d["session"].flush()
    issued = await AdminAuthService(d["session"]).issue(account, mfa_verified_at=datetime.now(timezone.utc))
    d["auth"] = {"Authorization": "Bearer " + issued["access_token"]}
    d["account"] = account
    d["city"] = "Source-fixture-" + str(uuid4())
    d["garage"].city = d["other_garage"].city = d["city"]
    await d["session"].flush()
    c1, c2, invoice, payment, refund, ticket, review, vehicle, dispute = [uuid4() for _ in range(9)]
    stamp = datetime.now(timezone.utc).isoformat()
    records = []
    def source(id, kind, status, payload=None, amount=None, parent_id=None, customer_id=c1, garage_id=None, **links):
        result = dict(id=str(id), source="fixture-source", external_id=str(id), kind=kind,
                      garage_id=str(garage_id or d["garage"].id), customer_id=str(customer_id),
                      status=status, occurred_at=stamp, payload=payload or {}, **links)
        if amount is not None:
            result.update(amount=amount, currency="INR")
        if parent_id:
            result["parent_id"] = str(parent_id)
        records.append(result)
    source(invoice, "INVOICE", "PAID", {"invoice_number": "INV-fixture", "subtotal": 10000, "tax_amount": 1800}, amount=11800)
    source(payment, "PAYMENT", "CAPTURED", amount=11800, parent_id=invoice)
    source(refund, "REFUND", "SETTLED", {"reason": "Confirmed source refund"}, amount=1800, parent_id=payment)
    source(ticket, "TICKET", "OPEN", {"subject": "Invoice question", "priority": "NORMAL", "description": "Please explain"})
    source(review, "REVIEW", "PUBLISHED", {"rating": 4, "text": "Recorded review"})
    source(vehicle, "VEHICLE", "ACTIVE", {"registration_number": "TEST-001"})
    source(dispute, "DISPUTE", "OPEN", {"reason": "Recorded dispute"}, parent_id=payment)
    other_invoice = uuid4()
    source(other_invoice, "INVOICE", "ISSUED", amount=5000, customer_id=c2, garage_id=d["other_garage"].id)
    source(uuid4(), "BOOKING_EVENT", "ACCEPTED", booking_id=str(d["booking"].id))
    source(uuid4(), "BOOKING_EVENT", "CONVERTED", booking_id=str(d["booking"].id))
    batch = SourceBatch.model_validate({
        "accounts": [
            {"id": str(c1), "source": "fixture-source", "name": "Source customer A", "garage_ids": [str(d["garage"].id)]},
            {"id": str(c2), "source": "fixture-source", "name": "Source customer B", "garage_ids": [str(d["other_garage"].id)]},
        ], "records": records,
    })
    await import_sources(d["session"], batch)
    d.update(customer=c1, other_customer=c2, invoice=invoice, payment=payment, refund=refund,
             ticket=ticket, review=review, vehicle=vehicle, dispute=dispute, other_invoice=other_invoice)
    yield d


async def get(d, path, **kwargs):
    if path.startswith(("/finance/", "/garage-owner-statistics")):
        kwargs["params"] = {"city": d["city"], **kwargs.get("params", {})}
    return await d["client"].get(BASE+path, headers=d["auth"], **kwargs)


async def mutate(d, path, data, method="patch", extra_headers=None):
    return await getattr(d["client"], method)(BASE+path, json=data, headers={**d["auth"], **(extra_headers or {})})


async def test_remaining_read_groups_and_source_financial_reconciliation(suite):
    d = suite
    paths = [
        "/permissions", "/roles", "/staff", "/customers", f"/customers/{d['customer']}",
        f"/customers/{d['customer']}/vehicles", f"/customers/{d['customer']}/reviews",
        f"/garages/{d['garage'].id}/reviews", "/jobs/delays", "/alerts",
        "/finance/summary", "/finance/trends", "/invoices", f"/invoices/{d['invoice']}",
        f"/invoices/{d['invoice']}/payment-attempts", "/payments", f"/payments/{d['payment']}",
        "/refunds", "/disputes", f"/disputes/{d['dispute']}",
        "/notifications", "/announcements", "/support/tickets", f"/support/tickets/{d['ticket']}",
        f"/support/tickets/{d['ticket']}/messages", "/garage-owner-statistics",
        "/garage-owner-statistics/summary", f"/garage-owner-statistics/{d['owner'].id}",
        f"/garage-owner-statistics/{d['owner'].id}/trends",
    ]
    for path in paths:
        response = await get(d, path)
        assert response.status_code == 200, (path, response.text)
        assert "password_hash" not in response.text
        owner = await d["client"].get(BASE+path, headers=headers(d["owner"]))
        assert owner.status_code in (401, 403)
    finance = (await get(d, "/finance/summary")).json()["data"]
    assert finance["gross_collected_amount"] == 11800
    assert finance["refunded_amount"] == 1800 and finance["net_collected_amount"] == 10000
    assert finance["paid_invoice_count"] == 1 and finance["issued_invoice_count"] == 2
    assert finance["issued_invoice_total_amount"] == 16800
    assert finance["money_unit"] == "paise" and finance["snapshot_id"]
    total = (await get(d, "/garage-owner-statistics/summary")).json()["data"]
    assert total["net_collected_amount"] == 10000
    assert total["eligible_accepted_bookings"] == total["converted_bookings"] == 1
    assert total["conversion_percent"] == 100


async def test_garage_version_and_independent_verification(suite):
    d = suite
    path = f"/garages/{d['garage'].id}"
    first = await mutate(d, path+"/status", {"operational_status": "SUSPENDED", "reason": "Review", "expected_version": 1})
    assert first.status_code == 200 and first.json()["data"]["version"] == 2
    assert (await mutate(d, path+"/status", {"operational_status": "ACTIVE", "reason": "Review", "expected_version": 1})).status_code == 409
    second = await mutate(d, path+"/verification", {"verification_status": "VERIFIED", "reason": "Checked", "expected_version": 2})
    assert second.status_code == 200
    assert second.json()["data"]["operational_status"] == "SUSPENDED"
    assert (await mutate(d, path+"/status", {"operational_status": "ACTIVE", "reason": " ", "expected_version": 3})).status_code == 422
    assert (await get(d, f"/jobs/{d['completed'].id}")).status_code == 200


async def test_scope_permissions_privacy_and_aggregate_scope(suite):
    d = suite
    d["account"].role_ids = ["role_operations"]
    d["account"].garage_scope = [str(d["garage"].id)]
    await d["session"].flush()
    for path in ("/garages", "/jobs", "/bookings", "/activity", "/customers", "/garage-owners", "/support/tickets"):
        response = await get(d, path)
        assert response.status_code == 200, (path, response.text)
        assert str(d["other_garage"].id) not in response.text
        assert str(d["other_customer"]) not in response.text
    for path in (f"/garages/{d['other_garage'].id}", f"/jobs/{d['missing'].id}", f"/customers/{d['other_customer']}"):
        assert (await get(d, path)).status_code == 404
    for path in ("/finance/summary", "/invoices", "/audit-logs", "/staff", "/roles"):
        assert (await get(d, path)).status_code == 403
    jobs = (await get(d, "/jobs")).json()["data"]
    assert jobs["restricted_fields"] and all(j["final_amount"] is None for j in jobs["items"])
    stats = (await get(d, "/garage-owner-statistics")).json()["data"]
    assert len(stats["items"]) == 1
    assert stats["items"][0]["net_collected_amount"] is None
    d["account"].role_ids = ["role_finance"]
    await d["session"].flush()
    finance = (await get(d, "/finance/summary")).json()["data"]
    assert finance["issued_invoice_count"] == 1 and finance["issued_invoice_total_amount"] == 11800
    assert (await get(d, f"/invoices/{d['other_invoice']}")).status_code == 404
    assert (await get(d, "/jobs")).status_code == 403


async def test_support_workflow_replay_closed_reply_and_eligibility(suite):
    d = suite
    base = f"/support/tickets/{d['ticket']}"
    assigned = await mutate(d, base+"/assignment", {
        "assignee_id": str(d["account"].id), "reason": "Support review", "expected_version": 1})
    assert assigned.status_code == 200 and assigned.json()["data"]["version"] == 2
    priority = await mutate(d, base+"/priority", {"priority": "HIGH", "reason": "Needs review", "expected_version": 2})
    assert priority.status_code == 200
    reply = {"client_message_id": "reply-one", "text": "We are reviewing this."}
    first = await mutate(d, base+"/messages", reply, "post")
    second = await mutate(d, base+"/messages", reply, "post")
    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert (await mutate(d, base+"/messages", {**reply, "text": "Changed"}, "post")).status_code == 409
    assert (await get(d, base+"/messages")).json()["data"]["items"][0]["text"] == reply["text"]
    assert (await mutate(d, base+"/status", {"status": "RESOLVED", "resolution": "Explained", "expected_version": 3})).status_code == 200
    assert (await mutate(d, base+"/status", {"status": "CLOSED", "resolution": "Confirmed", "expected_version": 4})).status_code == 200
    assert (await mutate(d, base+"/messages", {**reply, "client_message_id": "second"}, "post")).status_code == 409
    assert (await mutate(d, base+"/status", {"status": "OPEN", "expected_version": 5})).status_code == 409
    notifications = (await get(d, "/notifications")).json()["data"]["items"]
    assert any(n["message"] == reply["text"] for n in notifications)
    assert (await get(d, f"/notifications/{notifications[0]['id']}")).status_code == 200


async def test_announcements_preview_frozen_idempotent_and_delivery(suite):
    d = suite
    body = {"audience": {"recipient_roles": ["GARAGE_OWNER"], "garage_ids": [str(d["garage"].id)]},
            "channels": ["IN_APP"], "title": "Operational notice", "body": "Please review appointments."}
    preview = await mutate(d, "/announcements/preview", body, "post")
    assert preview.status_code == 200
    send = {"preview_id": preview.json()["data"]["preview_id"], "reason": "Operational capacity"}
    first = await mutate(d, "/announcements", send, "post", {"Idempotency-Key": "notice-one"})
    replay = await mutate(d, "/announcements", send, "post", {"Idempotency-Key": "notice-one"})
    assert first.status_code == replay.status_code == 202
    assert first.json()["data"]["id"] == replay.json()["data"]["id"]
    announcement = first.json()["data"]["id"]
    assert (await get(d, f"/announcements/{announcement}")).status_code == 200
    delivered = (await get(d, f"/announcements/{announcement}/deliveries")).json()["data"]["items"]
    assert len(delivered) == 1 and delivered[0]["status"] == "DELIVERED"
    assert (await mutate(d, "/announcements", {**send, "reason": "changed"}, "post",
                         {"Idempotency-Key": "notice-one"})).status_code == 409
    assert (await mutate(d, "/announcements/preview", {**body, "channels": ["SMS"]}, "post")).status_code == 409
    assert (await mutate(d, "/announcements", {**send, "body": "Changed content"}, "post",
                         {"Idempotency-Key": "notice-two"})).status_code == 422


@pytest.mark.parametrize("format", ["CSV", "XLSX"])
async def test_report_queue_snapshot_download_permissions_and_expiry(suite, format):
    d = suite
    body = {"report_type": "GARAGE_OWNER_PERFORMANCE", "format": format, "filters": {"city": d["city"]}}
    created = await mutate(d, "/reports/exports", body, "post", {"Idempotency-Key": "export-one"})
    assert created.status_code == 202, created.text
    export_id = created.json()["data"]["id"]
    path = f"/reports/exports/{export_id}"
    assert (await get(d, path+"/download")).status_code == 409
    await AdminExportService.process_queue(d["session"])
    await d["session"].flush()
    status = (await get(d, path)).json()["data"]
    assert status["status"] == "READY" and status["row_count"] == 2
    download = await get(d, path+"/download")
    assert download.status_code == 200 and download.headers["cache-control"] == "no-store"
    if format == "XLSX":
        with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
            assert "xl/worksheets/sheet1.xml" in archive.namelist()
    else:
        assert b"snapshot_id" in download.content and b"net_collected_amount" in download.content
    d["account"].role_ids = ["role_support"]
    await d["session"].flush()
    assert (await get(d, path+"/download")).status_code == 403
    d["account"].role_ids = ["role_ceo"]
    resource = await d["session"].get(AdminResource, uuid4())  # missing lookup must not affect scope
    resource = (await d["session"].execute(select(AdminResource).where(AdminResource.id == export_id))).scalar_one()
    resource.expires_at = datetime.now(timezone.utc)-timedelta(seconds=1)
    await d["session"].flush()
    assert (await get(d, path+"/download")).status_code == 410


async def test_staff_role_assignment_revokes_session_and_requires_recent_mfa(suite):
    d = suite
    other = AdminAccount(id=uuid4(), email=f"staff-{uuid4()}@fixture.test", name="Assignable",
                         password_hash=hash_admin_password("fixture-only-password"), role_ids=["role_support"])
    d["session"].add(other)
    await d["session"].flush()
    issued = await AdminAuthService(d["session"]).issue(other, mfa_verified_at=datetime.now(timezone.utc))
    body = {"role_ids": ["role_operations"], "data_scope": {"type": "GARAGES", "garage_ids": [str(d["garage"].id)]}, "reason": "Regional"}
    assigned = await mutate(d, f"/staff/{other.id}/roles", body, "put")
    assert assigned.status_code == 200
    assert (await d["client"].get(BASE+"/me", headers={"Authorization": "Bearer "+issued["access_token"]})).status_code == 401
    assert (await mutate(d, f"/staff/{d['account'].id}/roles", body, "put")).status_code == 403
    old = await AdminAuthService(d["session"]).issue(d["account"], mfa_verified_at=datetime.now(timezone.utc)-timedelta(minutes=6))
    d["auth"] = {"Authorization": "Bearer "+old["access_token"]}
    assert (await mutate(d, f"/garages/{d['garage'].id}/status", {
        "operational_status": "SUSPENDED", "reason": "Review", "expected_version": 1})).status_code == 403


async def test_snapshots_freeze_data_and_reject_different_filters(suite):
    d = suite
    original = (await get(d, "/garage-owner-statistics")).json()["data"]
    d["ready"].status = JobStatus.CANCELLED
    await d["session"].flush()
    frozen = await get(d, "/garage-owner-statistics", params={"snapshot_id": original["snapshot_id"]})
    assert frozen.status_code == 200
    assert frozen.json()["data"]["source_totals"] == original["source_totals"]
    assert (await get(d, "/garage-owner-statistics", params={
        "snapshot_id": original["snapshot_id"], "city": "different"})).status_code == 409
