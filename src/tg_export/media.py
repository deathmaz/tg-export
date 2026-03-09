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


def get_media_size(message) -> int | None:
    """Get the size of the media in bytes, if available."""
    media = message.media
    if isinstance(media, MessageMediaDocument) and media.document:
        doc = media.document
        if isinstance(doc, Document):
            return doc.size
    if isinstance(media, MessageMediaPhoto) and media.photo:
        # Photos don't have a simple size; allow them
        return 0
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
        return '<div class="media_wrap clearfix"><div class="fill pull_left media_photo"></div><div class="body">Photo</div></div>'

    if message.video or message.video_note:
        label = "Video message" if message.video_note else "Video"
        duration = ""
        if hasattr(message.media, "document") and message.media.document:
            for attr in message.media.document.attributes:
                if hasattr(attr, "duration"):
                    secs = int(attr.duration)
                    duration = f" ({secs // 60}:{secs % 60:02d})"
                    break
        if media_path:
            return (
                f'<a class="media_wrap clearfix pull_left" href="{html.escape(media_path)}">'
                f'<div class="fill pull_left media_video"></div>'
                f'<div class="body">{label}{html.escape(duration)}</div>'
                f'</a>'
            )
        return f'<div class="media_wrap clearfix"><div class="fill pull_left media_video"></div><div class="body">{label}{html.escape(duration)}</div></div>'

    if message.voice:
        duration = ""
        if hasattr(message.media, "document") and message.media.document:
            for attr in message.media.document.attributes:
                if hasattr(attr, "duration"):
                    secs = int(attr.duration)
                    duration = f" ({secs // 60}:{secs % 60:02d})"
                    break
        if media_path:
            return (
                f'<a class="media_wrap clearfix pull_left" href="{html.escape(media_path)}">'
                f'<div class="fill pull_left media_voice_message"></div>'
                f'<div class="body">Voice message{html.escape(duration)}</div>'
                f'</a>'
            )
        return f'<div class="media_wrap clearfix"><div class="fill pull_left media_voice_message"></div><div class="body">Voice message{html.escape(duration)}</div></div>'

    if message.sticker:
        if media_path:
            return f'<a class="sticker_wrap pull_left" href="{html.escape(media_path)}"><img class="sticker" src="{html.escape(media_path)}" style="max-width: 256px;"></a>'
        emoji = ""
        if hasattr(message.media, "document") and message.media.document:
            for attr in message.media.document.attributes:
                if hasattr(attr, "alt"):
                    emoji = attr.alt
                    break
        return f'<div class="media_wrap clearfix"><div class="fill pull_left media_file"></div><div class="body">Sticker {html.escape(emoji)}</div></div>'

    if message.audio:
        title = "Audio file"
        if hasattr(message.media, "document") and message.media.document:
            for attr in message.media.document.attributes:
                if hasattr(attr, "title") and attr.title:
                    title = attr.title
                    break
        if media_path:
            return (
                f'<a class="media_wrap clearfix pull_left" href="{html.escape(media_path)}">'
                f'<div class="fill pull_left media_music_file"></div>'
                f'<div class="body">{html.escape(title)}</div>'
                f'</a>'
            )
        return f'<div class="media_wrap clearfix"><div class="fill pull_left media_music_file"></div><div class="body">{html.escape(title)}</div></div>'

    if message.document:
        name = "File"
        if hasattr(message.media, "document") and message.media.document:
            for attr in message.media.document.attributes:
                if hasattr(attr, "file_name") and attr.file_name:
                    name = attr.file_name
                    break
        if media_path:
            return (
                f'<a class="media_wrap clearfix pull_left" href="{html.escape(media_path)}">'
                f'<div class="fill pull_left media_file"></div>'
                f'<div class="body">{html.escape(name)}</div>'
                f'</a>'
            )
        return f'<div class="media_wrap clearfix"><div class="fill pull_left media_file"></div><div class="body">{html.escape(name)}</div></div>'

    if isinstance(message.media, MessageMediaPoll):
        poll = message.media.poll
        question = poll.question
        # question can be a string or TextWithEntities
        q_text = question if isinstance(question, str) else getattr(question, "text", "Poll")
        return f'<div class="media_wrap clearfix"><div class="fill pull_left media_poll"></div><div class="body">Poll: {html.escape(q_text)}</div></div>'

    if isinstance(message.media, MessageMediaGeo):
        geo = message.media.geo
        return f'<div class="media_wrap clearfix"><div class="fill pull_left media_location"></div><div class="body">Location ({geo.lat:.6f}, {geo.long:.6f})</div></div>'

    if isinstance(message.media, MessageMediaContact):
        c = message.media
        name = f"{c.first_name} {c.last_name}".strip()
        return f'<div class="media_wrap clearfix"><div class="fill pull_left media_contact"></div><div class="body">{html.escape(name)}<br>{html.escape(c.phone_number)}</div></div>'

    if isinstance(message.media, MessageMediaWebPage):
        wp = message.media.webpage
        if hasattr(wp, "title") and wp.title:
            return f'<a class="media_wrap clearfix pull_left" href="{html.escape(wp.url)}"><div class="fill pull_left media_webpage"></div><div class="body">{html.escape(wp.title)}</div></a>'
        return ""

    return ""
