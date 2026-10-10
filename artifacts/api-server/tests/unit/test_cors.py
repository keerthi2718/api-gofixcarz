"""Cross-origin bearer-token requests work without granting cookie credentials."""
import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [
    "http://localhost:4200",
    "http://127.0.0.1:5500",
    "https://example.test",
])
async def test_cors_preflight_all_origins(origin):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options("/api/v1/auth/logout", headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in response.headers
    assert "POST" in response.headers["access-control-allow-methods"]


@pytest.mark.asyncio
async def test_cors_actual_response():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/version", headers={"Origin": "http://localhost:4200"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "access-control-allow-credentials" not in response.headers


@pytest.mark.asyncio
async def test_cors_does_not_bypass_auth():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/auth/logout", json={}, headers={"Origin": "https://example.test"})
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "*"
