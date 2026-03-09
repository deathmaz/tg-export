"""Message fetching from Telegram API."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from telethon import TelegramClient
from telethon.errors import TakeoutInitDelayError
from telethon.tl.types import Channel, Chat, User

from tg_export.formatters import format_message_text
from tg_export.media import download_media, render_media_html
from tg_export.models import ChannelInfo, ExportConfig, ExportedMessage, Reaction

console = Console()

# Telegram Desktop assigns userpic colors based on user ID
_COLOR_CLASSES = ["userpic1", "userpic2", "userpic3", "userpic4", "userpic5", "userpic6", "userpic7", "userpic8"]


def _userpic_color(user_id: int | None) -> str:
    if user_id is None:
        return _COLOR_CLASSES[0]
    return _COLOR_CLASSES[user_id % len(_COLOR_CLASSES)]


def _get_initials(name: str) -> str:
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return name[0].upper() if name else "?"


def _format_date_full(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M:%S UTC+00:00")


def _format_date_short(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _parse_channel_ref(channel_ref: str) -> str | int:
    """Parse channel reference — convert numeric strings to int for Telethon."""
    try:
        return int(channel_ref)
    except ValueError:
        return channel_ref


async def get_channel_info(client: TelegramClient, channel_ref: str) -> ChannelInfo:
    """Resolve a channel reference and get its info."""
    entity = await client.get_entity(_parse_channel_ref(channel_ref))
    title = getattr(entity, "title", None) or _entity_name(entity)
    username = getattr(entity, "username", None)
    desc = None
    member_count = None

    if isinstance(entity, (Channel, Chat)):
        try:
            full = await client.get_entity(entity)
            if hasattr(full, "participants_count"):
                member_count = full.participants_count
        except Exception:
            pass

    return ChannelInfo(
        id=entity.id,
        title=title,
        username=username,
        description=desc,
        member_count=member_count,
    )


def _entity_name(entity) -> str:
    if isinstance(entity, User):
        parts = [entity.first_name or "", entity.last_name or ""]
        return " ".join(p for p in parts if p) or "Deleted Account"
    return getattr(entity, "title", None) or "Unknown"


@asynccontextmanager
async def _takeout_or_client(client: TelegramClient, config: ExportConfig):
    """Use takeout session if configured, otherwise use the client directly."""
    if config.use_takeout:
        try:
            takeout_kwargs = dict(
                contacts=False,
                users=False,
                chats=True,
                megagroups=True,
                channels=True,
                files=config.download_media,
            )
            if config.download_media:
                takeout_kwargs["max_file_size"] = config.max_media_size_bytes
            async with client.takeout(**takeout_kwargs) as takeout:
                yield takeout
        except TakeoutInitDelayError as e:
            console.print(
                f"[yellow]Telegram requires waiting {e.seconds}s before takeout. "
                f"Falling back to normal mode.[/yellow]"
            )
            yield client
    else:
        yield client


async def _get_sender_name(client: TelegramClient, message) -> tuple[str, int | None]:
    """Get the sender's display name and ID."""
    sender = await message.get_sender()
    if sender is None:
        return ("Channel", None)
    name = _entity_name(sender)
    return (name, sender.id)


def _extract_reactions(message) -> list[Reaction]:
    """Extract reactions from a message."""
    if not hasattr(message, "reactions") or not message.reactions:
        return []
    results = message.reactions.results if message.reactions else []
    reactions = []
    for r in results:
        emoji = ""
        if hasattr(r.reaction, "emoticon"):
            emoji = r.reaction.emoticon
        elif hasattr(r.reaction, "document_id"):
            emoji = "custom"
        reactions.append(Reaction(emoji=emoji, count=r.count))
    return reactions


def _extract_forward_from(message) -> str | None:
    """Extract the forwarded-from info."""
    fwd = message.fwd_from
    if not fwd:
        return None
    if fwd.from_name:
        return fwd.from_name
    if fwd.from_id:
        # We'd need to resolve the entity; use a placeholder
        return "Forwarded"
    return "Forwarded"


def _is_service_message(message) -> bool:
    """Check if a message is a service/action message."""
    return message.action is not None


def _get_service_text(message) -> str:
    """Get a human-readable description of a service message action."""
    action = message.action
    if action is None:
        return ""
    # Get the class name and make it human-readable
    name = type(action).__name__
    name = name.replace("MessageAction", "")
    # Common service messages
    mapping = {
        "ChatAddUser": "joined the group",
        "ChatDeleteUser": "left the group",
        "ChatCreate": "created the group",
        "ChatEditTitle": "changed the group name",
        "ChatEditPhoto": "changed the group photo",
        "ChatDeletePhoto": "removed the group photo",
        "PinMessage": "pinned a message",
        "ChannelCreate": "created the channel",
        "ChatJoinedByLink": "joined by invite link",
        "ChatJoinedByRequest": "joined by request",
    }
    return mapping.get(name, name)


async def fetch_and_process_messages(
    client: TelegramClient,
    channel_info: ChannelInfo,
    config: ExportConfig,
    chat_dir: Path,
) -> list[ExportedMessage]:
    """Fetch all messages from a channel and process them."""
    messages: list[ExportedMessage] = []
    wait_time = config.wait_time if config.wait_time is not None else (0 if config.use_takeout else 2)

    # Load progress if resuming
    progress_file = chat_dir / ".progress"
    min_id = 0
    if progress_file.exists():
        try:
            progress_data = json.loads(progress_file.read_text())
            min_id = progress_data.get("last_id", 0)
            console.print(f"[cyan]Resuming from message ID {min_id}[/cyan]")
        except Exception:
            pass

    async with _takeout_or_client(client, config) as api:
        entity = await client.get_entity(channel_info.id)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching messages...", total=None)

            count = 0
            async for message in api.iter_messages(
                entity,
                limit=config.limit,
                offset_date=config.to_date,
                min_id=min_id,
                wait_time=wait_time,
            ):
                # Filter by from_date
                if config.from_date and message.date.replace(tzinfo=timezone.utc) < config.from_date:
                    break

                count += 1
                progress.update(task, completed=count, description=f"Fetching messages... ({count})")

                if _is_service_message(message):
                    exported = ExportedMessage(
                        id=message.id,
                        date=message.date,
                        date_full=_format_date_full(message.date),
                        date_short=_format_date_short(message.date),
                        sender_name="",
                        sender_id=None,
                        text_html="",
                        is_service=True,
                        service_text=_get_service_text(message),
                    )
                    messages.append(exported)
                    continue

                sender_name, sender_id = await _get_sender_name(client, message)
                text_html = format_message_text(message.text or "", message.entities)

                # Download media
                media_path = None
                if config.download_media and message.media:
                    media_path = await download_media(
                        client, message, chat_dir, config.max_media_size_bytes
                    )

                media_html = render_media_html(message, media_path)
                reactions = _extract_reactions(message)
                forwarded_from = _extract_forward_from(message)

                exported = ExportedMessage(
                    id=message.id,
                    date=message.date,
                    date_full=_format_date_full(message.date),
                    date_short=_format_date_short(message.date),
                    sender_name=sender_name,
                    sender_id=sender_id,
                    text_html=text_html,
                    media_type=None,
                    media_path=media_path,
                    media_html=media_html,
                    reply_to_id=getattr(message.reply_to, "reply_to_msg_id", None) if message.reply_to else None,
                    forwarded_from=forwarded_from,
                    reactions=reactions,
                    views=message.views,
                    signature=message.post_author,
                )
                messages.append(exported)

                # Save progress periodically
                if count % 500 == 0:
                    chat_dir.mkdir(parents=True, exist_ok=True)
                    progress_file.write_text(json.dumps({"last_id": message.id}))

            progress.update(task, description=f"Fetched {count} messages", completed=count, total=count)

    # Messages come newest-first from the API; reverse to chronological order
    messages.reverse()

    # Clean up progress file
    if progress_file.exists():
        progress_file.unlink()

    channel_info.message_count = len(messages)
    return messages


async def list_dialogs(client: TelegramClient) -> list[ChannelInfo]:
    """List all channels and groups the user belongs to."""
    channels = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if isinstance(entity, (Channel, Chat)):
            channels.append(ChannelInfo(
                id=entity.id,
                title=entity.title,
                username=getattr(entity, "username", None),
                member_count=getattr(entity, "participants_count", None),
            ))
    return channels
