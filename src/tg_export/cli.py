"""CLI interface for tg-export."""
from __future__ import annotations

import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from tg_export.auth import authenticate, connect_existing, get_api_credentials
from tg_export.config import compute_from_date, compute_to_date
from tg_export.fetcher import fetch_and_process_messages, get_channel_info, list_dialogs
from tg_export.models import ExportConfig
from tg_export.renderer import HtmlRenderer

console = Console()


@click.group()
def main():
    """Export Telegram channel messages to static HTML."""
    pass


@main.command()
@click.option("--api-id", type=int, default=None, help="Telegram API ID (or TG_API_ID env var)")
@click.option("--api-hash", type=str, default=None, help="Telegram API hash (or TG_API_HASH env var)")
@click.option("--phone", type=str, default=None, help="Phone number with country code (or TG_PHONE env var)")
@click.option("--session-dir", type=str, default=None, help="Directory for session file (default: ~/.tg-export/)")
def auth(api_id, api_hash, phone, session_dir):
    """Authenticate with Telegram."""
    resolved_id, resolved_hash = get_api_credentials(api_id, api_hash)

    async def _auth():
        client = await authenticate(resolved_id, resolved_hash, phone, session_dir)
        me = await client.get_me()
        name = f"{me.first_name or ''} {me.last_name or ''}".strip()
        console.print(f"Logged in as: [bold]{name}[/bold] (@{me.username or 'N/A'})")
        await client.disconnect()

    asyncio.run(_auth())


@main.command("list")
@click.option("--api-id", type=int, default=None, help="Telegram API ID")
@click.option("--api-hash", type=str, default=None, help="Telegram API hash")
@click.option("--session-dir", type=str, default=None, help="Session directory")
def list_channels(api_id, api_hash, session_dir):
    """List channels and groups you belong to."""
    resolved_id, resolved_hash = get_api_credentials(api_id, api_hash)

    async def _list():
        client = await connect_existing(resolved_id, resolved_hash, session_dir)
        channels = await list_dialogs(client)

        table = Table(title="Channels & Groups")
        table.add_column("Title", style="bold")
        table.add_column("Username")
        table.add_column("Members", justify="right")
        table.add_column("ID", justify="right")

        for ch in channels:
            table.add_row(
                ch.title,
                f"@{ch.username}" if ch.username else "-",
                str(ch.member_count) if ch.member_count else "-",
                str(ch.id),
            )

        console.print(table)
        await client.disconnect()

    asyncio.run(_list())


@main.command()
@click.argument("channel", required=False, default=None)
@click.option("-c", "--channel", "channel_opt", type=str, default=None, help="Channel (@username, invite link, or numeric ID)")
@click.option("-o", "--output", type=str, default="./export", help="Output directory")
@click.option("--api-id", type=int, default=None, help="Telegram API ID")
@click.option("--api-hash", type=str, default=None, help="Telegram API hash")
@click.option("--session-dir", type=str, default=None, help="Session directory")
@click.option("--from-date", type=str, default=None, help="Start date (ISO format: YYYY-MM-DD)")
@click.option("--to-date", type=str, default=None, help="End date (ISO format: YYYY-MM-DD)")
@click.option("--last", type=str, default=None, help="Relative duration: 24h, 7d, 2w, 1m")
@click.option("--limit", type=int, default=None, help="Max number of messages")
@click.option("--no-media", is_flag=True, default=False, help="Skip media downloads")
@click.option("--max-media-size", type=int, default=50, help="Max media file size in MB (default: 50)")
@click.option("--msgs-per-page", type=int, default=1000, help="Messages per HTML page (default: 1000)")
@click.option("--takeout/--no-takeout", default=True, help="Use takeout session (default: yes)")
@click.option("--wait-time", type=float, default=None, help="Seconds between API requests")
@click.option("-v", "--verbose", is_flag=True, default=False, help="Verbose output")
def export(
    channel, channel_opt, output, api_id, api_hash, session_dir,
    from_date, to_date, last, limit, no_media, max_media_size,
    msgs_per_page, takeout, wait_time, verbose,
):
    """Export messages from a Telegram channel to static HTML.

    CHANNEL can be a @username, invite link, or numeric ID.
    For negative IDs, use -c flag: tg-export export -c -100123456789
    """
    channel = channel_opt or channel
    if not channel:
        raise click.UsageError("Provide a channel as argument or via -c flag.")
    resolved_id, resolved_hash = get_api_credentials(api_id, api_hash)

    config = ExportConfig(
        output_dir=output,
        from_date=compute_from_date(last, from_date),
        to_date=compute_to_date(to_date),
        limit=limit,
        download_media=not no_media,
        max_media_size_bytes=max_media_size * 1024 * 1024,
        msgs_per_page=msgs_per_page,
        use_takeout=takeout,
        wait_time=wait_time,
    )

    async def _export():
        client = await connect_existing(resolved_id, resolved_hash, session_dir)

        console.print(f"[bold]Resolving channel:[/bold] {channel}")
        channel_info = await get_channel_info(client, channel)
        console.print(f"  Channel: [bold]{channel_info.title}[/bold] (ID: {channel_info.id})")

        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        chat_dir = output_dir / "chats" / f"chat_{channel_info.id}"
        chat_dir.mkdir(parents=True, exist_ok=True)

        console.print("[bold]Fetching messages...[/bold]")
        messages = await fetch_and_process_messages(
            client, channel_info, config, chat_dir
        )
        console.print(f"  [green]Fetched {len(messages)} messages[/green]")

        console.print("[bold]Generating HTML...[/bold]")
        renderer = HtmlRenderer(output_dir, config)
        renderer.copy_static_assets()
        renderer.render_channel(channel_info, messages, chat_dir)
        renderer.render_index([channel_info])

        console.print(f"\n[green bold]Export complete![/green bold]")
        console.print(f"  Output: {output_dir.resolve()}")
        console.print(f"  Open: {(chat_dir / 'messages.html').resolve()}")

        await client.disconnect()

    asyncio.run(_export())
