"""Channel-post caption editing pipeline."""

from __future__ import annotations

import asyncio

from aiogram import Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from utils.formatter import format_caption
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


async def edit_caption(bot, message, caption: str, markup) -> None:
    """Edit a post caption with bounded FloodWait retry."""
    for attempt in range(2):
        try:
            await bot.edit_message_caption(
                chat_id=message.chat.id,
                message_id=message.message_id,
                caption=caption or None,
                parse_mode="HTML",
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
            caption = f"{settings['prefix']}\n{caption}" if caption else settings["prefix"]
        if settings["suffix"]:
            caption = f"{caption}\n{settings['suffix']}" if caption else settings["suffix"]

        markup = build_markup(settings["buttons"])
        if caption != (message.caption or "") or markup:
            await edit_caption(message.bot, message, caption, markup)
            RUNTIME["edited"] += 1

        forward = settings["forward"]
        if forward["enabled"] and forward["destination"]:
            await copy_with_retry(message.bot, forward["destination"], message)
    except Exception as exc:
        await report_error(message.bot, message, exc)
