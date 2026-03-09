"""Tests for configuration parsing."""
from datetime import datetime, timedelta, timezone

import pytest

from tg_export.config import compute_from_date, compute_to_date, parse_date, parse_duration


class TestParseDuration:
    def test_hours(self):
        assert parse_duration("24h") == timedelta(hours=24)

    def test_days(self):
        assert parse_duration("7d") == timedelta(days=7)

    def test_weeks(self):
        assert parse_duration("2w") == timedelta(weeks=2)

    def test_months(self):
        assert parse_duration("1m") == timedelta(days=30)

    def test_single_unit(self):
        assert parse_duration("1h") == timedelta(hours=1)

    def test_large_value(self):
        assert parse_duration("365d") == timedelta(days=365)

    def test_whitespace_stripped(self):
        assert parse_duration("  7d  ") == timedelta(days=7)

    def test_uppercase(self):
        assert parse_duration("7D") == timedelta(days=7)

    def test_invalid_no_unit(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("24")

    def test_invalid_no_number(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("h")

    def test_invalid_unit(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("24x")

    def test_invalid_empty(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("")


class TestParseDate:
    def test_date_only(self):
        dt = parse_date("2025-01-15")
        assert dt == datetime(2025, 1, 15, tzinfo=timezone.utc)

    def test_datetime(self):
        dt = parse_date("2025-01-15T10:30:00")
        assert dt == datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_timezone_aware(self):
        dt = parse_date("2025-06-01")
        assert dt.tzinfo == timezone.utc

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Invalid date"):
            parse_date("15/01/2025")

    def test_invalid_gibberish(self):
        with pytest.raises(ValueError, match="Invalid date"):
            parse_date("not-a-date")


class TestComputeFromDate:
    def test_last_takes_precedence(self):
        result = compute_from_date("24h", "2025-01-01")
        # --last should win; result should be ~24h ago, not 2025-01-01
        assert result > datetime(2025, 1, 1, tzinfo=timezone.utc)

    def test_from_date_fallback(self):
        result = compute_from_date(None, "2025-01-01")
        assert result == datetime(2025, 1, 1, tzinfo=timezone.utc)

    def test_both_none(self):
        assert compute_from_date(None, None) is None


class TestComputeToDate:
    def test_with_date(self):
        result = compute_to_date("2025-03-01")
        assert result == datetime(2025, 3, 1, tzinfo=timezone.utc)

    def test_none(self):
        assert compute_to_date(None) is None
