"""Flood-wait sleep helper."""

import asyncio


async def sleep_for(seconds: int | float) -> None:
    """Sleep for a non-negative number of seconds."""
    await asyncio.sleep(max(0, int(seconds)))
