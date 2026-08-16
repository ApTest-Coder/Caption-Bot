"""HTML escaping helpers."""

from html import escape


def escape_text(text: str | None) -> str:
    """Escape text for Telegram HTML without quoting apostrophes."""
    return escape(text or "", quote=False)
