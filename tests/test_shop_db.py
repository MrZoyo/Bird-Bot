import asyncio
from datetime import datetime, timedelta

from bot.utils.shop_db import ShopDatabaseManager


def test_shop_balance_checkin_makeup_and_embed_state(tmp_path):
    async def scenario():
        db = ShopDatabaseManager(
            str(tmp_path / "shop.db"),
            config={"makeup_checkin_limit_per_month": 2},
        )
        await db.initialize_database()
        try:
            assert await db.get_user_balance(42) == 0
            assert await db.update_user_balance(42, 50) == 50

            assert await db.update_user_balance_with_record(
                user_id=42,
                amount=-10,
                operation_type="purchase",
                operator_id=99,
                note="smoke",
            ) == 40
            assert await db.get_transaction_count(42) == 1
            history = await db.get_transaction_history(42)
            assert history[0][2] == "purchase"
            assert history[0][4] == 40

            today = datetime.now().date().isoformat()
            checkin = await db.record_checkin(42)
            assert checkin["already_checked_in"] is False
            assert checkin["last_checkin"] == today

            duplicate = await db.record_checkin(42)
            assert duplicate["already_checked_in"] is True
            assert await db.get_today_checkin_count(today) == 1
            assert await db.get_today_first_checkin_user(today) == 42

            month_history = await db.get_checkin_history_by_month(42)
            assert month_history[0][0] == today[:7]
            assert str(datetime.now().day) in month_history[0][1]

            makeup_date = (datetime.now().date() - timedelta(days=1)).isoformat()
            assert await db.add_makeup_record(42, makeup_date) is True
            assert await db.get_makeup_count_this_month(42) == 1
            assert await db.get_remaining_makeup_count(42) == 1

            assert await db.create_checkin_embed_record(10, 20, today) is True
            embeds = await db.get_active_checkin_embeds()
            assert len(embeds) == 1
            embed_id = embeds[0]["id"]

            assert await db.update_embed_checkin_stats(embed_id, 42) is True
            embeds = await db.get_active_checkin_embeds()
            assert embeds[0]["today_checkin_count"] == 1
            assert embeds[0]["today_first_checkin_user_id"] == 42

            assert await db.reset_daily_embed_stats("2099-01-01") is True
            embeds = await db.get_active_checkin_embeds()
            assert embeds[0]["created_date"] == "2099-01-01"
            assert embeds[0]["today_checkin_count"] == 0
            assert embeds[0]["today_first_checkin_user_id"] is None

            assert await db.deactivate_checkin_embed(embed_id) is True
            assert await db.get_active_checkin_embeds() == []
        finally:
            await db.close()

    asyncio.run(scenario())
