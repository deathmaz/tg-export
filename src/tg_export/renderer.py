"""HTML rendering orchestrator."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

from rich.console import Console

from tg_export.config import resolve_tz
from tg_export.models import ChannelInfo, ExportConfig, ExportedMessage, MessageGroup
from tg_export.pagination import build_page_info, paginate_messages

import jinja2

console = Console()

# Telegram Desktop assigns userpic colors based on user ID
USERPIC_COLORS = ["userpic1", "userpic2", "userpic3", "userpic4", "userpic5", "userpic6", "userpic7", "userpic8"]

# Time window for grouping consecutive messages from the same sender
_GROUP_WINDOW = timedelta(seconds=60)


def userpic_color(user_id: int | None) -> str:
    if user_id is None:
        return USERPIC_COLORS[0]
    return USERPIC_COLORS[user_id % len(USERPIC_COLORS)]


def get_initials(name: str) -> str:
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[0].upper() if name else "?"


def format_utc_offset(dt: datetime) -> str:
    """Format a tz-aware datetime's UTC offset as 'UTC+HH:MM' or 'UTC-HH:MM'."""
    offset = dt.utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    return f"UTC{sign}{total_minutes // 60:02d}:{total_minutes % 60:02d}"


class HtmlRenderer:
    def __init__(self, output_dir: Path, config: ExportConfig, tz: tzinfo | None = None):
        self.output_dir = output_dir
        self.config = config
        self.tz = tz if tz is not None else resolve_tz(config.timezone)
        self._resources_dir = Path(__file__).parent / "resources"
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self._resources_dir / "templates")),
            autoescape=False,
        )
        self.env.filters["date_full"] = self._filter_date_full
        self.env.filters["date_short"] = self._filter_date_short

    def _filter_date_full(self, dt: datetime | None) -> str:
        if dt is None:
            return ""
        local = dt.astimezone(self.tz)
        return local.strftime("%d.%m.%Y %H:%M:%S ") + format_utc_offset(local)

    def _filter_date_short(self, dt: datetime | None) -> str:
        if dt is None:
            return ""
        return dt.astimezone(self.tz).strftime("%H:%M")

    def copy_static_assets(self) -> None:
        """Copy CSS, JS, and images to the output directory."""
        for subdir in ("css", "js", "images"):
            src = self._resources_dir / subdir
            dst = self.output_dir / subdir
            if src.exists():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)

    def save_channel_meta(self, channel: ChannelInfo, chat_dir: Path) -> None:
        """Save channel metadata to a JSON file in the chat directory."""
        meta = {
            "id": channel.id,
            "title": channel.title,
            "username": channel.username,
            "message_count": channel.message_count,
        }
        (chat_dir / "channel.json").write_text(json.dumps(meta), encoding="utf-8")

    def _load_all_channels(self) -> list[ChannelInfo]:
        """Scan chats/ directory and load channel metadata from all exports."""
        chats_dir = self.output_dir / "chats"
        if not chats_dir.exists():
            return []
        channels = []
        for chat_dir in sorted(chats_dir.iterdir()):
            meta_file = chat_dir / "channel.json"
            if meta_file.exists():
                meta = json.loads(meta_file.read_text())
                channels.append(ChannelInfo(
                    id=meta["id"],
                    title=meta["title"],
                    username=meta.get("username"),
                    message_count=meta.get("message_count", 0),
                ))
        return channels

    def render_index(self, channels: list[ChannelInfo] | None = None) -> None:
        """Generate export_results.html listing all exported channels."""
        if channels is None:
            channels = self._load_all_channels()
        template = self.env.get_template("index.html.j2")
        html = template.render(channels=channels)
        (self.output_dir / "export_results.html").write_text(html, encoding="utf-8")

    def render_channel(
        self, channel: ChannelInfo, messages: list[ExportedMessage], chat_dir: Path
    ) -> None:
        """Generate paginated message HTML files for a channel."""
        pages = paginate_messages(messages, self.config.msgs_per_page)
        total_pages = len(pages)
        template = self.env.get_template("messages.html.j2")

        console.print(f"  Generating {total_pages} page(s)...")

        for i, page_messages in enumerate(pages):
            page_num = i + 1
            page_info = build_page_info(page_num, total_pages)
            grouped = self._group_messages(page_messages)

            html = template.render(
                channel_name=channel.title,
                message_groups=grouped,
                pagination=page_info,
            )
            (chat_dir / page_info.filename).write_text(html, encoding="utf-8")

    def _group_messages(self, messages: list[ExportedMessage]) -> list[MessageGroup | dict]:
        """Group consecutive messages from the same sender, inserting date separators."""
        result: list[MessageGroup | dict] = []
        prev_msg: ExportedMessage | None = None
        prev_date_str: str | None = None

        for msg in messages:
            # Insert date separator if the date changed (in configured timezone)
            date_str = msg.date.astimezone(self.tz).strftime("%B %d, %Y")
            if date_str != prev_date_str:
                result.append({"type": "date_separator", "date": date_str})
                prev_date_str = date_str
                prev_msg = None  # Reset grouping after date separator

            if msg.is_service:
                result.append({"type": "service", "text": msg.service_text, "id": msg.id})
                prev_msg = None
                continue

            # Determine if this message should be joined to the previous
            joined = False
            if (
                prev_msg
                and not prev_msg.is_service
                and prev_msg.sender_id is not None
                and prev_msg.sender_id == msg.sender_id
                and (msg.date - prev_msg.date) < _GROUP_WINDOW
                and not msg.forwarded_from
            ):
                joined = True

            group = MessageGroup(
                message=msg,
                joined=joined,
                initials=get_initials(msg.sender_name) if not joined else "",
                userpic_color_class=userpic_color(msg.sender_id) if not joined else "",
            )
            result.append(group)
            prev_msg = msg

        return result
