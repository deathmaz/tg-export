"""Media download and path management."""
from __future__ import annotations

import html
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.types import (
    Document,
    MessageMediaContact,
    MessageMediaDocument,
    MessageMediaGeo,
    MessageMediaPhoto,
    MessageMediaPoll,
    MessageMediaWebPage,
)


def get_media_subdir(message) -> str | None:
    """Determine the subdirectory for a message's media, matching tdesktop conventions."""
    if message.photo:
        return "photos"
    if message.video:
        return "video_files"
    if message.voice:
        return "voice_messages"
    if message.video_note:
        return "round_video_messages"
    if message.sticker:
        return "stickers"
    if message.audio:
        return "audio_files"
    if message.document:
        return "files"
    return None


def _get_doc_attr(message, attr_name: str, default=None):
    """Extract an attribute from a message's document attributes."""
    media = message.media
    if not isinstance(media, MessageMediaDocument) or not media.document:
        return default
    for attr in media.document.attributes:
        val = getattr(attr, attr_name, None)
        if val is not None:
            return val
    return default


def _get_duration_str(message) -> str:
    """Get formatted duration string from a media message."""
    duration = _get_doc_attr(message, "duration")
    if duration is not None:
        secs = int(duration)
        return f" ({secs // 60}:{secs % 60:02d})"
    return ""


def _media_block(css_class: str, label: str, media_path: str | None) -> str:
    """Render a media HTML block, with link if media_path is available."""
    escaped_label = html.escape(label) if label else label
    if media_path:
        return (
            f'<a class="media_wrap clearfix pull_left" href="{html.escape(media_path)}">'
            f'<div class="fill pull_left {css_class}"></div>'
            f'<div class="body">{escaped_label}</div>'
            f'</a>'
        )
    return (
        f'<div class="media_wrap clearfix">'
        f'<div class="fill pull_left {css_class}"></div>'
        f'<div class="body">{escaped_label}</div>'
        f'</div>'
    )


def get_media_size(message) -> int | None:
    """Get the size of the media in bytes, if available."""
    media = message.media
    if isinstance(media, MessageMediaDocument) and media.document:
        doc = media.document
        if isinstance(doc, Document):
            return doc.size
    if isinstance(media, MessageMediaPhoto) and media.photo:
        return 0  # Photos don't have a simple size; allow them
    return None


async def download_media(
    client: TelegramClient,
    message,
    chat_dir: Path,
    max_size_bytes: int,
) -> str | None:
    """Download message media and return the relative path from chat_dir."""
    if not message.media:
        return None

    # Skip non-downloadable types
    if isinstance(message.media, (MessageMediaGeo, MessageMediaContact, MessageMediaPoll, MessageMediaWebPage)):
        return None

    subdir = get_media_subdir(message)
    if not subdir:
        return None

    # Check size limit
    size = get_media_size(message)
    if size is not None and size > max_size_bytes:
        return None

    dest_dir = chat_dir / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        path = await client.download_media(message, file=str(dest_dir))
        if path:
            return str(Path(path).relative_to(chat_dir))
    except Exception:
        pass
    return None


def render_media_html(message, media_path: str | None) -> str:
    """Generate the HTML block for a message's media, matching tdesktop format."""
    if not message.media:
        return ""

    if isinstance(message.media, MessageMediaPhoto):
        if media_path:
            return (
                f'<a class="photo_wrap clearfix pull_left" href="{html.escape(media_path)}">'
                f'<img class="photo" src="{html.escape(media_path)}" style="max-width: 480px;">'
                f'</a>'
            )
        return _media_block("media_photo", "Photo", None)

    if message.video or message.video_note:
        label = "Video message" if message.video_note else "Video"
        return _media_block("media_video", label + _get_duration_str(message), media_path)

    if message.voice:
        return _media_block("media_voice_message", "Voice message" + _get_duration_str(message), media_path)

    if message.sticker:
        if media_path:
            return (
                f'<a class="sticker_wrap pull_left" href="{html.escape(media_path)}">'
                f'<img class="sticker" src="{html.escape(media_path)}" style="max-width: 256px;">'
                f'</a>'
            )
        emoji = _get_doc_attr(message, "alt", "")
        return _media_block("media_file", f"Sticker {emoji}", None)

    if message.audio:
        title = _get_doc_attr(message, "title", "Audio file")
        return _media_block("media_music_file", title, media_path)

    if message.document:
        name = _get_doc_attr(message, "file_name", "File")
        return _media_block("media_file", name, media_path)

    if isinstance(message.media, MessageMediaPoll):
        poll = message.media.poll
        question = poll.question
        q_text = question if isinstance(question, str) else getattr(question, "text", "Poll")
        return _media_block("media_poll", f"Poll: {q_text}", None)

    if isinstance(message.media, MessageMediaGeo):
        geo = message.media.geo
        return _media_block("media_location", f"Location ({geo.lat:.6f}, {geo.long:.6f})", None)

    if isinstance(message.media, MessageMediaContact):
        c = message.media
        name = f"{c.first_name} {c.last_name}".strip()
        return _media_block("media_contact", f"{name}\n{c.phone_number}", None)

    if isinstance(message.media, MessageMediaWebPage):
        wp = message.media.webpage
        if hasattr(wp, "title") and wp.title:
            return (
                f'<a class="media_wrap clearfix pull_left" href="{html.escape(wp.url)}">'
                f'<div class="fill pull_left media_webpage"></div>'
                f'<div class="body">{html.escape(wp.title)}</div>'
                f'</a>'
            )
        return ""

    return ""
