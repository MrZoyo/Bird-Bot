import asyncio
from datetime import datetime, timedelta

from bot.utils.privateroom_db import PrivateRoomDatabaseManager


def test_privateroom_config_shop_and_room_state_round_trip(tmp_path):
    async def scenario():
        db = PrivateRoomDatabaseManager(str(tmp_path / "privateroom.db"))
        await db.initialize_database()

        await db.set_category_id(1234)
        assert await db.get_category_id() == 1234

        await db.set_config_value("renewal_threshold_days", "7")
        assert await db.get_config_value("renewal_threshold_days") == "7"

        await db.save_shop_message(10, 20)
        assert await db.get_shop_messages() == [(10, 20)]

        await db.remove_shop_message(10, 20)
        assert await db.get_shop_messages() == []

        await db.save_shop_message(11, 21)
        await db.delete_shop_messages()
        assert await db.get_shop_messages() == []

        start_date = datetime.now() - timedelta(days=1)
        end_date = datetime.now() + timedelta(days=3)
        await db.create_room(555, 777, start_date, end_date)

        active_room = await db.get_active_room_by_user(777)
        assert active_room["room_id"] == 555
        assert active_room["user_id"] == 777
        assert await db.get_active_rooms_count() == 1

        paginated_rooms, total_count = await db.get_paginated_active_rooms(
            page=1,
            items_per_page=10,
        )
        assert total_count == 1
        assert paginated_rooms[0][0] == 555

        renewal_rooms = await db.get_rooms_eligible_for_renewal(threshold_days=10)
        assert [room["room_id"] for room in renewal_rooms] == [555]

        await db.update_renewal_reminder_flag(555, True)
        assert await db.get_rooms_eligible_for_renewal(threshold_days=10) == []

        await db.extend_room_validity(555, datetime.now() + timedelta(days=30))
        await db.update_renewal_reminder_flag(555, False)
        assert await db.get_rooms_eligible_for_renewal(threshold_days=10) == []

        await db.mark_room_inactive(555)
        assert await db.get_active_room_by_user(777) is None

        inactive_room = await db.get_inactive_valid_room(777)
        assert inactive_room["room_id"] == 555

        await db.reset_privateroom_system()
        assert await db.get_category_id() is None
        assert await db.get_active_rooms_count() == 0

    asyncio.run(scenario())
