"""Safe configuration template.

Copy this file to ``config.py`` and replace every placeholder locally.
Do not commit real credentials to a public repository.
"""

# Telegram credentials
BOT_TOKEN = "YOUR_BOT_TOKEN"
API_ID = 12345678
API_HASH = "YOUR_API_HASH"
OWNER_ID = 123456789

# Access and public channels
PUBLIC_MODE = True
ADMIN_USERNAME = "@ApxCoder"
MAIN_CHANNEL = "@YourMainChannel"
FSUB_CHANNEL = "@YourFsubChannel"
FSUB_LINK = "https://t.me/YourFsubChannel"

# UI assets
START_PIC = "assets/start.jpg"
FSUB_PIC = "assets/fsub.jpg"

# Database
DATABASE_TYPE = "mongodb"  # mongodb | sqlite
MONGO_URI = "YOUR_MONGODB_URI"
DATABASE_NAME = "caption_bot"
SQLITE_DATABASE = "data/bot.db"

# Optional diagnostics
LOG_CHANNEL = 0

# Attribution
PROJECT_CREDIT = "https://github.com/Ap-Loveris"
