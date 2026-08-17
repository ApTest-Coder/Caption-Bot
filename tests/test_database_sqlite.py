import json

import pytest

from database import settings as database_settings


@pytest.mark.asyncio
async def test_sqlite_database_round_trip(tmp_path, monkeypatch):
    """Exercise users, admins, channels, blocking and counts on real SQLite."""
    monkeypatch.setattr(database_settings, "DATABASE_TYPE", "sqlite")
    monkeypatch.setattr(
        database_settings,
        "SQLITE_DATABASE",
        str(tmp_path / "caption-bot.db"),
    )

    db = database_settings.Database()
    await db.connect()
    try:
        await db.user_upsert(1001, "tester")
        await db.add_admin(2002)
        assert await db.is_admin(2002) is True

        config = json.dumps(database_settings.default_settings())
        await db.save_channel(
            1001,
            -1001234567890,
            "Test Channel",
            "testchannel",
            config,
        )

        channel = await db.get_channel(-1001234567890)
        assert channel["owner_id"] == 1001
        assert len(await db.list_channels(1001)) == 1

        counts = await db.counts()
        assert counts == {"users": 1, "channels": 1}

        await db.mark_blocked(1001)
        assert await db.user_ids() == []

        await db.delete_channel(-1001234567890, 1001)
        assert await db.get_channel(-1001234567890) is None
    finally:
        await db.sqlite.close()
