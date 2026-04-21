"""Configuration loading and duration parsing."""
from __future__ import annotations

import re
import tomllib
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

# IANA timezone name used for interpreting --last today/yesterday, bare dates,
# and for rendering timestamps. Omit or leave empty to use the system timezone.
# timezone = "Europe/Berlin"
"""


def resolve_tz(name: str | None) -> tzinfo:
    """Resolve a timezone by IANA name, or return system local tz when name is None/empty."""
    if name:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone '{name}'. Use an IANA name like 'Europe/Berlin'.") from exc
    local = datetime.now().astimezone().tzinfo
    return local or timezone.utc


def ensure_utc(dt: datetime) -> datetime:
    """Return dt as a UTC-aware datetime; naive inputs are assumed to already be UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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


def parse_date(date_str: str, tz: tzinfo | None = None) -> datetime:
    """Parse an ISO date or datetime string into a UTC-aware datetime.

    Naive inputs (no offset) are interpreted in `tz` (defaults to UTC for back-compat),
    then converted to UTC. Inputs with explicit offset are honored as-is.
    """
    local_tz = tz or timezone.utc
    try:
        dt = datetime.fromisoformat(date_str)
    except ValueError:
        raise ValueError(f"Invalid date '{date_str}'. Use ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_tz)
    return dt.astimezone(timezone.utc)


def compute_from_date(last: str | None, from_date: str | None, tz: tzinfo | None = None) -> datetime | None:
    """Compute the from_date from --last or --from-date flags.

    Calendar shortcuts (today/yesterday) and bare dates are interpreted in `tz`.
    Durations are TZ-agnostic (now minus delta).
    """
    local_tz = tz or timezone.utc
    if last:
        name = last.strip().lower()
        if name == "today":
            midnight_local = datetime.now(local_tz).replace(hour=0, minute=0, second=0, microsecond=0)
            return midnight_local.astimezone(timezone.utc)
        if name == "yesterday":
            midnight_local = datetime.now(local_tz).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            return midnight_local.astimezone(timezone.utc)
        delta = parse_duration(last)
        return datetime.now(timezone.utc) - delta
    if from_date:
        return parse_date(from_date, local_tz)
    return None


def compute_to_date(to_date: str | None, tz: tzinfo | None = None) -> datetime | None:
    """Compute the to_date from --to-date flag."""
    if to_date:
        return parse_date(to_date, tz or timezone.utc)
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
    return ensure_utc(datetime.fromisoformat(value))


def save_checkpoint(dt: datetime, path: Path | None = None) -> None:
    """Persist the given datetime as the export checkpoint (stored as UTC ISO)."""
    cp_path = path or DEFAULT_CHECKPOINT_PATH
    cp_path.parent.mkdir(parents=True, exist_ok=True)
    cp_path.write_text(f'{CHECKPOINT_KEY} = "{ensure_utc(dt).isoformat()}"\n')


def clear_checkpoint(path: Path | None = None) -> bool:
    """Delete the checkpoint file if present. Returns True if something was removed."""
    cp_path = path or DEFAULT_CHECKPOINT_PATH
    try:
        cp_path.unlink()
        return True
    except FileNotFoundError:
        return False
