"""Example configuration for Caption Bot.

Copy this file to ``config.py`` and replace every placeholder with your
real deployment values. Never commit real credentials.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Telegram application
# ─────────────────────────────────────────────────────────────────────────────
BOT_TOKEN = "YOUR_BOT_TOKEN"
API_ID = 12345678
API_HASH = "YOUR_API_HASH"
OWNER_ID = 123456789

# ─────────────────────────────────────────────────────────────────────────────
# Access & channels
# ─────────────────────────────────────────────────────────────────────────────
PUBLIC_MODE = True
ADMIN_USERNAME = "@ApxCoder"
MAIN_CHANNEL = "@YourMainChannel"

# Used by get_chat_member(). Username or numeric chat ID is accepted.
FSUB_CHANNEL = "@YourFsubChannel"

# Used only by the Join button. Must be a valid Telegram HTTP/t.me URL.
FSUB_LINK = "https://t.me/YourFsubChannel"

# ─────────────────────────────────────────────────────────────────────────────
# Assets & diagnostics
# ─────────────────────────────────────────────────────────────────────────────
START_PIC = "assets/start.jpg"
FSUB_PIC = "assets/fsub.jpg"
LOG_CHANNEL = 0

# ─────────────────────────────────────────────────────────────────────────────
# Storage
# ─────────────────────────────────────────────────────────────────────────────
DATABASE_TYPE = "mongodb"  # mongodb | sqlite
MONGO_URI = "mongodb+srv://username:password@cluster.mongodb.net/"
DATABASE_NAME = "caption_bot"
SQLITE_DATABASE = "data/bot.db"

# Project attribution.
PROJECT_CREDIT = "https://github.com/Ap-Loveris"
