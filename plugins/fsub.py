"""Force-subscribe membership checks and public join UI."""

from aiogram.enums import ButtonStyle
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import FSUB_CHANNEL, FSUB_LINK, FSUB_PIC
from .context import LOGGER, valid_http_url


def join_keyboard() -> InlineKeyboardMarkup | None:
    """Return a public Join button only when its URL is valid."""
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


async def is_member(bot, user_id: int) -> bool:
    """Check membership using only the configured public channel target."""
    if not FSUB_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(FSUB_CHANNEL, user_id)
        return member.status in {"creator", "administrator", "member"}
    except Exception:
        LOGGER.exception("FSUB membership check failed")
        return False


async def require_membership(bot, user_id: int) -> tuple[bool, InlineKeyboardMarkup | None]:
    """Return membership state and a public join keyboard when required."""
    if await is_member(bot, user_id):
        return True, None
    return False, join_keyboard()


async def send_gate(message) -> None:
    """Send the FSUB gate with the configured photo when available."""
    keyboard = join_keyboard()
    text = "🔒 <b>Join Required</b>\n\nPlease join our channel to use this bot."
    if FSUB_PIC:
        try:
            with open(FSUB_PIC, "rb") as photo:
                await message.answer_photo(
                    photo,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            return
        except OSError:
            pass
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
