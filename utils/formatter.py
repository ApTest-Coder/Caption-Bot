"""Caption template rendering and dynamic variable expansion."""
from __future__ import annotations

import re
from datetime import datetime

from .parser import media_values, parse_filename

TOKEN_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def human_size(value: int | float | None) -> str | None:
    """Return a human-readable file size."""
    if value is None:
        return None
    size = float(value)
    units = ("B", "KB", "MB", "GB", "TB")
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {units[index]}"


def format_caption(template: str, message) -> str:
    """Render a caption template without failing on missing metadata.

    Episode, season, quality and audio have explicit fallbacks. Other missing
    variables remove the complete line containing that variable.
    """
    original = message.caption or message.text or ""
    values = media_values(message)
    filename = values.get("filename") or ""

    parsed = parse_filename(filename)
    caption_parsed = parse_filename(original)
    for key in ("episode", "season", "quality", "year", "language", "audio"):
        if not parsed.get(key):
            parsed[key] = caption_parsed.get(key)
    values.update(parsed)

    values["caption"] = re.sub(r"<[^>]+>", "", original)
    values["html_caption"] = original
    values["ext"] = filename.rsplit(".", 1)[-1] if "." in filename else None
    values["resolution"] = (
        f"{values['width']}x{values['height']}"
        if values.get("width") and values.get("height")
        else None
    )
    values["filesize"] = human_size(values.get("filesize"))
    values["wish"] = wish()

    # Explicit fallbacks requested by the project specification.
    values["audio"] = values.get("audio") or "Audio"
    values["episode"] = values.get("episode") or "E01 - E0?"
    values["season"] = values.get("season") or "S01 - S0?"
    values["quality"] = values.get("quality") or "Unknown Quality"

    # Unknown/non-special variables cause their whole line to be skipped.
    special = {"episode", "season", "quality", "audio"}
    lines: list[str] = []
    for line in template.splitlines():
        tokens = TOKEN_RE.findall(line)
        if tokens and any(
            token not in special and not values.get(token) for token in tokens
        ):
            continue
        lines.append(line)

    def replace(match: re.Match[str]) -> str:
        value = values.get(match.group(1))
        return str(value) if value is not None else ""

    rendered = TOKEN_RE.sub(replace, "\n".join(lines))
    return "\n".join(line.rstrip() for line in rendered.splitlines()).strip()


def wish() -> str:
    """Return a simple local-time greeting."""
    hour = datetime.now().hour
    if hour < 12:
        return "Good Morning"
    if hour < 17:
        return "Good Afternoon"
    return "Good Evening"
