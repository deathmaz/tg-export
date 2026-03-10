"""CLI interface for tg-export."""
from __future__ import annotations

import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from tg_export.auth import authenticate, connect_existing, get_api_credentials
from tg_export.config import DEFAULT_CONFIG_CONTENT, DEFAULT_CONFIG_PATH, compute_from_date, compute_to_date, load_config
from tg_export.fetcher import entity_name, fetch_and_process_messages, get_channel_info, list_dialogs
from tg_export.models import ExportConfig
from tg_export.renderer import HtmlRenderer

console = Console()


@click.group()
def main():
    """Export Telegram channel messages to static HTML."""
    pass


@main.command()
@click.option("--api-id", type=int, default=None, help="Telegram API ID (or TG_EXPORT_API_ID env var)")
@click.option("--api-hash", type=str, default=None, help="Telegram API hash (or TG_EXPORT_API_HASH env var)")
@click.option("--phone", type=str, default=None, help="Phone number with country code (or TG_EXPORT_PHONE env var)")
@click.option("--session-dir", type=str, default=None, help="Directory for session file (default: ~/.tg-export/)")
def auth(api_id, api_hash, phone, session_dir):
    """Authenticate with Telegram."""
    resolved_id, resolved_hash = get_api_credentials(api_id, api_hash)

    async def _auth():
        client = await authenticate(resolved_id, resolved_hash, phone, session_dir)
        me = await client.get_me()
        console.print(f"Logged in as: [bold]{entity_name(me)}[/bold] (@{me.username or 'N/A'})")
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
@click.argument("channels", nargs=-1)
@click.option("-c", "--channel", "channel_opts", type=str, multiple=True, help="Channel (@username, invite link, or numeric ID). Repeatable.")
@click.option("-o", "--output", type=str, default=None, help="Output directory (default: ./export)")
@click.option("--api-id", type=int, default=None, help="Telegram API ID")
@click.option("--api-hash", type=str, default=None, help="Telegram API hash")
@click.option("--session-dir", type=str, default=None, help="Session directory")
@click.option("--config", "config_path", type=str, default=None, help="Path to config file (default: ~/.tg-export/config.toml)")
@click.option("--from-date", type=str, default=None, help="Start date (ISO format: YYYY-MM-DD)")
@click.option("--to-date", type=str, default=None, help="End date (ISO format: YYYY-MM-DD)")
@click.option("--last", type=str, default=None, help="Relative duration: 24h, 7d, 2w, 1m")
@click.option("--limit", type=int, default=None, help="Max number of messages per channel")
@click.option("--no-media", is_flag=True, default=False, help="Skip media downloads")
@click.option("--max-media-size", type=int, default=50, help="Max media file size in MB (default: 50)")
@click.option("--msgs-per-page", type=int, default=1000, help="Messages per HTML page (default: 1000)")
@click.option("--takeout/--no-takeout", default=True, help="Use takeout session (default: yes)")
@click.option("--wait-time", type=float, default=None, help="Seconds between API requests")
@click.option("-v", "--verbose", is_flag=True, default=False, help="Verbose output")
def export(
    channels, channel_opts, output, api_id, api_hash, session_dir,
    config_path, from_date, to_date, last, limit, no_media, max_media_size,
    msgs_per_page, takeout, wait_time, verbose,
):
    """Export messages from Telegram channels to static HTML.

    CHANNEL can be a @username, invite link, or numeric ID.
    Multiple channels can be provided as arguments or via -c flags.
    For negative IDs, use -c flag: tg-export export -c -100123456789

    \b
    Examples:
      tg-export export @channel1 @channel2 --last 24h
      tg-export export -c -100111 -c -100222 --last 7d
      tg-export export @public -c -100private --last 24h
    """
    cfg = load_config(config_path)

    all_channels = list(channels) + list(channel_opts)
    if not all_channels:
        all_channels = [str(ch) for ch in cfg.get("channels", [])]
    if not all_channels:
        raise click.UsageError("Provide at least one channel as argument, via -c flag, or in config file.")

    if output is None:
        output = cfg.get("output", ExportConfig.output_dir)
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
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        renderer = HtmlRenderer(output_dir, config)
        renderer.copy_static_assets()

        for i, ch in enumerate(all_channels, 1):
            console.print(f"\n[bold][{i}/{len(all_channels)}] Resolving channel:[/bold] {ch}")
            try:
                channel_info = await get_channel_info(client, ch)
            except Exception as e:
                console.print(f"  [red]Failed to resolve: {e}[/red]")
                continue

            console.print(f"  Channel: [bold]{channel_info.title}[/bold] (ID: {channel_info.id})")

            chat_dir = output_dir / "chats" / f"chat_{channel_info.id}"
            chat_dir.mkdir(parents=True, exist_ok=True)

            console.print("  Fetching messages...")
            try:
                messages = await fetch_and_process_messages(
                    client, channel_info, config, chat_dir
                )
            except Exception as e:
                console.print(f"  [red]Failed to fetch: {e}[/red]")
                continue

            console.print(f"  [green]Fetched {len(messages)} messages[/green]")
            renderer.render_channel(channel_info, messages, chat_dir)
            renderer.save_channel_meta(channel_info, chat_dir)

        renderer.render_index()

        console.print(f"\n[green bold]Export complete![/green bold]")
        console.print(f"  Output: {output_dir.resolve()}")
        console.print(f"  Index:  {(output_dir / 'export_results.html').resolve()}")

        await client.disconnect()

    asyncio.run(_export())


@main.group()
def config():
    """Manage tg-export configuration."""
    pass


@config.command("init")
def config_init():
    """Create a default config file at ~/.tg-export/config.toml."""
    path = DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "x") as f:
            f.write(DEFAULT_CONFIG_CONTENT)
    except FileExistsError:
        console.print(f"Config file already exists: {path}")
        return
    console.print(f"Created config file: {path}")


@config.command("show")
def config_show():
    """Show the current config file contents."""
    path = DEFAULT_CONFIG_PATH
    if not path.is_file():
        console.print(f"No config file found at {path}")
        console.print("Run 'tg-export config init' to create one.")
        return
    console.print(f"[bold]{path}[/bold]\n")
    console.print(path.read_text())


@config.command("path")
def config_path():
    """Print the config file path."""
    console.print(str(DEFAULT_CONFIG_PATH))
