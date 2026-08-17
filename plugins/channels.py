"""Multi-channel management and per-channel settings input."""

from __future__ import annotations

import json

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from database.settings import default_settings
from .context import (
    DB,
    STATES,
    VALID_FILTERS,
    channel_menu,
    merged_config,
    public_access,
    public_access_cb,
    settings_menu,
    valid_http_url,
)

router = Router()


@router.message(Command("channels"))
async def channels_command(message: Message) -> None:
    """List connected channels in private chat."""
    if message.chat.type != "private" or not await public_access(message):
        return
    rows = await DB.list_channels(message.from_user.id)
    await message.answer(
        f"📺 <b>Channels</b>\n\nConnected: <b>{len(rows)}</b>",
        parse_mode="HTML",
        reply_markup=channel_menu(rows),
    )


@router.callback_query(F.data == "channels")
async def channels_callback(query) -> None:
    """Open the connected-channel selector."""
    if not await public_access_cb(query):
        return
    rows = await DB.list_channels(query.from_user.id)
    await query.message.edit_text(
        f"📺 <b>Channels</b>\n\nConnected: <b>{len(rows)}</b>",
        parse_mode="HTML",
        reply_markup=channel_menu(rows),
    )
    await query.answer()


@router.callback_query(F.data == "add_channel")
async def add_channel_callback(query) -> None:
    """Start the add-channel flow."""
    if not await public_access_cb(query):
        return
    STATES[query.from_user.id] = {"type": "channel"}
    await query.message.edit_text(
        "➕ <b>Add Channel</b>\n\n"
        "Send the Channel ID or forward a message directly from that channel.\n"
        "The bot must already be an administrator there.\n\n/cancel",
        parse_mode="HTML",
    )
    await query.answer()


@router.callback_query(F.data.startswith("ch:"))
async def channel_callback(query) -> None:
    """Open one channel's settings panel."""
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
    await query.message.edit_text(
        f"📄 <b>{row['title']}</b>\n"
        f"🆔 <code>{channel_id}</code>\n"
        f"🔗 @{row.get('username') or 'private'}",
        parse_mode="HTML",
        reply_markup=settings_menu(channel_id, merged_config(row)),
    )
    await query.answer()


@router.message(Command("cancel"))
async def cancel(message: Message) -> None:
    """Cancel a pending channel/settings input."""
    STATES.pop(message.from_user.id, None)
    await message.answer("❌ Cancelled.")


@router.message(F.chat.type == "private")
async def private_input(message: Message) -> None:
    """Consume validated values for channel and setting prompts."""
    state = STATES.get(message.from_user.id)
    if not state:
        return
    try:
        if state["type"] == "channel":
            origin = getattr(getattr(message, "forward_origin", None), "chat", None)
            if origin is None:
                raw_id = (message.text or "").strip()
                if not raw_id or not raw_id.lstrip("-").isdigit():
                    await message.answer(
                        "❌ Send a numeric Channel ID or forward a message "
                        "directly from a channel."
                    )
                    return
                channel_id = int(raw_id)
            else:
                if origin.type != "channel":
                    await message.answer(
                        "❌ Please forward a message directly from a channel."
                    )
                    return
                channel_id = origin.id

            me = await message.bot.get_me()
            member = await message.bot.get_chat_member(channel_id, me.id)
            if member.status not in {"administrator", "creator"}:
                await message.answer("❌ Bot must be an administrator in this channel.")
                return
            chat = await message.bot.get_chat(channel_id)
            settings = default_settings()
            await DB.save_channel(
                message.from_user.id,
                channel_id,
                chat.title or "Channel",
                chat.username or "",
                json.dumps(settings),
            )
            STATES.pop(message.from_user.id, None)
            await message.answer(
                f"✅ <b>{chat.title}</b> added.",
                parse_mode="HTML",
                reply_markup=settings_menu(channel_id, settings),
            )
            return

        channel_id = int(state["channel_id"])
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
            settings["buttons"].append(
                {"text": parts[0], "url": parts[1], "color": parts[2].lower()}
            )
        elif kind == "forward":
            if not text.lstrip("-").isdigit():
                await message.answer("❌ Channel ID numeric hona chahiye.")
                return
            settings["forward"] = {"enabled": True, "destination": int(text)}
        elif kind == "filters":
            filter_type = text.lower()
            if filter_type not in VALID_FILTERS:
                await message.answer(
                    "❌ Valid: video/audio/document/photo/animation/voice/sticker"
                )
                return
            settings["filters"] = {"type": filter_type}
        else:
            STATES.pop(message.from_user.id, None)
            await message.answer("❌ Unknown configuration request. Try again.")
            return

        await DB.save_channel(
            row["owner_id"], channel_id, row["title"], row.get("username", ""),
            json.dumps(settings),
        )
        STATES.pop(message.from_user.id, None)
        await message.answer("✅ Saved.", reply_markup=settings_menu(channel_id, settings))
    except (ValueError, TypeError):
        await message.answer("❌ Invalid value. Please check the format and try again.")
    except Exception as exc:
        from .context import report_error
        await report_error(message.bot, message, exc)
