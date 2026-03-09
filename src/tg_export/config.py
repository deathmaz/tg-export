"""Configuration loading and duration parsing."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_SESSION_DIR = Path.home() / ".tg-export"


def parse_duration(duration_str: str) -> timedelta:
    """Parse a duration string like '24h', '7d', '2w' into a timedelta."""
    match = re.fullmatch(r"(\d+)\s*([hdwm])", duration_str.strip().lower())
    if not match:
        raise ValueError(
            f"Invalid duration '{duration_str}'. Use format like: 24h, 7d, 2w, 1m"
        )
    value = int(match.group(1))
    unit = match.group(2)
    if unit == "h":
        return timedelta(hours=value)
    elif unit == "d":
        return timedelta(days=value)
    elif unit == "w":
        return timedelta(weeks=value)
    elif unit == "m":
        return timedelta(days=value * 30)
    raise ValueError(f"Unknown unit '{unit}'")


def parse_date(date_str: str) -> datetime:
    """Parse an ISO date or datetime string into a timezone-aware datetime."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Invalid date '{date_str}'. Use ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")


def compute_from_date(last: str | None, from_date: str | None) -> datetime | None:
    """Compute the from_date from --last or --from-date flags."""
    if last:
        delta = parse_duration(last)
        return datetime.now(timezone.utc) - delta
    if from_date:
        return parse_date(from_date)
    return None


def compute_to_date(to_date: str | None) -> datetime | None:
    """Compute the to_date from --to-date flag."""
    if to_date:
        return parse_date(to_date)
    return None
