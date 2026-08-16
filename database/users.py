"""User data helpers. The Database class in db.py is the runtime facade."""
from .db import Database

async def is_admin(db: Database, user_id: int) -> bool:
    return await db.is_admin(user_id)
