"""Shared runtime context for feature plugins."""

from __future__ import annotations

import json
import logging
import time
from html import escape
from urllib.parse import urlparse

from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMIN_USERNAME, FSUB_LINK, OWNER_ID, PUBLIC_MODE
from database.settings import Database, default_settings

LOGGER = logging.getLogger("caption_bot")
DB = Database()
RUNTIME = {"processed": 0, "edited": 0, "failed": 0}
STATES: dict[int, dict] = {}
STARTED_AT = time.monotonic()
VALID_FILTERS = {
    "video",
    "audio",
    "document",
    "photo",
    "animation",
    "voice",
    "sticker",
}


def valid_http_url(value: str) -> bool:
    """Return True only for absolute HTTP(S) URLs."""
    parsed = urlparse((value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def button_style(value: str | None) -> ButtonStyle:
    """Convert a user-facing colour name to Telegram's button style."""
    return {
        "blue": ButtonStyle.PRIMARY,
        "primary": ButtonStyle.PRIMARY,
        "green": ButtonStyle.SUCCESS,
        "success": ButtonStyle.SUCCESS,
        "red": ButtonStyle.DANGER,
        "danger": ButtonStyle.DANGER,
    }.get((value or "blue").strip().lower(), ButtonStyle.PRIMARY)


def _safe_settings(stored: object) -> dict:
    """Normalize persisted settings without letting corrupt data crash the UI."""
    base = default_settings()
    if not isinstance(stored, dict):
        return base

    buttons = stored.get("buttons")
    if isinstance(buttons, list):
        base["buttons"] = [
            item
            for item in buttons
            if isinstance(item, dict)
            and isinstance(item.get("text"), str)
            and isinstance(item.get("url"), str)
        ]

    replacements = stored.get("replacements")
    if isinstance(replacements, dict):
        base["replacements"] = {
            str(old): str(new)
            for old, new in replacements.items()
            if str(old).strip()
        }

    filters = stored.get("filters")
    if isinstance(filters, dict) and isinstance(filters.get("type"), str):
        filter_type = filters["type"].strip().lower()
        if filter_type in VALID_FILTERS:
            base["filters"] = {"type": filter_type}

    forward = stored.get("forward")
    if isinstance(forward, dict):
        enabled = forward.get("enabled")
        destination = forward.get("destination")
        if isinstance(enabled, bool):
            base["forward"]["enabled"] = enabled
        if isinstance(destination, int):
            base["forward"]["destination"] = destination

    stickers = stored.get("stickers")
    if isinstance(stickers, dict) and isinstance(stickers.get("enabled"), bool):
        base["stickers"]["enabled"] = stickers["enabled"]

    for key in ("caption", "prefix", "suffix"):
        value = stored.get(key)
        if isinstance(value, str):
            base[key] = value

    media_details = stored.get("media_details")
    if isinstance(media_details, bool):
        base["media_details"] = media_details

    return base


def merged_config(row: dict) -> dict:
    """Merge persisted channel settings with safe current defaults."""
    try:
        stored = json.loads(row.get("config") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        LOGGER.warning("Invalid settings JSON for channel %s", row.get("channel_id"))
        return default_settings()
    return _safe_settings(stored)


def uptime_text() -> str:
    """Return process uptime."""
    seconds = int(time.monotonic() - STARTED_AT)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    return f"{days}d {hours}h {minutes}m"


def has_media(message: Message) -> bool:
    """Return whether a post contains supported media."""
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
    media_type = str(filters.get("type") or "").strip().lower() if isinstance(filters, dict) else ""
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
                    text="📺 Channels",
                    callback_data="channels",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    text="📊 Stats",
                    callback_data="stats",
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Settings",
                    callback_data="settings",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    text="ℹ️ Help",
                    callback_data="help",
                    style=ButtonStyle.PRIMARY,
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
                    text="↩️ Back",
                    callback_data="home",
                    style=ButtonStyle.PRIMARY,
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def settings_menu(channel_id: int, settings: dict) -> InlineKeyboardMarkup:
    """Build the per-channel settings panel."""
    safe = _safe_settings(settings)

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
                    text=f"🔘 Buttons ({len(safe['buttons'])})",
                    callback_data=f"set:buttons:{channel_id}",
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"🔄 Replace ({len(safe['replacements'])})",
                    callback_data=f"set:replace:{channel_id}",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    text=f"🎯 Filters {state(bool(safe['filters']))}",
                    callback_data=f"set:filters:{channel_id}",
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"📤 Forward {state(safe['forward']['enabled'])}",
                    callback_data=f"set:forward:{channel_id}",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    text=f"✨ Prefix {state(bool(safe['prefix']))}",
                    callback_data=f"set:prefix:{channel_id}",
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"✨ Suffix {state(bool(safe['suffix']))}",
                    callback_data=f"set:suffix:{channel_id}",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    text=f"🎉 Stickers {state(safe['stickers']['enabled'])}",
                    callback_data=f"set:stickers:{channel_id}",
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"📊 Media Details {state(safe['media_details'])}",
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
                    text="↩️ Back",
                    callback_data="channels",
                    style=ButtonStyle.PRIMARY,
                ),
            ],
        ]
    )


async def public_access(message: Message) -> bool:
    """Apply public/private mode and the force-subscribe gate."""
    await DB.user_upsert(message.from_user.id, message.from_user.username or "")
    if await is_admin(message.from_user.id):
        return True
    if not PUBLIC_MODE:
        await private_notice(message)
        return False

    from .fsub import require_membership, send_gate

    allowed, _ = await require_membership(message.bot, message.from_user.id)
    if allowed:
        return True
    if not valid_http_url(FSUB_LINK):
        await message.answer(
            "⚠️ Force-subscribe is temporarily unavailable. "
            "Please contact the administrator."
        )
        return False
    await send_gate(message)
    return False


async def public_access_cb(query) -> bool:
    """Apply public/private mode to inline callbacks."""
    await DB.user_upsert(query.from_user.id, query.from_user.username or "")
    if await is_admin(query.from_user.id):
        return True
    if not PUBLIC_MODE:
        await query.answer(
            "🔒 This Bot Is Private. "
            f"Contact the administrator {ADMIN_USERNAME}",
            show_alert=True,
        )
        return False

    from .fsub import require_membership, send_gate

    allowed, keyboard = await require_membership(query.bot, query.from_user.id)
    if allowed:
        return True
    if keyboard:
        await query.message.answer(
            "🔒 <b>Join Required</b>\n\nPlease join our channel to use this bot.",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        await query.answer(
            "⚠️ Force-subscribe is temporarily unavailable."
            ,
            show_alert=True,
        )
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


async def report_error(bot, message: Message, error: Exception) -> None:
    """Send unexpected processing errors to the owner."""
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
