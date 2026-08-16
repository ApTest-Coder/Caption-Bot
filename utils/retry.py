import asyncio

async def retry(coro_factory, attempts=3, delay=1):
    last=None
    for n in range(attempts):
        try: return await coro_factory()
        except Exception as exc:
            last=exc
            if n+1<attempts: await asyncio.sleep(delay*(n+1))
    raise last
