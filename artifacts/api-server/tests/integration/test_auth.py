"""Integration tests for the auth flow."""
import uuid

import pytest
import httpx

BASE_URL = "http://localhost:8080"


@pytest.mark.asyncio
async def test_health_endpoint():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["data"]["database"] == "connected"


@pytest.mark.asyncio
async def test_version_endpoint():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.get("/api/version")
    assert r.status_code == 200
    assert r.json()["data"]["app_name"] == "Garage Management API"


@pytest.mark.asyncio
async def test_sign_up_new_user():
    mobile = f"7{uuid.uuid4().int % 10**9:09d}"
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.post("/api/v1/auth/sign-up", json={"mobile": mobile, "name": "Test"})
    assert r.status_code == 201
    assert r.json()["success"] is True


@pytest.mark.asyncio
async def test_sign_up_duplicate_fails():
    mobile = f"6{uuid.uuid4().int % 10**9:09d}"
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        await client.post("/api/v1/auth/sign-up", json={"mobile": mobile, "name": "Test"})
        r = await client.post("/api/v1/auth/sign-up", json={"mobile": mobile, "name": "Test"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_verify_otp_returns_jwt(auth_token):
    assert auth_token and len(auth_token) > 20


@pytest.mark.asyncio
async def test_protected_endpoint_requires_auth():
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.get("/api/v1/customers")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_profile_accessible_with_token(auth_token):
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        r = await client.get(
            "/api/v1/profile",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
    assert r.status_code == 200
    assert r.json()["success"] is True
