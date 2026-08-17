"""Owner-only broadcast delivery with FloodWait and blocked-user handling."""

import asyncio
import logging

from aiogram import Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.types import Message

from .context import DB, require_admin

LOGGER = logging.getLogger("caption_bot.broadcast")
router = Router()


async def deliver(bot, user_id: int, source: Message, text: str) -> str:
    """Deliver one broadcast item and return its result category."""
    for attempt in range(2):
        try:
            if source.reply_to_message:
                await bot.copy_message(
                    user_id,
                    source.chat.id,
                    source.reply_to_message.message_id,
                )
            else:
                await bot.send_message(user_id, text, parse_mode="HTML")
            return "sent"
        except TelegramRetryAfter as exc:
            if attempt:
                return "failed"
            await asyncio.sleep(exc.retry_after)
        except TelegramForbiddenError:
            await DB.mark_blocked(user_id)
            return "blocked"
        except Exception:
            LOGGER.exception("Broadcast delivery failed for %s", user_id)
            return "failed"
    return "failed"


@router.message(Command("broadcast"))
async def broadcast(message: Message) -> None:
    """Broadcast text or a replied-to Telegram message to tracked users."""
    if not await require_admin(message):
        return
    body = (message.text or "").split(maxsplit=1)
    text = body[1].strip() if len(body) > 1 else ""
    if not message.reply_to_message and not text:
        await message.answer(
            "Usage: reply to a message with /broadcast, or /broadcast <text>."
        )
        return

    user_ids = await DB.user_ids()
    if not user_ids:
        await message.answer("No users to broadcast to yet.")
        return

    status = await message.answer(f"📤 Broadcasting to {len(user_ids)} users…")
    sent = blocked = failed = 0
    for user_id in user_ids:
        result = await deliver(message.bot, user_id, message, text)
        if result == "sent":
            sent += 1
        elif result == "blocked":
            blocked += 1
        else:
            failed += 1
        await asyncio.sleep(0.05)

    await status.edit_text(
        "✅ <b>Broadcast complete</b>\n\n"
        f"👥 Total: {len(user_ids)}\n"
        f"✅ Sent: {sent}\n"
        f"🚫 Blocked: {blocked}\n"
        f"❌ Failed: {failed}",
        parse_mode="HTML",
    )
