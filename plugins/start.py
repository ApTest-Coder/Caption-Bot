"""Start and help entry points."""

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from config import START_PIC
from .context import main_menu, public_access

router = Router()


@router.message(CommandStart())
async def start(message: Message) -> None:
    """Show the welcome screen."""
    if not await public_access(message):
        return
    text = (
        "👋 <b>Welcome to Auto Caption Bot</b>\n\n"
        "⚡ Multi-channel • Smart Caption • Colored Buttons"
    )
    if START_PIC:
        try:
            with open(START_PIC, "rb") as photo:
                await message.answer_photo(
                    photo,
                    caption=text,
                    reply_markup=main_menu(),
                    parse_mode="HTML",
                )
            return
        except OSError:
            pass
    await message.answer(text, reply_markup=main_menu(), parse_mode="HTML")


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    """Show the public help entry point."""
    if await public_access(message):
        await message.answer(
            "<b>Help</b>\n\nUse /channels to add and configure channels.",
            parse_mode="HTML",
        )


@router.message(Command("settings"))
async def settings_command(message: Message) -> None:
    """Open the settings entry point."""
    if await public_access(message):
        await message.answer(
            "⚙️ Select a channel from /channels.",
            reply_markup=main_menu(),
        )
