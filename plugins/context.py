"""Shared runtime context for feature plugins.

Feature modules import their dependencies from here instead of importing
``main``. This keeps the plugin layer free from circular imports.
"""

from __future__ import annotations

import json
import logging
import time
from urllib.parse import urlparse

from aiogram import Bot, Router
from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMIN_USERNAME, FSUB_CHANNEL, FSUB_LINK, OWNER_ID, PUBLIC_MODE
from database.settings import Database, default_settings

LOGGER = logging.getLogger("caption_bot")
DB = Database()
RUNTIME = {"processed": 0, "edited": 0, "failed": 0}
STATES: dict[int, dict] = {}
STARTED_AT = time.monotonic()
VALID_FILTERS = {
    "video", "audio", "document", "photo", "animation", "voice", "sticker"
}


def valid_http_url(value: str) -> bool:
    """Return True only for absolute HTTP(S) URLs."""
    parsed = urlparse((value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def button_style(value: str | None) -> ButtonStyle:
    """Convert the user-facing colour name to Telegram's button style."""
    return {
        "blue": ButtonStyle.PRIMARY,
        "primary": ButtonStyle.PRIMARY,
        "green": ButtonStyle.SUCCESS,
        "success": ButtonStyle.SUCCESS,
        "red": ButtonStyle.DANGER,
        "danger": ButtonStyle.DANGER,
    }.get((value or "blue").strip().lower(), ButtonStyle.PRIMARY)


def merged_config(row: dict) -> dict:
    """Merge persisted channel settings with new defaults."""
    base = default_settings()
    try:
        stored = json.loads(row.get("config") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        LOGGER.warning("Invalid settings JSON for channel %s", row.get("channel_id"))
        return base
    for key, value in stored.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key].update(value)
        else:
            base[key] = value
    return base


def uptime_text() -> str:
    """Return process uptime."""
    seconds = int(time.monotonic() - STARTED_AT)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    return f"{days}d {hours}h {minutes}m"


def has_media(message: Message) -> bool:
    """Return whether a post contains one of the supported media types."""
    return any(
        (
            message.video,
            message.audio,
            message.document,
            message.photo,
            message.animation,
            message.voice,
            message.sticker,
        )
    )


def media_matches_filter(message: Message, filters: dict) -> bool:
    """Check a channel's optional media-type filter."""
    media_type = str(filters.get("type") or "").lower().strip() if filters else ""
    if not media_type:
        return True
    return bool(
        {
            "video": message.video,
            "audio": message.audio,
            "document": message.document,
            "photo": message.photo,
            "animation": message.animation,
            "voice": message.voice,
            "sticker": message.sticker,
        }.get(media_type)
    )


async def is_admin(user_id: int) -> bool:
    """Check owner or database administrators."""
    return user_id == OWNER_ID or await DB.is_admin(user_id)


async def private_notice(message: Message) -> None:
    """Send the configured private-mode notice."""
    await message.answer(
        "🔒 This Bot Is Private\n\n"
        f"Please contact the administrator. {ADMIN_USERNAME}"
    )


def main_menu() -> InlineKeyboardMarkup:
    """Build the common main menu."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📺 Channels", callback_data="channels", style=ButtonStyle.PRIMARY
                ),
                InlineKeyboardButton(
                    text="📊 Stats", callback_data="stats", style=ButtonStyle.SUCCESS
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Settings", callback_data="settings", style=ButtonStyle.PRIMARY
                ),
                InlineKeyboardButton(
                    text="ℹ️ Help", callback_data="help", style=ButtonStyle.PRIMARY
                ),
            ],
        ]
    )


def channel_menu(rows: list[dict]) -> InlineKeyboardMarkup:
    """Build the connected-channel selector."""
    keyboard = [
        [
            InlineKeyboardButton(
                text=f"📢 {row.get('title', 'Channel')}",
                callback_data=f"ch:{row['channel_id']}",
                style=ButtonStyle.PRIMARY,
            )
        ]
        for row in rows[:40]
    ]
    keyboard.extend(
        [
            [
                InlineKeyboardButton(
                    text="➕ Add New Channel",
                    callback_data="add_channel",
                    style=ButtonStyle.SUCCESS,
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Back", callback_data="home", style=ButtonStyle.PRIMARY
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def settings_menu(channel_id: int, settings: dict) -> InlineKeyboardMarkup:
    """Build the per-channel settings panel."""
    def state(value: bool) -> str:
        return "ON ✅" if value else "OFF ❌"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Caption",
                    callback_data=f"set:caption:{channel_id}",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    text=f"🔘 Buttons ({len(settings['buttons'])})",
                    callback_data=f"set:buttons:{channel_id}",
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"🔄 Replace ({len(settings['replacements'])})",
                    callback_data=f"set:replace:{channel_id}",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    text=f"🎯 Filters {state(bool(settings['filters']))}",
                    callback_data=f"set:filters:{channel_id}",
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"📤 Forward {state(settings['forward']['enabled'])}",
                    callback_data=f"set:forward:{channel_id}",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    text=f"✨ Prefix {state(bool(settings['prefix']))}",
                    callback_data=f"set:prefix:{channel_id}",
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"✨ Suffix {state(bool(settings['suffix']))}",
                    callback_data=f"set:suffix:{channel_id}",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    text=f"🎉 Stickers {state(settings['stickers']['enabled'])}",
                    callback_data=f"set:stickers:{channel_id}",
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"📊 Media Details {state(settings['media_details'])}",
                    callback_data=f"set:media:{channel_id}",
                    style=ButtonStyle.PRIMARY,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Remove",
                    callback_data=f"remove:{channel_id}",
                    style=ButtonStyle.DANGER,
                ),
                InlineKeyboardButton(
                    text="↩️ Back", callback_data="channels", style=ButtonStyle.PRIMARY
                ),
            ],
        ]
    )


async def public_access(message: Message) -> bool:
    """Apply public/private mode and the FSUB gate to messages."""
    await DB.user_upsert(message.from_user.id, message.from_user.username or "")
    if await is_admin(message.from_user.id):
        return True
    if not PUBLIC_MODE:
        await private_notice(message)
        return False
    if await force_subscribed(message.bot, message.from_user.id):
        return True
    if not valid_http_url(FSUB_LINK):
        await message.answer(
            "⚠️ Force-subscribe is temporarily unavailable. "
            "Please contact the administrator."
        )
        return False
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Join Channel", url=FSUB_LINK, style=ButtonStyle.SUCCESS
                )
            ]
        ]
    )
    await message.answer(
        "🔒 <b>Join Required</b>\n\nPlease join our channel to use this bot.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    return False


async def public_access_cb(query) -> bool:
    """Apply the same access rules to callbacks."""
    await DB.user_upsert(query.from_user.id, query.from_user.username or "")
    if await is_admin(query.from_user.id):
        return True
    if not PUBLIC_MODE:
        await query.answer(
            f"🔒 This Bot Is Private. Contact the administrator {ADMIN_USERNAME}",
            show_alert=True,
        )
        return False
    if await force_subscribed(query.bot, query.from_user.id):
        return True
    await query.answer("🔒 Please join the required channel first.", show_alert=True)
    return False


async def force_subscribed(bot: Bot, user_id: int) -> bool:
    """Check membership using FSUB_CHANNEL only; never generate an invite URL."""
    if not FSUB_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(FSUB_CHANNEL, user_id)
        return member.status in {"creator", "administrator", "member"}
    except Exception:
        LOGGER.exception("FSUB membership check failed")
        return False


async def require_admin(message: Message) -> bool:
    """Allow only the owner or a stored admin."""
    if await is_admin(message.from_user.id):
        return True
    if not PUBLIC_MODE:
        await private_notice(message)
    else:
        await message.answer("❌ Admin only.")
    return False


async def report_error(bot: Bot, message: Message, error: Exception) -> None:
    """Send unexpected processing errors to the owner."""
    from html import escape

    RUNTIME["failed"] += 1
    try:
        await bot.send_message(
            OWNER_ID,
            "<b>🚨 Caption Bot Error</b>\n\n"
            f"<b>Channel:</b> {escape(str(message.chat.title or message.chat.id))}\n"
            f"<b>Message:</b> {message.message_id}\n"
            f"<blockquote expandable><b>Reason:</b> {escape(str(error)[:3000])}</blockquote>",
            parse_mode="HTML",
        )
    except Exception:
        LOGGER.exception("Could not deliver owner error report")
