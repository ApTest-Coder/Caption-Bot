"""User database helpers."""

from .settings import Database


async def is_admin(db: Database, user_id: int) -> bool:
    """Return whether the user is an administrator."""
    return await db.is_admin(user_id)
