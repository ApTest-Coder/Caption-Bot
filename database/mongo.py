from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, DATABASE_NAME

async def connect():
    client=AsyncIOMotorClient(MONGO_URI,serverSelectionTimeoutMS=5000)
    await client.admin.command('ping')
    return client, client[DATABASE_NAME]
