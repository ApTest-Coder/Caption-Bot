import aiosqlite
from config import SQLITE_DATABASE

async def connect():
    db=await aiosqlite.connect(SQLITE_DATABASE)
    await db.executescript('CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY,username TEXT,blocked INTEGER DEFAULT 0,first_seen TEXT,last_seen TEXT); CREATE TABLE IF NOT EXISTS channels(channel_id INTEGER PRIMARY KEY,owner_id INTEGER,title TEXT,username TEXT,config TEXT); CREATE TABLE IF NOT EXISTS admins(user_id INTEGER PRIMARY KEY;')
    await db.commit()
    return db
