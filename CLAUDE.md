# CLAUDE.md

## Project Overview

tg-export is a Python CLI tool that exports Telegram channel/group messages to static HTML, matching Telegram Desktop's export format exactly. Uses Telethon (MTProto API), Click (CLI), Jinja2 (templates), and Rich (terminal output).

## Build & Test

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_config.py -v
```

## Project Structure

- `src/tg_export/cli.py` — Click CLI commands: auth, list, export, config
- `src/tg_export/auth.py` — Telegram authentication flow, API credential resolution
- `src/tg_export/config.py` — TOML config loading, duration/date parsing
- `src/tg_export/fetcher.py` — Message fetching with takeout sessions, sender caching
- `src/tg_export/formatters.py` — Telegram message entities to HTML conversion
- `src/tg_export/media.py` — Media download and HTML rendering
- `src/tg_export/models.py` — Dataclasses: ExportedMessage, ExportConfig, ChannelInfo, etc.
- `src/tg_export/renderer.py` — Jinja2 HTML generation, message grouping, pagination
- `src/tg_export/pagination.py` — Message page splitting, tdesktop filename convention
- `src/tg_export/resources/` — Static CSS/JS/templates from tdesktop

## Conventions

- Python >=3.11, uses built-in `tomllib` (no backport dependency)
- Environment variables prefixed with `TG_EXPORT_` (e.g., `TG_EXPORT_API_ID`)
- Config file at `~/.tg-export/config.toml`, session at `~/.tg-export/session.session`
- Uses conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, etc.
- Default API credentials are Telegram Desktop's public ones (hardcoded in auth.py)
- `ExportConfig` dataclass is the single source of truth for export defaults
- CLI flags > config file > hardcoded defaults (priority order)
