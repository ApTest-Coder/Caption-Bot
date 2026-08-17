"""Force-subscribe membership checks and public join UI."""

from aiogram import Router
from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import FSUB_CHANNEL, FSUB_LINK
from .context import LOGGER, valid_http_url

router = Router()


async def is_member(bot, user_id: int) -> bool:
    """Check membership without generating or exposing private invite links."""
    if not FSUB_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(FSUB_CHANNEL, user_id)
        return member.status in {"creator", "administrator", "member"}
    except Exception:
        LOGGER.exception("FSUB membership check failed")
        return False


def join_keyboard() -> InlineKeyboardMarkup | None:
    """Return the public Join button only when its URL is valid."""
    if not valid_http_url(FSUB_LINK):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Join Channel",
                    url=FSUB_LINK,
                    style=ButtonStyle.SUCCESS,
                )
            ]
        ]
    )


async def require_membership(bot, user_id: int) -> tuple[bool, InlineKeyboardMarkup | None]:
    """Return membership state and the public join keyboard."""
    if await is_member(bot, user_id):
        return True, None
    return False, join_keyboard()
