"""Telegram application entry point.

The module intentionally keeps Telegram handlers thin. Persistent state lives in
``database.settings`` and caption parsing/rendering lives in ``utils``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from copy import deepcopy
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ButtonStyle
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import (
    ADMIN_USERNAME,
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


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
LOGGER = logging.getLogger("caption_bot")

router = Router()
db = Database()
states: dict[int, dict[str, Any]] = {}
started_at = time.monotonic()
runtime = {"processed": 0, "edited": 0, "failed": 0}


# ---------------------------------------------------------------------------
# Access helpers
# ---------------------------------------------------------------------------
async def is_admin(user_id: int) -> bool:
    return await db.is_admin(user_id)


async def fsub_is_satisfied(bot: Bot, user_id: int) -> bool:
    """Return True when FSUB is disabled or the user is already a member."""
    if not FSUB_CHANNEL:
        return True

    try:
        member = await bot.get_chat_member(FSUB_CHANNEL, user_id)
    except Exception as exc:  # Telegram may reject private/invalid channels.
        LOGGER.warning("FSUB membership check failed: %s", exc)
        return False

    return member.status in {"creator", "administrator", "member"}


def fsub_button_url() -> str | None:
    """Return a valid public URL for the FSUB button.

    ``FSUB_CHANNEL`` is deliberately kept separate because it is also used by
    ``get_chat_member``. Telegram's inline URL button requires a URL, not an
    ``@username`` value.
    """
    if FSUB_LINK and FSUB_LINK.startswith(("https://", "http://")):
        return FSUB_LINK

    if FSUB_CHANNEL.startswith("@"):
        return f"https://t.me/{FSUB_CHANNEL[1:]}"

    if FSUB_CHANNEL.startswith(("https://", "http://")):
        return FSUB_CHANNEL

    return None


async def allow_user(message: Message) -> bool:
    """Apply public/private mode and FSUB checks for user-facing commands."""
    user = message.from_user
    if user is None:
        return False

    await db.user_upsert(user.id, user.username or "")

    if await is_admin(user.id):
        return True

    if not PUBLIC_MODE:
        await message.answer(
            f"🔒 This Bot Is Private\n\nPlease contact the administrator. {ADMIN_USERNAME}"
        )
        return False

    if await fsub_is_satisfied(message.bot, user.id):
        return True

    url = fsub_button_url()
    if not url:
        LOGGER.error("FSUB is enabled but no valid public FSUB_LINK is configured")
        await message.answer("⚠️ Force-subscription is temporarily unavailable. Please contact the administrator.")
        return False

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Join Channel",
                    url=url,
                    style=ButtonStyle.SUCCESS,
                )
            ]
        ]
    )
    text = "🔒 <b>Join Required</b>\n\nPlease join our channel to use this bot."

    if FSUB_PIC and os.path.isfile(FSUB_PIC):
        with open(FSUB_PIC, "rb") as photo:
            await message.answer_photo(
                photo,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    return False


async def require_admin(message: Message) -> bool:
    user = message.from_user
    if user and await is_admin(user.id):
        return True

    if not PUBLIC_MODE:
        await message.answer(
            f"🔒 This Bot Is Private\n\nPlease contact the administrator. {ADMIN_USERNAME}"
        )
    else:
        await message.answer("❌ Admin only.")
    return False


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------
def merge_settings(base: dict[str, Any], saved: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge persisted settings so old documents get new defaults safely."""
    result = deepcopy(base)
    for key, value in saved.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_settings(result[key], value)
        else:
            result[key] = value
    return result


def channel_config(row: dict[str, Any]) -> dict[str, Any]:
    try:
        saved = json.loads(row.get("config") or "{}")
        if not isinstance(saved, dict):
            saved = {}
    except (TypeError, ValueError, json.JSONDecodeError):
        saved = {}
    return merge_settings(default_settings(), saved)


def button_style(color: str | None) -> ButtonStyle:
    return {
        "blue": ButtonStyle.PRIMARY,
        "primary": ButtonStyle.PRIMARY,
        "green": ButtonStyle.SUCCESS,
        "success": ButtonStyle.SUCCESS,
        "red": ButtonStyle.DANGER,
        "danger": ButtonStyle.DANGER,
    }.get((color or "blue").lower(), ButtonStyle.PRIMARY)


# ---------------------------------------------------------------------------
# UI builders
# ---------------------------------------------------------------------------
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
    keyboard.extend(
        [
            [InlineKeyboardButton(text="➕ Add New Channel", callback_data="add_channel", style=ButtonStyle.SUCCESS)],
            [InlineKeyboardButton(text="↩️ Back", callback_data="home", style=ButtonStyle.PRIMARY)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def settings_menu(channel_id: int, config: dict[str, Any]) -> InlineKeyboardMarkup:
    def state(value: bool) -> str:
        return "ON ✅" if value else "OFF ❌"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Caption", callback_data=f"set:caption:{channel_id}", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text=f"🔘 Buttons ({len(config['buttons'])})", callback_data=f"set:buttons:{channel_id}", style=ButtonStyle.SUCCESS),
            ],
            [
                InlineKeyboardButton(text=f"🔄 Replace ({len(config['replacements'])})", callback_data=f"set:replace:{channel_id}", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text=f"🎯 Filters {state(bool(config['filters']))}", callback_data=f"set:filters:{channel_id}", style=ButtonStyle.SUCCESS),
            ],
            [
                InlineKeyboardButton(text=f"📤 Forward {state(config['forward']['enabled'])}", callback_data=f"set:forward:{channel_id}", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text=f"✨ Prefix {state(bool(config['prefix']))}", callback_data=f"set:prefix:{channel_id}", style=ButtonStyle.SUCCESS),
            ],
            [
                InlineKeyboardButton(text=f"✨ Suffix {state(bool(config['suffix']))}", callback_data=f"set:suffix:{channel_id}", style=ButtonStyle.PRIMARY),
                InlineKeyboardButton(text=f"🎉 Stickers {state(config['stickers']['enabled'])}", callback_data=f"set:stickers:{channel_id}", style=ButtonStyle.SUCCESS),
            ],
            [
                InlineKeyboardButton(text=f"📊 Media Details {state(config['media_details'])}", callback_data=f"set:media:{channel_id}", style=ButtonStyle.PRIMARY),
            ],
            [
                InlineKeyboardButton(text="🗑 Remove", callback_data=f"remove:{channel_id}", style=ButtonStyle.DANGER),
                InlineKeyboardButton(text="↩️ Back", callback_data="channels", style=ButtonStyle.PRIMARY),
            ],
        ]
    )


# ---------------------------------------------------------------------------
# Error reporting
# ---------------------------------------------------------------------------
async def report_error(bot: Bot, message: Message, error: Exception) -> None:
    runtime["failed"] += 1
    safe_reason = str(error).replace(BOT_TOKEN, "[BOT_TOKEN]")[:3000]
    chat_title = getattr(message.chat, "title", None) or str(message.chat.id)

    try:
        await bot.send_message(
            OWNER_ID,
            "<b>🚨 Caption Bot Error</b>\n\n"
            f"<b>Channel:</b> {chat_title}\n"
            f"<b>Message:</b> {message.message_id}\n"
            f"<blockquote expandable><b>Reason:</b> {safe_reason}</blockquote>",
            parse_mode="HTML",
        )
    except Exception as report_exc:
        LOGGER.error("Unable to send owner error report: %s", report_exc)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
@router.message(CommandStart())
async def start(message: Message) -> None:
    if not await allow_user(message):
        return

    text = "👋 <b>Welcome to Auto Caption Bot</b>\n\n⚡ Multi-channel • Smart Caption • Colored Buttons"
    if START_PIC and os.path.isfile(START_PIC):
        with open(START_PIC, "rb") as photo:
            await message.answer_photo(photo, caption=text, reply_markup=main_menu(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=main_menu(), parse_mode="HTML")


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    if await allow_user(message):
        await message.answer(
            "<b>Help</b>\n\nUse /channels to add and configure channels. "
            "Each channel has its own settings.",
            parse_mode="HTML",
        )


@router.message(Command("settings"))
async def settings_command(message: Message) -> None:
    if await allow_user(message):
        await message.answer("⚙️ Open /channels and select a channel.", reply_markup=main_menu())


@router.message(Command("channels"))
async def channels_command(message: Message) -> None:
    if message.chat.type != "private" or not await allow_user(message):
        return
    rows = await db.list_channels(message.from_user.id)
    await message.answer(
        f"📺 <b>Channels</b>\n\nConnected: <b>{len(rows)}</b>",
        parse_mode="HTML",
        reply_markup=channel_menu(rows),
    )


@router.message(Command("stats"))
async def stats_command(message: Message) -> None:
    if not await allow_user(message):
        return
    counts = await db.counts()
    uptime = int(time.monotonic() - started_at)
    await message.answer(
        "📊 <b>Statistics</b>\n\n"
        f"👥 Users: {counts['users']}\n"
        f"📺 Channels: {counts['channels']}\n"
        f"📥 Processed: {runtime['processed']}\n"
        f"✅ Edited: {runtime['edited']}\n"
        f"❌ Errors: {runtime['failed']}\n"
        f"⏱ Uptime: {uptime // 86400}d {(uptime % 86400) // 3600}h {(uptime % 3600) // 60}m",
        parse_mode="HTML",
    )


@router.message(Command("addadmin"))
async def add_admin_command(message: Message) -> None:
    if not await require_admin(message):
        return
    try:
        user_id = int((message.text or "").split(maxsplit=1)[1])
    except (IndexError, ValueError):
        await message.answer("Usage: /addadmin USER_ID")
        return
    await db.add_admin(user_id)
    await message.answer("✅ Admin added.")


@router.message(Command("deladmin"))
async def delete_admin_command(message: Message) -> None:
    if not await require_admin(message):
        return
    try:
        user_id = int((message.text or "").split(maxsplit=1)[1])
    except (IndexError, ValueError):
        await message.answer("Usage: /deladmin USER_ID")
        return
    await db.del_admin(user_id)
    await message.answer("✅ Admin removed.")


@router.message(Command("set_public"))
async def set_public_command(message: Message) -> None:
    if await require_admin(message):
        await message.answer("Change PUBLIC_MODE in config.py and restart the bot.")


@router.message(Command("broadcast"))
async def broadcast_command(message: Message) -> None:
    if not await require_admin(message):
        return
    if not message.reply_to_message:
        await message.answer("Reply to a message with /broadcast.")
        return

    if db.db is not None:
        users = await db.db.users.find({}, {"user_id": 1, "_id": 0}).to_list(10000)
    else:
        cursor = await db.sqlite.execute("SELECT user_id FROM users")
        users = [{"user_id": row[0]} for row in await cursor.fetchall()]

    sent = failed = 0
    for user in users:
        delivered = False
        for attempt in range(3):
            try:
                await message.reply_to_message.copy_to(user["user_id"])
                delivered = True
                break
            except TelegramRetryAfter as exc:
                LOGGER.warning("Broadcast rate limited; sleeping %.1fs", exc.retry_after)
                await asyncio.sleep(exc.retry_after)
            except Exception:
                break

        if delivered:
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.10)

    await message.answer(f"📢 <b>Broadcast complete</b>\n\n✅ Sent: {sent}\n❌ Failed: {failed}", parse_mode="HTML")


# ---------------------------------------------------------------------------
# Callback navigation
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "home")
async def home_callback(query: CallbackQuery) -> None:
    await query.message.edit_text("🤖 <b>Auto Caption Bot</b>", parse_mode="HTML", reply_markup=main_menu())
    await query.answer()


@router.callback_query(F.data == "help")
async def help_callback(query: CallbackQuery) -> None:
    await query.message.edit_text("Use /channels to manage channels.", reply_markup=main_menu())
    await query.answer()


@router.callback_query(F.data == "settings")
async def settings_callback(query: CallbackQuery) -> None:
    await query.message.edit_text("⚙️ Select a channel from /channels.", reply_markup=main_menu())
    await query.answer()


@router.callback_query(F.data == "stats")
async def stats_callback(query: CallbackQuery) -> None:
    counts = await db.counts()
    await query.message.edit_text(
        f"📊 Users: {counts['users']}\n"
        f"📺 Channels: {counts['channels']}\n"
        f"📥 Processed: {runtime['processed']}\n"
        f"✅ Edited: {runtime['edited']}\n"
        f"❌ Errors: {runtime['failed']}",
        reply_markup=main_menu(),
    )
    await query.answer()


@router.callback_query(F.data == "channels")
async def channels_callback(query: CallbackQuery) -> None:
    rows = await db.list_channels(query.from_user.id)
    await query.message.edit_text(
        f"📺 <b>Channels</b>\n\nConnected: <b>{len(rows)}</b>",
        parse_mode="HTML",
        reply_markup=channel_menu(rows),
    )
    await query.answer()


@router.callback_query(F.data == "add_channel")
async def add_channel_callback(query: CallbackQuery) -> None:
    states[query.from_user.id] = {"type": "channel"}
    await query.message.edit_text(
        "➕ <b>Add Channel</b>\n\n"
        "Send the channel ID or forward a message directly from the channel.\n"
        "The bot must already be an administrator.\n\n"
        "/cancel",
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(F.data.startswith("ch:"))
async def channel_callback(query: CallbackQuery) -> None:
    try:
        channel_id = int(query.data.split(":", 1)[1])
    except (ValueError, AttributeError):
        await query.answer("Invalid channel.", show_alert=True)
        return

    row = await db.get_channel(channel_id)
    if not row or row["owner_id"] != query.from_user.id:
        await query.answer("Not your channel.", show_alert=True)
        return

    await query.message.edit_text(
        f"📄 <b>{row['title']}</b>\n"
        f"🆔 <code>{channel_id}</code>\n"
        f"🔗 @{row.get('username') or 'private'}",
        parse_mode="HTML",
        reply_markup=settings_menu(channel_id, channel_config(row)),
    )
    await query.answer()


@router.callback_query(F.data.startswith("set:"))
async def setting_callback(query: CallbackQuery) -> None:
    try:
        _, kind, channel_id_text = query.data.split(":", 2)
        channel_id = int(channel_id_text)
    except (ValueError, AttributeError):
        await query.answer("Invalid setting.", show_alert=True)
        return

    row = await db.get_channel(channel_id)
    if not row or row["owner_id"] != query.from_user.id:
        await query.answer("Not your channel.", show_alert=True)
        return

    config = channel_config(row)
    if kind == "media":
        config["media_details"] = not config["media_details"]
    elif kind == "stickers":
        config["stickers"]["enabled"] = not config["stickers"]["enabled"]
    else:
        states[query.from_user.id] = {"type": kind, "cid": channel_id}
        prompts = {
            "caption": "📝 Send your caption template.",
            "buttons": "🔘 Send: Button Text | URL | blue/green/red",
            "replace": "🔄 Send: old text | new text",
            "filters": "🎯 Send a media type: video/audio/document/photo/animation/voice/sticker",
            "forward": "📤 Send the destination channel ID.",
            "prefix": "✨ Send the prefix text.",
            "suffix": "✨ Send the suffix text.",
        }
        await query.message.edit_text(f"{prompts[kind]}\n\n/cancel")
        await query.answer()
        return

    await db.save_channel(row["owner_id"], channel_id, row["title"], row.get("username", ""), json.dumps(config))
    await query.message.edit_reply_markup(reply_markup=settings_menu(channel_id, config))
    await query.answer()


@router.callback_query(F.data.startswith("remove:"))
async def remove_channel_callback(query: CallbackQuery) -> None:
    try:
        channel_id = int(query.data.split(":", 1)[1])
    except (ValueError, AttributeError):
        await query.answer("Invalid channel.", show_alert=True)
        return

    row = await db.get_channel(channel_id)
    if not row or row["owner_id"] != query.from_user.id:
        await query.answer("Not your channel.", show_alert=True)
        return

    await db.delete_channel(channel_id, query.from_user.id)
    await query.message.edit_text(
        "🗑 Channel removed.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="↩️ Channels", callback_data="channels", style=ButtonStyle.PRIMARY)]
            ]
        ),
    )
    await query.answer()


# ---------------------------------------------------------------------------
# Interactive private input
# ---------------------------------------------------------------------------
@router.message(Command("cancel"))
async def cancel_command(message: Message) -> None:
    states.pop(message.from_user.id, None)
    await message.answer("❌ Cancelled.")


async def resolve_channel_input(message: Message) -> int | None:
    """Resolve only a channel-origin forward or an explicit numeric channel ID."""
    origin = message.forward_origin
    origin_chat = getattr(origin, "chat", None)
    if origin_chat is not None:
        if getattr(origin_chat, "type", None) != "channel":
            await message.answer("❌ Please forward a message directly from a Telegram channel.")
            return None
        return origin_chat.id

    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Send a numeric channel ID or forward a message from the channel.")
        return None

    try:
        return int(text)
    except ValueError:
        await message.answer("❌ Invalid channel ID. Example: <code>-1001234567890</code>", parse_mode="HTML")
        return None


@router.message(F.chat.type == "private")
async def private_input(message: Message) -> None:
    state = states.get(message.from_user.id)
    if not state:
        return

    try:
        if state["type"] == "channel":
            channel_id = await resolve_channel_input(message)
            if channel_id is None:
                return

            me = await message.bot.get_me()
            member = await message.bot.get_chat_member(channel_id, me.id)
            if member.status not in {"administrator", "creator"}:
                await message.answer("❌ Bot must be administrator in this channel.")
                return

            chat = await message.bot.get_chat(channel_id)
            config = default_settings()
            await db.save_channel(
                message.from_user.id,
                channel_id,
                chat.title or "Channel",
                chat.username or "",
                json.dumps(config),
            )
            states.pop(message.from_user.id, None)
            await message.answer(
                f"✅ <b>{chat.title}</b> added.",
                parse_mode="HTML",
                reply_markup=settings_menu(channel_id, config),
            )
            return

        channel_id = state["cid"]
        row = await db.get_channel(channel_id)
        if not row or row["owner_id"] != message.from_user.id:
            states.pop(message.from_user.id, None)
            await message.answer("❌ Channel configuration was not found.")
            return

        config = channel_config(row)
        text = message.text or message.caption or ""
        kind = state["type"]

        if kind == "caption":
            config["caption"] = text
        elif kind in {"prefix", "suffix"}:
            config[kind] = text
        elif kind == "replace":
            parts = text.split("|", 1)
            if len(parts) != 2 or not parts[0].strip():
                await message.answer("Use: old text | new text")
                return
            config["replacements"][parts[0].strip()] = parts[1].strip()
        elif kind == "buttons":
            parts = [part.strip() for part in text.split("|")]
            if len(parts) != 3 or parts[2].lower() not in {"blue", "green", "red"}:
                await message.answer("Use: Button Text | URL | blue/green/red")
                return
            if not parts[1].startswith(("https://", "http://", "tg://")):
                await message.answer("❌ Button URL must be a valid http(s) or tg:// URL.")
                return
            config["buttons"].append({"text": parts[0], "url": parts[1], "color": parts[2].lower()})
        elif kind == "forward":
            config["forward"] = {"enabled": True, "destination": int(text)}
        elif kind == "filters":
            config["filters"] = {"type": text.lower()}
        else:
            await message.answer("❌ Unknown setting.")
            states.pop(message.from_user.id, None)
            return

        await db.save_channel(row["owner_id"], channel_id, row["title"], row.get("username", ""), json.dumps(config))
        states.pop(message.from_user.id, None)
        await message.answer("✅ Saved.", reply_markup=settings_menu(channel_id, config))
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        await private_input(message)
    except Exception as exc:
        await report_error(message.bot, message, exc)
        await message.answer("❌ Something went wrong. The administrator has been notified.")


# ---------------------------------------------------------------------------
# Channel processing
# ---------------------------------------------------------------------------
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
    if not filters:
        return True
    media_type = str(filters.get("type") or "").lower()
    if not media_type:
        return True
    media_map = {
        "video": message.video,
        "audio": message.audio,
        "document": message.document,
        "photo": message.photo,
        "animation": message.animation,
        "voice": message.voice,
        "sticker": message.sticker,
    }
    return bool(media_map.get(media_type))


async def edit_caption_with_retry(message: Message, caption: str, keyboard: InlineKeyboardMarkup | None) -> bool:
    for attempt in range(3):
        try:
            await message.bot.edit_message_caption(
                chat_id=message.chat.id,
                message_id=message.message_id,
                caption=caption or None,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            return True
        except TelegramRetryAfter as exc:
            LOGGER.warning("Caption edit rate limited; retry %d after %.1fs", attempt + 1, exc.retry_after)
            await asyncio.sleep(exc.retry_after)
    return False


@router.channel_post()
async def channel_post(message: Message) -> None:
    row = await db.get_channel(message.chat.id)
    if not row or not has_media(message):
        return

    config = channel_config(row)
    if not media_matches_filter(message, config["filters"]):
        return

    runtime["processed"] += 1

    try:
        caption = format_caption(config["caption"], message) if config["caption"] else (message.caption or "")

        for old, new in config["replacements"].items():
            caption = caption.replace(old, new)
        if config["prefix"]:
            caption = f"{config['prefix']}\n{caption}" if caption else config["prefix"]
        if config["suffix"]:
            caption = f"{caption}\n{config['suffix']}" if caption else config["suffix"]

        buttons = [
            InlineKeyboardButton(
                text=item["text"],
                url=item["url"],
                style=button_style(item.get("color")),
            )
            for item in config["buttons"]
            if item.get("text") and item.get("url")
        ]
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[buttons[index : index + 2] for index in range(0, len(buttons), 2)]
        ) if buttons else None

        if caption != (message.caption or "") or keyboard:
            if await edit_caption_with_retry(message, caption, keyboard):
                runtime["edited"] += 1

        destination = config["forward"].get("destination")
        if config["forward"].get("enabled") and destination:
            for attempt in range(3):
                try:
                    await message.bot.copy_message(destination, message.chat.id, message.message_id)
                    break
                except TelegramRetryAfter as exc:
                    await asyncio.sleep(exc.retry_after)
                except Exception:
                    raise
    except Exception as exc:
        await report_error(message.bot, message, exc)


async def main() -> None:
    await db.connect()
    bot = Bot(BOT_TOKEN)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    LOGGER.info("Starting Auto Caption Bot")
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
