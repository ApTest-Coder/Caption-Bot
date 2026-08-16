"""Telegram entry point for Caption Bot.

The application is intentionally thin: configuration, persistence, parsing and
caption rendering live in dedicated modules so channel-specific behaviour is
safe to extend without turning the dispatcher into a monolith.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ButtonStyle
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import (
    ADMIN_USERNAME,
    API_HASH,
    API_ID,
    BOT_TOKEN,
    FSUB_CHANNEL,
    FSUB_LINK,
    FSUB_PIC,
    OWNER_ID,
    PUBLIC_MODE,
    START_PIC,
)
from database.settings import Database, default_settings
from utils.formatter import format_caption

LOGGER = logging.getLogger("caption_bot")
ROUTER = Router()
DB = Database()
STATES: dict[int, dict[str, Any]] = {}
STARTED_AT = time.monotonic()
RUNTIME = {"processed": 0, "edited": 0, "failed": 0}


def button_style(value: str | None) -> ButtonStyle:
    """Map a user-facing colour name to Telegram's supported button styles."""
    styles = {
        "blue": ButtonStyle.PRIMARY,
        "primary": ButtonStyle.PRIMARY,
        "green": ButtonStyle.SUCCESS,
        "success": ButtonStyle.SUCCESS,
        "red": ButtonStyle.DANGER,
        "danger": ButtonStyle.DANGER,
    }
    return styles.get((value or "blue").strip().lower(), ButtonStyle.PRIMARY)


def valid_http_url(value: str) -> bool:
    """Return True only for an absolute HTTP(S) URL suitable for a button."""
    try:
        parsed = urlparse(value.strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def merged_config(row: dict[str, Any]) -> dict[str, Any]:
    """Merge stored channel settings over a fresh default configuration."""
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
    seconds = int(time.monotonic() - STARTED_AT)
    days, seconds = divmod(seconds, 86_400)
    hours, seconds = divmod(seconds, 3_600)
    minutes, _ = divmod(seconds, 60)
    return f"{days}d {hours}h {minutes}m"


def has_media(message: Message) -> bool:
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


def media_matches_filter(message: Message, filters: dict[str, Any]) -> bool:
    """Apply the configured media type filter without raising on bad config."""
    if not filters:
        return True
    media_type = str(filters.get("type") or "").lower().strip()
    if not media_type:
        return True
    media = {
        "video": message.video,
        "audio": message.audio,
        "document": message.document,
        "photo": message.photo,
        "animation": message.animation,
        "voice": message.voice,
        "sticker": message.sticker,
    }
    return bool(media.get(media_type))


async def is_admin(user_id: int) -> bool:
    return user_id == OWNER_ID or await DB.is_admin(user_id)


async def force_subscribed(bot: Bot, user_id: int) -> bool:
    if not FSUB_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(FSUB_CHANNEL, user_id)
        return member.status in {"creator", "administrator", "member"}
    except Exception:
        LOGGER.exception("FSUB membership check failed")
        return False


async def send_private_notice(message: Message) -> None:
    await message.answer(
        "🔒 This Bot Is Private\n\n"
        f"Please contact the administrator. {ADMIN_USERNAME}"
    )


async def has_public_access(message: Message) -> bool:
    await DB.user_upsert(message.from_user.id, message.from_user.username or "")
    if await is_admin(message.from_user.id):
        return True
    if not PUBLIC_MODE:
        await send_private_notice(message)
        return False

    if await force_subscribed(message.bot, message.from_user.id):
        return True

    if not valid_http_url(FSUB_LINK):
        await message.answer("⚠️ Force-subscribe is temporarily unavailable. Please contact the administrator.")
        LOGGER.error("Invalid FSUB_LINK configured: %r", FSUB_LINK)
        return False

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Join Channel",
                    url=FSUB_LINK,
                    style=ButtonStyle.SUCCESS,
                )
            ]
        ]
    )
    text = "🔒 <b>Join Required</b>\n\nPlease join our channel to use this bot."
    if FSUB_PIC and os.path.exists(FSUB_PIC):
        with open(FSUB_PIC, "rb") as photo:
            await message.answer_photo(photo, caption=text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    return False


async def require_admin(message: Message) -> bool:
    if await is_admin(message.from_user.id):
        return True
    if not PUBLIC_MODE:
        await send_private_notice(message)
    else:
        await message.answer("❌ Admin only.")
    return False


async def report_error(bot: Bot, message: Message, error: Exception) -> None:
    """Send unexpected processing errors to the owner without exposing secrets."""
    RUNTIME["failed"] += 1
    reason = str(error).replace("BOT_TOKEN", "[REDACTED]")[:3000]
    try:
        await bot.send_message(
            OWNER_ID,
            "<b>🚨 Caption Bot Error</b>\n\n"
            f"<b>Channel:</b> {message.chat.title or message.chat.id}\n"
            f"<b>Message:</b> {message.message_id}\n"
            f"<blockquote expandable><b>Reason:</b> {reason}</blockquote>",
            parse_mode="HTML",
        )
    except Exception:
        LOGGER.exception("Could not deliver owner error report")


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📺 Channels", callback_data="channels", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text="📊 Stats", callback_data="stats", style=ButtonStyle.SUCCESS),
            ],
            [
                InlineKeyboardButton(text="⚙️ Settings", callback_data="settings", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text="ℹ️ Help", callback_data="help", style=ButtonStyle.PRIMARY),
            ],
        ]
    )


def channel_menu(rows: list[dict[str, Any]]) -> InlineKeyboardMarkup:
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
    keyboard += [
        [InlineKeyboardButton(text="➕ Add New Channel", callback_data="add_channel", style=ButtonStyle.SUCCESS)],
        [InlineKeyboardButton(text="↩️ Back", callback_data="home", style=ButtonStyle.PRIMARY)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def settings_menu(channel_id: int, settings: dict[str, Any]) -> InlineKeyboardMarkup:
    def state(value: bool) -> str:
        return "ON ✅" if value else "OFF ❌"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Caption", callback_data=f"set:caption:{channel_id}", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text=f"🔘 Buttons ({len(settings['buttons'])})", callback_data=f"set:buttons:{channel_id}", style=ButtonStyle.SUCCESS),
            ],
            [
                InlineKeyboardButton(text=f"🔄 Replace ({len(settings['replacements'])})", callback_data=f"set:replace:{channel_id}", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text=f"🎯 Filters {state(bool(settings['filters']))}", callback_data=f"set:filters:{channel_id}", style=ButtonStyle.SUCCESS),
            ],
            [
                InlineKeyboardButton(text=f"📤 Forward {state(settings['forward']['enabled'])}", callback_data=f"set:forward:{channel_id}", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text=f"✨ Prefix {state(bool(settings['prefix']))}", callback_data=f"set:prefix:{channel_id}", style=ButtonStyle.SUCCESS),
            ],
            [
                InlineKeyboardButton(text=f"✨ Suffix {state(bool(settings['suffix']))}", callback_data=f"set:suffix:{channel_id}", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text=f"🎉 Stickers {state(settings['stickers']['enabled'])}", callback_data=f"set:stickers:{channel_id}", style=ButtonStyle.SUCCESS),
            ],
            [InlineKeyboardButton(text=f"📊 Media Details {state(settings['media_details'])}", callback_data=f"set:media:{channel_id}", style=ButtonStyle.PRIMARY)],
            [
                InlineKeyboardButton(text="🗑 Remove", callback_data=f"remove:{channel_id}", style=ButtonStyle.DANGER),
                InlineKeyboardButton(text="↩️ Back", callback_data="channels", style=ButtonStyle.PRIMARY),
            ],
        ]
    )


@ROUTER.message(CommandStart())
async def start_command(message: Message) -> None:
    if not await has_public_access(message):
        return
    text = "👋 <b>Welcome to Auto Caption Bot</b>\n\n⚡ Multi-channel • Smart Caption • Colored Buttons"
    if START_PIC and os.path.exists(START_PIC):
        with open(START_PIC, "rb") as photo:
            await message.answer_photo(photo, caption=text, reply_markup=main_menu(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=main_menu(), parse_mode="HTML")


@ROUTER.message(Command("help"))
async def help_command(message: Message) -> None:
    if await has_public_access(message):
        await message.answer("<b>Help</b>\n\nUse /channels to add and configure channels.", parse_mode="HTML")


@ROUTER.message(Command("settings"))
async def settings_command(message: Message) -> None:
    if await has_public_access(message):
        await message.answer("⚙️ Select a channel from /channels.", reply_markup=main_menu())


@ROUTER.message(Command("channels"))
async def channels_command(message: Message) -> None:
    if message.chat.type != "private" or not await has_public_access(message):
        return
    rows = await DB.list_channels(message.from_user.id)
    await message.answer(
        f"📺 <b>Channels</b>\n\nConnected: <b>{len(rows)}</b>",
        parse_mode="HTML",
        reply_markup=channel_menu(rows),
    )


@ROUTER.message(Command("stats"))
async def stats_command(message: Message) -> None:
    if not await has_public_access(message):
        return
    counts = await DB.counts()
    await message.answer(
        "📊 <b>Statistics</b>\n\n"
        f"👥 Users: {counts['users']}\n"
        f"📺 Channels: {counts['channels']}\n"
        f"📥 Processed: {RUNTIME['processed']}\n"
        f"✅ Edited: {RUNTIME['edited']}\n"
        f"❌ Errors: {RUNTIME['failed']}\n"
        f"⏱ Uptime: {uptime_text()}",
        parse_mode="HTML",
    )


@ROUTER.message(Command("addadmin"))
async def add_admin_command(message: Message) -> None:
    if not await require_admin(message):
        return
    try:
        user_id = int((message.text or "").split(maxsplit=1)[1])
        await DB.add_admin(user_id)
        await message.answer("✅ Admin added.")
    except (IndexError, ValueError):
        await message.answer("Usage: /addadmin USER_ID")


@ROUTER.message(Command("deladmin"))
async def delete_admin_command(message: Message) -> None:
    if not await require_admin(message):
        return
    try:
        user_id = int((message.text or "").split(maxsplit=1)[1])
        await DB.del_admin(user_id)
        await message.answer("✅ Admin removed.")
    except (IndexError, ValueError):
        await message.answer("Usage: /deladmin USER_ID")


@ROUTER.message(Command("set_public"))
async def set_public_command(message: Message) -> None:
    if await require_admin(message):
        await message.answer("Change PUBLIC_MODE in config.py and restart the bot.")


@ROUTER.message(Command("cancel"))
async def cancel_command(message: Message) -> None:
    STATES.pop(message.from_user.id, None)
    await message.answer("❌ Cancelled.")


@ROUTER.callback_query(F.data == "home")
async def home_callback(query) -> None:
    await query.message.edit_text("🤖 <b>Auto Caption Bot</b>", parse_mode="HTML", reply_markup=main_menu())
    await query.answer()


@ROUTER.callback_query(F.data == "help")
async def help_callback(query) -> None:
    await query.message.edit_text("Use /channels to manage channels.", reply_markup=main_menu())
    await query.answer()


@ROUTER.callback_query(F.data == "settings")
async def settings_callback(query) -> None:
    await query.message.edit_text("⚙️ Select a channel from /channels.", reply_markup=main_menu())
    await query.answer()


@ROUTER.callback_query(F.data == "stats")
async def stats_callback(query) -> None:
    counts = await DB.counts()
    await query.message.edit_text(
        f"📊 Users: {counts['users']}\n📺 Channels: {counts['channels']}\n"
        f"📥 Processed: {RUNTIME['processed']}\n✅ Edited: {RUNTIME['edited']}\n❌ Errors: {RUNTIME['failed']}",
        reply_markup=main_menu(),
    )
    await query.answer()


@ROUTER.callback_query(F.data == "channels")
async def channels_callback(query) -> None:
    rows = await DB.list_channels(query.from_user.id)
    await query.message.edit_text(
        f"📺 <b>Channels</b>\n\nConnected: <b>{len(rows)}</b>",
        parse_mode="HTML",
        reply_markup=channel_menu(rows),
    )
    await query.answer()


@ROUTER.callback_query(F.data == "add_channel")
async def add_channel_callback(query) -> None:
    STATES[query.from_user.id] = {"type": "channel"}
    await query.message.edit_text(
        "➕ <b>Add Channel</b>\n\nSend the Channel ID or forward a message directly from that channel.\n"
        "The bot must already be an administrator there.\n\n/cancel",
        parse_mode="HTML",
    )
    await query.answer()


@ROUTER.callback_query(F.data.startswith("ch:"))
async def channel_callback(query) -> None:
    channel_id = int(query.data.split(":", 1)[1])
    row = await DB.get_channel(channel_id)
    if not row or row["owner_id"] != query.from_user.id:
        await query.answer("Not your channel.", show_alert=True)
        return
    settings = merged_config(row)
    await query.message.edit_text(
        f"📄 <b>{row['title']}</b>\n🆔 <code>{channel_id}</code>\n🔗 @{row.get('username') or 'private'}",
        parse_mode="HTML",
        reply_markup=settings_menu(channel_id, settings),
    )
    await query.answer()


@ROUTER.message(F.chat.type == "private")
async def private_input(message: Message) -> None:
    state = STATES.get(message.from_user.id)
    if not state:
        return

    try:
        if state["type"] == "channel":
            origin = getattr(message, "forward_origin", None)
            origin_chat = getattr(origin, "chat", None)
            if origin_chat is None:
                raw_id = (message.text or "").strip()
                if not raw_id or not raw_id.lstrip("-").isdigit():
                    await message.answer("❌ Send a numeric Channel ID or forward a message directly from a channel.")
                    return
                channel_id = int(raw_id)
            else:
                channel_id = origin_chat.id

            me = await message.bot.get_me()
            member = await message.bot.get_chat_member(channel_id, me.id)
            if member.status not in {"administrator", "creator"}:
                await message.answer("❌ Bot must be an administrator in this channel.")
                return

            chat = await message.bot.get_chat(channel_id)
            settings = default_settings()
            await DB.save_channel(message.from_user.id, channel_id, chat.title or "Channel", chat.username or "", json.dumps(settings))
            STATES.pop(message.from_user.id, None)
            await message.answer(
                f"✅ <b>{chat.title}</b> added.",
                parse_mode="HTML",
                reply_markup=settings_menu(channel_id, settings),
            )
            return

        channel_id = state["channel_id"]
        row = await DB.get_channel(channel_id)
        if not row or row["owner_id"] != message.from_user.id:
            STATES.pop(message.from_user.id, None)
            await message.answer("❌ Channel configuration was not found.")
            return

        settings = merged_config(row)
        text = message.text or message.caption or ""
        kind = state["type"]
        if kind == "caption":
            settings["caption"] = text
        elif kind in {"prefix", "suffix"}:
            settings[kind] = text
        elif kind == "replace":
            parts = text.split("|", 1)
            if len(parts) != 2:
                await message.answer("Use: old text | new text")
                return
            settings["replacements"][parts[0].strip()] = parts[1].strip()
        elif kind == "buttons":
            parts = [item.strip() for item in text.split("|")]
            if len(parts) != 3 or parts[2].lower() not in {"blue", "green", "red"}:
                await message.answer("Use: Button Text | URL | blue/green/red")
                return
            if not valid_http_url(parts[1]):
                await message.answer("❌ Button URL must start with http:// or https://")
                return
            settings["buttons"].append({"text": parts[0], "url": parts[1], "color": parts[2].lower()})
        elif kind == "forward":
            settings["forward"] = {"enabled": True, "destination": int(text)}
        elif kind == "filters":
            settings["filters"] = {"type": text.lower().strip()}

        await DB.save_channel(row["owner_id"], channel_id, row["title"], row.get("username", ""), json.dumps(settings))
        STATES.pop(message.from_user.id, None)
        await message.answer("✅ Saved.", reply_markup=settings_menu(channel_id, settings))
    except (ValueError, TypeError) as exc:
        await message.answer("❌ Invalid value. Please check the format and try again.")
        LOGGER.info("Invalid channel-setting input: %s", exc)
    except Exception as exc:
        await report_error(message.bot, message, exc)


@ROUTER.channel_post()
async def channel_post(message: Message) -> None:
    row = await DB.get_channel(message.chat.id)
    if not row or not has_media(message):
        return

    settings = merged_config(row)
    if not media_matches_filter(message, settings["filters"]):
        return

    RUNTIME["processed"] += 1
    try:
        caption = format_caption(settings["caption"], message) if settings["caption"] else (message.caption or "")
        for old, new in settings["replacements"].items():
            caption = caption.replace(old, new)
        if settings["prefix"]:
            caption = f"{settings['prefix']}\n{caption}" if caption else settings["prefix"]
        if settings["suffix"]:
            caption = f"{caption}\n{settings['suffix']}" if caption else settings["suffix"]

        buttons = [
            InlineKeyboardButton(
                text=item["text"],
                url=item["url"],
                style=button_style(item.get("color")),
            )
            for item in settings["buttons"]
            if item.get("text") and valid_http_url(item.get("url", ""))
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=[buttons[index : index + 2] for index in range(0, len(buttons), 2)]) if buttons else None

        if caption != (message.caption or "") or markup:
            await message.bot.edit_message_caption(
                chat_id=message.chat.id,
                message_id=message.message_id,
                caption=caption or None,
                parse_mode="HTML",
                reply_markup=markup,
            )
            RUNTIME["edited"] += 1

        if settings["forward"]["enabled"] and settings["forward"]["destination"]:
            await message.bot.copy_message(settings["forward"]["destination"], message.chat.id, message.message_id)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        try:
            await message.bot.edit_message_caption(
                chat_id=message.chat.id,
                message_id=message.message_id,
                caption=caption or None,
                parse_mode="HTML",
            )
        except Exception as retry_error:
            await report_error(message.bot, message, retry_error)
    except Exception as exc:
        await report_error(message.bot, message, exc)


async def main() -> None:
    """Initialise persistence and start long polling."""
    await DB.connect()
    bot = Bot(BOT_TOKEN)
    dispatcher = Dispatcher()
    dispatcher.include_router(ROUTER)
    LOGGER.info("Caption Bot starting in %s mode", "public" if PUBLIC_MODE else "private")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
