"""Real development SQL discovery-to-booking journeys, always rolled back."""
import math
from uuid import UUID, uuid4

import pytest
from loguru import logger
from sqlalchemy import select

from app.core.customer_security import now
from app.core.exceptions import NotFoundException
from app.models.garage import Garage
from app.models.service_package import ServicePackage
from app.schemas.garage import GarageCreate
from app.repositories.garage_repository import GarageRepository
from app.schemas.customer_discovery import LocationInput
from app.services.booking_service import BookingService
from app.services.customer_discovery_service import EARTH_RADIUS_KM, distance_expression
from tests.integration.test_customer_app import customer_api
from tests.integration.test_customer_workspace import workspace, vehicle, booking


async def search(d, **data):
    return (await d["call"]("POST", "/garages/search", json=data)).json()["data"]


async def extra_garage(d, name, latitude=0, longitude=0, status="ACTIVE", services=1):
    garage = Garage(id=uuid4(), user_id=d["garage"].user_id, name=name, owner="PRIVATE_OWNER",
                    latitude=latitude, longitude=longitude, operational_status=status)
    d["db"].add(garage)
    await d["db"].flush()
    for index in range(services):
        d["db"].add(ServicePackage(id=uuid4(), garage_id=garage.id, name=f"Discovery Oil {index}",
                                   description="Engine oil", price=500, duration_minutes=30, is_active=True))
    await d["db"].flush()
    return garage


async def test_service_garage_mixed_search_previews_and_private_fields(workspace):
    d = workspace
    g = await extra_garage(d, "Discovery Oil Garage", services=8)
    other = await extra_garage(d, "Discovery Other Garage")
    await extra_garage(d, "Discovery Suspended", status="SUSPENDED")
    deleted = await extra_garage(d, "Discovery Deleted")
    deleted.deleted_at = now()
    d["db"].add_all([
        ServicePackage(garage_id=g.id, name="Discovery Inactive", price=10, is_active=False),
        ServicePackage(garage_id=g.id, name="Discovery Deleted Service", price=10, is_active=True, deleted_at=now()),
        ServicePackage(garage_id=g.id, name="Discovery No Duration", price=10, is_active=True),
    ])
    await d["db"].flush()
    result = await search(d, q="dIsCoVeRy oIl", search_by="service", page_size=1)
    assert result["total"] == 2 and len(result["items"]) == 1 and result["pages"] == 2
    all_items = (await search(d, q="Discovery Oil", search_by="service"))["items"]
    match = next(r for r in all_items if r["id"] == str(g.id))
    assert match["active_service_count"] == 9 and match["matching_service_count"] == 8
    assert len(match["services"]) == 5 and match["services_has_more"]
    assert match["matched_by"] == ["service"] and match["distance_km"] is None
    svc = match["services"][0]
    assert svc["amount"] == 50000 and svc["price_inr"] == "500.00" and svc["duration_minutes"] == 30
    named = (await search(d, q="Discovery Other", search_by="garage"))["items"][0]
    assert named["id"] == str(other.id) and named["services"][0]["name"] == "Discovery Oil 0"
    mixed = await search(d, q="Discovery Oil")
    assert next(r for r in mixed["items"] if r["id"] == str(g.id))["matched_by"] == ["garage", "service"]
    assert "PRIVATE_OWNER" not in str(mixed)
    assert not {"owner", "user_id", "alternate_number", "latitude", "longitude"} & match.keys()
    catalogue = (await d["call"]("GET", f"/garages/{g.id}/services", params={"page_size": 5})).json()["data"]
    assert catalogue["total"] == 9 and len(catalogue["items"]) == 5
    unbookable = (await d["call"]("GET", f"/garages/{g.id}/services",
                                params={"q": "No Duration"})).json()["data"]["items"][0]
    assert not unbookable["booking_eligible"] and unbookable["unavailable_reason"]
    assert (await search(d, q="Discovery Inactive"))["total"] == 0
    assert (await search(d, q="Discovery Deleted"))["total"] == 0
    for text in ("%", "_", "Discovery/%", "not-found-" + uuid4().hex):
        assert (await search(d, q=text))["total"] == 0
    for endpoint in (f"/garages/{deleted.id}", f"/garages/{deleted.id}/services"):
        await d["call"]("GET", endpoint, expected=404)
    page2 = await search(d, q="Discovery Oil", search_by="service", page_size=1, page=2)
    assert result["items"][0]["id"] != page2["items"][0]["id"]
    assert (await search(d, q="Discovery Oil", page=100))["items"] == []


async def test_new_owner_garage_defaults_to_verified(workspace):
    d = workspace
    garage = await GarageRepository(d["db"]).create(
        d["garage"].user_id,
        GarageCreate(name="Verified by default", owner="New Garage Owner"),
    )
    assert garage.verification_status == "VERIFIED"


async def test_missing_pin_garage_city_search_uses_existing_catalogue(workspace):
    """Regression for the production garage, using rolled-back diagnostic fixtures."""
    d = workspace
    garage_id = UUID("fbce7066-6c45-408b-b125-db55d1535dde")
    garage = Garage(
        id=garage_id, user_id=d["garage"].user_id, name="Pranati's Workshop 2",
        owner="Fixture owner", city="Hyderabad", operational_status="ACTIVE",
        verification_status="UNVERIFIED", latitude=None, longitude=None,
    )
    d["db"].add(garage)
    await d["db"].flush()
    for name, price, duration in (("AC repair", 1000, 20), ("Car wash ", 600, 60), ("Full engine", 2000, 60)):
        d["db"].add(ServicePackage(garage_id=garage_id, name=name, price=price,
                                   duration_minutes=duration, is_active=True))
    await d["db"].flush()
    result = await search(d, city="  hYdErAbAd  ")
    assert result["radius_km"] is None
    found = next(item for item in result["items"] if item["id"] == str(garage_id))
    assert found["active_service_count"] == 3 and found["distance_km"] is None
    assert {s["name"].strip() for s in found["services"]} == {"AC repair", "Car wash", "Full engine"}
    detail = (await d["call"]("GET", f"/garages/{garage_id}")).json()["data"]
    catalogue = (await d["call"]("GET", f"/garages/{garage_id}/services")).json()["data"]
    assert detail["id"] == str(garage_id) and detail["active_service_count"] == 3
    assert {s["id"] for s in found["services"]} == {s["id"] for s in detail["services"]}
    assert catalogue["total"] == 3
    assert {s["id"] for s in catalogue["items"]} == {s["id"] for s in found["services"]}
    matched = await search(d, city="Hyderabad", q="AC repair", search_by="service")
    assert any(g["id"] == str(garage_id) for g in matched["items"])
    assert not (await search(d, city="Hyder"))["items"]
    # Synthetic test coordinates are not the customer's actual location.
    # Missing pins are excluded for every radius, but city browsing remains usable.
    nearby = await search(d, latitude=0, longitude=0)
    assert str(garage_id) not in {g["id"] for g in nearby["items"]}
    located_city = await search(d, city="Hyderabad", latitude=0, longitude=0)
    assert located_city["radius_km"] is None
    assert any(g["id"] == str(garage_id) for g in located_city["items"])
    strict = await search(d, city="Hyderabad", latitude=0, longitude=0, radius_km=5)
    assert str(garage_id) not in {g["id"] for g in strict["items"]}
    for payload in ({"city": " "}, {"city": "H" * 101}, {"city": "Hyderabad", "radius_km": 5}):
        await d["call"]("POST", "/garages/search", expected=422, json=payload)
    assert (await search(d, city="%"))["total"] == 0
    garage.operational_status = "SUSPENDED"
    await d["db"].flush()
    assert str(garage_id) not in {g["id"] for g in (await search(d, city="Hyderabad"))["items"]}


async def test_city_location_ordering_radius_and_pagination(workspace):
    d = workspace
    near = await extra_garage(d, "City Garage Near", longitude=0.01)
    far = await extra_garage(d, "City Garage Far", longitude=1)
    missing = await extra_garage(d, "City Garage Missing", latitude=None, longitude=None)
    invalid = await extra_garage(d, "City Garage Invalid", latitude=91)
    for garage in (near, far, missing, invalid):
        garage.city = " City Fixture "
    other_city = await extra_garage(d, "City Garage Other", longitude=0)
    other_city.city = "Other"
    await d["db"].flush()
    first = await search(d, city="city fixture", latitude=0, longitude=0, page_size=2)
    second = await search(d, city="city fixture", latitude=0, longitude=0, page_size=2, page=2)
    assert first["total"] == 4 and first["pages"] == 2
    assert [g["id"] for g in first["items"]] == [str(near.id), str(far.id)]
    assert {g["id"] for g in second["items"]} == {str(missing.id), str(invalid.id)}
    assert all(g["distance_km"] is None for g in second["items"])
    strict = await search(d, city="city fixture", latitude=0, longitude=0, radius_km=5)
    assert [g["id"] for g in strict["items"]] == [str(near.id)]
    assert (await search(d, city="Other"))["total"] == 1


async def test_radius_distance_sorting_detail_and_location_privacy(workspace):
    d = workspace
    near = await extra_garage(d, "Discovery Radius Near", longitude=0.01)
    far = await extra_garage(d, "Discovery Radius Far", longitude=0.06)
    missing = await extra_garage(d, "Discovery Radius Missing", latitude=None, longitude=None)
    await extra_garage(d, "Discovery Radius Invalid", latitude=91)
    boundary_lng = math.degrees(5 / EARTH_RADIUS_KM)
    boundary = await extra_garage(d, "Discovery Radius Boundary", longitude=boundary_lng)
    result = await search(d, q="Discovery Radius", latitude=0, longitude=0, page_size=1)
    assert result["radius_km"] == 5 and result["items"][0]["id"] == str(near.id)
    assert result["items"][0]["distance_km"] == pytest.approx(1.112)
    assert str(far.id) not in str(result) and str(missing.id) not in str(result)
    # Test exact, unrounded database boundary independently of rounded display.
    exact = await d["db"].scalar(select(distance_expression(LocationInput(latitude=0, longitude=0))).where(
        Garage.id == boundary.id))
    for radius, expected in ((exact - 0.000001, 0), (exact, 1), (exact + 0.000001, 1)):
        found = await search(d, q="Discovery Radius Boundary", latitude=0, longitude=0, radius_km=radius)
        assert found["total"] == expected
    detail = (await d["call"]("POST", f"/garages/{near.id}/details",
                             json={"latitude": 0, "longitude": 0})).json()["data"]
    assert detail["distance_km"] == result["items"][0]["distance_km"]
    assert (await d["call"]("GET", f"/garages/{near.id}")).json()["data"]["distance_km"] is None
    assert any(r["id"] == str(missing.id) for r in (await search(d, q="Discovery Radius"))["items"])
    # Nearby browsing works without text as well.
    assert any(r["id"] == str(near.id) for r in (await search(d, latitude=0, longitude=0))["items"])
    logs = []
    sink = logger.add(lambda msg: logs.append(str(msg)))
    try:
        await search(d, q="Discovery", latitude=12.3456789, longitude=76.5432198)
    finally:
        logger.remove(sink)
    assert "12.3456789" not in "".join(logs) and "76.5432198" not in "".join(logs)


async def test_dateline_and_high_latitude_distance(workspace):
    d = workspace
    wrap = await extra_garage(d, "Discovery Wrap", longitude=-179.99)
    result = await search(d, q="Discovery Wrap", latitude=0, longitude=179.99)
    assert result["items"][0]["id"] == str(wrap.id)
    assert result["items"][0]["distance_km"] == pytest.approx(2.224)
    await extra_garage(d, "Discovery Polar", latitude=89.99, longitude=90)
    polar = await search(d, q="Discovery Polar", latitude=89.99, longitude=0)
    assert polar["items"][0]["distance_km"] == pytest.approx(1.573)
    zero = await extra_garage(d, "Discovery Zero", latitude=0, longitude=0)
    assert (await search(d, q="Discovery Zero", latitude=0, longitude=0))["items"][0]["distance_km"] == 0
    assert zero.id


async def test_validation_and_customer_auth_boundary(workspace):
    d = workspace
    for payload in ({}, {"q": " "}, {"q": "Oil", "latitude": 0}, {"q": "Oil", "longitude": 0},
                    {"q": "Oil", "radius_km": 5}, {"latitude": 91, "longitude": 0},
                    {"latitude": 0, "longitude": -181}, {"latitude": 0, "longitude": 0, "radius_km": 0},
                    {"latitude": 0, "longitude": 0, "radius_km": 201}, {"q": "Oil", "page_size": 101},
                    {"q": "Oil", "page": 0}, {"q": "Oil", "search_by": "owner"},
                    {"q": "Oil", "owner_id": str(uuid4())}, {"q": "Oil", "accuracy_meters": 10}):
        await d["call"]("POST", "/garages/search", expected=422, json=payload)
    for method, path, kwargs in (
        ("POST", "/garages/search", {"json": {"q": "Oil"}}),
        ("POST", f"/garages/{d['garage'].id}/details", {"json": {}}),
        ("GET", f"/garages/{d['garage'].id}", {}),
        ("GET", f"/garages/{d['garage'].id}/services", {}),
    ):
        await d["call"](method, path, expected=401, headers={}, **kwargs)
    await d["call"]("POST", f"/garages/{uuid4()}/details", expected=404, json={})


@pytest.mark.parametrize("action", ["accept", "reject"])
async def test_discovered_service_shared_owner_booking_lifecycle(workspace, action):
    d = workspace
    d["service"].name = "Discovery Booking Oil"
    d["garage"].latitude, d["garage"].longitude = 0, 0
    await d["db"].flush()
    result = await search(d, q="Discovery Booking Oil", search_by="service", latitude=0, longitude=0)
    g = result["items"][0]
    v = await vehicle(d)
    service_ids = [g["services"][0]["id"]]
    slots = (await d["call"]("GET", f"/garages/{g['id']}/availability", params={
        "date": d["slot"].starts_at.date().isoformat(), "service_ids": service_ids,
    })).json()["data"]
    assert slots
    q = (await d["call"]("POST", "/bookings/quote", json={
        "garage_id": g["id"], "service_ids": service_ids, "vehicle_id": v["id"], "slot_id": str(d["slot"].id),
    })).json()["data"]
    key = uuid4().hex
    b = await booking(d, q, key)
    assert (await booking(d, q, key))["id"] == b["id"]
    owner = BookingService(d["db"])
    assert str((await owner.get(UUID(g["id"]), UUID(b["id"]))).id) == b["id"]
    assert b["id"] in [str(item.id) for item in (await owner.list(UUID(g["id"]))).items]
    with pytest.raises(NotFoundException):
        await owner.get(uuid4(), UUID(b["id"]))
    await getattr(owner, action)(UUID(g["id"]), UUID(b["id"]))
    current = (await d["call"]("GET", f"/bookings/{b['id']}")).json()["data"]
    assert current["status"] == ("ACCEPTED" if action == "accept" else "REJECTED")
    if action == "accept":
        job = await owner.create_job_from_booking(UUID(g["id"]), UUID(b["id"]))
        current = (await d["call"]("GET", f"/bookings/{b['id']}")).json()["data"]
        assert current["status"] == "CONVERTED" and current["linked_job_id"] == str(job.id)
        assert str(job.booking_id) == b["id"]
