"""Database helpers for channel ownership and configuration."""

from __future__ import annotations

from .settings import Database


async def get(db: Database, channel_id: int):
    """Return a channel by Telegram channel ID."""
    return await db.get_channel(channel_id)


async def list_for_owner(db: Database, owner_id: int) -> list[dict]:
    """Return every channel owned by a user."""
    return await db.list_channels(owner_id)


async def save(
    db: Database,
    owner_id: int,
    channel_id: int,
    title: str,
    username: str,
    config: str,
) -> None:
    """Create or update a channel configuration."""
    await db.save_channel(owner_id, channel_id, title, username, config)


async def remove(db: Database, owner_id: int, channel_id: int) -> None:
    """Delete a channel only when it belongs to the requesting owner."""
    await db.delete_channel(channel_id, owner_id)


async def owned_by(db: Database, owner_id: int, channel_id: int) -> bool:
    """Return whether the user owns the requested channel."""
    row = await db.get_channel(channel_id)
    return bool(row and row.get("owner_id") == owner_id)
