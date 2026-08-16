"""Helpers for reading button settings from a stored channel config."""

import json


def load(config: str | None) -> list:
    """Return configured buttons, or an empty list for invalid data."""
    try:
        return json.loads(config or "{}").get("buttons", [])
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
