"""Database helpers for per-channel caption templates."""

from __future__ import annotations

import json

from .settings import Database, default_settings


def load(config: str | None) -> str:
    """Read the configured caption template from serialized settings."""
    try:
        data = json.loads(config or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return ""
    value = data.get("caption", "")
    return value if isinstance(value, str) else ""


async def get(db: Database, channel_id: int) -> str:
    """Return the caption configured for a channel."""
    row = await db.get_channel(channel_id)
    return load(row.get("config")) if row else ""


async def set_template(
    db: Database,
    owner_id: int,
    channel_id: int,
    caption: str,
) -> None:
    """Update only the caption while preserving the other channel settings."""
    row = await db.get_channel(channel_id)
    if not row or row.get("owner_id") != owner_id:
        raise PermissionError("Channel is not owned by this user")
    try:
        settings = json.loads(row.get("config") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        settings = default_settings()
    settings["caption"] = caption
    await db.save_channel(
        owner_id,
        channel_id,
        row.get("title", "Channel"),
        row.get("username", ""),
        json.dumps(settings, ensure_ascii=False),
    )


async def delete(db: Database, owner_id: int, channel_id: int) -> None:
    """Clear the caption without deleting the channel configuration."""
    await set_template(db, owner_id, channel_id, "")
