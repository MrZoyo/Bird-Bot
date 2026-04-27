import asyncio
from datetime import timedelta

import discord

from bot.utils.ban_db import BanDatabaseManager


def test_tempban_lifecycle_and_cleanup(tmp_path):
    async def scenario():
        db = BanDatabaseManager(str(tmp_path / "ban.db"))
        await db.initialize_database()

        future_unban = discord.utils.utcnow() + timedelta(hours=1)
        tempban_id = await db.add_tempban(
            user_id=100,
            guild_id=200,
            banned_by=300,
            reason="smoke",
            unban_at=future_unban,
            delete_message_days=1,
        )

        user_record = await db.get_user_tempban(100, 200)
        assert user_record[0] == tempban_id
        assert user_record[1] == 100
        assert user_record[2] == 200
        assert user_record[7] == 1

        active_records = await db.get_active_tempbans(200)
        assert [record[0] for record in active_records] == [tempban_id]

        stats = await db.get_tempban_stats(200)
        assert stats["active_tempbans"] == 1
        assert stats["recent_tempbans"] == 1

        assert await db.deactivate_tempban_by_user(100, 200) is True
        assert await db.get_user_tempban(100, 200) is None

        expired_unban = discord.utils.utcnow() - timedelta(days=31)
        old_id = await db.add_tempban(
            user_id=101,
            guild_id=200,
            banned_by=300,
            reason="old",
            unban_at=expired_unban,
        )
        assert await db.deactivate_tempban(old_id) is True
        assert await db.cleanup_old_records(days_old=30) == 1

    asyncio.run(scenario())
