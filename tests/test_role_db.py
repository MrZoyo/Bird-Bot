import asyncio

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

        assert await db.toggle_signature_permission(42, True) is True
        assert (await db.get_user_signature(42))["is_disabled"] in (1, True)

        assert await db.clear_user_signature(42) is True
        cleared = await db.get_user_signature(42)
        assert cleared["signature"] is None
        assert cleared["change_time1"] is None

    asyncio.run(scenario())
