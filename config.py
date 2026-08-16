"""Application configuration.

Keep secrets local. Do not commit real credentials to the public repository.
"""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────────────────────
# Telegram
# ──────────────────────────────────────────────────────────────────────────────
BOT_TOKEN = "YOUR_BOT_TOKEN"
API_ID = 12345678
API_HASH = "YOUR_API_HASH"
OWNER_ID = 123456789

# ──────────────────────────────────────────────────────────────────────────────
# Access & branding
# ──────────────────────────────────────────────────────────────────────────────
PUBLIC_MODE = True
ADMIN_USERNAME = "@ApxCoder"
MAIN_CHANNEL = "@YourMainChannel"
FSUB_CHANNEL = "@YourFsubChannel"  # Public username/link only.

# ──────────────────────────────────────────────────────────────────────────────
# UI assets
# ──────────────────────────────────────────────────────────────────────────────
START_PIC = "assets/start.jpg"
FSUB_PIC = "assets/fsub.jpg"

# ──────────────────────────────────────────────────────────────────────────────
# Storage
# ──────────────────────────────────────────────────────────────────────────────
DATABASE_TYPE = "mongodb"  # mongodb | sqlite
MONGO_URI = "YOUR_MONGODB_URI"
DATABASE_NAME = "caption_bot"
SQLITE_DATABASE = "data/bot.db"

# ──────────────────────────────────────────────────────────────────────────────
# Diagnostics
# ──────────────────────────────────────────────────────────────────────────────
LOG_CHANNEL = 0

# Project credit. Attribution only; it is not used by the bot runtime.
PROJECT_CREDIT = "https://github.com/Ap-Loveris"
