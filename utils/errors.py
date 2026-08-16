"""Error logging helpers."""

import logging

LOGGER = logging.getLogger("caption-bot")


def log_exception(exc: Exception) -> None:
    """Log an exception with traceback information."""
    LOGGER.exception("Unhandled bot error: %s", exc)
