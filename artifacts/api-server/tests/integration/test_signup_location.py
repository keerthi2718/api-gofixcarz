"""Signup location persistence through real SQL and authenticated HTTP APIs.

All rows roll back using the customer API fixture; no SMS is sent.
"""
import json
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.garage import Garage
from app.models.user import User
from tests.integration.test_customer_app import customer_api, account, bearer


def payload():
    tag = uuid4().hex
    return {
        "first_name": "Location Test",
        "workshop_name": "Signup Location " + tag,
        "email": f"location-{tag}@example.com",
        "mobile": str(uuid4().int % 10**10).zfill(10),
        "terms_accepted": True,
        "city": "Hyderabad",
        "latitude": 17.4356741,
        "longitude": 78.3605197,
    }


async def test_signup_get_and_customer_search_preserve_location(customer_api, monkeypatch):
    d = customer_api
    monkeypatch.setattr(
        "app.services.auth_service.AuthService._submit_otp",
        AsyncMock(return_value="fixture-sms-not-sent"),
    )
    body = payload()
    signup = await d["client"].post("/api/v1/auth/sign-up", json=body)
    assert signup.status_code == 201, signup.text
    saved = signup.json()["data"]["garage"]
    garage_id = UUID(saved["id"])
    db_garage = await d["db"].get(Garage, garage_id)
    assert db_garage.latitude == Decimal("17.4356741")
    assert db_garage.longitude == Decimal("78.3605197")
    assert saved["latitude"] == "17.4356741"
    assert saved["longitude"] == "78.3605197"
    # Complete the actual owner OTP flow; SMS delivery alone is mocked.
    user = (await d["db"].execute(select(User).where(User.mobile == body["mobile"]))).scalar_one()
    login = await d["client"].post("/api/v1/auth/verify-otp", json={
        "mobile": body["mobile"], "otp": user.otp,
    })
    assert login.status_code == 200, login.text
    owner_headers = bearer(login.json()["data"])
    get = await d["client"].get("/api/v1/garage", headers=owner_headers)
    assert get.status_code == 200, get.text
    assert get.json()["data"]["latitude"] == saved["latitude"]
    assert get.json()["data"]["longitude"] == saved["longitude"]
    # An unrelated profile edit must not erase the map pin.
    edit = await d["client"].put("/api/v1/garage", headers=owner_headers, json={
        "city": "Hyderabad",
    })
    assert edit.status_code == 200, edit.text
    assert edit.json()["data"]["latitude"] == saved["latitude"]
    assert edit.json()["data"]["longitude"] == saved["longitude"]
    _, customer_tokens = await account(d)
    search_body = {
        "latitude": 17.44, "longitude": 78.36,
        "radius_km": 200, "q": "", "search_by": "all",
    }
    response = await d["client"].post(
        "/api/v1/customer-app/garages/search", json=search_body,
        headers=bearer(customer_tokens),
    )
    assert response.status_code == 200, response.text
    matches = [g for g in response.json()["data"]["items"] if g["id"] == str(garage_id)]
    assert len(matches) == 1
    assert 0 < matches[0]["distance_km"] < 200
    assert saved["operational_status"] == "ACTIVE"
    assert saved["verification_status"] == "VERIFIED"
    # Sanitized evidence: no tokens, mobile, OTP, email, owner or other garages.
    print("\nLOCATION_EVIDENCE=" + json.dumps({
        "environment": "development transaction; rolled back",
        "signup": {"status": signup.status_code, "request": {
            k: body[k] for k in ("workshop_name", "city", "latitude", "longitude")
        }, "garage": {k: saved[k] for k in (
            "id", "latitude", "longitude", "operational_status", "verification_status"
        )}},
        "get_garage": {"status": get.status_code, "data": {
            k: get.json()["data"][k] for k in ("id", "latitude", "longitude")
        }},
        "search": {"status": response.status_code, "request": search_body,
                   "total": response.json()["data"]["total"],
                   "matched_garage": matches[0], "errors": response.json()["errors"]},
    }, default=str))


@pytest.mark.parametrize("coordinates", [
    {"latitude": 90.000001, "longitude": 0},
    {"latitude": -90.000001, "longitude": 0},
    {"latitude": 0, "longitude": 180.000001},
    {"latitude": 0, "longitude": -180.000001},
    {"latitude": "NaN", "longitude": 0},
    {"latitude": 0, "longitude": "Infinity"},
    {"latitude": None, "longitude": 0},
    {"latitude": 0, "longitude": None},
    {"latitude": "17.4356741", "longitude": 78.3605197},
    {"latitude": True, "longitude": 0},
])
async def test_invalid_signup_coordinates_rejected(customer_api, coordinates):
    body = {**payload(), **coordinates}
    response = await customer_api["client"].post("/api/v1/auth/sign-up", json=body)
    assert response.status_code == 422, response.text
    user = await customer_api["db"].scalar(select(User).where(User.mobile == body["mobile"]))
    assert user is None


@pytest.mark.parametrize("latitude,longitude", [(90, 180), (-90, -180), (0, 0), (None, None)])
def test_signup_coordinate_boundaries_and_legacy(latitude, longitude):
    from app.schemas.auth import SignUpRequest
    result = SignUpRequest(**{**payload(), "latitude": latitude, "longitude": longitude})
    assert result.latitude == latitude and result.longitude == longitude
