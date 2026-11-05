"""Real development SQL discovery/date-booking journeys; all fixture data rolls back."""
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.customer_security import now
from app.core.exceptions import NotFoundException, BadRequestException
from app.models.booking import Booking, BookingStatus
from app.models.garage import Garage
from app.models.service_package import ServicePackage
from app.models.customer_workspace import CustomerBookingLink
from app.schemas.customer_discovery import LocationInput
from app.services.booking_service import BookingService
from app.services.customer_discovery_service import EARTH_RADIUS_KM, distance_expression
from tests.integration.test_customer_app import customer_api
from tests.integration.test_customer_workspace import workspace, vehicle, booking


async def search(d, **data):
    return (await d["call"]("POST", "/garages/search", json={
        "latitude": 0, "longitude": 0, **data,
    })).json()["data"]


async def extra_garage(d, name, latitude=0, longitude=0, status="ACTIVE", services=1, verified="VERIFIED"):
    g = Garage(id=uuid4(), user_id=d["garage"].user_id, name=name, owner="PRIVATE_OWNER",
               latitude=latitude, longitude=longitude, operational_status=status, verification_status=verified)
    d["db"].add(g)
    await d["db"].flush()
    for i in range(services):
        d["db"].add(ServicePackage(garage_id=g.id, name=f"Discovery Oil {i}",
                                  description="Engine oil", price=500, duration_minutes=30, is_active=True))
    await d["db"].flush()
    return g


async def test_search_has_no_garage_pagination_or_service_preview_limit(workspace):
    d = workspace
    g = await extra_garage(d, "Discovery Garage", services=8)
    others = [await extra_garage(d, f"Discovery Other {i}") for i in range(25)]
    for state in ("UNVERIFIED", "REJECTED"):
        await extra_garage(d, f"Discovery {state}", verified=state)
    await extra_garage(d, "Discovery Suspended", status="SUSPENDED")
    gone = await extra_garage(d, "Discovery Deleted")
    gone.deleted_at = now()
    d["db"].add_all([
        ServicePackage(garage_id=g.id, name="Inactive", price=1, is_active=False),
        ServicePackage(garage_id=g.id, name="Deleted", price=1, is_active=True, deleted_at=now()),
        ServicePackage(garage_id=g.id, name="No Duration", price=10, is_active=True),
    ])
    await d["db"].flush()
    result = await search(d, q="Discovery Oil", search_by="service", page_size=1, page=9)
    assert result["total"] == 26 == len(result["items"])
    assert result["page"] == 1 and result["pages"] == 1
    match = next(r for r in result["items"] if r["id"] == str(g.id))
    assert len(match["services"]) == 8 and not match["services_has_more"]
    assert all(s["description"] == "Engine oil" and s["amount"] == 50000 for s in match["services"])
    assert "PRIVATE_OWNER" not in str(result)
    assert {str(g.id), *(str(o.id) for o in others)} == {r["id"] for r in result["items"]}
    detail = (await d["call"]("GET", f"/garages/{g.id}")).json()["data"]
    assert len(detail["services"]) == 9 and detail["booking_prerequisites"][-1] == "SELECT_DATE"
    catalogue = (await d["call"]("GET", f"/garages/{g.id}/services")).json()["data"]
    assert len(catalogue["items"]) == 9
    assert next(s for s in catalogue["items"] if s["name"] == "No Duration")["booking_eligible"]


async def test_200km_default_nearest_sort_city_and_changed_location(workspace):
    d = workspace
    near = await extra_garage(d, "Radius Near", latitude=0.01)
    far = await extra_garage(d, "Radius Far", latitude=1.5)
    outside = await extra_garage(d, "Radius Outside", latitude=2)
    missing = await extra_garage(d, "Radius Missing", latitude=None, longitude=None)
    for g in (near, far, outside, missing):
        g.city = "Hyderabad"
    await d["db"].flush()
    found = await search(d, q="Radius", city=" Hyderabad ")
    assert found["radius_km"] == 200
    assert [r["id"] for r in found["items"]] == [str(near.id), str(far.id)]
    closer = await search(d, q="Radius", latitude=1.5)
    assert closer["items"][0]["id"] == str(far.id)
    narrow = await search(d, q="Radius", radius_km=5)
    assert [r["id"] for r in narrow["items"]] == [str(near.id)]
    # Strict full-precision boundary check, not rounded display distances.
    boundary = await extra_garage(d, "Boundary", latitude=1)
    exact = await d["db"].scalar(select(distance_expression(LocationInput(latitude=0, longitude=0)))
                                 .where(Garage.id == boundary.id))
    for radius, expected in ((exact - 0.000001, 0), (exact, 1), (exact + 0.000001, 1)):
        assert (await search(d, q="Boundary", radius_km=radius))["total"] == expected
    wrap = await extra_garage(d, "Dateline", longitude=-179.99)
    assert (await search(d, q="Dateline", longitude=179.99))["items"][0]["id"] == str(wrap.id)
    assert EARTH_RADIUS_KM > 6371


async def test_unverified_detail_services_and_booking_are_ineligible(workspace):
    d = workspace
    d["garage"].verification_status = "UNVERIFIED"
    await d["db"].flush()
    for path in (f"/garages/{d['garage'].id}", f"/garages/{d['garage'].id}/services"):
        await d["call"]("GET", path, expected=404)
    v = await vehicle(d)
    payload = {"garage_id": str(d["garage"].id), "vehicle_id": v["id"],
               "service_ids": [str(d["service"].id)], "booking_date": (now().date() + timedelta(days=2)).isoformat()}
    await d["call"]("POST", "/bookings/summary", expected=409, json=payload)
    await d["call"]("POST", "/bookings", expected=409, json=payload,
                    headers={**d["headers"], "Idempotency-Key": uuid4().hex})


async def test_location_contract_and_customer_auth(workspace):
    d = workspace
    for payload in ({}, {"q": "Oil"}, {"city": "Hyderabad"}, {"latitude": 0},
                    {"latitude": 91, "longitude": 0}, {"latitude": 0, "longitude": -181},
                    {"latitude": 0, "longitude": 0, "radius_km": 201},
                    {"latitude": 0, "longitude": 0, "radius_km": 0},
                    {"latitude": 0, "longitude": 0, "owner_id": str(uuid4())}):
        await d["call"]("POST", "/garages/search", expected=422, json=payload)
    await d["call"]("POST", "/garages/search", expected=401, headers={},
                    json={"latitude": 0, "longitude": 0})


@pytest.mark.parametrize("action", ["accept", "reject"])
async def test_direct_date_booking_is_shared_with_owner_and_idempotent(workspace, action):
    d = workspace
    d["garage"].latitude, d["garage"].longitude = 0, 0
    await d["db"].flush()
    result = await search(d, search_by="service", q="Basic")
    assert result["items"][0]["id"] == str(d["garage"].id)
    # No slot rows are needed; deliberately deactivate the fixture's legacy slot.
    d["slot"].active = False
    await d["db"].flush()
    v = await vehicle(d)
    payload = {"garage_id": str(d["garage"].id), "vehicle_id": v["id"],
               "service_ids": [str(d["service"].id)], "booking_date": (now().date() + timedelta(days=3)).isoformat()}
    headers = {**d["headers"], "Idempotency-Key": uuid4().hex}
    # Direct creation without even calling summary.
    b = (await d["call"]("POST", "/bookings", expected=201, json=payload, headers=headers)).json()["data"]
    assert b["status"] == "PENDING" and b["booking_date"] == payload["booking_date"]
    assert b["estimated_total"] == 150000 and b["starts_at"] is None
    assert "quote_id" not in b and "slot_id" not in b
    assert (await d["call"]("POST", "/bookings", expected=201, json=payload, headers=headers)).json()["data"]["id"] == b["id"]
    link = await d["db"].get(CustomerBookingLink, UUID(b["id"]))
    assert link.slot_id is None
    d["service"].price = 1750
    await d["db"].flush()
    frozen = (await d["call"]("GET", f"/bookings/{b['id']}")).json()["data"]
    assert frozen["estimated_total"] == 150000
    owner = BookingService(d["db"])
    assert str((await owner.get(d["garage"].id, UUID(b["id"]))).id) == b["id"]
    assert b["id"] in [str(r.id) for r in (await owner.list(d["garage"].id)).items]
    with pytest.raises(NotFoundException):
        await owner.get(uuid4(), UUID(b["id"]))
    await getattr(owner, action)(d["garage"].id, UUID(b["id"]))
    current = (await d["call"]("GET", f"/bookings/{b['id']}")).json()["data"]
    assert current["status"] == ("ACCEPTED" if action == "accept" else "REJECTED")
    replay = (await d["call"]("POST", "/bookings", expected=201, json=payload, headers=headers)).json()["data"]
    assert replay["status"] == current["status"]
    if action == "accept":
        j = await owner.create_job_from_booking(d["garage"].id, UUID(b["id"]))
        assert str(j.booking_id) == b["id"]


async def test_booking_rejects_old_contract_past_dates_fees_and_bad_service_ownership(workspace):
    d = workspace
    v = await vehicle(d)
    payload = {"garage_id": str(d["garage"].id), "vehicle_id": v["id"],
               "service_ids": [str(d["service"].id)], "booking_date": (now().date() + timedelta(days=1)).isoformat()}
    for extra in ({"slot_id": str(uuid4())}, {"quote_id": str(uuid4())}, {"booking_fee": 100}, {"total": 1}):
        await d["call"]("POST", "/bookings", expected=422, json={**payload, **extra},
                        headers={**d["headers"], "Idempotency-Key": uuid4().hex})
    await d["call"]("POST", "/bookings/summary", expected=422,
                    json={**payload, "booking_date": (now().date() - timedelta(days=1)).isoformat()})
    await d["call"]("POST", "/bookings/summary", expected=422,
                    json={**payload, "service_ids": [str(uuid4())]})
    await d["call"]("POST", "/bookings/summary", expected=409, json={**payload, "expected_total": 1})


async def test_optional_duration_same_day_and_legacy_slot_read_compatibility(workspace):
    d = workspace
    from zoneinfo import ZoneInfo
    from tests.integration.test_customer_workspace import quote
    d["service"].duration_minutes = None
    await d["db"].flush()
    summary = await quote(d)
    assert summary["services"][0]["duration_minutes"] is None
    today = now().astimezone(ZoneInfo("Asia/Kolkata")).date()
    summary["booking_date"] = today.isoformat()
    b = await booking(d, summary)
    assert b["can_cancel"] and b["booking_date"] == today.isoformat()
    # Existing pre-change records can still carry a slot and older snapshot keys.
    link = await d["db"].get(CustomerBookingLink, UUID(b["id"]))
    link.slot_id = d["slot"].id
    from app.models.customer_workspace import CustomerResource
    snapshot = await d["db"].get(CustomerResource, link.quote_id)
    snapshot.payload = {**snapshot.payload, "services": [
        {"id": s["id"], "name": s["name"], "amount": s["amount"],
         "duration_minutes": s.get("duration_minutes")} for s in snapshot.payload["services"]]}
    await d["db"].flush()
    legacy = (await d["call"]("GET", f"/bookings/{b['id']}")).json()["data"]
    assert legacy["starts_at"] is not None and legacy["services"][0]["price_inr"] is None
    d["slot"].starts_at = now() - timedelta(minutes=1)
    await d["db"].flush()
    with pytest.raises(BadRequestException):
        await BookingService(d["db"]).accept(d["garage"].id, UUID(b["id"]))
