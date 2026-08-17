"""Database helpers for tracked users and administrators."""

from __future__ import annotations

from .settings import Database


async def upsert(db: Database, user_id: int, username: str = "") -> None:
    """Insert a user or refresh their last-seen information."""
    await db.user_upsert(user_id, username)


async def is_admin(db: Database, user_id: int) -> bool:
    """Return whether a user is the owner or a stored administrator."""
    return await db.is_admin(user_id)


async def add_admin(db: Database, user_id: int) -> None:
    """Add a user to the administrator list."""
    await db.add_admin(user_id)


async def remove_admin(db: Database, user_id: int) -> None:
    """Remove a user from the administrator list."""
    await db.del_admin(user_id)


async def mark_blocked(db: Database, user_id: int) -> None:
    """Mark a user as blocked so broadcasts can skip them."""
    await db.mark_blocked(user_id)


async def all_ids(db: Database) -> list[int]:
    """Return IDs of users who have not blocked the bot."""
    return await db.user_ids()
