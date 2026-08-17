"""Per-channel forward/copy helpers."""

import asyncio

from aiogram.exceptions import TelegramRetryAfter


async def copy_with_retry(bot, destination: int, message, attempts: int = 2) -> None:
    """Copy a channel post to its destination with bounded FloodWait retry."""
    for attempt in range(attempts):
        try:
            await bot.copy_message(destination, message.chat.id, message.message_id)
            return
        except TelegramRetryAfter as exc:
            if attempt + 1 >= attempts:
                raise
            await asyncio.sleep(exc.retry_after)
