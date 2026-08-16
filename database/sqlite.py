"""SQLite connection helper."""

import aiosqlite

from config import SQLITE_DATABASE


async def connect():
    """Open SQLite and ensure the supporting tables exist."""
    db = await aiosqlite.connect(SQLITE_DATABASE)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=30000")
    await db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            blocked INTEGER DEFAULT 0,
            first_seen TEXT,
            last_seen TEXT
        );
        CREATE TABLE IF NOT EXISTS channels(
            channel_id INTEGER PRIMARY KEY,
            owner_id INTEGER,
            title TEXT,
            username TEXT,
            config TEXT
        );
        CREATE TABLE IF NOT EXISTS admins(
            user_id INTEGER PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS stats(
            key TEXT PRIMARY KEY,
            value INTEGER DEFAULT 0
        );
        """
    )
    await db.commit()
    return db
