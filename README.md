# tg-export

CLI tool that exports Telegram channel/group messages to a static HTML website, visually identical to Telegram Desktop's built-in export. Supports private channels.

## Features

- Produces HTML output matching Telegram Desktop's export format (same CSS, JS, DOM structure)
- Exports from private channels and groups (you must be a member)
- Downloads media: photos, videos, voice messages, documents, stickers
- Relative time filters (`--last 24h`) and date range filters
- Incremental exports via `--save-checkpoint` / `--from-checkpoint`
- Paginated output (~1000 messages per page)
- Uses Telegram's takeout API for faster exports with lower rate limits
- Stays invisible — sets your status to offline while running
- Resume interrupted exports automatically
- Dark mode support (via `prefers-color-scheme`)

## Installation

Requires Python 3.11+.

### With pipx (recommended)

```bash
pipx install /path/to/tg-export
```

### With pip

```bash
pip install /path/to/tg-export
```

### Development

```bash
cd /path/to/tg-export
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Quick Start

### 1. Authenticate

```bash
tg-export auth --phone "+1234567890"
```

You'll be prompted for a verification code sent to your Telegram app (check your chat list for a message from "Telegram"). If you have 2FA enabled, you'll also be prompted for your password.

Authentication is one-time — the session is saved at `~/.tg-export/session.session`.

> **Note:** On the first export with `--takeout` (enabled by default), Telegram will ask you to confirm the data export request in your Telegram app. This is also a one-time prompt.

### 2. List your channels

```bash
tg-export list
```

Displays a table of all channels and groups you belong to, with their IDs.

### 3. Export messages

```bash
# By username
tg-export export @channelname --last 24h

# Today's messages only
tg-export export @channelname --last today

# Yesterday's messages onward
tg-export export @channelname --last yesterday

# By channel ID (use -c for negative IDs)
tg-export export -c -100123456789 --last 7d

# With date range
tg-export export @channelname --from-date 2025-01-01 --to-date 2025-03-01

# Limit number of messages
tg-export export @channelname --limit 500

# Text only, no media downloads
tg-export export @channelname --last 24h --no-media

# Custom output directory
tg-export export @channelname --last 24h -o ./my-export

# Incremental exports (resume from the last run)
tg-export export @channelname --last 7d --save-checkpoint   # first run
tg-export export @channelname --from-checkpoint --save-checkpoint   # next runs

# Multiple channels at once
tg-export export @channel1 @channel2 @channel3 --last 24h

# Multiple private channels
tg-export export -c -100111 -c -100222 --last 7d

# Mix of public and private
tg-export export @public -c -100private --last 24h
```

### 4. View the export

Open the generated HTML file in your browser:

```bash
open ./export/chats/chat_*/messages.html
# or
xdg-open ./export/chats/chat_*/messages.html
```

## Usage

### `tg-export auth`

Authenticate with Telegram.

```
Options:
  --phone TEXT        Phone number with country code
  --api-id INTEGER    Custom Telegram API ID (optional, has built-in default)
  --api-hash TEXT     Custom Telegram API hash (optional, has built-in default)
  --session-dir TEXT  Directory for session file (default: ~/.tg-export/)
```

### `tg-export list`

List channels and groups you belong to.

```
Options:
  --api-id INTEGER    Telegram API ID
  --api-hash TEXT     Telegram API hash
  --session-dir TEXT  Session directory
```

### `tg-export export`

Export messages from one or more channels to static HTML.

```
Arguments:
  CHANNEL...             One or more @username, invite link, or numeric ID

Options:
  -c, --channel TEXT       Channel (repeatable, required for negative IDs)
  -o, --output TEXT        Output directory (default: ./export)
  --last TEXT              Relative duration: today, yesterday, 24h, 7d, 2w, 1m
  --from-date TEXT         Start date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
  --to-date TEXT           End date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
  --from-checkpoint        Use the stored checkpoint as --from-date
  --save-checkpoint        Store current time as checkpoint after success
  --limit INTEGER          Max number of messages to export
  --no-media               Skip downloading media files
  --max-media-size INT     Max media file size in MB (default: 50)
  --msgs-per-page INT      Messages per HTML page (default: 1000)
  --takeout / --no-takeout Use takeout session (default: enabled)
  --wait-time FLOAT        Seconds between API requests
  -v, --verbose            Verbose output
```

## Output Structure

```
export/
├── export_results.html          # Index page listing exported channels
├── css/style.css                # Telegram Desktop's export stylesheet
├── js/script.js                 # Telegram Desktop's export scripts
└── chats/
    └── chat_<id>/
        ├── messages.html        # Page 1 (newest messages)
        ├── messages2.html       # Page 2
        ├── messages3.html       # Page 3, etc.
        ├── photos/              # Downloaded photos
        ├── video_files/         # Downloaded videos
        ├── voice_messages/      # Downloaded voice messages
        ├── stickers/            # Downloaded stickers
        └── files/               # Downloaded documents
```

## Configuration File

Create a config file to set default channels and output directory:

```bash
tg-export config init
```

This creates `~/.tg-export/config.toml`:

```toml
# Default channels to export when none specified on the command line.
# Accepts @usernames, invite links, or numeric IDs.
channels = [
    "@channel1",
    "@channel2",
    "-1001234567890",
]

# Default output directory (default: ./export)
output = "./export"

# IANA timezone name. Controls how --last today / yesterday and bare dates
# (e.g. --from-date 2026-04-21) are interpreted, and how timestamps render
# in the exported HTML. Omit or leave empty to use the system timezone.
timezone = "Europe/Berlin"
```

With a config file, you can run exports without specifying channels:

```bash
tg-export export --last 24h        # exports all channels from config
tg-export export @other --last 24h # overrides config channels
```

CLI flags always take precedence over the config file.

### Config commands

```bash
tg-export config init    # Create default config file
tg-export config show    # Show current config
tg-export config path    # Print config file path
```

Use `--config /path/to/config.toml` on the export command to use an alternative config file.

## Timezone handling

Telegram stores every message in UTC. `tg-export` keeps internal storage and the checkpoint file in UTC, but interprets user input and renders output in the configured timezone.

Set `timezone` in `~/.tg-export/config.toml` to an IANA zone name (e.g. `Europe/Berlin`, `America/New_York`). If omitted, the system timezone is used.

| Surface | Behavior |
|---|---|
| `--last today` / `yesterday` | Local calendar day in the configured timezone |
| `--from-date 2026-04-21` (bare date) | Midnight in the configured timezone |
| `--from-date 2026-04-21T10:00+02:00` | Explicit offset honored as-is |
| `--last 1d`, `7d`, `24h` | Rolling window from `now` — timezone-independent |
| Rendered HTML timestamps (`HH:MM`, tooltip, date separator) | Configured timezone |
| Checkpoint file on disk | UTC ISO (portable) |
| `--save-checkpoint` / `checkpoint show` console output | Configured timezone |

## Incremental Exports (Checkpoint)

For recurring exports you can persist the time of the last successful run and resume from it next time, instead of picking a date manually.

```bash
# First run: export the last week AND save a checkpoint on success
tg-export export @channel --last 7d --save-checkpoint

# Later runs: start from the stored checkpoint, then advance it
tg-export export @channel --from-checkpoint --save-checkpoint
```

`--save-checkpoint` captures `datetime.now(UTC)` **after** the export finishes successfully and writes it to `~/.tg-export/checkpoint.toml` (always UTC for portability). A failed run leaves the previous checkpoint intact. The console echo and `checkpoint show` convert the stored instant to the configured timezone for display.

`--from-checkpoint` is mutually exclusive with `--from-date` and `--last`. If no checkpoint is stored yet, the command errors out and tells you to run with `--save-checkpoint` first.

### Checkpoint commands

```bash
tg-export checkpoint show    # Print the stored datetime (or "No checkpoint set.")
tg-export checkpoint clear   # Delete the checkpoint file
tg-export checkpoint path    # Print the checkpoint file path
```

## Environment Variables

Instead of passing flags every time, you can set these:

```bash
export TG_EXPORT_API_ID=12345678         # Custom API ID (optional)
export TG_EXPORT_API_HASH="abcdef..."    # Custom API hash (optional)
export TG_EXPORT_PHONE="+1234567890"     # Phone number
```

## API Credentials

The tool uses Telegram Desktop's public API credentials by default — no setup needed. These are from tdesktop's open-source repository and are safe to use (they identify the app, not your account).

If you prefer to use your own:

1. Go to https://my.telegram.org and log in
2. Click "API development tools"
3. Create an application (any name works)
4. Pass the credentials via `--api-id` / `--api-hash` or environment variables

## Private Channels

Private channels work the same as public ones — you just need to be a member. Use the channel ID (find it with `tg-export list`) since private channels don't have usernames:

```bash
tg-export export -c -100123456789 --last 7d
```

## Troubleshooting

### "Not authenticated" error
Run `tg-export auth` to create or refresh your session.

### No verification code received
- Check the **Telegram app** on your phone or desktop for a message from "Telegram"
- Check **Archived Chats** and **Spam** folder
- Wait 15 minutes if you've made multiple attempts (rate limit cooldown)
- As a fallback, Telegram may send via SMS — check your text messages

### Rate limiting / FloodWaitError
The tool uses takeout sessions by default to minimize rate limits. If you still hit limits, the tool will display the wait time and automatically retry. You can also increase `--wait-time` to add delay between requests.

### Takeout permission prompt
On first use, Telegram will show a popup in your app asking to allow data export. Accept it — this is a one-time confirmation.

### Negative channel IDs
Channel IDs starting with `-100` must be passed with the `-c` flag:
```bash
tg-export export -c -100123456789 --last 24h
```

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Tests cover:
- Config parsing (durations, dates, flag precedence, TOML loading)
- Text formatting (all entity types, nesting, XSS escaping)
- Pagination (page splits, tdesktop filename convention, nav links)
- Message grouping (join window, date separators, service messages)
- HTML rendering (file generation, tdesktop CSS classes, multi-page output)

## License

MIT
