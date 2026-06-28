import asyncio
from datetime import datetime, timedelta, timezone

from bot.utils.db_connect import connect_database
from bot.utils.role_db import RoleDatabaseManager


def test_role_views_and_signature_state_round_trip(tmp_path):
    async def scenario():
        db = RoleDatabaseManager(str(tmp_path / "role.db"))
        await db.initialize_database()

        assert await db.save_role_view(111, 222, table="starsign_views") is True
        assert await db.get_all_role_views(table="starsign_views") == [("111", "222")]

        assert await db.remove_role_view(111, 222, table="starsign_views") is True
        assert await db.get_all_role_views(table="starsign_views") == []

        assert await db.get_signature_remaining_changes(42) == 3
        assert await db.find_available_time_slot(42) == 1

        assert await db.update_user_signature(42, "ready", 1) is True
        signature = await db.get_user_signature(42)
        assert signature["signature"] == "ready"
        assert signature["change_time1"] is not None
        assert signature["is_disabled"] in (0, False)
        assert await db.get_signature_remaining_changes(42) == 2
        assert await db.find_available_time_slot(42) == 2

        assert await db.update_user_signature(42, "ready 2", 2) is True
        assert await db.update_user_signature(42, "ready 3", 3) is True
        assert await db.get_signature_remaining_changes(42) == 0
        assert await db.find_available_time_slot(42) is None

        old_change_time = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        async with connect_database(db.db_path) as raw_db:
            await raw_db.execute(
                """
                UPDATE user_signatures
                SET change_time1 = ?, change_time2 = ?, change_time3 = ?
                WHERE user_id = ?
                """,
                (old_change_time, old_change_time, old_change_time, 42),
            )
            await raw_db.commit()

        assert await db.get_signature_remaining_changes(42, cooldown_days=7) == 3
        assert await db.find_available_time_slot(42, cooldown_days=7) == 1
        assert await db.get_signature_remaining_changes(42, cooldown_days=14) == 0
        assert await db.find_available_time_slot(42, cooldown_days=14) is None

        assert await db.toggle_signature_permission(42, True) is True
        assert (await db.get_user_signature(42))["is_disabled"] in (1, True)

        assert await db.clear_user_signature(42) is True
        cleared = await db.get_user_signature(42)
        assert cleared["signature"] is None
        assert cleared["change_time1"] is None

    asyncio.run(scenario())
