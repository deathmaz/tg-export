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
from tg_export.models import ChannelInfo, ExportConfig, ExportedMessage, Reaction, Reactor
from tg_export.renderer import get_initials, userpic_color

console = Console()


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


def entity_name(entity) -> str:
    """Get a display name from a Telegram entity."""
    if isinstance(entity, User):
        parts = [entity.first_name or "", entity.last_name or ""]
        return " ".join(p for p in parts if p) or "Deleted Account"
    return getattr(entity, "title", None) or "Unknown"


async def get_channel_info(client: TelegramClient, channel_ref: str) -> ChannelInfo:
    """Resolve a channel reference and get its info."""
    entity = await client.get_entity(_parse_channel_ref(channel_ref))
    title = getattr(entity, "title", None) or entity_name(entity)
    username = getattr(entity, "username", None)
    member_count = getattr(entity, "participants_count", None)

    return ChannelInfo(
        id=entity.id,
        title=title,
        username=username,
        member_count=member_count,
    )


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


def _peer_uid(peer) -> int | None:
    """Extract a numeric id from a Telethon Peer (user/channel/chat)."""
    return (
        getattr(peer, "user_id", None)
        or getattr(peer, "channel_id", None)
        or getattr(peer, "chat_id", None)
    )


async def _resolve_peer_name(
    client, peer, sender_cache: dict[int, str], fallback: str
) -> tuple[int | None, str | None]:
    """Resolve a peer to (uid, display_name), caching the name. None if uid missing."""
    uid = _peer_uid(peer)
    if uid is None:
        return None, None
    if uid in sender_cache:
        return uid, sender_cache[uid]
    try:
        ent = await client.get_entity(peer)
        name = entity_name(ent)
    except Exception:
        name = fallback
    sender_cache[uid] = name
    return uid, name


async def _extract_reactions(client, message, sender_cache: dict[int, str]) -> list[Reaction]:
    """Extract reactions from a message, including recent reactor info."""
    if not hasattr(message, "reactions") or not message.reactions:
        return []

    reactor_map: dict[str, list[Reactor]] = {}
    recent = getattr(message.reactions, "recent_reactions", None) or []
    for rr in recent:
        peer_id = getattr(rr, "peer_id", None)
        if not peer_id:
            continue
        uid, name = await _resolve_peer_name(client, peer_id, sender_cache, "User")
        if uid is None:
            continue
        reaction = rr.reaction
        emoji_key = getattr(reaction, "emoticon", None) or "custom"
        reactors = reactor_map.setdefault(emoji_key, [])
        reactors.append(Reactor(
            name=name,
            initials=get_initials(name),
            color_class=userpic_color(uid),
        ))

    reactions = []
    for r in message.reactions.results:
        emoji = ""
        if hasattr(r.reaction, "emoticon"):
            emoji = r.reaction.emoticon
        elif hasattr(r.reaction, "document_id"):
            emoji = "custom"
        reactors = reactor_map.get(emoji, [])
        reactions.append(Reaction(emoji=emoji, count=r.count, reactors=reactors))
    return reactions


async def _extract_forward_from(client, message, sender_cache: dict[int, str]) -> str | None:
    """Extract the forwarded-from sender name, resolving from_id when from_name absent."""
    fwd = message.fwd_from
    if not fwd:
        return None
    if fwd.from_name:
        return fwd.from_name
    if fwd.from_id is None:
        return None
    _, name = await _resolve_peer_name(client, fwd.from_id, sender_cache, "Deleted Account")
    return name


def _get_service_text(message) -> str:
    """Get a human-readable description of a service message action."""
    action = message.action
    if action is None:
        return ""
    name = type(action).__name__.replace("MessageAction", "")
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
    sender_cache: dict[int, str] = {}
    wait_time = config.wait_time if config.wait_time is not None else (0 if config.use_takeout else 2)

    # Load progress if resuming
    progress_file = chat_dir / ".progress"
    min_id = 0
    try:
        progress_data = json.loads(progress_file.read_text())
        min_id = progress_data.get("last_id", 0)
        console.print(f"[cyan]Resuming from message ID {min_id}[/cyan]")
    except (FileNotFoundError, json.JSONDecodeError):
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

                if message.action is not None:
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

                # Resolve sender with caching
                sender = await message.get_sender()
                if sender is None:
                    sender_name, sender_id = "Channel", None
                else:
                    sender_id = sender.id
                    if sender_id in sender_cache:
                        sender_name = sender_cache[sender_id]
                    else:
                        sender_name = entity_name(sender)
                        sender_cache[sender_id] = sender_name

                text_html = format_message_text(message.raw_text or "", message.entities)

                # Download media
                media_path = None
                if config.download_media and message.media:
                    media_path = await download_media(
                        client, message, chat_dir, config.max_media_size_bytes
                    )

                media_html = render_media_html(message, media_path)

                fwd_date_full = None
                fwd_date_short = None
                if message.fwd_from and message.fwd_from.date:
                    fwd_date_full = _format_date_full(message.fwd_from.date)
                    fwd_date_short = _format_date_short(message.fwd_from.date)

                exported = ExportedMessage(
                    id=message.id,
                    date=message.date,
                    date_full=_format_date_full(message.date),
                    date_short=_format_date_short(message.date),
                    sender_name=sender_name,
                    sender_id=sender_id,
                    text_html=text_html,
                    media_path=media_path,
                    media_html=media_html,
                    reply_to_id=getattr(message.reply_to, "reply_to_msg_id", None) if message.reply_to else None,
                    forwarded_from=await _extract_forward_from(client, message, sender_cache),
                    forwarded_date_full=fwd_date_full,
                    forwarded_date_short=fwd_date_short,
                    reactions=await _extract_reactions(client, message, sender_cache),
                    views=message.views,
                    signature=message.post_author,
                )
                messages.append(exported)

                # Save progress periodically
                if count % 500 == 0:
                    progress_file.write_text(json.dumps({"last_id": message.id}))

            progress.update(task, description=f"Fetched {count} messages", completed=count, total=count)

    # Messages come newest-first from the API; reverse to chronological order
    messages.reverse()

    # Clean up progress file
    progress_file.unlink(missing_ok=True)

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
