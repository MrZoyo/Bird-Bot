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
