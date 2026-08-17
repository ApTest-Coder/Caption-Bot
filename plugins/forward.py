"""Per-channel forward/copy helpers."""

from __future__ import annotations

import asyncio

from aiogram.exceptions import TelegramRetryAfter


def parse_destination(value: str) -> int | None:
    """Parse a Telegram channel/chat ID, including negative -100... IDs."""
    value = (value or "").strip()
    if not value or not value.lstrip("-").isdigit():
        return None
    destination = int(value)
    return destination if destination != 0 else None


async def copy_with_retry(
    bot,
    destination: int,
    message,
    attempts: int = 2,
) -> None:
    """Copy a channel post with bounded FloodWait retry."""
    if destination == 0:
        raise ValueError("Forward destination cannot be zero")
    attempts = max(1, min(attempts, 3))
    for attempt in range(attempts):
        try:
            await bot.copy_message(
                destination,
                message.chat.id,
                message.message_id,
            )
            return
        except TelegramRetryAfter as exc:
            if attempt + 1 >= attempts:
                raise
            await asyncio.sleep(exc.retry_after)
