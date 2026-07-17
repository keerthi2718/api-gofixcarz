"""Unit tests for OTP generation and expiry logic."""
import time
from datetime import datetime, timezone

import pytest

from app.core.security import generate_otp, get_otp_expiry


def test_otp_is_numeric():
    otp = generate_otp(6)
    assert otp.isdigit()


def test_otp_length():
    for length in (4, 6, 8):
        otp = generate_otp(length)
        assert len(otp) == length, f"Expected length {length}, got {len(otp)}"


def test_otp_uniqueness():
    otps = {generate_otp(6) for _ in range(100)}
    # With 10^6 possibilities, 100 samples are extremely unlikely to all match
    assert len(otps) > 1


def test_otp_expiry_in_future():
    before = datetime.now(timezone.utc)
    expiry = get_otp_expiry()
    after = datetime.now(timezone.utc)
    assert expiry > before
    assert expiry > after


def test_otp_expiry_within_settings():
    from app.core.config import settings
    expiry = get_otp_expiry()
    delta = (expiry - datetime.now(timezone.utc)).total_seconds()
    # Should be within ±5s of OTP_EXPIRY_SECONDS
    assert abs(delta - settings.OTP_EXPIRY_SECONDS) < 5
