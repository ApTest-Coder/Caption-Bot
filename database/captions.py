"""Helpers for reading the configured caption template."""

import json


def load(config: str | None) -> str:
    """Return the stored caption or an empty string for invalid data."""
    try:
        return json.loads(config or "{}").get("caption", "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return ""
