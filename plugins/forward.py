"""Per-channel forward/copy helpers."""

import asyncio

from aiogram.exceptions import TelegramRetryAfter


async def copy_message(bot, destination: int, message) -> None:
    """Copy a channel post to its configured destination with FloodWait retry."""
    for attempt in range(2):
        try:
            await bot.copy_message(destination, message.chat.id, message.message_id)
            return
        except TelegramRetryAfter:
            if attempt:
                raise
            raise


async def copy_with_retry(bot, destination: int, message, attempts: int = 2) -> None:
    """Retry a copy operation after Telegram asks us to wait."""
    for attempt in range(attempts):
        try:
            await bot.copy_message(destination, message.chat.id, message.message_id)
            return
        except TelegramRetryAfter as exc:
            if attempt + 1 >= attempts:
                raise
            await asyncio.sleep(exc.retry_after)
