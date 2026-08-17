"""Database helpers for per-channel button configuration."""

from __future__ import annotations

import json
from typing import Any

from .settings import Database, default_settings


def load(config: str | None) -> list[dict[str, Any]]:
    """Read button definitions from a serialized channel configuration."""
    try:
        data = json.loads(config or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    buttons = data.get("buttons", [])
    return buttons if isinstance(buttons, list) else []


def dumps(buttons: list[dict[str, Any]]) -> str:
    """Serialize a button list using stable JSON formatting."""
    return json.dumps(buttons, ensure_ascii=False)


async def get(db: Database, channel_id: int) -> list[dict[str, Any]]:
    """Return buttons for a channel, or an empty list when unset."""
    row = await db.get_channel(channel_id)
    if not row:
        return []
    return load(row.get("config"))


async def replace(db: Database, owner_id: int, channel_id: int, buttons: list[dict[str, Any]]) -> None:
    """Replace the complete button list while preserving other settings."""
    row = await db.get_channel(channel_id)
    if not row or row.get("owner_id") != owner_id:
        raise PermissionError("Channel is not owned by this user")
    try:
        settings = json.loads(row.get("config") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        settings = default_settings()
    settings["buttons"] = buttons
    await db.save_channel(
        owner_id,
        channel_id,
        row.get("title", "Channel"),
        row.get("username", ""),
        json.dumps(settings, ensure_ascii=False),
    )
