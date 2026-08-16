"""Telegram media-type detection helpers."""

MEDIA_TYPES = (
    "video",
    "audio",
    "document",
    "photo",
    "animation",
    "voice",
    "sticker",
)


def media_type(message) -> str | None:
    """Return the first supported media type present on a message."""
    for name in MEDIA_TYPES:
        if getattr(message, name, None):
            return name
    return None
