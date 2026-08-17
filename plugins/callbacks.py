"""Shared callback actions for navigation and channel settings."""

import json

from aiogram import F, Router
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .context import DB, STATES, main_menu, merged_config, public_access_cb, settings_menu

router = Router()


@router.callback_query(F.data == "home")
async def home(query) -> None:
    """Return to the main menu."""
    if not await public_access_cb(query):
        return
    await query.message.edit_text(
        "🤖 <b>Auto Caption Bot</b>",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )
    await query.answer()


@router.callback_query(F.data == "help")
async def help_menu(query) -> None:
    """Show help from the inline menu."""
    if not await public_access_cb(query):
        return
    await query.message.edit_text(
        "Use /channels to manage channels.",
        reply_markup=main_menu(),
    )
    await query.answer()


@router.callback_query(F.data == "settings")
async def settings_menu_callback(query) -> None:
    """Open the settings entry point."""
    if not await public_access_cb(query):
        return
    await query.message.edit_text(
        "⚙️ Select a channel from /channels.",
        reply_markup=main_menu(),
    )
    await query.answer()


@router.callback_query(F.data.startswith("set:"))
async def setting_callback(query) -> None:
    """Toggle boolean settings or start a validated text-input flow."""
    if not await public_access_cb(query):
        return
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer("Invalid setting.", show_alert=True)
        return
    _, kind, raw_channel_id = parts
    try:
        channel_id = int(raw_channel_id)
    except ValueError:
        await query.answer("Invalid channel.", show_alert=True)
        return

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
        prompts = {
            "caption": "📝 Send caption template.",
            "buttons": "🔘 Button Text | URL | blue/green/red",
            "replace": "🔄 old text | new text",
            "filters": "🎯 video/audio/document/photo/animation/voice/sticker",
            "forward": "📤 Destination channel ID.",
            "prefix": "✨ Send prefix.",
            "suffix": "✨ Send suffix.",
        }
        prompt = prompts.get(kind)
        if prompt is None:
            await query.answer("Unknown setting.", show_alert=True)
            return
        STATES[query.from_user.id] = {"type": kind, "channel_id": channel_id}
        await query.message.edit_text(f"{prompt}\n\n/cancel")
        await query.answer()
        return

    await DB.save_channel(
        row["owner_id"], channel_id, row["title"], row.get("username", ""),
        json.dumps(settings),
    )
    await query.message.edit_reply_markup(reply_markup=settings_menu(channel_id, settings))
    await query.answer()


@router.callback_query(F.data.startswith("remove:"))
async def remove_channel(query) -> None:
    """Remove a channel owned by the current user."""
    if not await public_access_cb(query):
        return
    try:
        channel_id = int(query.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await query.answer("Invalid channel.", show_alert=True)
        return
    row = await DB.get_channel(channel_id)
    if not row or row["owner_id"] != query.from_user.id:
        await query.answer("Not your channel.", show_alert=True)
        return
    await DB.delete_channel(channel_id, query.from_user.id)
    await query.message.edit_text(
        "🗑 Channel removed.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="↩️ Channels",
                        callback_data="channels",
                    )
                ]
            ]
        ),
    )
    await query.answer()
