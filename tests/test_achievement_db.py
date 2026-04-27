import asyncio

from bot.utils.achievement_db import AchievementDatabaseManager
from bot.utils.shop_db import ShopDatabaseManager


def test_achievement_counts_leaderboards_voice_and_shop_interop(tmp_path):
    async def scenario():
        db_path = str(tmp_path / "achievement.db")
        achievements = AchievementDatabaseManager(db_path)
        shop = ShopDatabaseManager(db_path)
        await achievements.initialize_database()
        await shop.initialize_database()
        try:
            assert await achievements.update_achievement_count(10, "message", 3) is True
            assert await achievements.update_achievement_count(20, "message", 5) is True
            assert (await achievements.get_user_achievements(10))["message_count"] == 3
            assert await achievements.get_leaderboard("message") == [(20, 5), (10, 3)]
            assert await achievements.get_user_rank(10, "message") == (2, 2)

            assert await achievements.update_monthly_achievement_count(
                user_id=10,
                achievement_type="reaction",
                amount=7,
                year=2026,
                month=4,
            ) is True
            monthly = await achievements.get_monthly_achievements(10, 2026, 4)
            assert monthly["reaction_count"] == 7
            assert await achievements.get_monthly_leaderboard(2026, 4, "reaction") == [(10, 7)]

            assert await achievements.start_voice_session(10, 100) is True
            active_sessions = await achievements.get_active_voice_sessions(10)
            assert len(active_sessions) == 1
            assert active_sessions[0][0] == 100
            assert await achievements.end_voice_session(10, 100) >= 0
            assert await achievements.get_active_voice_sessions(10) == []

            assert await achievements.apply_manual_changes(
                target_id=10,
                changes={"time_spent": 60, "giveaway_count": 2},
                operation="increase",
            ) is True
            assert await achievements.log_manual_operation(
                operator_id=99,
                target_id=10,
                operation="increase",
                changes={"time_spent": 60, "giveaway_count": 2},
            ) is True
            operations = await achievements.get_all_operations()
            assert operations[0][0] == 99
            assert operations[0][1] == 10
            assert operations[0][2] == "increase"

            checkin = await shop.record_checkin(10)
            assert checkin["already_checked_in"] is False

            user_data = await achievements.get_user_achievements(10)
            assert user_data["checkin_sum"] == 1
            assert user_data["checkin_combo"] == 1
            assert await achievements.get_checkin_leaderboard("checkin_sum") == [(10, 1)]
        finally:
            await achievements.close()
            await shop.close()

    asyncio.run(scenario())
