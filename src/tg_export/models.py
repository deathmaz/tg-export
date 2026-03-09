"""Data models for exported messages and channel info."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Reaction:
    emoji: str
    count: int


@dataclass
class ExportedMessage:
    id: int
    date: datetime
    date_full: str  # "DD.MM.YYYY HH:MM:SS UTC+HH:MM"
    date_short: str  # "HH:MM"
    sender_name: str
    sender_id: int | None
    text_html: str
    media_path: str | None = None  # Relative path to downloaded media
    media_html: str = ""
    reply_to_id: int | None = None
    forwarded_from: str | None = None
    is_service: bool = False
    service_text: str | None = None
    reactions: list[Reaction] = field(default_factory=list)
    views: int | None = None
    signature: str | None = None


@dataclass
class MessageGroup:
    """A message with display metadata for rendering."""
    message: ExportedMessage
    joined: bool = False  # Same sender as previous, within time window
    initials: str = ""
    userpic_color_class: str = "userpic1"


@dataclass
class ChannelInfo:
    id: int
    title: str
    username: str | None = None
    member_count: int | None = None
    message_count: int = 0


@dataclass
class PageInfo:
    page_number: int
    filename: str  # "messages.html", "messages2.html", etc.
    has_prev: bool = False
    has_next: bool = False
    prev_url: str | None = None
    next_url: str | None = None


@dataclass
class ExportConfig:
    output_dir: str = "./export"
    from_date: datetime | None = None
    to_date: datetime | None = None
    limit: int | None = None
    download_media: bool = True
    max_media_size_bytes: int = 50 * 1024 * 1024  # 50 MB
    msgs_per_page: int = 1000
    use_takeout: bool = True
    wait_time: float | None = None  # None = auto (0 with takeout, 2 without)
