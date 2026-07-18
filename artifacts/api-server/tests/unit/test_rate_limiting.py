"""Tests that OTP endpoints enforce per-identifier rate limits.

Strategy:
- Override get_session to avoid a real DB connection.
- Patch AuthService so each call returns a canned success response.
- Use unique identifiers per test run to avoid counter cross-contamination.
- Assert requests 1-5 succeed (non-429) and request 6 is HTTP 429.

Note: /sign-in is keyed on the 'login' field (email or mobile).
      /send-otp is keyed on the 'mobile' field.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.database.session import get_session
from app.main import app

# ── helpers ───────────────────────────────────────────────────────────────────

def _unique_mobile() -> str:
    """Return a deterministic 10-digit mobile number unique to this test run."""
    return str(uuid.uuid4().int % 10**10).zfill(10)


def _make_mock_session():
    async def _override():
        mock_session = AsyncMock()
        yield mock_session
    return _override


# ── sign-in rate limit ────────────────────────────────────────────────────────

def test_sign_in_rate_limit_blocks_sixth_request():
    """The 6th /sign-in call with the same login value in one minute must return 429."""
    mobile = _unique_mobile()

    app.dependency_overrides[get_session] = _make_mock_session()
    try:
        canned = {"message": "OTP sent", "mobile": mobile, "country_code": "91"}
        with patch("app.api.v1.auth.AuthService") as MockService:
            instance = MockService.return_value
            instance.sign_in = AsyncMock(return_value=canned)

            with TestClient(app, raise_server_exceptions=False) as client:
                statuses = []
                for _ in range(6):
                    r = client.post(
                        "/api/v1/auth/sign-in",
                        json={"login": mobile},  # new field name
                    )
                    statuses.append(r.status_code)

        # First 5 must not be rate-limited
        assert all(s != 429 for s in statuses[:5]), (
            f"Unexpected 429 in first 5 requests: {statuses}"
        )
        # 6th must be rate-limited
        assert statuses[5] == 429, (
            f"Expected 429 on 6th request but got {statuses[5]}"
        )
    finally:
        app.dependency_overrides.pop(get_session, None)


# ── send-otp rate limit ───────────────────────────────────────────────────────

def test_send_otp_rate_limit_blocks_sixth_request():
    """The 6th /send-otp call from the same mobile in one minute must return 429."""
    mobile = _unique_mobile()

    app.dependency_overrides[get_session] = _make_mock_session()
    try:
        canned = {"message": "OTP sent", "mobile": mobile, "country_code": "91"}
        with patch("app.api.v1.auth.AuthService") as MockService:
            instance = MockService.return_value
            instance.send_otp = AsyncMock(return_value=canned)

            with TestClient(app, raise_server_exceptions=False) as client:
                statuses = []
                for _ in range(6):
                    r = client.post(
                        "/api/v1/auth/send-otp",
                        json={"mobile": mobile},
                    )
                    statuses.append(r.status_code)

        assert all(s != 429 for s in statuses[:5]), (
            f"Unexpected 429 before limit reached: {statuses}"
        )
        assert statuses[5] == 429, (
            f"Expected 429 on 6th request but got {statuses[5]}"
        )
    finally:
        app.dependency_overrides.pop(get_session, None)


# ── login field normalisation (whitespace) ────────────────────────────────────

def test_rate_limit_normalizes_login_whitespace():
    """Login values with leading/trailing spaces share the same rate-limit bucket.

    A caller cannot bypass the 5/min limit by padding the login with spaces.
    """
    mobile = _unique_mobile()
    padded = f"  {mobile}  "

    app.dependency_overrides[get_session] = _make_mock_session()
    try:
        canned = {"message": "OTP sent", "mobile": mobile, "country_code": "91"}
        with patch("app.api.v1.auth.AuthService") as MockService:
            instance = MockService.return_value
            instance.sign_in = AsyncMock(return_value=canned)

            with TestClient(app, raise_server_exceptions=False) as client:
                statuses = []
                # 4 requests with the canonical number
                for _ in range(4):
                    r = client.post("/api/v1/auth/sign-in", json={"login": mobile})
                    statuses.append(r.status_code)

                # 1 request with a padded variant — still same bucket (total = 5)
                r = client.post("/api/v1/auth/sign-in", json={"login": padded})
                statuses.append(r.status_code)

                # 6th attempt with the canonical number should be 429
                r = client.post("/api/v1/auth/sign-in", json={"login": mobile})
                statuses.append(r.status_code)

        assert all(s != 429 for s in statuses[:5]), (
            f"Unexpected 429 before limit reached: {statuses}"
        )
        assert statuses[5] == 429, (
            f"Expected 429 on 6th request (whitespace bypass closed) but got {statuses[5]}"
        )
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_rate_limit_is_per_login_not_global():
    """Requests from different login values are counted separately."""
    mobile_a = _unique_mobile()
    mobile_b = _unique_mobile()

    app.dependency_overrides[get_session] = _make_mock_session()
    try:
        with patch("app.api.v1.auth.AuthService") as MockService:
            instance = MockService.return_value
            instance.sign_in = AsyncMock(
                return_value={"message": "OTP sent", "mobile": mobile_a, "country_code": "91"}
            )

            with TestClient(app, raise_server_exceptions=False) as client:
                # Exhaust mobile_a's limit
                for _ in range(5):
                    client.post("/api/v1/auth/sign-in", json={"login": mobile_a})

                # mobile_b should still get through
                r = client.post("/api/v1/auth/sign-in", json={"login": mobile_b})
                assert r.status_code != 429, (
                    f"mobile_b was incorrectly rate-limited: {r.status_code}"
                )
    finally:
        app.dependency_overrides.pop(get_session, None)
