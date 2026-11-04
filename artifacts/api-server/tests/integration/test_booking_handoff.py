"""Customer/partner handoff on isolated, rolled-back development accounts."""
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.core.customer_security import now
from app.core.security import create_access_token
from app.dependencies.garage import get_current_garage
from app.main import app
from app.models.booking import Booking, BookingStatus
from app.models.customer_workspace import CustomerBookingLink, CustomerResource
from app.models.garage import Garage
from app.models.user import User
from app.repositories.booking_repository import BookingRepository
from tests.integration.test_customer_app import customer_api
from tests.integration.test_customer_workspace import (
    workspace, vehicle, booking,
)


@pytest.mark.parametrize("with_slot", [False, True])
@pytest.mark.parametrize("decision", ["accept", "reject"])
async def test_customer_booking_reaches_only_authenticated_garage(workspace, with_slot, decision):
    d = workspace
    # Exercise the real token -> user -> garage dependency, not the workspace
    # fixture's garage override. Each HTTP request uses a fresh SQL session.
    app.dependency_overrides.pop(get_current_garage)
    owner_headers = {
        "Authorization": "Bearer " + create_access_token(d["garage"].user_id),
    }
    outsider = User(
        id=uuid4(), mobile=str(uuid4().int % 10**10).zfill(10),
        role="garage_owner", terms_accepted=True,
    )
    d["db"].add(outsider)
    await d["db"].flush()
    other_garage = Garage(
        id=uuid4(), user_id=outsider.id, name="Isolated other garage", owner="Fixture owner",
    )
    d["db"].add(other_garage)
    await d["db"].flush()
    other_headers = {"Authorization": "Bearer " + create_access_token(outsider.id)}

    v = await vehicle(d)
    selection = {
        "garage_id": str(d["garage"].id), "vehicle_id": v["id"],
        "service_ids": [str(d["service"].id)],
    }
    if with_slot:
        selection["slot_id"] = str(d["slot"].id)
    q = (await d["call"]("POST", "/bookings/quote", json=selection)).json()["data"]
    key = uuid4().hex
    b = await booking(d, q, key)
    replay = await booking(d, q, key)
    assert replay["booking_id"] == b["booking_id"]
    identifier = UUID(b["booking_id"])
    repo = BookingRepository(d["db"])
    stored = await repo.get_by_id(identifier, d["garage"].id)
    assert stored is not None
    assert stored.garage_id == UUID(q["garage"]["id"])
    assert stored.status == BookingStatus.PENDING
    link = await d["db"].get(CustomerBookingLink, identifier)
    assert link.booking_id == stored.id and link.quote_id == UUID(q["quote_id"])

    for params in ({}, {"status": "PENDING"}):
        listed = (await d["call"](
            "GET", "/api/v1/bookings", headers=owner_headers, params=params,
        )).json()["data"]
        assert listed["total"] == 1
        assert [item["id"] for item in listed["items"]] == [b["booking_id"]]
        assert listed["items"][0]["garage_id"] == str(d["garage"].id)
        assert listed["items"][0]["status"] == "PENDING"
        hidden = (await d["call"](
            "GET", "/api/v1/bookings", headers=other_headers, params=params,
        )).json()["data"]
        assert hidden["items"] == [] and hidden["total"] == 0

    detail = (await d["call"](
        "GET", f"/api/v1/bookings/{identifier}", headers=owner_headers,
    )).json()["data"]
    assert detail["id"] == b["booking_id"]
    for method, suffix in (("GET", ""), ("PATCH", "/accept"), ("PATCH", "/reject")):
        await d["call"](
            method, f"/api/v1/bookings/{identifier}{suffix}",
            headers=other_headers, expected=404,
        )
    await d["call"](
        "PATCH", f"/api/v1/bookings/{identifier}/{decision}", headers=owner_headers,
    )
    expected = "REJECTED" if decision == "reject" else "ACCEPTED" if with_slot else "PENDING"
    # Preserve the approved slotless policy: owner agreement is recorded, but
    # the booking stays PENDING until an actual appointment is assigned.
    await d["db"].refresh(stored)
    assert stored.status.value == expected
    if decision == "accept":
        assert stored.owner_accepted_at is not None
        if not with_slot:
            start = now() + timedelta(days=3)
            await d["call"](
                "PATCH", f"/api/v1/bookings/{identifier}/schedule", headers=owner_headers,
                json={"scheduled_start": start.isoformat(),
                      "scheduled_end": (start + timedelta(hours=1)).isoformat()},
            )
            expected = "ACCEPTED"

    customer_detail = (await d["call"]("GET", f"/bookings/{identifier}")).json()["data"]
    customer_list = (await d["call"]("GET", "/bookings")).json()["data"]["items"]
    partner_detail = (await d["call"](
        "GET", f"/api/v1/bookings/{identifier}", headers=owner_headers,
    )).json()["data"]
    assert customer_detail["booking_id"] == partner_detail["id"] == str(identifier)
    assert customer_detail["status"] == partner_detail["status"] == expected
    assert customer_list[0]["booking_id"] == str(identifier)
    assert customer_list[0]["status"] == expected
    await d["db"].refresh(stored)
    assert stored.status.value == expected
    assert (await d["db"].execute(select(func.count()).select_from(Booking).where(
        Booking.garage_id == d["garage"].id,
    ))).scalar_one() == 1
    quote_row = await d["db"].get(CustomerResource, UUID(q["quote_id"]))
    assert quote_row.garage_id == stored.garage_id
