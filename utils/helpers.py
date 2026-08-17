"""Small generic helpers shared by configuration and input code."""

from __future__ import annotations


def clean_id(value: object) -> int:
    """Convert an ID-like value to an integer after trimming whitespace."""
    return int(str(value).strip())


def bool_value(value: object) -> bool:
    """Convert common human-readable truthy values to a boolean."""
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
