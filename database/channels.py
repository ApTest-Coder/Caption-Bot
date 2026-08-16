"""Channel persistence helpers."""
from .db import Database

async def get(db: Database, channel_id: int):
    return await db.get_channel(channel_id)

async def list_for_owner(db: Database, owner_id: int):
    return await db.list_channels(owner_id)
