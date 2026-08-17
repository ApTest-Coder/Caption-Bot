"""Channel-post caption editing pipeline."""

from __future__ import annotations

import asyncio
from html import escape

from aiogram import Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyParameters

from utils.formatter import format_caption, human_duration, human_size
from utils.parser import media_values
from .context import (
    DB,
    RUNTIME,
    button_style,
    has_media,
    media_matches_filter,
    merged_config,
    report_error,
    valid_http_url,
)
from .forward import copy_with_retry

router = Router()


async def edit_caption(bot, message, caption: str) -> None:
    """Edit a caption with bounded FloodWait retry."""
    for attempt in range(2):
        try:
            await bot.edit_message_caption(
                chat_id=message.chat.id,
                message_id=message.message_id,
                caption=caption or None,
                parse_mode="HTML",
            )
            return
        except TelegramRetryAfter as exc:
            if attempt:
                raise
            await asyncio.sleep(exc.retry_after)


async def edit_markup(bot, message, markup: InlineKeyboardMarkup) -> None:
    """Edit only reply markup, including on sticker messages."""
    for attempt in range(2):
        try:
            await bot.edit_message_reply_markup(
                chat_id=message.chat.id,
                message_id=message.message_id,
                reply_markup=markup,
            )
            return
        except TelegramRetryAfter as exc:
            if attempt:
                raise
            await asyncio.sleep(exc.retry_after)


def build_markup(buttons: list[dict]) -> InlineKeyboardMarkup | None:
    """Build two-column colored URL buttons from stored settings."""
    valid = [
        InlineKeyboardButton(
            text=item["text"],
            url=item["url"],
            style=button_style(item.get("color")),
        )
        for item in buttons
        if item.get("text") and valid_http_url(item.get("url", ""))
    ]
    if not valid:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[valid[index : index + 2] for index in range(0, len(valid), 2)]
    )


def supports_caption_edit(message) -> bool:
    """Return whether the Telegram media type supports caption editing."""
    return any(
        (
            message.video,
            message.audio,
            message.document,
            message.photo,
            message.animation,
        )
    )


def media_details_caption(message) -> str:
    """Build a compact metadata block for the optional Media Details setting."""
    values = media_values(message)
    parts: list[str] = []
    size = human_size(values.get("filesize"))
    duration = human_duration(values.get("duration"))
    width = values.get("width")
    height = values.get("height")
    mime_type = values.get("mime_type")

    if size:
        parts.append(f"• Size: {escape(size)}")
    if duration:
        parts.append(f"• Duration: {escape(duration)}")
    if width and height:
        parts.append(
            f"• Resolution: {escape(str(width))}x{escape(str(height))}"
        )
    if mime_type:
        parts.append(f"• MIME: {escape(str(mime_type))}")
    if not parts:
        return ""
    return (
        "<blockquote expandable>📊 <b>Media Details</b>\n"
        + "\n".join(parts)
        + "</blockquote>"
    )


@router.channel_post()
async def process_channel_post(message) -> None:
    """Apply the selected channel's caption and button configuration."""
    row = await DB.get_channel(message.chat.id)
    if not row or not has_media(message):
        return
    settings = merged_config(row)
    if not media_matches_filter(message, settings["filters"]):
        return

    RUNTIME["processed"] += 1
    try:
        caption = (
            format_caption(settings["caption"], message)
            if settings["caption"]
            else (message.caption or "")
        )
        for old, new in settings["replacements"].items():
            caption = caption.replace(old, new)
        if settings["prefix"]:
            caption = (
                f"{settings['prefix']}\n{caption}"
                if caption
                else settings["prefix"]
            )
        if settings["suffix"]:
            caption = (
                f"{caption}\n{settings['suffix']}"
                if caption
                else settings["suffix"]
            )
        if settings["media_details"]:
            details = media_details_caption(message)
            if details:
                caption = f"{caption}\n{details}" if caption else details

        markup = build_markup(settings["buttons"])
        original_caption = message.caption or ""
        if supports_caption_edit(message):
            if caption != original_caption:
                await edit_caption(message.bot, message, caption)
                RUNTIME["edited"] += 1
            if markup:
                await edit_markup(message.bot, message, markup)
                RUNTIME["edited"] += 1
        elif markup:
            await edit_markup(message.bot, message, markup)
            RUNTIME["edited"] += 1

        sticker = settings["stickers"]
        if sticker.get("enabled") and sticker.get("file_id"):
            await message.bot.send_sticker(
                chat_id=message.chat.id,
                sticker=sticker["file_id"],
                reply_parameters=ReplyParameters(message_id=message.message_id),
            )

        forward = settings["forward"]
        if forward["enabled"] and forward["destination"]:
            await copy_with_retry(message.bot, forward["destination"], message)
    except Exception as exc:
        await report_error(message.bot, message, exc)
