"""Button validation and rendering helpers."""

COLORS = ("blue", "green", "red")

from .context import button_style, valid_http_url


def validate_button(text: str, url: str, color: str) -> tuple[bool, str]:
    """Validate a user-created URL button and return an error if invalid."""
    if not text.strip():
        return False, "Button text cannot be empty."
    if not valid_http_url(url):
        return False, "Button URL must start with http:// or https://"
    if color.lower() not in COLORS:
        return False, "Button color must be blue, green or red."
    return True, ""


def normalize_button(text: str, url: str, color: str) -> dict:
    """Return the canonical database representation of a button."""
    return {
        "text": text.strip(),
        "url": url.strip(),
        "color": color.strip().lower(),
    }
