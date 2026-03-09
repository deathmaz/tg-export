"""HTML rendering orchestrator."""
from __future__ import annotations

import shutil
from datetime import timedelta
from importlib import resources as pkg_resources
from pathlib import Path

from rich.console import Console

from tg_export.models import ChannelInfo, ExportConfig, ExportedMessage, MessageGroup
from tg_export.pagination import build_page_info, paginate_messages

import jinja2

console = Console()

# Telegram Desktop assigns userpic colors based on user ID
_COLOR_CLASSES = ["userpic1", "userpic2", "userpic3", "userpic4", "userpic5", "userpic6", "userpic7", "userpic8"]

# Time window for grouping consecutive messages from the same sender
_GROUP_WINDOW = timedelta(seconds=60)


def _userpic_color(user_id: int | None) -> str:
    if user_id is None:
        return _COLOR_CLASSES[0]
    return _COLOR_CLASSES[user_id % len(_COLOR_CLASSES)]


def _get_initials(name: str) -> str:
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[0].upper() if name else "?"


class HtmlRenderer:
    def __init__(self, output_dir: Path, config: ExportConfig):
        self.output_dir = output_dir
        self.config = config
        self._resources_dir = Path(__file__).parent / "resources"
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self._resources_dir / "templates")),
            autoescape=False,
        )

    def copy_static_assets(self) -> None:
        """Copy CSS, JS, and images to the output directory."""
        for subdir in ("css", "js", "images"):
            src = self._resources_dir / subdir
            dst = self.output_dir / subdir
            if src.exists():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)

    def render_index(self, channels: list[ChannelInfo]) -> None:
        """Generate export_results.html listing exported channels."""
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
            # Insert date separator if the date changed
            date_str = msg.date.strftime("%B %d, %Y")
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
                initials=_get_initials(msg.sender_name) if not joined else "",
                userpic_color_class=_userpic_color(msg.sender_id) if not joined else "",
            )
            result.append(group)
            prev_msg = msg

        return result
