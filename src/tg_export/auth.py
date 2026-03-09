"""Telegram authentication flow."""
from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console
from rich.prompt import Prompt
from telethon import TelegramClient
from telethon.tl.functions.account import UpdateStatusRequest

from tg_export.config import DEFAULT_SESSION_DIR

console = Console()


def get_session_path(session_dir: str | None = None) -> Path:
    """Get the session file path."""
    d = Path(session_dir) if session_dir else DEFAULT_SESSION_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d / "session"


# Telegram Desktop's public API credentials (from tdesktop open-source repo).
# Safe to use — these are hardcoded in the tdesktop source and widely used by
# third-party tools. You can optionally provide your own via --api-id/--api-hash.
_DEFAULT_API_ID = 611335
_DEFAULT_API_HASH = "d524b414d21f4d37f08684c1df41ac9c"


def get_api_credentials(api_id: int | None, api_hash: str | None) -> tuple[int, str]:
    """Resolve API credentials from args, env vars, or tdesktop defaults."""
    resolved_id = api_id or os.environ.get("TG_API_ID") or _DEFAULT_API_ID
    resolved_hash = api_hash or os.environ.get("TG_API_HASH") or _DEFAULT_API_HASH
    return int(resolved_id), str(resolved_hash)


async def create_client(
    api_id: int,
    api_hash: str,
    session_dir: str | None = None,
) -> TelegramClient:
    """Create a Telethon client with the given credentials."""
    session_path = get_session_path(session_dir)
    client = TelegramClient(str(session_path), api_id, api_hash)
    return client


async def authenticate(
    api_id: int,
    api_hash: str,
    phone: str | None = None,
    session_dir: str | None = None,
) -> TelegramClient:
    """Authenticate with Telegram and return a connected client."""
    phone = phone or os.environ.get("TG_PHONE")
    client = await create_client(api_id, api_hash, session_dir)
    await client.connect()

    if await client.is_user_authorized():
        console.print("[green]Already authenticated.[/green]")
        await _set_offline(client)
        return client

    if not phone:
        phone = Prompt.ask("Enter your phone number (with country code)")

    await client.send_code_request(phone)
    code = Prompt.ask("Enter the verification code sent to your Telegram")

    try:
        await client.sign_in(phone, code)
    except Exception:
        # Might need 2FA password
        password = Prompt.ask("Enter your 2FA password", password=True)
        await client.sign_in(password=password)

    console.print("[green]Authentication successful![/green]")
    await _set_offline(client)
    return client


async def connect_existing(
    api_id: int,
    api_hash: str,
    session_dir: str | None = None,
) -> TelegramClient:
    """Connect using an existing session. Raises if not authenticated."""
    client = await create_client(api_id, api_hash, session_dir)
    await client.connect()

    if not await client.is_user_authorized():
        console.print(
            "[red]Not authenticated. Run 'tg-export auth' first.[/red]"
        )
        raise SystemExit(1)

    await _set_offline(client)
    return client


async def _set_offline(client: TelegramClient) -> None:
    """Set the user's status to offline."""
    try:
        await client(UpdateStatusRequest(offline=True))
    except Exception:
        pass  # Non-critical
