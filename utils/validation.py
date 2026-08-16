"""Small, reusable validation helpers used across the bot."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_COLOR_NAMES = {"blue", "green", "red"}
_CHANNEL_ID_RE = re.compile(r"^-100\d{5,}$|^\d{5,}$")


def is_valid_channel_id(value: str) -> bool:
    """Return True when *value* looks like a Telegram channel ID."""
    return bool(_CHANNEL_ID_RE.fullmatch(value.strip()))


def is_public_url(value: str) -> bool:
    """Accept http(s) URLs only; callers can apply Telegram-specific checks separately."""
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize_button_color(value: str) -> str | None:
    """Normalize supported UI button colors."""
    color = value.strip().lower()
    return color if color in _COLOR_NAMES else None
