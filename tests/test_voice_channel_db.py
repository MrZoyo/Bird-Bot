import asyncio

from bot.utils.voice_channel_db import VoiceChannelDatabaseManager


def test_voice_channel_runtime_state_round_trip(tmp_path):
    async def scenario():
        db = VoiceChannelDatabaseManager(str(tmp_path / "voice.db"))
        await db.initialize_database()
        try:
            assert await db.list_channel_configs() == {}

            await db.upsert_channel_config(11, "Room", "public")
            assert await db.list_channel_configs() == {
                11: {"name_prefix": "Room", "type": "public"}
            }

            await db.upsert_channel_config(11, "Team", "private")
            assert await db.list_channel_configs() == {
                11: {"name_prefix": "Team", "type": "private"}
            }

            await db.delete_channel_config(11)
            assert await db.list_channel_configs() == {}

            await db.insert_temp_channel(101, 202, True, "public")
            assert await db.exists(101) is True
            assert await db.fetch_all_channel_ids() == [101]

            await db.set_room_type(101, "private")
            await db.set_soundboard(101, False)
            await db.set_control_panel(101, 303, 404)

            rows = await db.fetch_all_records()
            assert len(rows) == 1
            row = rows[0]
            assert row[0] == 101
            assert row[1] == 202
            assert row[3] == 303
            assert row[4] == 404
            assert row[5] == 0
            assert row[6] == "private"

            assert await db.fetch_control_panels() == [(101, 202, 303, 0, "private")]

            await db.clear_control_panel(101)
            assert await db.fetch_control_panels() == []

            await db.delete_temp_channel(101)
            assert await db.exists(101) is False
        finally:
            await db.close()

    asyncio.run(scenario())
