"""Owner and administrator commands."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from .context import DB, require_admin

router = Router()
ADMIN_COMMANDS = ("/addadmin", "/deladmin", "/broadcast", "/set_public")


@router.message(Command("addadmin"))
async def add_admin(message: Message) -> None:
    """Add a stored administrator by numeric Telegram ID."""
    if not await require_admin(message):
        return
    try:
        user_id = int((message.text or "").split(maxsplit=1)[1])
    except (IndexError, ValueError):
        await message.answer("Usage: /addadmin USER_ID")
        return
    await DB.add_admin(user_id)
    await message.answer("✅ Admin added.")


@router.message(Command("deladmin"))
async def delete_admin(message: Message) -> None:
    """Remove a stored administrator; the owner is protected."""
    if not await require_admin(message):
        return
    try:
        user_id = int((message.text or "").split(maxsplit=1)[1])
    except (IndexError, ValueError):
        await message.answer("Usage: /deladmin USER_ID")
        return
    await DB.del_admin(user_id)
    await message.answer("✅ Admin removed.")


@router.message(Command("set_public"))
async def set_public(message: Message) -> None:
    """Explain the deployment-level public mode setting."""
    if await require_admin(message):
        await message.answer("Change PUBLIC_MODE in config.py and restart the bot.")
