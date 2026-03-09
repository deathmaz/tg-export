# tg-export

CLI tool that exports Telegram channel/group messages to a static HTML website, visually identical to Telegram Desktop's built-in export. Supports private channels.

## Features

- Produces HTML output matching Telegram Desktop's export format (same CSS, JS, DOM structure)
- Exports from private channels and groups (you must be a member)
- Downloads media: photos, videos, voice messages, documents, stickers
- Relative time filters (`--last 24h`) and date range filters
- Paginated output (~1000 messages per page)
- Uses Telegram's takeout API for faster exports with lower rate limits
- Stays invisible — sets your status to offline while running
- Resume interrupted exports automatically
- Dark mode support (via `prefers-color-scheme`)

## Installation

Requires Python 3.10+.

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

Export messages from a channel to static HTML.

```
Arguments:
  CHANNEL              @username, invite link, or numeric ID

Options:
  -c, --channel TEXT       Channel (alternative to positional arg, required for negative IDs)
  -o, --output TEXT        Output directory (default: ./export)
  --last TEXT              Relative duration: 24h, 7d, 2w, 1m
  --from-date TEXT         Start date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
  --to-date TEXT           End date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
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

## Environment Variables

Instead of passing flags every time, you can set these:

```bash
export TG_API_ID=12345678         # Custom API ID (optional)
export TG_API_HASH="abcdef..."    # Custom API hash (optional)
export TG_PHONE="+1234567890"     # Phone number
export TG_SESSION_DIR="/path"     # Session directory
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
- Config parsing (durations, dates, flag precedence)
- Text formatting (all entity types, nesting, XSS escaping)
- Pagination (page splits, tdesktop filename convention, nav links)
- Message grouping (join window, date separators, service messages)
- HTML rendering (file generation, tdesktop CSS classes, multi-page output)

## License

MIT
