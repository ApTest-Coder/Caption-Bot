"""Channel persistence helpers."""

from .settings import Database


async def get(db: Database, channel_id: int):
    """Return a channel by ID."""
    return await db.get_channel(channel_id)


async def list_for_owner(db: Database, owner_id: int):
    """Return channels owned by a user."""
    return await db.list_channels(owner_id)
