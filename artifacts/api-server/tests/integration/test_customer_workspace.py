"""Real dev PostgreSQL journeys; SMS/S3 mocked, no live payments or messages."""
import io
import json
import os
import re
from pathlib import Path
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4
from PIL import Image
import pytest
import pytest_asyncio
from fastapi import Depends, Request
from sqlalchemy import select
from app.main import app
from app.core.customer_security import now
from app.core.admin_policy import PERMISSIONS
from app.database.session import get_session
from app.dependencies.garage import get_current_garage
from app.dependencies.auth import get_current_admin
from app.models.user import User
from app.models.garage import Garage
from app.models.job import Job, JobStatus
from app.models.job_timeline import JobTimeline
from app.models.service_package import ServicePackage
from app.models.admin_operations import SourceRecord
from app.models.customer_workspace import CustomerResource, CustomerBookingLink, AppointmentSlot
from app.services.booking_service import BookingService
from tests.integration.test_customer_app import customer_api, register, verify, bearer, BASE


def scrub(value):
    if isinstance(value, dict):
        return {k: ("<redacted-example>" if any(word in k for word in (
            "access_token", "refresh_token", "push_token", "otp")) else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def capture(method, path, response):
    target = os.environ.get("CUSTOMER_CONTRACT_EXAMPLES")
    if not target or not path.startswith(BASE):
        return
    path = path.split("?")[0]
    # New FastAPI may retain included routers lazily instead of exposing their
    # children as app.routes; OpenAPI is the flattened route contract.
    template = next((p for p, methods in app.openapi()["paths"].items()
                     if method.lower() in methods and re.fullmatch(
                         re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(p)), path)), None)
    if not template:
        return
    key = method.upper() + " " + template
    dest = Path(target)
    catalog = json.loads(dest.read_text()) if dest.exists() else {}
    if "application/json" in response.headers.get("content-type", ""):
        body = scrub(response.json())
    else:
        body = {"binary": True, "content_type": response.headers.get("content-type"),
                "content_disposition": response.headers.get("content-disposition"),
                "description": "Binary file bytes, not a JSON envelope."}
    entry = {"status": response.status_code, "body": body}
    entries = catalog.setdefault(key, [])
    if not any(e["status"] == entry["status"] for e in entries):
        entries.append(entry)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(catalog, indent=2))


@pytest_asyncio.fixture
async def workspace(customer_api, monkeypatch):
    d = customer_api
    db = d["db"]
    user = User(id=uuid4(), mobile=str(uuid4().int % 10**10).zfill(10), role="garage_owner", terms_accepted=True)
    admin = User(id=uuid4(), mobile=str(uuid4().int % 10**10).zfill(10), role="admin", terms_accepted=True)
    db.add_all([user, admin])
    await db.flush()
    garage = Garage(id=uuid4(), user_id=user.id, name="Example Garage", owner="Demo Owner", address="Example Street")
    db.add(garage)
    await db.flush()
    service = ServicePackage(id=uuid4(), garage_id=garage.id, name="Basic Service",
                             price=1500, duration_minutes=60, is_active=True)
    db.add(service)
    await db.flush()
    slot = AppointmentSlot(id=uuid4(), garage_id=garage.id,
                           starts_at=now() + timedelta(days=2), ends_at=now() + timedelta(days=2, hours=2),
                           timezone="Asia/Kolkata", capacity=1, active=True)
    db.add(slot)
    await db.flush()
    permissions, scopes = [set(PERMISSIONS)], [None]

    async def owner_override():
        return garage

    async def admin_override(request: Request, session=Depends(get_session)):
        access = {"principal_id": str(admin.id), "permissions": permissions[0],
                  "garage_ids": scopes[0], "mfa_verified_at": now()}
        session.info["admin_access"] = access
        request.state.admin_access = access
        return admin

    app.dependency_overrides[get_current_garage] = owner_override
    app.dependency_overrides[get_current_admin] = admin_override
    objects = {}

    class Storage:
        def put_object(self, **kwargs):
            objects[kwargs["Key"]] = (kwargs["Body"], kwargs["ContentType"])
        def get_object(self, **kwargs):
            content, mime = objects[kwargs["Key"]]
            return {"Body": io.BytesIO(content), "ContentType": mime}
        def delete_object(self, **kwargs):
            objects.pop(kwargs["Key"], None)

    monkeypatch.setattr("app.services.customer_attachment_service._client", lambda: Storage())
    monkeypatch.setattr("app.utils.s3._client", lambda: Storage())
    number, challenge = await register(d)
    tokens = await verify(d, number, challenge)
    d.update(headers=bearer(tokens), tokens=tokens, garage=garage, service=service, slot=slot,
             permissions=permissions, scopes=scopes, objects=objects)

    async def call(method, path, *, expected=200, headers=None, **kwargs):
        url = path if path.startswith("/api/") else BASE + path
        response = await d["client"].request(method, url, headers=headers if headers is not None else d["headers"], **kwargs)
        capture(method, url, response)
        assert response.status_code == expected, response.text
        if url.startswith(BASE):
            assert response.headers.get("cache-control") == "no-store"
        return response

    d["call"] = call
    yield d


async def vehicle(d, suffix=None):
    return (await d["call"]("POST", "/vehicles", expected=201, json={
        "registration_number": suffix or ("TS00" + uuid4().hex[:6].upper()),
        "brand": "Maruti Suzuki", "model": "Swift", "fuel_type": "PETROL", "year": 2023,
        "odometer_km": 25000,
    })).json()["data"]


async def quote(d, v=None):
    v = v or await vehicle(d)
    return (await d["call"]("POST", "/bookings/quote", json={
        "garage_id": str(d["garage"].id), "vehicle_id": v["id"], "service_ids": [str(d["service"].id)],
        "slot_id": str(d["slot"].id), "notes": "Please inspect engine noise",
    })).json()["data"]


async def booking(d, q=None, key=None):
    q = q or await quote(d)
    return (await d["call"]("POST", "/bookings", expected=201, json={"quote_id": q["quote_id"]},
                            headers={**d["headers"], "Idempotency-Key": key or uuid4().hex})).json()["data"]


async def job(d):
    b = await booking(d)
    service = BookingService(d["db"])
    await service.accept(d["garage"].id, UUID(b["id"]))
    result = await service.create_job_from_booking(d["garage"].id, UUID(b["id"]))
    return await d["db"].get(Job, result.id)


async def image(d, purpose="PROFILE_PHOTO"):
    stream = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(stream, "JPEG")
    return (await d["call"]("POST", "/attachments", expected=201, data={"purpose": purpose},
                            files={"file": ("vehicle.jpg", stream.getvalue(), "image/jpeg")})).json()["data"]


async def test_vehicle_crud_default_duplicate_and_archival(workspace):
    d = workspace
    first = await vehicle(d, "TS00AA0001")
    assert first["is_default"]
    second = await vehicle(d, "TS00AA0002")
    assert not second["is_default"]
    await d["call"]("POST", "/vehicles", expected=409, json={
        "registration_number": "ts-00 aa 0001", "brand": "A", "model": "B", "fuel_type": "DIESEL"})
    await d["call"]("GET", "/vehicles")
    await d["call"]("GET", f"/vehicles/{first['id']}")
    edited = (await d["call"]("PATCH", f"/vehicles/{first['id']}", json={"odometer_km": 26000})).json()["data"]
    assert edited["odometer_km"] == 26000
    await d["call"]("PATCH", f"/vehicles/{first['id']}", expected=422, json={"customer_id": str(uuid4())})
    await d["call"]("PUT", f"/vehicles/{second['id']}/default")
    await d["call"]("DELETE", f"/vehicles/{second['id']}")
    assert (await d["call"]("GET", f"/vehicles/{first['id']}")).json()["data"]["is_default"]
    await d["call"]("GET", f"/vehicles/{second['id']}", expected=404)
    await d["call"]("GET", f"/vehicles/{second['id']}/service-history")


async def test_private_uploads_photo_link_and_actual_byte_validation(workspace):
    d = workspace
    a = await image(d)
    await d["call"]("PUT", "/me/photo", json={"attachment_id": a["id"]})
    assert (await d["call"]("GET", "/me")).json()["data"]["photo"]["attachment_id"] == a["id"]
    response = await d["call"]("GET", a["download_path"])
    assert response.content.startswith(b"\xff\xd8")
    assert response.headers["x-content-type-options"] == "nosniff"
    await d["call"]("DELETE", f"/attachments/{a['id']}", expected=409)
    await d["call"]("DELETE", "/me/photo")
    await d["call"]("DELETE", f"/attachments/{a['id']}")
    await d["call"]("GET", a["download_path"], expected=404)
    await d["call"]("POST", "/attachments", expected=422, data={"purpose": "PROFILE_PHOTO"},
                    files={"file": ("evil.jpg", b"<script>alert(1)</script>", "image/jpeg")})
    await d["call"]("POST", "/attachments", expected=413, data={"purpose": "PROFILE_PHOTO"},
                    files={"file": ("large.jpg", b"x" * (5 * 1024 * 1024 + 1), "image/jpeg")})
    bad = await image(d, "BOOKING_PHOTO")
    await d["call"]("PUT", "/me/photo", expected=422, json={"attachment_id": bad["id"]})


async def test_booking_capacity_idempotency_cancellation_and_customer_isolation(workspace):
    d = workspace
    v = await vehicle(d)
    q = await quote(d, v)
    await d["call"]("GET", f"/garages/{d['garage'].id}/availability", params={
        "date": d["slot"].starts_at.date().isoformat(), "service_ids": str(d["service"].id)})
    key = uuid4().hex
    b = await booking(d, q, key)
    replay = await booking(d, q, key)
    assert replay["id"] == b["id"]
    await d["call"]("POST", "/bookings", expected=409, headers={**d["headers"], "Idempotency-Key": key},
                    json={"quote_id": str(uuid4())})
    await d["call"]("GET", "/bookings")
    await d["call"]("GET", f"/bookings/{b['id']}")
    await d["call"]("GET", f"/bookings/{b['id']}/timeline")
    await d["call"]("DELETE", f"/vehicles/{v['id']}", expected=409)
    number, challenge = await register(d)
    other = await verify(d, number, challenge)
    for path in (f"/vehicles/{v['id']}", f"/bookings/{b['id']}", f"/bookings/{b['id']}/timeline"):
        await d["call"]("GET", path, expected=404, headers=bearer(other))
    await d["call"]("POST", "/bookings", expected=404, headers={**bearer(other), "Idempotency-Key": uuid4().hex},
                    json={"quote_id": q["quote_id"]})
    await d["call"]("POST", "/bookings/quote", expected=409, json={
        "garage_id": str(d["garage"].id), "vehicle_id": v["id"],
        "service_ids": [str(d["service"].id)], "slot_id": str(d["slot"].id)})
    await d["call"]("POST", f"/bookings/{b['id']}/cancel", json={"reason": "Change of plans"})
    from app.core.exceptions import BadRequestException
    with pytest.raises(BadRequestException):
        await BookingService(d["db"]).accept(d["garage"].id, UUID(b["id"]))
    await quote(d, v)  # Cancellation released capacity.


@pytest.mark.parametrize("owner_action", ["accept", "reject"])
async def test_customer_booking_without_slot_and_owner_schedule(workspace, owner_action):
    d = workspace
    extra_service = ServicePackage(
        id=uuid4(), garage_id=d["garage"].id, name="Additional Inspection",
        price=325, duration_minutes=30, is_active=True,
    )
    d["db"].add(extra_service)
    await d["db"].flush()
    v = await vehicle(d)

    quote_response = await d["call"]("POST", "/bookings/quote", json={
        "garage_id": str(d["garage"].id),
        "vehicle_id": v["id"],
        "service_ids": [str(d["service"].id), str(extra_service.id)],
        "notes": "",
        "attachment_ids": [],
    })
    q = quote_response.json()["data"]
    quote_id = UUID(q["quote_id"])
    assert str(quote_id) == q["quote_id"]
    assert q["slot_id"] is None
    assert q["scheduled_date"] is None
    assert q["scheduled_start"] is None and q["scheduled_end"] is None
    assert len(q["services"]) == 2
    assert q["estimated_total"] == 182500

    b = await booking(d, q)
    booking_id = UUID(b["booking_id"])
    assert b["id"] == b["booking_id"]
    assert b["quote_id"] == str(quote_id)
    assert b["status"] == "PENDING"
    assert b["scheduled_date"] is None
    assert b["scheduled_start"] is None and b["scheduled_end"] is None
    link = await d["db"].get(CustomerBookingLink, booking_id)
    assert link and link.slot_id is None

    owner_list = (await d["call"]("GET", "/api/v1/bookings")).json()["data"]
    assert b["id"] in [item["id"] for item in owner_list["items"]]
    await d["call"]("PATCH", f"/api/v1/bookings/{b['id']}/{owner_action}")
    current = (await d["call"]("GET", f"/bookings/{b['id']}")).json()["data"]

    if owner_action == "reject":
        assert current["status"] == "REJECTED"
        assert current["scheduled_date"] is None
        return

    assert current["status"] == "ACCEPTED"
    assert current["scheduled_date"] is None
    scheduled_start = now() + timedelta(days=5)
    scheduled_end = scheduled_start + timedelta(hours=1)
    assigned = await d["call"]("PATCH", f"/api/v1/bookings/{b['id']}/schedule", json={
        "scheduled_start": scheduled_start.isoformat(),
        "scheduled_end": scheduled_end.isoformat(),
    })
    owner_booking = assigned.json()["data"]
    assert owner_booking["status"] == "ACCEPTED"
    assert owner_booking["scheduled_date"] == scheduled_start.date().isoformat()

    customer_booking = (await d["call"]("GET", f"/bookings/{b['id']}")).json()["data"]
    assert customer_booking["booking_id"] == b["id"]
    assert customer_booking["quote_id"] == str(quote_id)
    assert customer_booking["status"] == "ACCEPTED"
    assert customer_booking["scheduled_date"] == scheduled_start.date().isoformat()
    assert customer_booking["scheduled_start"] == scheduled_start.isoformat()
    assert customer_booking["scheduled_end"] == scheduled_end.isoformat()
    assert customer_booking["garage"]["id"] == str(d["garage"].id)
    assert customer_booking["vehicle"]["id"] == v["id"]
    assert len(customer_booking["services"]) == 2
    assert customer_booking["estimated_total"] == 182500


async def test_tracking_publication_invoices_confirmed_finance_and_reviews(workspace):
    d = workspace
    j = await job(d)
    # Raw notes and cost data must never be returned.
    j.inspection = {"internal_note": "SECRET_INTERNAL"}
    j.billing = {"cost_margin": 12345}
    j.status, j.completed_at = JobStatus.COMPLETED, now()
    d["db"].add(JobTimeline(job_id=j.id, status="COMPLETED", notes="SECRET_INTERNAL"))
    await d["db"].flush()
    await d["call"]("GET", "/jobs")
    raw = await d["call"]("GET", f"/jobs/{j.id}")
    assert "SECRET_INTERNAL" not in raw.text and "cost_margin" not in raw.text
    await d["call"]("PUT", f"/api/v1/jobs/{j.id}/customer-publication", json={
        "findings": ["Brake pads inspected"], "notes": "Ready for pickup", "services": ["Basic Service"]})
    detail = await d["call"]("GET", f"/jobs/{j.id}")
    assert detail.json()["data"]["published"]
    stream = io.BytesIO()
    Image.new("RGB", (8, 8), "blue").save(stream, "JPEG")
    photo_key = f"garages/{j.garage_id}/jobs/{j.id}/demo.jpg"
    d["objects"][photo_key] = (stream.getvalue(), "image/jpeg")
    j.photos = [photo_key]
    await d["db"].flush()
    await d["call"]("PUT", f"/api/v1/jobs/{j.id}/customer-publication", json={
        "notes": "Ready for pickup", "photo_keys": [photo_key]})
    photo_detail = (await d["call"]("GET", f"/jobs/{j.id}")).json()["data"]
    assert "photo_keys" not in photo_detail
    assert (await d["call"]("GET", photo_detail["photos"][0]["download_path"])).content.startswith(b"\xff\xd8")
    timeline = await d["call"]("GET", f"/jobs/{j.id}/timeline")
    assert "SECRET_INTERNAL" not in timeline.text
    invoice = (await d["call"]("POST", f"/api/v1/jobs/{j.id}/customer-invoice", expected=201, json={
        "invoice_number": "DEMO-001", "subtotal": 150000, "tax_amount": 27000, "discount_amount": 0
    })).json()["data"]
    assert invoice["total"] == 177000
    await d["call"]("GET", "/invoices")
    await d["call"]("GET", f"/invoices/{invoice['id']}")
    assert (await d["call"]("GET", f"/invoices/{invoice['id']}/pdf")).content.startswith(b"%PDF")
    await d["call"]("POST", f"/invoices/{invoice['id']}/payment-attempts", expected=503,
                    headers={**d["headers"], "Idempotency-Key": uuid4().hex}, json={})
    await d["call"]("GET", f"/invoices/{invoice['id']}/payment-attempts")
    paid = SourceRecord(id=uuid4(), kind="PAYMENT", source="test-confirmed-gateway",
                        external_id=uuid4().hex, garage_id=j.garage_id, customer_id=UUID(d["tokens"]["customer"]["id"]),
                        job_id=j.id, booking_id=j.booking_id, parent_id=UUID(invoice["id"]), status="CAPTURED",
                        occurred_at=now(), amount=177000, currency="INR", payload={"gateway_reference": "demo-confirmed"})
    d["db"].add(paid)
    await d["db"].flush()
    assert (await d["call"]("GET", f"/invoices/{invoice['id']}")).json()["data"]["payment_status"] == "PAID"
    assert (await d["call"]("GET", "/invoices", params={"payment_status": "PAID"})).json()["data"]["total"] == 1
    assert (await d["call"]("GET", "/invoices", params={"payment_status": "UNPAID"})).json()["data"]["total"] == 0
    await d["call"]("GET", f"/payments/{paid.id}")
    assert (await d["call"]("GET", f"/payments/{paid.id}/receipt")).content.startswith(b"%PDF")
    link = await d["db"].get(CustomerBookingLink, j.booking_id)
    await d["call"]("GET", f"/vehicles/{link.vehicle_id}/service-history")
    review = (await d["call"]("POST", f"/jobs/{j.id}/review", expected=201,
                             json={"rating": 5, "comment": "Good service"})).json()["data"]
    assert review["status"] == "PENDING"
    await d["call"]("GET", "/me/reviews")
    await d["call"]("PATCH", f"/reviews/{review['id']}", json={"rating": 4})
    await d["call"]("POST", f"/jobs/{j.id}/review", expected=409, json={"rating": 5})
    await d["call"]("GET", "/api/v1/admin/customer-reviews")
    await d["call"]("PATCH", f"/api/v1/admin/customer-reviews/{review['id']}", json={"status": "PUBLISHED"})
    d["permissions"][0] = {"support.read"}
    await d["call"]("PATCH", f"/api/v1/admin/customer-reviews/{review['id']}", expected=403, json={"status": "HIDDEN"})


async def test_context_conversations_garage_replies_cursor_and_terminal_guard(workspace):
    d = workspace
    b = await booking(d)
    c = (await d["call"]("POST", "/conversations", expected=201, json={"booking_id": b["id"]})).json()["data"]
    assert (await d["call"]("POST", "/conversations", json={"booking_id": b["id"]})).json()["data"]["id"] == c["id"]
    await d["call"]("GET", "/conversations")
    text = {"client_message_id": "demo-message-1", "text": "Thank you"}
    m = (await d["call"]("POST", f"/conversations/{c['id']}/messages", expected=201, json=text)).json()["data"]
    await d["call"]("POST", f"/conversations/{c['id']}/messages", json=text)
    await d["call"]("POST", f"/conversations/{c['id']}/messages", expected=409,
                    json={**text, "text": "Different text"})
    await d["call"]("GET", "/api/v1/garage/customer-conversations")
    await d["call"]("POST", f"/api/v1/garage/customer-conversations/{c['id']}/messages",
                    json={"client_message_id": "garage-demo-1", "text": "See you soon"})
    await d["call"]("GET", f"/api/v1/garage/customer-conversations/{c['id']}/messages")
    page = (await d["call"]("GET", f"/conversations/{c['id']}/messages", params={"limit": 1})).json()["data"]
    assert page["next_cursor"] == m["id"]
    await d["call"]("GET", f"/conversations/{c['id']}/messages", params={"cursor": m["id"]})
    await d["call"]("POST", f"/conversations/{c['id']}/read", json={"last_read_message_id": m["id"]})
    await d["call"]("POST", f"/bookings/{b['id']}/cancel", json={"reason": "Change of plans"})
    await d["call"]("POST", f"/conversations/{c['id']}/messages", expected=409,
                    json={"client_message_id": "demo-message-2", "text": "New message"})


async def test_support_customer_and_admin_external_messages_and_scope(workspace):
    d = workspace
    a = await image(d, "SUPPORT_ATTACHMENT")
    t = (await d["call"]("POST", "/support/tickets", expected=201, json={
        "category": "GENERAL", "subject": "App question", "description": "Please help",
        "attachment_ids": [a["id"]]
    })).json()["data"]
    await d["call"]("GET", "/support/tickets")
    await d["call"]("GET", f"/support/tickets/{t['id']}")
    await d["call"]("POST", f"/support/tickets/{t['id']}/messages", expected=201, json={
        "client_message_id": "demo-support-1", "text": "An update please", "attachment_ids": []})
    await d["call"]("GET", f"/support/tickets/{t['id']}/messages")
    await d["call"]("GET", "/api/v1/admin/customer-support/tickets")
    await d["call"]("POST", f"/api/v1/admin/customer-support/tickets/{t['id']}/messages",
                    json={"client_message_id": "admin-demo-1", "text": "We are checking"})
    await d["call"]("GET", f"/api/v1/admin/customer-support/tickets/{t['id']}/messages")
    await d["call"]("PATCH", f"/api/v1/admin/customer-support/tickets/{t['id']}", json={"status": "CLOSED"})
    await d["call"]("POST", f"/support/tickets/{t['id']}/messages", expected=409, json={
        "client_message_id": "demo-support-2", "text": "Please reopen"})
    d["scopes"][0] = [d["garage"].id]
    await d["call"]("GET", f"/api/v1/admin/customer-support/tickets/{t['id']}/messages", expected=404)


async def test_device_notification_counts_and_logout_detachment(workspace):
    d = workspace
    await booking(d)
    await d["call"]("PUT", "/devices/demo-installation", json={"platform": "ANDROID", "push_token": "demo-push-token"})
    notifications = (await d["call"]("GET", "/notifications", params={"category": "BOOKINGS"})).json()["data"]
    assert notifications["unread_count"] >= 1
    await d["call"]("PATCH", f"/notifications/{notifications['items'][0]['id']}", json={"is_read": True})
    await d["call"]("POST", "/notifications/read-all", json={})
    assert (await d["call"]("GET", "/notifications")).json()["data"]["unread_count"] == 0
    await d["call"]("DELETE", "/devices/demo-installation")
    await d["call"]("PUT", "/devices/demo-installation", json={"platform": "IOS", "push_token": "demo-push-token"})
    await d["call"]("POST", "/auth/logout")
    row = (await d["db"].execute(select(CustomerResource).where(
        CustomerResource.customer_id == UUID(d["tokens"]["customer"]["id"]),
        CustomerResource.kind == "DEVICE"))).scalar_one()
    await d["db"].refresh(row)
    assert row.status == "DETACHED" and not row.payload
    await d["call"]("GET", "/vehicles", expected=401)


async def test_garage_slot_management_overlap_and_customer_auth_boundary(workspace):
    d = workspace
    data = {"starts_at": (now() + timedelta(days=4)).isoformat(),
            "ends_at": (now() + timedelta(days=4, hours=2)).isoformat(),
            "timezone": "Asia/Kolkata", "capacity": 2}
    slot = (await d["call"]("POST", "/api/v1/garage/customer-slots", expected=201, json=data)).json()["data"]
    await d["call"]("POST", "/api/v1/garage/customer-slots", expected=409, json=data)
    await d["call"]("GET", "/api/v1/garage/customer-slots")
    await d["call"]("DELETE", f"/api/v1/garage/customer-slots/{slot['id']}")
    await d["call"]("GET", "/vehicles", expected=401, headers={})


async def test_stale_quote_and_linked_attachment_retention(workspace):
    d = workspace
    a = await image(d, "BOOKING_PHOTO")
    v = await vehicle(d)
    q = (await d["call"]("POST", "/bookings/quote", json={
        "garage_id": str(d["garage"].id), "vehicle_id": v["id"], "service_ids": [str(d["service"].id)],
        "slot_id": str(d["slot"].id), "attachment_ids": [a["id"]]
    })).json()["data"]
    await d["call"]("DELETE", f"/attachments/{a['id']}", expected=409)
    d["service"].price = 1600
    await d["db"].flush()
    await d["call"]("POST", "/bookings", expected=409, headers={**d["headers"], "Idempotency-Key": uuid4().hex},
                    json={"quote_id": q["quote_id"]})
    d["service"].price = 1500
    await d["db"].flush()
    await booking(d, q)
    quote_row = await d["db"].get(CustomerResource, UUID(q["quote_id"]))
    quote_row.payload = {**quote_row.payload, "expires_at": (now() - timedelta(hours=1)).isoformat()}
    await d["db"].flush()
    await d["call"]("DELETE", f"/attachments/{a['id']}", expected=409)


async def test_all_context_resources_reject_other_customer_and_inconsistent_links(workspace):
    d = workspace
    j = await job(d)
    j.status, j.completed_at = JobStatus.COMPLETED, now()
    await d["db"].flush()
    inv = (await d["call"]("POST", f"/api/v1/jobs/{j.id}/customer-invoice", expected=201, json={
        "invoice_number": "DEMO-OWNED", "subtotal": 10000, "tax_amount": 0
    })).json()["data"]
    c = (await d["call"]("POST", "/conversations", expected=201, json={"job_id": str(j.id)})).json()["data"]
    t = (await d["call"]("POST", "/support/tickets", expected=201, json={
        "category": "SERVICE", "subject": "Question", "description": "Please help", "job_id": str(j.id)
    })).json()["data"]
    a = await image(d)
    await d["call"]("POST", "/support/tickets", expected=422, json={
        "category": "SERVICE", "subject": "Mismatch", "description": "Please help",
        "invoice_id": inv["id"], "job_id": str(uuid4())
    })
    number, challenge = await register(d)
    other = bearer(await verify(d, number, challenge))
    for path in (f"/jobs/{j.id}", f"/jobs/{j.id}/timeline", f"/invoices/{inv['id']}",
                 f"/invoices/{inv['id']}/pdf", f"/invoices/{inv['id']}/payment-attempts",
                 f"/conversations/{c['id']}/messages", f"/support/tickets/{t['id']}",
                 f"/support/tickets/{t['id']}/messages", a["download_path"]):
        await d["call"]("GET", path, expected=404, headers=other)
    await d["call"]("PUT", "/me/photo", expected=404, headers=other, json={"attachment_id": a["id"]})
    await d["call"]("POST", f"/conversations/{c['id']}/messages", expected=404, headers=other, json={
        "client_message_id": "foreign", "text": "No access"})
    await d["call"]("POST", f"/jobs/{j.id}/review", expected=404, headers=other, json={"rating": 5})


async def test_pending_appointment_expiry_is_recorded_and_releases_work(workspace):
    d = workspace
    b = await booking(d)
    d["slot"].starts_at = now() - timedelta(minutes=1)
    d["slot"].ends_at = now() + timedelta(hours=1)
    await d["db"].flush()
    from app.services.customer_booking_maintenance import expire_pending_bookings
    assert await expire_pending_bookings(d["db"]) == 1
    result = (await d["call"]("GET", f"/bookings/{b['id']}")).json()["data"]
    assert result["status"] == "EXPIRED" and not result["can_cancel"]
    assert (await d["call"]("GET", "/bookings", params={"status": "EXPIRED"})).json()["data"]["total"] == 1
    assert await expire_pending_bookings(d["db"]) == 0
