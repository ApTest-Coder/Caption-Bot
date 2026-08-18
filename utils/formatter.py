"""Caption template rendering and dynamic variable expansion."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from html import escape

from .parser import media_values, parse_filename

TOKEN_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
SPECIAL_FALLBACKS = {
    "episode": "E01 - E0?",
    "season": "S01 - S0?",
    "quality": "Unknown Quality",
    "audio": "Audio",
}

HTML_TAG_RE = re.compile(
    r"</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|blockquote|tg-spoiler)"
    r"(?:\s[^>]*)?>",
    re.IGNORECASE,
)


def human_size(value: int | float | None) -> str | None:
    """Convert a byte count to a compact human-readable value."""
    if value is None:
        return None
    size = float(value)
    units = ("B", "KB", "MB", "GB", "TB")
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {units[index]}"


def human_duration(value: int | float | None) -> str | None:
    """Convert seconds to a human-readable duration."""
    if value is None:
        return None
    return str(timedelta(seconds=int(value)))


def strip_html(value: str) -> str:
    """Remove supported Telegram HTML tags without destroying plain text."""
    return HTML_TAG_RE.sub("", value)


def _wish() -> str:
    """Return a greeting based on the local process time."""
    hour = datetime.now().hour
    if hour < 12:
        return "Good Morning"
    if hour < 17:
        return "Good Afternoon"
    return "Good Evening"


def _escape_dynamic(value: object) -> str:
    """Escape dynamic metadata before it is inserted into Telegram HTML."""
    return escape(str(value), quote=False)


def _html_caption(message, original: str) -> str:
    """Return Telegram's HTML representation when available, else safe text."""
    rendered = getattr(message, "html_caption", None)
    if rendered:
        return str(rendered)
    rendered = getattr(message, "html_text", None)
    if rendered:
        return str(rendered)
    return escape(original, quote=False)


def format_caption(template: str, message) -> str:
    """Render a caption while safely handling unavailable media metadata."""
    original = message.caption or message.text or ""
    values = media_values(message)
    filename = values.get("filename") or ""

    parsed = parse_filename(filename)
    caption_parsed = parse_filename(original)
    for key in ("episode", "season", "quality", "year", "language", "audio"):
        if not parsed.get(key):
            parsed[key] = caption_parsed.get(key)
    values.update(parsed)

    values["caption"] = strip_html(original)
    values["html_caption"] = _html_caption(message, original)
    values["ext"] = filename.rsplit(".", 1)[-1] if "." in filename else None
    values["resolution"] = (
        f"{values['width']}x{values['height']}"
        if values.get("width") and values.get("height")
        else None
    )
    values["filesize"] = human_size(values.get("filesize"))
    values["duration"] = human_duration(values.get("duration"))
    values["wish"] = _wish()

    for key, fallback in SPECIAL_FALLBACKS.items():
        values[key] = values.get(key) or fallback

    lines: list[str] = []
    for line in template.splitlines():
        tokens = TOKEN_RE.findall(line)
        if tokens and any(
            token not in SPECIAL_FALLBACKS and not values.get(token)
            for token in tokens
        ):
            continue
        lines.append(line)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = values.get(key)
        if value is None:
            return ""
        if key == "html_caption":
            return str(value)
        return _escape_dynamic(value)

    rendered = TOKEN_RE.sub(replace, "\n".join(lines))
    return "\n".join(line.rstrip() for line in rendered.splitlines()).strip()
