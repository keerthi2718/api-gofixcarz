"""Tests for the /api/health endpoint.

Verifies that:
- The endpoint returns HTTP 200 with the expected shape.
- Pool stats (pool_size, checked_in, checked_out, overflow) are present when
  the database is reachable.
- The endpoint returns a degraded status (still HTTP 200) but empty pool stats
  when the database is unreachable.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

POOL_STAT_KEYS = {"pool_size", "checked_in", "checked_out", "overflow"}


def _mock_pool():
    pool = MagicMock()
    pool.size.return_value = 10
    pool.checkedin.return_value = 8
    pool.checkedout.return_value = 2
    pool.overflow.return_value = 0
    return pool


def _mock_engine(pool=None):
    """Build an AsyncMock engine so `await engine.dispose()` works in lifespan."""
    engine = MagicMock()
    engine.dispose = AsyncMock()
    engine.sync_engine.pool = pool or _mock_pool()
    return engine


def test_health_returns_pool_stats_when_db_is_up():
    """Health endpoint includes all pool stats when the DB check succeeds."""
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.main.async_session", return_value=mock_session_cm),
        patch("app.main.engine", _mock_engine()),
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/health")

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    pool = data.get("pool", {})
    assert POOL_STAT_KEYS.issubset(pool.keys()), (
        f"Missing pool stat keys. Got: {set(pool.keys())}"
    )
    assert pool["pool_size"] == 10
    assert pool["checked_in"] == 8
    assert pool["checked_out"] == 2
    assert pool["overflow"] == 0


def test_health_returns_degraded_when_db_is_down():
    """Health endpoint reports degraded status (HTTP 200) when the DB is unreachable."""
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))

    with (
        patch("app.main.async_session", return_value=mock_session_cm),
        patch("app.main.engine", _mock_engine()),
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/health")

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "degraded"
    assert data["database"] == "disconnected"
    # pool stats are absent when the DB is unreachable
    assert data.get("pool") == {}


def test_healthz_alias_works():
    """/api/healthz is an alias for /api/health and returns the same shape."""
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_session_cm.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.main.async_session", return_value=mock_session_cm),
        patch("app.main.engine", _mock_engine()),
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/healthz")

    assert r.status_code == 200
    assert "pool" in r.json()["data"]
    assert POOL_STAT_KEYS.issubset(r.json()["data"]["pool"].keys())


def test_liveness_health_does_not_access_database():
    """The deployment liveness probe stays healthy when the database is down."""
    client = TestClient(app, raise_server_exceptions=False)

    with patch("app.main.async_session") as session_factory:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    session_factory.assert_not_called()


def test_docs_are_available_at_root_and_legacy_api_paths():
    """Both documentation URLs serve Swagger UI using the existing OpenAPI URL."""
    client = TestClient(app, raise_server_exceptions=False)

    for path in ("/docs", "/api/docs"):
        response = client.get(path)
        assert response.status_code == 200
        assert "swagger-ui" in response.text
        assert "/api/openapi.json" in response.text
