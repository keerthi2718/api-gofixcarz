"""Unit tests for analytics date bucketing logic."""
from datetime import date, timedelta

import pytest

from app.services.analytics_service import _date_label, _period_dates


class FakeDatetime:
    """Simulate a datetime with a .date() method."""
    def __init__(self, d: date):
        self._d = d

    def date(self):
        return self._d


def test_date_label_day():
    bucket = FakeDatetime(date(2026, 7, 17))
    assert _date_label(bucket, "day") == "2026-07-17"


def test_date_label_week():
    bucket = FakeDatetime(date(2026, 7, 13))  # Monday of week 28
    label = _date_label(bucket, "week")
    assert "Week" in label
    assert "2026" in label


def test_date_label_month():
    bucket = FakeDatetime(date(2026, 7, 1))
    assert _date_label(bucket, "month") == "Jul 2026"


def test_date_label_none():
    assert _date_label(None, "day") == ""


def test_period_dates_daily():
    s, e, trunc = _period_dates("daily")
    today = date.today()
    assert e == today
    assert s == today - timedelta(days=6)
    assert trunc == "day"


def test_period_dates_weekly():
    s, e, trunc = _period_dates("weekly")
    today = date.today()
    assert e == today
    assert trunc == "week"
    assert (e - s).days == 28


def test_period_dates_monthly():
    _, _, trunc = _period_dates("monthly")
    assert trunc == "month"


def test_period_dates_custom():
    start = date(2026, 1, 1)
    end = date(2026, 3, 31)
    s, e, trunc = _period_dates("custom", start, end)
    assert s == start
    assert e == end
    assert trunc == "day"


def test_period_dates_custom_defaults_today():
    today = date.today()
    s, e, trunc = _period_dates("custom")
    assert e == today
