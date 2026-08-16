# Caption Bot

Advanced Telegram Auto Caption Bot with a clean button-based UI.

## Features

- Multi-channel support; each channel has independent settings
- Add channel by ID or by forwarding a channel message in bot DM
- Caption templates with dynamic variables
- Episode/season/quality/audio fallback rules
- HTML formatting including `<blockquote expandable>`
- Colored buttons: blue, green, red
- Text replacement, filters, forwarding, prefix, suffix, stickers, media details
- Public/private mode
- Public-link-only force subscribe; no generated invite links
- Broadcast, user tracking and statistics
- Lightweight MongoDB primary backend with optional SQLite backend
- Docker support
- Owner/admin-only management commands
- Unexpected errors are sent to the owner/admin DM; missing metadata does not stop processing

## Public mode

`PUBLIC_MODE = True` lets normal users use the bot. Admin-only commands remain protected.

`PUBLIC_MODE = False` shows exactly:

```text
🔒 This Bot Is Private

Please contact the administrator. @ApxCoder
```

## Setup

1. Copy `example_config.py` to `config.py`.
2. Fill in Bot Token, API ID, API Hash, Owner ID and database values.
3. Install dependencies: `pip install -r requirements.txt`.
4. Run: `python main.py`.

## Images

Put your own `start.jpg` and `fsub.jpg` inside `assets/`. The bot safely falls back to a text message if an image is not present.

## Commands

Public: `/start`, `/help`, `/channels`, `/stats`, `/settings`

Admin: `/addadmin`, `/deladmin`, `/broadcast`, `/set_public`

Channel configuration is intentionally handled through the inline UI rather than a long list of commands.

## Security

Do not commit real credentials. Keep `config.py` private on your server and use `example_config.py` as the public template.
