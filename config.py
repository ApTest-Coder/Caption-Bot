"""Application configuration.

Keep real credentials in this file locally and never publish them.
Copy the layout from ``example_config.py`` when setting up a new instance.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Telegram credentials
# ---------------------------------------------------------------------------
BOT_TOKEN = "YOUR_BOT_TOKEN"
API_ID = 12345678
API_HASH = "YOUR_API_HASH"
OWNER_ID = 123456789

# ---------------------------------------------------------------------------
# Access and channels
# ---------------------------------------------------------------------------
PUBLIC_MODE = True
ADMIN_USERNAME = "@ApxCoder"
MAIN_CHANNEL = "@YourMainChannel"

# Used by get_chat_member(). Keep the channel username or numeric ID here.
FSUB_CHANNEL = "@YourFsubChannel"
# Used only for the inline Join button. Must be a valid t.me/http(s) URL.
FSUB_LINK = "https://t.me/YourFsubChannel"

# ---------------------------------------------------------------------------
# UI assets
# ---------------------------------------------------------------------------
START_PIC = "assets/start.jpg"
FSUB_PIC = "assets/fsub.jpg"

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
DATABASE_TYPE = "mongodb"  # mongodb | sqlite
MONGO_URI = "YOUR_MONGODB_URI"
DATABASE_NAME = "caption_bot"
SQLITE_DATABASE = "data/bot.db"

# ---------------------------------------------------------------------------
# Diagnostics and attribution
# ---------------------------------------------------------------------------
LOG_CHANNEL = 0
PROJECT_CREDIT = "https://github.com/Ap-Loveris"
