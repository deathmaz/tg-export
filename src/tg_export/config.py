"""Configuration loading and duration parsing."""
from __future__ import annotations

import re
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_SESSION_DIR = Path.home() / ".tg-export"
DEFAULT_CONFIG_PATH = DEFAULT_SESSION_DIR / "config.toml"
DEFAULT_CHECKPOINT_PATH = DEFAULT_SESSION_DIR / "checkpoint.toml"
CHECKPOINT_KEY = "last_export"


DEFAULT_CONFIG_CONTENT = """\
# tg-export configuration file

# Default channels to export when none specified on the command line.
# Accepts @usernames, invite links, or numeric IDs.
# channels = [
#     "@channel1",
#     "@channel2",
#     "-1001234567890",
# ]

# Default output directory (default: ./export)
# output = "./export"
"""


def load_config(config_path: str | None = None) -> dict:
    """Load config from a TOML file. Returns empty dict if file doesn't exist."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.is_file():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


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
        name = last.strip().lower()
        if name == "today":
            return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        if name == "yesterday":
            return (datetime.now(timezone.utc) - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
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


def load_checkpoint(path: Path | None = None) -> datetime | None:
    """Load the stored export checkpoint datetime, or None if not set."""
    cp_path = path or DEFAULT_CHECKPOINT_PATH
    try:
        with open(cp_path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return None
    value = data.get(CHECKPOINT_KEY)
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def save_checkpoint(dt: datetime, path: Path | None = None) -> None:
    """Persist the given datetime as the export checkpoint."""
    cp_path = path or DEFAULT_CHECKPOINT_PATH
    cp_path.parent.mkdir(parents=True, exist_ok=True)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    cp_path.write_text(f'{CHECKPOINT_KEY} = "{dt.isoformat()}"\n')


def clear_checkpoint(path: Path | None = None) -> bool:
    """Delete the checkpoint file if present. Returns True if something was removed."""
    cp_path = path or DEFAULT_CHECKPOINT_PATH
    try:
        cp_path.unlink()
        return True
    except FileNotFoundError:
        return False
