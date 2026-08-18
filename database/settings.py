"""Async persistence facade for SQLite and MongoDB deployments."""

from __future__ import annotations

import copy
import os
from datetime import UTC, datetime

import aiosqlite
from motor.motor_asyncio import AsyncIOMotorClient

from config import (
    DATABASE_NAME,
    DATABASE_TYPE,
    MONGO_URI,
    OWNER_ID,
    SQLITE_DATABASE,
)

DEFAULT_SETTINGS = {
    "caption": "",
    "buttons": [],
    "replacements": {},
    "filters": {},
    "forward": {"enabled": False, "destination": None},
    "prefix": "",
    "suffix": "",
    "stickers": {"enabled": False, "file_id": None},
    "media_details": False,
}


def default_settings() -> dict:
    """Return a fresh copy of the default per-channel settings."""
    return copy.deepcopy(DEFAULT_SETTINGS)


async def _ensure_sqlite_column(
    db: aiosqlite.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    """Add a missing column to an existing SQLite installation."""
    cursor = await db.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in await cursor.fetchall()}
    if column not in columns:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


class Database:
    """Small storage abstraction used by the bot and plugin modules."""

    def __init__(self) -> None:
        self.mongo = None
        self.db = None
        self.sqlite = None

    async def connect(self) -> None:
        """Connect to the configured backend and initialize its schema."""
        backend = DATABASE_TYPE.strip().lower()
        if backend == "mongodb":
            if not MONGO_URI:
                raise RuntimeError("MONGO_URI is required for MongoDB mode")
            self.mongo = AsyncIOMotorClient(
                MONGO_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=10000,
            )
            await self.mongo.admin.command("ping")
            self.db = self.mongo[DATABASE_NAME]
            await self.db.users.create_index("user_id", unique=True)
            await self.db.channels.create_index("channel_id", unique=True)
            await self.db.admins.create_index("user_id", unique=True)
            return

        if backend != "sqlite":
            raise RuntimeError("DATABASE_TYPE must be 'mongodb' or 'sqlite'")

        os.makedirs(os.path.dirname(SQLITE_DATABASE) or ".", exist_ok=True)
        self.sqlite = await aiosqlite.connect(SQLITE_DATABASE, timeout=30)
        await self.sqlite.execute("PRAGMA journal_mode=WAL")
        await self.sqlite.execute("PRAGMA busy_timeout=30000")
        await self.sqlite.executescript(
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
                owner_id INTEGER NOT NULL,
                title TEXT,
                username TEXT,
                config TEXT
            );
            CREATE TABLE IF NOT EXISTS admins(
                user_id INTEGER PRIMARY KEY
            );
            """
        )
        await _ensure_sqlite_column(
            self.sqlite, "users", "blocked", "INTEGER DEFAULT 0"
        )
        await _ensure_sqlite_column(self.sqlite, "users", "first_seen", "TEXT")
        await _ensure_sqlite_column(self.sqlite, "users", "last_seen", "TEXT")
        await _ensure_sqlite_column(
            self.sqlite, "channels", "owner_id", "INTEGER DEFAULT 0"
        )
        await _ensure_sqlite_column(self.sqlite, "channels", "title", "TEXT")
        await _ensure_sqlite_column(self.sqlite, "channels", "username", "TEXT")
        await _ensure_sqlite_column(self.sqlite, "channels", "config", "TEXT")
        await self.sqlite.execute("UPDATE users SET blocked=0 WHERE blocked IS NULL")
        await self.sqlite.commit()

    async def close(self) -> None:
        """Close whichever database backend is currently connected."""
        if self.sqlite is not None:
            await self.sqlite.close()
            self.sqlite = None
        if self.mongo is not None:
            self.mongo.close()
            self.mongo = None
        self.db = None

    async def user_upsert(self, user_id: int, username: str) -> None:
        """Insert or refresh a tracked user without clearing a block marker."""
        now = datetime.now(UTC).isoformat()
        if self.db is not None:
            await self.db.users.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "username": username,
                        "last_seen": now,
                    },
                    "$setOnInsert": {
                        "first_seen": now,
                        "blocked": False,
                    },
                },
                upsert=True,
            )
            return

        await self.sqlite.execute(
            "INSERT INTO users(user_id,username,blocked,first_seen,last_seen) "
            "VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
            "username=excluded.username, last_seen=excluded.last_seen",
            (user_id, username, 0, now, now),
        )
        await self.sqlite.commit()

    async def is_admin(self, user_id: int) -> bool:
        """Return whether a user is the owner or a stored administrator."""
        if user_id == OWNER_ID:
            return True
        if self.db is not None:
            return bool(await self.db.admins.find_one({"user_id": user_id}))
        cursor = await self.sqlite.execute(
            "SELECT 1 FROM admins WHERE user_id=?",
            (user_id,),
        )
        return await cursor.fetchone() is not None

    async def add_admin(self, user_id: int) -> None:
        """Add an administrator."""
        if self.db is not None:
            await self.db.admins.update_one(
                {"user_id": user_id},
                {"$set": {"user_id": user_id}},
                upsert=True,
            )
            return
        await self.sqlite.execute(
            "INSERT OR IGNORE INTO admins(user_id) VALUES(?)",
            (user_id,),
        )
        await self.sqlite.commit()

    async def del_admin(self, user_id: int) -> None:
        """Remove an administrator without removing the owner."""
        if user_id == OWNER_ID:
            return
        if self.db is not None:
            await self.db.admins.delete_one({"user_id": user_id})
            return
        await self.sqlite.execute(
            "DELETE FROM admins WHERE user_id=?",
            (user_id,),
        )
        await self.sqlite.commit()

    async def save_channel(
        self,
        owner_id: int,
        channel_id: int,
        title: str,
        username: str,
        config: str,
    ) -> None:
        """Create or update a channel without allowing ownership takeover."""
        existing = await self.get_channel(channel_id)
        if existing and existing.get("owner_id") != owner_id:
            raise PermissionError("Channel is already managed by another owner")

        if self.db is not None:
            await self.db.channels.update_one(
                {"channel_id": channel_id},
                {
                    "$set": {
                        "owner_id": owner_id,
                        "title": title,
                        "username": username,
                        "config": config,
                    }
                },
                upsert=True,
            )
            return

        await self.sqlite.execute(
            "INSERT INTO channels(channel_id,owner_id,title,username,config) "
            "VALUES(?,?,?,?,?) ON CONFLICT(channel_id) DO UPDATE SET "
            "title=excluded.title,username=excluded.username,config=excluded.config",
            (channel_id, owner_id, title, username, config),
        )
        await self.sqlite.commit()

    async def get_channel(self, channel_id: int):
        """Return one channel configuration by ID."""
        if self.db is not None:
            return await self.db.channels.find_one({"channel_id": channel_id})
        cursor = await self.sqlite.execute(
            "SELECT channel_id,owner_id,title,username,config "
            "FROM channels WHERE channel_id=?",
            (channel_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "channel_id": row[0],
            "owner_id": row[1],
            "title": row[2],
            "username": row[3],
            "config": row[4],
        }

    async def list_channels(self, owner_id: int | None = None) -> list[dict]:
        """Return channels, optionally filtered to an owner."""
        if self.db is not None:
            query = {} if owner_id is None else {"owner_id": owner_id}
            return await self.db.channels.find(query).to_list(1000)

        query = "SELECT channel_id,owner_id,title,username,config FROM channels"
        args: tuple = ()
        if owner_id is not None:
            query += " WHERE owner_id=?"
            args = (owner_id,)
        cursor = await self.sqlite.execute(query, args)
        rows = await cursor.fetchall()
        return [
            {
                "channel_id": row[0],
                "owner_id": row[1],
                "title": row[2],
                "username": row[3],
                "config": row[4],
            }
            for row in rows
        ]

    async def delete_channel(self, channel_id: int, owner_id: int) -> None:
        """Delete a channel only when owned by the requester."""
        if self.db is not None:
            await self.db.channels.delete_one(
                {"channel_id": channel_id, "owner_id": owner_id}
            )
            return
        await self.sqlite.execute(
            "DELETE FROM channels WHERE channel_id=? AND owner_id=?",
            (channel_id, owner_id),
        )
        await self.sqlite.commit()

    async def mark_blocked(self, user_id: int) -> None:
        """Flag a user as blocked so broadcasts skip them."""
        if self.db is not None:
            await self.db.users.update_one(
                {"user_id": user_id},
                {"$set": {"blocked": True}},
            )
            return
        await self.sqlite.execute(
            "UPDATE users SET blocked=1 WHERE user_id=?",
            (user_id,),
        )
        await self.sqlite.commit()

    async def user_ids(self) -> list[int]:
        """Return tracked users that have not blocked the bot."""
        if self.db is not None:
            rows = await self.db.users.find(
                {"blocked": {"$ne": True}},
                {"user_id": 1, "_id": 0},
            ).to_list(None)
            return [int(row["user_id"]) for row in rows]
        cursor = await self.sqlite.execute(
            "SELECT user_id FROM users WHERE blocked=0"
        )
        rows = await cursor.fetchall()
        return [int(row[0]) for row in rows]

    async def counts(self) -> dict[str, int]:
        """Return total tracked users and channels."""
        if self.db is not None:
            return {
                "users": await self.db.users.count_documents({}),
                "channels": await self.db.channels.count_documents({}),
            }
        user_cursor = await self.sqlite.execute("SELECT COUNT(*) FROM users")
        channel_cursor = await self.sqlite.execute("SELECT COUNT(*) FROM channels")
        users = await user_cursor.fetchone()
        channels = await channel_cursor.fetchone()
        return {"users": users[0], "channels": channels[0]}
