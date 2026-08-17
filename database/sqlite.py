"""SQLite backend connection and schema utilities."""

from __future__ import annotations

import os

import aiosqlite

from config import SQLITE_DATABASE


SCHEMA = """
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


async def _ensure_column(
    db: aiosqlite.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    """Add a column when upgrading a database created by an older release."""
    cursor = await db.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in await cursor.fetchall()}
    if column not in columns:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


async def connect() -> aiosqlite.Connection:
    """Open SQLite, configure locking behavior, and initialize/migrate schema."""
    os.makedirs(os.path.dirname(SQLITE_DATABASE) or ".", exist_ok=True)
    db = await aiosqlite.connect(SQLITE_DATABASE, timeout=30)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=30000")
    await db.executescript(SCHEMA)

    await _ensure_column(db, "users", "blocked", "INTEGER DEFAULT 0")
    await _ensure_column(db, "users", "first_seen", "TEXT")
    await _ensure_column(db, "users", "last_seen", "TEXT")
    await _ensure_column(db, "channels", "owner_id", "INTEGER DEFAULT 0")
    await _ensure_column(db, "channels", "title", "TEXT")
    await _ensure_column(db, "channels", "username", "TEXT")
    await _ensure_column(db, "channels", "config", "TEXT")
    await db.commit()
    return db


async def close(db: aiosqlite.Connection | None) -> None:
    """Close a SQLite connection when one is open."""
    if db is not None:
        await db.close()
