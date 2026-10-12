import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest

from bot.cogs.tickets import cog as tickets_cog
from bot.cogs.tickets import views as tickets_views
from bot.cogs.tickets.cog import TicketsCog
from bot.cogs.tickets.views import TicketThreadView
from bot.utils.tickets_db import TicketsDatabaseManager


class RecoveryMessage:
    def __init__(self, message_id):
        self.id = message_id
        self.edits = []
        self.fail_edits = 0
        self.edit_started = None
        self.allow_edit = None

    async def edit(self, **payload):
        if self.edit_started is not None:
            self.edit_started.set()
            await self.allow_edit.wait()
        if self.fail_edits:
            self.fail_edits -= 1
            raise discord.HTTPException(SimpleNamespace(status=503, reason="unavailable"), "retry")
        self.edits.append(payload)


class RecoveryChannel:
    def __init__(self, channel_id, message_id, *, archived=False):
        self.id = channel_id
        self.name = f"ticket-{channel_id}"
        self.archived = archived
        self.message = RecoveryMessage(message_id)
        self.fetches = []
        self.fetch_error = None

    async def fetch_message(self, message_id):
        self.fetches.append(message_id)
        if self.fetch_error:
            raise self.fetch_error
        assert message_id == self.message.id
        return self.message


class RecoveryDB:
    def __init__(self, rows):
        self.rows = rows
        self.active_calls = 0
        self.all_calls = 0
        self.fail_active = 0

    async def get_config(self):
        return {"ticket_channel_id": 10, "main_message_id": 30}

    async def get_active_tickets(self):
        self.active_calls += 1
        if self.fail_active:
            self.fail_active -= 1
            raise RuntimeError("database temporarily unavailable")
        return [dict(row) for row in self.rows if not row["is_closed"]]

    async def get_all_tickets(self):
        self.all_calls += 1
        return [dict(row) for row in self.rows]


def ticket(thread_id, *, closed=False, accepted=False):
    return {
        "thread_id": thread_id,
        "message_id": thread_id + 1000,
        "creator_id": 123,
        "type_name": "support",
        "is_closed": int(closed),
        "is_accepted": int(accepted),
        "accepted_by": 456 if accepted else None,
    }


@pytest.fixture
def recovery(monkeypatch):
    text = {
        "tickets.messages.refresh_buttons_complete": "updated={updated}; skipped={skipped}; errors={errors}",
        "tickets.messages.refresh_buttons_starting": "total={total}",
        "tickets.messages.refresh_buttons_progress": "updated={updated}; skipped={skipped}; errors={errors}",
    }
    translate = lambda key, **kwargs: text.get(key, key.rsplit(".", 1)[-1])
    monkeypatch.setattr(tickets_cog, "t", translate)
    monkeypatch.setattr(tickets_views, "t", translate)
    real_sleep = asyncio.sleep

    def build(rows, db=None):
        db = db if db is not None else RecoveryDB(rows)
        channels = {10: RecoveryChannel(10, 30)}
        channels.update({row["thread_id"]: RecoveryChannel(row["thread_id"], row["message_id"]) for row in rows})
        bot = SimpleNamespace(user=SimpleNamespace(id=999, avatar=None), views=[], lookups=[])

        def get_channel(channel_id):
            bot.lookups.append(channel_id)
            return channels.get(channel_id)

        def add_view(view, **kwargs):
            bot.views.append((view, kwargs))

        bot.get_channel = get_channel
        bot.add_view = add_view
        monkeypatch.setattr(tickets_cog, "Config", lambda: SimpleNamespace(get_config=lambda name: {"db_path": "unused"}))
        monkeypatch.setattr(tickets_cog, "TicketsDatabaseManager", lambda path: db)
        cog = TicketsCog(bot)
        cog.ticket_types = {"support": {"description": "Support", "button_color": "b"}}
        cog.check_and_close_missing_tickets = AsyncMock()
        sleeps = []

        async def record_sleep(delay):
            sleeps.append(delay)
            await real_sleep(0)

        monkeypatch.setattr(tickets_cog.asyncio, "sleep", record_sleep)
        return SimpleNamespace(cog=cog, db=db, channels=channels, bot=bot, sleeps=sleeps)

    return build


def test_startup_filters_closed_database_rows_before_batching(recovery, tmp_path):
    async def scenario():
        rows = [ticket(100 + i, closed=i >= 2, accepted=i == 1) for i in range(10)]
        db = TicketsDatabaseManager(str(tmp_path / "tickets.db"))
        await db.initialize_database()
        await db.set_config(10, 20, 30)
        for row in rows:
            await db.create_ticket(row["thread_id"], row["message_id"], 123, "support", 10, row["thread_id"])
            if row["is_accepted"]:
                await db.accept_ticket(row["thread_id"], 456)
            if row["is_closed"]:
                await db.close_ticket(row["thread_id"], 456, "done")
        h = recovery(rows, db)
        await h.cog.on_ready()

        assert h.sleeps == []
        for row in rows:
            channel = h.channels[row["thread_id"]]
            if row["is_closed"]:
                assert channel.fetches == []
                assert row["thread_id"] not in h.bot.lookups
            else:
                assert channel.fetches == [row["message_id"]]
                view = channel.message.edits[0]["view"]
                assert view.children[0].disabled is bool(row["is_accepted"])
                assert all(not child.disabled for child in view.children[1:])

    asyncio.run(scenario())


def test_all_closed_history_does_not_fetch_tickets_or_sleep(recovery):
    async def scenario():
        rows = [ticket(100 + i, closed=True) for i in range(9)]
        h = recovery(rows)
        await h.cog.on_ready()
        await h.cog.on_ready()

        assert h.sleeps == []
        assert all(not h.channels[row["thread_id"]].fetches for row in rows)
        assert len(h.channels[10].message.edits) == 1
        assert h.db.active_calls == 1

    asyncio.run(scenario())


def test_repeated_ready_does_not_repeat_successful_recovery(recovery):
    async def scenario():
        h = recovery([ticket(100), ticket(101, accepted=True)])
        await h.cog.on_ready()
        first_views = len(h.bot.views)
        await h.cog.on_ready()

        assert h.db.active_calls == 1
        assert len(h.bot.views) == first_views
        assert all(len(channel.fetches) == 1 for channel in h.channels.values())
        h.cog.check_and_close_missing_tickets.assert_awaited_once()

    asyncio.run(scenario())


def test_concurrent_ready_serializes_recovery(recovery):
    async def scenario():
        h = recovery([ticket(100)])
        main = h.channels[10].message
        main.edit_started = asyncio.Event()
        main.allow_edit = asyncio.Event()
        first = asyncio.create_task(h.cog.on_ready())
        await asyncio.wait_for(main.edit_started.wait(), timeout=2)
        second = asyncio.create_task(h.cog.on_ready())
        main.allow_edit.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=2)

        assert h.db.active_calls == 1
        assert all(len(channel.fetches) == 1 for channel in h.channels.values())
        assert len(main.edits) == 1
        h.cog.check_and_close_missing_tickets.assert_awaited_once()

    asyncio.run(scenario())


def test_later_ready_retries_failed_ticket_without_reediting_successes(recovery, caplog):
    caplog.set_level(logging.INFO)

    async def scenario():
        h = recovery([ticket(100), ticket(101)])
        h.channels[101].message.fail_edits = 1
        await h.cog.on_ready()
        assert len(h.channels[100].message.edits) == 1
        assert h.channels[101].message.edits == []
        await h.cog.on_ready()
        await h.cog.on_ready()

        assert h.channels[100].fetches == [1100]
        assert h.channels[101].fetches == [1101, 1101]
        assert len(h.channels[101].message.edits) == 1
        assert len(h.channels[10].fetches) == 1
        assert h.db.active_calls == 2
        summaries = [record.getMessage() for record in caplog.records if "Ticket view recovery:" in record.getMessage()]
        assert summaries == [
            "TicketsCog: Ticket view recovery: open=2, pending=2, registered=2, updated=1, skipped=0, failed=1, complete=False",
            "TicketsCog: Ticket view recovery: open=2, pending=1, registered=1, updated=1, skipped=0, failed=0, complete=True",
        ]

    asyncio.run(scenario())


def test_later_ready_retries_main_message_without_reediting_tickets(recovery):
    async def scenario():
        h = recovery([ticket(100)])
        h.channels[10].message.fail_edits = 1
        await h.cog.on_ready()
        await h.cog.on_ready()
        await h.cog.on_ready()

        assert h.channels[10].fetches == [30, 30]
        assert len(h.channels[10].message.edits) == 1
        assert h.channels[100].fetches == [1100]

    asyncio.run(scenario())


def test_database_failure_leaves_recovery_retryable(recovery):
    async def scenario():
        h = recovery([ticket(100)])
        h.db.fail_active = 1
        await h.cog.on_ready()
        assert h.channels[100].fetches == []
        await h.cog.on_ready()
        await h.cog.on_ready()

        assert h.db.active_calls == 2
        assert h.channels[100].fetches == [1100]
        assert h.channels[10].fetches == [30]

    asyncio.run(scenario())


def test_missing_cached_ticket_retries_when_channel_becomes_available(recovery):
    async def scenario():
        h = recovery([ticket(100), ticket(101)])
        missing_channel = h.channels.pop(101)
        await h.cog.on_ready()
        h.channels[101] = missing_channel
        await h.cog.on_ready()
        await h.cog.on_ready()

        assert h.db.active_calls == 2
        assert h.channels[100].fetches == [1100]
        assert missing_channel.fetches == [1101]
        assert h.channels[10].fetches == [30]

    asyncio.run(scenario())


def test_archived_open_ticket_does_not_prevent_recovery_completion(recovery):
    async def scenario():
        h = recovery([ticket(100), ticket(101)])
        h.channels[101].archived = True
        await h.cog.on_ready()
        await h.cog.on_ready()

        assert h.db.active_calls == 1
        assert h.channels[100].fetches == [1100]
        assert h.channels[101].fetches == []

    asyncio.run(scenario())


def test_manual_refresh_includes_closed_and_disables_all_their_buttons(recovery):
    async def scenario():
        h = recovery([ticket(100), ticket(101, closed=True), ticket(102, closed=True)])
        h.channels[102].archived = True
        h.cog.is_admin_for_type = AsyncMock(return_value=True)
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=456),
            response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
            edit_original_response=AsyncMock(),
        )
        await TicketsCog.refresh_buttons_command.callback(h.cog, interaction)

        assert h.db.all_calls == 1
        assert h.db.active_calls == 0
        assert h.channels[100].fetches == [1100]
        assert h.channels[101].fetches == [1101]
        closed_view = h.channels[101].message.edits[0]["view"]
        assert all(child.disabled for child in closed_view.children)
        assert h.channels[102].fetches == []
        interaction.followup.send.assert_awaited_once_with("updated=2; skipped=1; errors=0", ephemeral=True)

    asyncio.run(scenario())


def test_manual_refresh_reports_failed_edits_as_errors(recovery):
    async def scenario():
        h = recovery([ticket(100), ticket(101)])
        h.channels[101].message.fail_edits = 1
        h.cog.is_admin_for_type = AsyncMock(return_value=True)
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=456),
            response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
            edit_original_response=AsyncMock(),
        )
        await TicketsCog.refresh_buttons_command.callback(h.cog, interaction)

        interaction.followup.send.assert_awaited_once_with("updated=1; skipped=0; errors=1", ephemeral=True)

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["success", "no_id", "not_found", "http_error", "unexpected_error"])
def test_ticket_message_update_reports_actual_success(recovery, outcome):
    async def scenario():
        row = ticket(100)
        h = recovery([row])
        channel = h.channels[100]
        if outcome == "no_id":
            row["message_id"] = None
        elif outcome == "not_found":
            channel.fetch_error = discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "missing")
        elif outcome == "http_error":
            channel.message.fail_edits = 1
        elif outcome == "unexpected_error":
            channel.fetch_error = RuntimeError("unexpected fetch failure")
        view = TicketThreadView(h.cog, 100, "support")
        result = await h.cog.update_ticket_message_buttons(channel, row, view)

        assert result is (outcome == "success")
        assert len(channel.message.edits) == int(outcome == "success")

    asyncio.run(scenario())
