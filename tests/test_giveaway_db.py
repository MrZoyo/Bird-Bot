import asyncio
from datetime import datetime

from bot.utils.giveaway_db import GiveawayDatabaseManager


def test_giveaway_record_participants_winners_and_views(tmp_path):
    async def scenario():
        db = GiveawayDatabaseManager(str(tmp_path / "giveaway.db"))
        await db.initialize_database()

        await db.insert_giveaway(
            giveaway_id=1,
            message_id="message-1",
            starttime=datetime.now().isoformat(),
            duration=60,
            winner_number=2,
            prizes="Prize",
            description="Initial",
            creator_id="900",
            winner_ids="",
            reaction_req=1,
            message_req=2,
            timespent_req=3,
            provider="Provider",
            image_url="https://example.com/prize.png",
            image_filename="prize.png",
            ui_version=2,
        )

        record = await db.fetch_giveaway(1)
        assert record["giveaway_id"] == 1
        assert record["description"] == "Initial"
        assert record["reaction_req"] == 1
        assert record["provider"] == "Provider"
        assert record["image_url"] == "https://example.com/prize.png"
        assert record["image_filename"] == "prize.png"
        assert record["ui_version"] == 2
        assert await db.fetch_all_giveaway_ids() == [1]
        assert await db.fetch_giveaway_requirements(1) == (1, 2, 3)

        await db.add_participant(1, 101)
        await db.add_participant(1, 202)
        assert await db.fetch_participant_ids(1) == ["101", "202"]
        assert await db.is_participant(1, 202) is True

        await db.remove_participant(1, 101)
        assert await db.fetch_participant_ids(1) == ["202"]

        await db.update_giveaway_description(1, "Updated")
        await db.update_giveaway_duration(1, 120)
        updated = await db.fetch_giveaway(1)
        assert updated["description"] == "Updated"
        assert updated["duration"] == 120

        await db.save_giveaway_view(1, 303, 404)
        loaded_views = await db.load_giveaway_views()
        assert [(str(row[0]), str(row[1]), str(row[2])) for row in loaded_views] == [
            ("1", "303", "404")
        ]

        await db.update_giveaway_winners(1, [202])
        assert await db.fetch_winner_ids(1) == [202]
        assert (await db.fetch_giveaway(1))["is_end"] == 1

        await db.cleanup_ended_giveaway_views()
        assert await db.load_giveaway_views() == []

    asyncio.run(scenario())
