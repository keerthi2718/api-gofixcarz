"""Tests that OTP endpoints enforce per-mobile rate limits.

Strategy:
- Override get_session to avoid a real DB connection.
- Patch AuthService so each call returns a canned success response.
- Use a unique mobile per test run to avoid counter cross-contamination.
- Assert requests 1-5 succeed (non-429) and request 6 is HTTP 429.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

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
    """The 6th /sign-in call from the same mobile in one minute must return 429."""
    mobile = _unique_mobile()

    app.dependency_overrides[get_session] = _make_mock_session()
    try:
        canned = {"message": "OTP sent", "mobile": mobile}
        with patch("app.api.v1.auth.AuthService") as MockService:
            instance = MockService.return_value
            instance.sign_in = AsyncMock(return_value=canned)

            with TestClient(app, raise_server_exceptions=False) as client:
                statuses = []
                for _ in range(6):
                    r = client.post(
                        "/api/v1/auth/sign-in",
                        json={"mobile": mobile},
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
        canned = {"message": "OTP sent", "mobile": mobile}
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
            f"Unexpected 429 in first 5 requests: {statuses}"
        )
        assert statuses[5] == 429, (
            f"Expected 429 on 6th request but got {statuses[5]}"
        )
    finally:
        app.dependency_overrides.pop(get_session, None)


# ── different mobiles share no counter ───────────────────────────────────────

def test_rate_limit_normalizes_mobile_whitespace():
    """Mobile numbers with leading/trailing spaces share the same rate-limit bucket.

    A caller cannot bypass the 5/min limit by padding the number with spaces.
    """
    mobile = _unique_mobile()
    padded = f"  {mobile}  "

    app.dependency_overrides[get_session] = _make_mock_session()
    try:
        canned = {"message": "OTP sent", "mobile": mobile}
        with patch("app.api.v1.auth.AuthService") as MockService:
            instance = MockService.return_value
            instance.sign_in = AsyncMock(return_value=canned)

            with TestClient(app, raise_server_exceptions=False) as client:
                statuses = []
                # 4 requests with the canonical number
                for _ in range(4):
                    r = client.post("/api/v1/auth/sign-in", json={"mobile": mobile})
                    statuses.append(r.status_code)

                # 1 request with a padded variant — still same bucket (total = 5)
                r = client.post("/api/v1/auth/sign-in", json={"mobile": padded})
                statuses.append(r.status_code)

                # 6th attempt with the canonical number should be 429
                r = client.post("/api/v1/auth/sign-in", json={"mobile": mobile})
                statuses.append(r.status_code)

        assert all(s != 429 for s in statuses[:5]), (
            f"Unexpected 429 before limit reached: {statuses}"
        )
        assert statuses[5] == 429, (
            f"Expected 429 on 6th request (whitespace bypass closed) but got {statuses[5]}"
        )
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_rate_limit_is_per_mobile_not_global():
    """Requests from different mobile numbers are counted separately."""
    mobile_a = _unique_mobile()
    mobile_b = _unique_mobile()

    app.dependency_overrides[get_session] = _make_mock_session()
    try:
        with patch("app.api.v1.auth.AuthService") as MockService:
            instance = MockService.return_value
            instance.sign_in = AsyncMock(
                side_effect=lambda d: {"message": "OTP sent", "mobile": d.mobile}
            )

            with TestClient(app, raise_server_exceptions=False) as client:
                # Exhaust mobile_a's limit
                for _ in range(5):
                    client.post("/api/v1/auth/sign-in", json={"mobile": mobile_a})

                # mobile_b should still get through
                r = client.post("/api/v1/auth/sign-in", json={"mobile": mobile_b})
                assert r.status_code != 429, (
                    f"mobile_b was incorrectly rate-limited: {r.status_code}"
                )
    finally:
        app.dependency_overrides.pop(get_session, None)
