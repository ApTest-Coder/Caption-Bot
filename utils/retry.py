"""Generic asynchronous retry helper."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry(
    coro_factory: Callable[[], Awaitable[T]],
    attempts: int = 3,
    delay: float = 1,
) -> T:
    """Retry an async operation a bounded number of times."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    last: Exception | None = None
    for number in range(attempts):
        try:
            return await coro_factory()
        except Exception as exc:
            last = exc
            if number + 1 < attempts:
                await asyncio.sleep(delay * (number + 1))

    assert last is not None
    raise last
