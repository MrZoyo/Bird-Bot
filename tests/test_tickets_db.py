import asyncio

from bot.utils.tickets_db import TicketsDatabaseManager


def run(coro):
    return asyncio.run(coro)


def test_ticket_type_crud_round_trips_json_payload(tmp_path):
    db = TicketsDatabaseManager(str(tmp_path / "tickets.db"))
    payload = {
        "description": "Support request",
        "guide": "Describe the problem",
        "button_color": "primary",
        "admin_roles": [101, 202],
        "admin_users": [303],
    }

    run(db.initialize_database())

    assert run(db.upsert_ticket_type("support", payload)) is True
    assert run(db.list_ticket_types()) == {"support": payload}

    updated_payload = {**payload, "description": "Updated support request"}
    assert run(db.upsert_ticket_type("support", updated_payload)) is True
    assert run(db.list_ticket_types()) == {"support": updated_payload}

    renamed_payload = {**updated_payload, "button_color": "danger"}
    assert run(db.rename_ticket_type("support", "urgent", renamed_payload)) is True
    assert run(db.list_ticket_types()) == {"urgent": renamed_payload}

    assert run(db.remove_ticket_type("urgent")) is True
    assert run(db.list_ticket_types()) == {}


def test_ticket_config_uses_latest_updated_row(tmp_path):
    db = TicketsDatabaseManager(str(tmp_path / "tickets.db"))

    run(db.initialize_database())

    assert run(db.get_config()) is None
    assert run(db.set_config(11, 22, 33)) is True
    assert run(db.get_config()) == {
        "ticket_channel_id": 11,
        "info_channel_id": 22,
        "main_message_id": 33,
    }

    assert run(db.set_config(44, 55, None)) is True
    assert run(db.get_config()) == {
        "ticket_channel_id": 44,
        "info_channel_id": 55,
        "main_message_id": None,
    }


def test_ticket_lifecycle_members_stats_and_history(tmp_path):
    async def scenario():
        db = TicketsDatabaseManager(str(tmp_path / "tickets.db"))
        await db.initialize_database()

        assert await db.get_ticket_number() == 1
        assert await db.create_ticket(
            thread_id=1001,
            message_id=2001,
            creator_id=3001,
            type_name="support",
            ticket_channel_id=4001,
            ticket_number=1,
        ) is True

        ticket = await db.fetch_ticket(1001)
        assert ticket["thread_id"] == 1001
        assert ticket["ticket_number"] == 1
        assert ticket["message_id"] == 2001
        assert ticket["is_closed"] == 0

        assert await db.check_member_exists(1001, 3001) is True
        assert await db.add_ticket_member(1001, 3002, added_by=9001) is True
        assert await db.add_ticket_member(1001, 3002, added_by=9001) is False
        members = await db.get_ticket_members(1001)
        assert {member[0] for member in members} == {3001, 3002}

        assert await db.accept_ticket(1001, accepted_by=9002) is True
        assert await db.accept_ticket(1001, accepted_by=9003) is False

        active = await db.get_active_tickets()
        assert active[0]["thread_id"] == 1001
        assert active[0]["is_accepted"] == 1

        assert await db.update_ticket_message_id(1001, 2002) is True
        assert (await db.fetch_ticket(1001))["message_id"] == 2002

        stats = await db.get_ticket_stats()
        assert stats["total"] == 1
        assert stats["active"] == 1
        assert stats["closed"] == 0
        assert stats["by_type"] == [("support", 1)]

        assert await db.close_ticket(1001, closed_by=9004, reason="done") is True
        assert await db.add_ticket_member(1001, 3003, added_by=9001) is False
        assert await db.check_ticket_status(1001) == (True, True)

        history = await db.get_ticket_history(1001)
        assert history["closed_by"] == 9004
        assert history["close_reason"] == "done"
        assert {member["user_id"] for member in history["members"]} == {3001, 3002}

        stats = await db.get_ticket_stats()
        assert stats["total"] == 1
        assert stats["active"] == 0
        assert stats["closed"] == 1
        assert await db.get_ticket_number() == 2

    run(scenario())
