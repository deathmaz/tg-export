"""Tests for configuration parsing."""
import tomllib
from datetime import datetime, timedelta, timezone

import pytest

from tg_export.config import (
    clear_checkpoint,
    compute_from_date,
    compute_to_date,
    load_checkpoint,
    load_config,
    parse_date,
    parse_duration,
    save_checkpoint,
)


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

    def test_today(self):
        result = compute_from_date("today", None)
        now = datetime.now(timezone.utc)
        assert result == now.replace(hour=0, minute=0, second=0, microsecond=0)

    def test_yesterday(self):
        result = compute_from_date("yesterday", None)
        now = datetime.now(timezone.utc)
        expected = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        assert result == expected


class TestComputeToDate:
    def test_with_date(self):
        result = compute_to_date("2025-03-01")
        assert result == datetime(2025, 3, 1, tzinfo=timezone.utc)

    def test_none(self):
        assert compute_to_date(None) is None


class TestLoadConfig:
    def test_load_valid_config(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'channels = ["@channel1", "-1001234567890"]\n'
            'output = "/tmp/export"\n'
        )
        cfg = load_config(str(config_file))
        assert cfg["channels"] == ["@channel1", "-1001234567890"]
        assert cfg["output"] == "/tmp/export"

    def test_file_not_found(self, tmp_path):
        cfg = load_config(str(tmp_path / "nonexistent.toml"))
        assert cfg == {}

    def test_partial_config(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('channels = ["@only_channels"]\n')
        cfg = load_config(str(config_file))
        assert cfg["channels"] == ["@only_channels"]
        assert "output" not in cfg

    def test_empty_config(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        cfg = load_config(str(config_file))
        assert cfg == {}

    def test_invalid_toml(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("this is not valid toml [[[")
        with pytest.raises(tomllib.TOMLDecodeError):
            load_config(str(config_file))


class TestCheckpoint:
    def test_save_and_load_roundtrip(self, tmp_path):
        cp = tmp_path / "checkpoint.toml"
        dt = datetime(2026, 4, 20, 17, 42, 3, tzinfo=timezone.utc)
        save_checkpoint(dt, path=cp)
        assert cp.is_file()
        assert load_checkpoint(path=cp) == dt

    def test_load_missing_returns_none(self, tmp_path):
        cp = tmp_path / "nope.toml"
        assert load_checkpoint(path=cp) is None

    def test_load_empty_key_returns_none(self, tmp_path):
        cp = tmp_path / "checkpoint.toml"
        cp.write_text("")
        assert load_checkpoint(path=cp) is None

    def test_save_creates_parent_dir(self, tmp_path):
        cp = tmp_path / "nested" / "dir" / "checkpoint.toml"
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        save_checkpoint(dt, path=cp)
        assert cp.is_file()

    def test_save_naive_datetime_assumed_utc(self, tmp_path):
        cp = tmp_path / "checkpoint.toml"
        naive = datetime(2026, 4, 20, 12, 0, 0)
        save_checkpoint(naive, path=cp)
        loaded = load_checkpoint(path=cp)
        assert loaded == naive.replace(tzinfo=timezone.utc)

    def test_clear_removes_file(self, tmp_path):
        cp = tmp_path / "checkpoint.toml"
        save_checkpoint(datetime(2026, 1, 1, tzinfo=timezone.utc), path=cp)
        assert clear_checkpoint(path=cp) is True
        assert not cp.exists()

    def test_clear_missing_is_noop(self, tmp_path):
        cp = tmp_path / "nope.toml"
        assert clear_checkpoint(path=cp) is False
