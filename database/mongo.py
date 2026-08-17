"""MongoDB backend connection utilities.

The high-level :class:`database.settings.Database` facade owns application
operations. This module keeps connection creation reusable for tests and
future backend-specific tooling without duplicating application logic.
"""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from config import DATABASE_NAME, MONGO_URI


async def connect() -> tuple[AsyncIOMotorClient, AsyncIOMotorDatabase]:
    """Connect to MongoDB, verify the server, and return client/database."""
    if not MONGO_URI:
        raise RuntimeError("MONGO_URI is required for MongoDB mode")

    client = AsyncIOMotorClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=10000,
    )
    await client.admin.command("ping")
    return client, client[DATABASE_NAME]


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create the indexes required by the bot's MongoDB collections."""
    await db.users.create_index("user_id", unique=True)
    await db.channels.create_index("channel_id", unique=True)
    await db.admins.create_index("user_id", unique=True)
