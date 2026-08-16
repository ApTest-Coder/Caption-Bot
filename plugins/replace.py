"""Text replacement helper."""


def apply(text: str, rules: dict | None) -> str:
    """Apply configured string replacements in order."""
    for old, new in (rules or {}).items():
        text = text.replace(old, new)
    return text
