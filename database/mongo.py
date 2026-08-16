"""MongoDB connection helper."""

from config import DATABASE_NAME, MONGO_URI
from motor.motor_asyncio import AsyncIOMotorClient


async def connect():
    """Connect to MongoDB and return the client and selected database."""
    client = AsyncIOMotorClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
    )
    await client.admin.command("ping")
    return client, client[DATABASE_NAME]
