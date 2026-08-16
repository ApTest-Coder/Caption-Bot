import asyncio

async def sleep_for(seconds):
    await asyncio.sleep(max(0,int(seconds)))
