"""Caption Bot entry point.

Telegram handlers live here; persistence, parsing and rendering stay in
separate modules so the project remains maintainable.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ButtonStyle
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

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
from utils.logger import setup as setup_logging

LOGGER = logging.getLogger("caption_bot")
ROUTER = Router()
DB = Database()
STATES: dict[int, dict] = {}
STARTED_AT = time.monotonic()
RUNTIME = {"processed": 0, "edited": 0, "failed": 0}
VALID_FILTERS = {"video", "audio", "document", "photo", "animation", "voice", "sticker"}


def valid_http_url(value: str) -> bool:
    """Validate a URL before giving it to Telegram as a button target."""
    parsed = urlparse((value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def button_style(value: str | None) -> ButtonStyle:
    """Map blue/green/red user settings to Telegram button styles."""
    return {
        "blue": ButtonStyle.PRIMARY,
        "primary": ButtonStyle.PRIMARY,
        "green": ButtonStyle.SUCCESS,
        "success": ButtonStyle.SUCCESS,
        "red": ButtonStyle.DANGER,
        "danger": ButtonStyle.DANGER,
    }.get((value or "blue").strip().lower(), ButtonStyle.PRIMARY)


def merged_config(row: dict) -> dict:
    """Merge stored settings onto current defaults for backward compatibility."""
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
    """Return process uptime in a compact form."""
    seconds = int(time.monotonic() - STARTED_AT)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    return f"{days}d {hours}h {minutes}m"


def has_media(message: Message) -> bool:
    """Return whether a channel post contains supported media."""
    return any((message.video, message.audio, message.document, message.photo, message.animation, message.voice, message.sticker))


def media_matches_filter(message: Message, filters: dict) -> bool:
    """Apply the optional per-channel media-type filter."""
    media_type = str(filters.get("type") or "").lower().strip() if filters else ""
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
    """Check the owner or a stored administrator."""
    return user_id == OWNER_ID or await DB.is_admin(user_id)


async def private_notice(message: Message) -> None:
    """Tell non-admin users that private mode is enabled."""
    await message.answer(f"🔒 This Bot Is Private\n\nPlease contact the administrator. {ADMIN_USERNAME}")


async def force_subscribed(bot: Bot, user_id: int) -> bool:
    """Check whether a user belongs to the configured force-subscribe channel."""
    if not FSUB_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(FSUB_CHANNEL, user_id)
        return member.status in {"creator", "administrator", "member"}
    except Exception:
        LOGGER.exception("FSUB membership check failed")
        return False


async def public_access(message: Message) -> bool:
    """Apply private mode and force-subscribe access rules."""
    await DB.user_upsert(message.from_user.id, message.from_user.username or "")
    if await is_admin(message.from_user.id):
        return True
    if not PUBLIC_MODE:
        await private_notice(message)
        return False
    if await force_subscribed(message.bot, message.from_user.id):
        return True
    if not valid_http_url(FSUB_LINK):
        LOGGER.error("Invalid FSUB_LINK configured: %r", FSUB_LINK)
        await message.answer("⚠️ Force-subscribe is temporarily unavailable. Please contact the administrator.")
        return False
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 Join Channel", url=FSUB_LINK, style=ButtonStyle.SUCCESS)]])
    text = "🔒 <b>Join Required</b>\n\nPlease join our channel to use this bot."
    if FSUB_PIC and os.path.exists(FSUB_PIC):
        with open(FSUB_PIC, "rb") as photo:
            await message.answer_photo(photo, caption=text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    return False


async def public_access_cb(query) -> bool:
    """Apply the same private-mode / force-subscribe rules to inline-menu clicks."""
    await DB.user_upsert(query.from_user.id, query.from_user.username or "")
    if await is_admin(query.from_user.id):
        return True
    if not PUBLIC_MODE:
        await query.answer(f"🔒 This Bot Is Private. Contact the administrator {ADMIN_USERNAME}", show_alert=True)
        return False
    if await force_subscribed(query.bot, query.from_user.id):
        return True
    await query.answer("🔒 Please join our channel first — use /start to get the join button.", show_alert=True)
    return False


async def require_admin(message: Message) -> bool:
    """Allow an owner/admin command only to privileged users."""
    if await is_admin(message.from_user.id):
        return True
    if not PUBLIC_MODE:
        await private_notice(message)
    else:
        await message.answer("❌ Admin only.")
    return False


async def report_error(bot: Bot, message: Message, error: Exception) -> None:
    """Send unexpected processing errors to the owner without exposing them in channels."""
    RUNTIME["failed"] += 1
    reason = str(error)[:3000]
    try:
        await bot.send_message(OWNER_ID, f"<b>🚨 Caption Bot Error</b>\n\n<b>Channel:</b> {message.chat.title or message.chat.id}\n<b>Message:</b> {message.message_id}\n<blockquote expandable><b>Reason:</b> {reason}</blockquote>", parse_mode="HTML")
    except Exception:
        LOGGER.exception("Could not deliver owner error report")


def main_menu() -> InlineKeyboardMarkup:
    """Build the primary bot menu."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📺 Channels", callback_data="channels", style=ButtonStyle.PRIMARY), InlineKeyboardButton(text="📊 Stats", callback_data="stats", style=ButtonStyle.SUCCESS)],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="settings", style=ButtonStyle.PRIMARY), InlineKeyboardButton(text="ℹ️ Help", callback_data="help", style=ButtonStyle.PRIMARY)],
    ])


def channel_menu(rows: list[dict]) -> InlineKeyboardMarkup:
    """Build the connected-channel selector."""
    keyboard = [[InlineKeyboardButton(text=f"📢 {row.get('title', 'Channel')}", callback_data=f"ch:{row['channel_id']}", style=ButtonStyle.PRIMARY)] for row in rows[:40]]
    keyboard += [[InlineKeyboardButton(text="➕ Add New Channel", callback_data="add_channel", style=ButtonStyle.SUCCESS)], [InlineKeyboardButton(text="↩️ Back", callback_data="home", style=ButtonStyle.PRIMARY)]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def settings_menu(channel_id: int, settings: dict) -> InlineKeyboardMarkup:
    """Build the per-channel settings panel."""
    def state(value: bool) -> str:
        return "ON ✅" if value else "OFF ❌"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Caption", callback_data=f"set:caption:{channel_id}", style=ButtonStyle.PRIMARY), InlineKeyboardButton(text=f"🔘 Buttons ({len(settings['buttons'])})", callback_data=f"set:buttons:{channel_id}", style=ButtonStyle.SUCCESS)],
        [InlineKeyboardButton(text=f"🔄 Replace ({len(settings['replacements'])})", callback_data=f"set:replace:{channel_id}", style=ButtonStyle.PRIMARY), InlineKeyboardButton(text=f"🎯 Filters {state(bool(settings['filters']))}", callback_data=f"set:filters:{channel_id}", style=ButtonStyle.SUCCESS)],
        [InlineKeyboardButton(text=f"📤 Forward {state(settings['forward']['enabled'])}", callback_data=f"set:forward:{channel_id}", style=ButtonStyle.PRIMARY), InlineKeyboardButton(text=f"✨ Prefix {state(bool(settings['prefix']))}", callback_data=f"set:prefix:{channel_id}", style=ButtonStyle.SUCCESS)],
        [InlineKeyboardButton(text=f"✨ Suffix {state(bool(settings['suffix']))}", callback_data=f"set:suffix:{channel_id}", style=ButtonStyle.PRIMARY), InlineKeyboardButton(text=f"🎉 Stickers {state(settings['stickers']['enabled'])}", callback_data=f"set:stickers:{channel_id}", style=ButtonStyle.SUCCESS)],
        [InlineKeyboardButton(text=f"📊 Media Details {state(settings['media_details'])}", callback_data=f"set:media:{channel_id}", style=ButtonStyle.PRIMARY)],
        [InlineKeyboardButton(text="🗑 Remove", callback_data=f"remove:{channel_id}", style=ButtonStyle.DANGER), InlineKeyboardButton(text="↩️ Back", callback_data="channels", style=ButtonStyle.PRIMARY)],
    ])


@ROUTER.message(CommandStart())
async def start_command(message: Message) -> None:
    """Handle /start."""
    if not await public_access(message):
        return
    text = "👋 <b>Welcome to Auto Caption Bot</b>\n\n⚡ Multi-channel • Smart Caption • Colored Buttons"
    if START_PIC and os.path.exists(START_PIC):
        with open(START_PIC, "rb") as photo:
            await message.answer_photo(photo, caption=text, reply_markup=main_menu(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=main_menu(), parse_mode="HTML")


@ROUTER.message(Command("help"))
async def help_command(message: Message) -> None:
    """Show the basic help entry point."""
    if await public_access(message):
        await message.answer("<b>Help</b>\n\nUse /channels to add and configure channels.", parse_mode="HTML")


@ROUTER.message(Command("settings"))
async def settings_command(message: Message) -> None:
    """Open the settings entry point."""
    if await public_access(message):
        await message.answer("⚙️ Select a channel from /channels.", reply_markup=main_menu())


@ROUTER.message(Command("channels"))
async def channels_command(message: Message) -> None:
    """List channels from a private chat only."""
    if message.chat.type != "private" or not await public_access(message):
        return
    rows = await DB.list_channels(message.from_user.id)
    await message.answer(f"📺 <b>Channels</b>\n\nConnected: <b>{len(rows)}</b>", parse_mode="HTML", reply_markup=channel_menu(rows))


@ROUTER.message(Command("stats"))
async def stats_command(message: Message) -> None:
    """Show bot usage statistics."""
    if not await public_access(message):
        return
    counts = await DB.counts()
    await message.answer(f"📊 <b>Statistics</b>\n\n👥 Users: {counts['users']}\n📺 Channels: {counts['channels']}\n📥 Processed: {RUNTIME['processed']}\n✅ Edited: {RUNTIME['edited']}\n❌ Errors: {RUNTIME['failed']}\n⏱ Uptime: {uptime_text()}", parse_mode="HTML")


@ROUTER.message(Command("addadmin"))
async def add_admin_command(message: Message) -> None:
    """Add a stored administrator."""
    if not await require_admin(message):
        return
    try:
        user_id = int((message.text or "").split(maxsplit=1)[1])
    except (IndexError, ValueError):
        await message.answer("Usage: /addadmin USER_ID")
        return
    await DB.add_admin(user_id)
    await message.answer("✅ Admin added.")


@ROUTER.message(Command("deladmin"))
async def delete_admin_command(message: Message) -> None:
    """Remove a stored administrator."""
    if not await require_admin(message):
        return
    try:
        user_id = int((message.text or "").split(maxsplit=1)[1])
    except (IndexError, ValueError):
        await message.answer("Usage: /deladmin USER_ID")
        return
    await DB.del_admin(user_id)
    await message.answer("✅ Admin removed.")


@ROUTER.message(Command("broadcast"))
async def broadcast_command(message: Message) -> None:
    """Send an announcement to every tracked user. Admin only."""
    if not await require_admin(message):
        return
    reply = message.reply_to_message
    body = (message.text or "").split(maxsplit=1)
    text = body[1].strip() if len(body) > 1 else ""
    if not reply and not text:
        await message.answer("Usage: reply to a message with /broadcast, or send /broadcast <text>.")
        return
    user_ids = await DB.user_ids()
    if not user_ids:
        await message.answer("No users to broadcast to yet.")
        return
    status = await message.answer(f"📤 Broadcasting to {len(user_ids)} users…")
    sent = blocked = failed = 0
    for user_id in user_ids:
        retries_left = 1
        while True:
            try:
                if reply:
                    await message.bot.copy_message(user_id, message.chat.id, reply.message_id)
                else:
                    await message.bot.send_message(user_id, text, parse_mode="HTML")
                sent += 1
                break
            except TelegramRetryAfter as exc:
                if retries_left <= 0:
                    failed += 1
                    break
                retries_left -= 1
                await asyncio.sleep(exc.retry_after)
            except TelegramForbiddenError:
                await DB.mark_blocked(user_id)
                blocked += 1
                break
            except Exception:
                LOGGER.exception("Broadcast delivery failed for user %s", user_id)
                failed += 1
                break
        await asyncio.sleep(0.05)
    await status.edit_text("✅ <b>Broadcast complete</b>\n\n" f"👥 Total: {len(user_ids)}\n" f"✅ Sent: {sent}\n" f"🚫 Blocked: {blocked}\n" f"❌ Failed: {failed}", parse_mode="HTML")


@ROUTER.message(Command("set_public"))
async def set_public_command(message: Message) -> None:
    """Explain how the deployment-level public mode is changed."""
    if await require_admin(message):
        await message.answer("Change PUBLIC_MODE in config.py and restart the bot.")


@ROUTER.message(Command("cancel"))
async def cancel_command(message: Message) -> None:
    """Cancel the current private-chat configuration prompt."""
    STATES.pop(message.from_user.id, None)
    await message.answer("❌ Cancelled.")


@ROUTER.callback_query(F.data == "home")
async def home_callback(query):
    """Return to the main menu."""
    if not await public_access_cb(query):
        return
    await query.message.edit_text("🤖 <b>Auto Caption Bot</b>", parse_mode="HTML", reply_markup=main_menu())
    await query.answer()


@ROUTER.callback_query(F.data == "help")
async def help_callback(query):
    """Show help from the inline menu."""
    if not await public_access_cb(query):
        return
    await query.message.edit_text("Use /channels to manage channels.", reply_markup=main_menu())
    await query.answer()


@ROUTER.callback_query(F.data == "settings")
async def settings_callback(query):
    """Open the settings entry point from the inline menu."""
    if not await public_access_cb(query):
        return
    await query.message.edit_text("⚙️ Select a channel from /channels.", reply_markup=main_menu())
    await query.answer()


@ROUTER.callback_query(F.data == "stats")
async def stats_callback(query):
    """Show statistics from the inline menu."""
    if not await public_access_cb(query):
        return
    counts = await DB.counts()
    await query.message.edit_text(f"📊 Users: {counts['users']}\n📺 Channels: {counts['channels']}\n📥 Processed: {RUNTIME['processed']}\n✅ Edited: {RUNTIME['edited']}\n❌ Errors: {RUNTIME['failed']}", reply_markup=main_menu())
    await query.answer()


@ROUTER.callback_query(F.data == "channels")
async def channels_callback(query):
    """Show channels from the inline menu."""
    if not await public_access_cb(query):
        return
    rows = await DB.list_channels(query.from_user.id)
    await query.message.edit_text(f"📺 <b>Channels</b>\n\nConnected: <b>{len(rows)}</b>", parse_mode="HTML", reply_markup=channel_menu(rows))
    await query.answer()


@ROUTER.callback_query(F.data == "add_channel")
async def add_channel_callback(query):
    """Start the add-channel input flow."""
    if not await public_access_cb(query):
        return
    STATES[query.from_user.id] = {"type": "channel"}
    await query.message.edit_text("➕ <b>Add Channel</b>\n\nSend the Channel ID or forward a message directly from that channel.\nThe bot must already be an administrator there.\n\n/cancel", parse_mode="HTML")
    await query.answer()


@ROUTER.callback_query(F.data.startswith("ch:"))
async def channel_callback(query):
    """Open one channel's settings panel."""
    if not await public_access_cb(query):
        return
    channel_id = int(query.data.split(":", 1)[1])
    row = await DB.get_channel(channel_id)
    if not row or row["owner_id"] != query.from_user.id:
        await query.answer("Not your channel.", show_alert=True)
        return
    await query.message.edit_text(f"📄 <b>{row['title']}</b>\n🆔 <code>{channel_id}</code>\n🔗 @{row.get('username') or 'private'}", parse_mode="HTML", reply_markup=settings_menu(channel_id, merged_config(row)))
    await query.answer()


@ROUTER.message(F.chat.type == "private")
async def private_input(message: Message) -> None:
    """Handle all active private-chat configuration prompts."""
    state = STATES.get(message.from_user.id)
    if not state:
        return
    try:
        if state["type"] == "channel":
            origin_chat = getattr(getattr(message, "forward_origin", None), "chat", None)
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
            await message.answer(f"✅ <b>{chat.title}</b> added.", parse_mode="HTML", reply_markup=settings_menu(channel_id, settings))
            return
        channel_id = state["channel_id"]
        row = await DB.get_channel(channel_id)
        if not row or row["owner_id"] != message.from_user.id:
            STATES.pop(message.from_user.id, None)
            await message.answer("❌ Channel configuration was not found.")
            return
        settings = merged_config(row)
        text = (message.text or message.caption or "").strip()
        kind = state["type"]
        if kind == "caption":
            settings["caption"] = text
        elif kind in {"prefix", "suffix"}:
            settings[kind] = text
        elif kind == "replace":
            parts = text.split("|", 1)
            if len(parts) != 2 or not parts[0].strip():
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
            if not text.lstrip("-").isdigit():
                await message.answer("❌ Channel ID numeric hona chahiye.")
                return
            settings["forward"] = {"enabled": True, "destination": int(text)}
        elif kind == "filters":
            filter_type = text.lower()
            if filter_type not in VALID_FILTERS:
                await message.answer("❌ Valid: video/audio/document/photo/animation/voice/sticker")
                return
            settings["filters"] = {"type": filter_type}
        await DB.save_channel(row["owner_id"], channel_id, row["title"], row.get("username", ""), json.dumps(settings))
        STATES.pop(message.from_user.id, None)
        await message.answer("✅ Saved.", reply_markup=settings_menu(channel_id, settings))
    except (ValueError, TypeError):
        await message.answer("❌ Invalid value. Please check the format and try again.")
    except Exception as exc:
        await report_error(message.bot, message, exc)


@ROUTER.callback_query(F.data.startswith("set:"))
async def setting_callback(query):
    """Handle per-channel setting actions."""
    if not await public_access_cb(query):
        return
    _, kind, channel_id = query.data.split(":")
    channel_id = int(channel_id)
    row = await DB.get_channel(channel_id)
    if not row or row["owner_id"] != query.from_user.id:
        await query.answer("Not your channel.", show_alert=True)
        return
    settings = merged_config(row)
    if kind == "media":
        settings["media_details"] = not settings["media_details"]
    elif kind == "stickers":
        settings["stickers"]["enabled"] = not settings["stickers"]["enabled"]
    else:
        STATES[query.from_user.id] = {"type": kind, "channel_id": channel_id}
        prompts = {
            "caption": "📝 Send caption template.",
            "buttons": "🔘 Button Text | URL | blue/green/red",
            "replace": "🔄 old text | new text",
            "filters": "🎯 video/audio/document/photo/animation/voice/sticker",
            "forward": "📤 Destination channel ID.",
            "prefix": "✨ Send prefix.",
            "suffix": "✨ Send suffix.",
        }
        prompt = prompts.get(kind, "⚠️ Unknown option.")
        await query.message.edit_text(prompt + "\n\n/cancel")
        await query.answer()
        return
    await DB.save_channel(row["owner_id"], channel_id, row["title"], row.get("username", ""), json.dumps(settings))
    await query.message.edit_reply_markup(reply_markup=settings_menu(channel_id, settings))
    await query.answer()


@ROUTER.callback_query(F.data.startswith("remove:"))
async def remove_callback(query):
    """Remove a channel owned by the current user."""
    if not await public_access_cb(query):
        return
    channel_id = int(query.data.split(":", 1)[1])
    row = await DB.get_channel(channel_id)
    if not row or row["owner_id"] != query.from_user.id:
        await query.answer("Not your channel.", show_alert=True)
        return
    await DB.delete_channel(channel_id, query.from_user.id)
    await query.message.edit_text("🗑 Channel removed.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Channels", callback_data="channels", style=ButtonStyle.PRIMARY)]]))
    await query.answer()


async def retry_after_floodwait(func, *args, **kwargs):
    """Call a Telegram API method, retrying once with the server-requested delay."""
    try:
        return await func(*args, **kwargs)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(exc.retry_after)
        return await func(*args, **kwargs)


@ROUTER.channel_post()
async def channel_post(message: Message) -> None:
    """Process a connected channel post and apply its saved configuration."""
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
        buttons = [InlineKeyboardButton(text=item["text"], url=item["url"], style=button_style(item.get("color"))) for item in settings["buttons"] if item.get("text") and valid_http_url(item.get("url", ""))]
        markup = InlineKeyboardMarkup(inline_keyboard=[buttons[index:index + 2] for index in range(0, len(buttons), 2)]) if buttons else None
        if caption != (message.caption or "") or markup:
            await retry_after_floodwait(message.bot.edit_message_caption, chat_id=message.chat.id, message_id=message.message_id, caption=caption or None, parse_mode="HTML", reply_markup=markup)
            RUNTIME["edited"] += 1
        if settings["forward"]["enabled"] and settings["forward"]["destination"]:
            await retry_after_floodwait(message.bot.copy_message, settings["forward"]["destination"], message.chat.id, message.message_id)
    except Exception as exc:
        await report_error(message.bot, message, exc)


async def main() -> None:
    """Connect storage and start long polling."""
    setup_logging()
    await DB.connect()
    bot = Bot(BOT_TOKEN)
    dispatcher = Dispatcher()
    dispatcher.include_router(ROUTER)
    LOGGER.info("Caption Bot starting")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
