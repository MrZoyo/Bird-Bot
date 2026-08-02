import asyncio
from types import SimpleNamespace

import discord

from bot.cogs.shop.cog import ShopCog


def _http_exception(status=522):
    response = SimpleNamespace(status=status, reason="server error")
    return discord.HTTPException(response, "temporary Discord failure")


def _not_found():
    response = SimpleNamespace(status=404, reason="not found")
    return discord.NotFound(response, "missing")


class FakeMessage:
    def __init__(self, events):
        self.events = events

    async def edit(self, **kwargs):
        self.events.append(("edit", kwargs))


class FakeChannel:
    def __init__(self, events, *, fetch_exception=None):
        self.id = 10
        self.name = "checkin"
        self.events = events
        self.fetch_exception = fetch_exception
        self.message = FakeMessage(events)

    async def fetch_message(self, message_id):
        self.events.append(("fetch_message", message_id))
        if self.fetch_exception is not None:
            raise self.fetch_exception
        return self.message


class FakeBot:
    def __init__(self, channel):
        self.channel = channel

    def get_channel(self, channel_id):
        return self.channel if self.channel.id == channel_id else None

    async def fetch_channel(self, channel_id):
        return self.channel


class FakePanelDB:
    def __init__(self, events):
        self.events = events
        self.active_embeds = [{
            "id": 3,
            "channel_id": 10,
            "message_id": 20,
            "created_date": "2000-01-01",
        }]
        self.deactivated = []
        self.resets = []

    async def get_active_checkin_embeds(self):
        return self.active_embeds

    async def deactivate_checkin_embed(self, embed_id):
        self.events.append(("deactivate", embed_id))
        self.deactivated.append(embed_id)
        return True

    async def reset_daily_embed_stats(self, date_str, *, embed_id=None):
        self.events.append(("reset", date_str, embed_id))
        self.resets.append((date_str, embed_id))
        return True


def _build_cog(events, *, fetch_exception=None):
    channel = FakeChannel(events, fetch_exception=fetch_exception)
    cog = object.__new__(ShopCog)
    cog.bot = FakeBot(channel)
    cog.db = FakePanelDB(events)

    async def create_daily_checkin_view(date_str):
        events.append(("create_view", date_str))
        return SimpleNamespace(date=date_str)

    def create_checkin_image_file():
        events.append(("create_file",))
        return SimpleNamespace(filename="checkin.png")

    cog.create_daily_checkin_view = create_daily_checkin_view
    cog.create_checkin_image_file = create_checkin_image_file
    return cog


def test_transient_discord_fetch_failure_keeps_panel_active_for_retry():
    async def scenario():
        events = []
        cog = _build_cog(events, fetch_exception=_http_exception())

        await ShopCog.update_checkin_embeds_after_checkin(cog, user_id=42)

        assert events == [("fetch_message", 20)]
        assert cog.db.deactivated == []

    asyncio.run(scenario())


def test_missing_discord_message_deactivates_panel():
    async def scenario():
        events = []
        cog = _build_cog(events, fetch_exception=_not_found())

        await ShopCog.update_checkin_embeds_after_checkin(cog, user_id=42)

        assert events == [
            ("fetch_message", 20),
            ("deactivate", 3),
        ]
        assert cog.db.deactivated == [3]

    asyncio.run(scenario())


def test_daily_refresh_marks_only_panel_after_message_edit_succeeds():
    async def scenario():
        events = []
        cog = _build_cog(events)

        await ShopCog.update_daily_embeds.coro(cog)

        event_names = [event[0] for event in events]
        assert event_names == [
            "fetch_message",
            "create_view",
            "create_file",
            "edit",
            "reset",
        ]
        view_date = next(event[1] for event in events if event[0] == "create_view")
        assert cog.db.resets == [(view_date, 3)]
        assert event_names.index("edit") < event_names.index("reset")

    asyncio.run(scenario())


def test_failed_daily_refresh_does_not_advance_panel_date():
    async def scenario():
        events = []
        cog = _build_cog(events, fetch_exception=_http_exception())

        await ShopCog.update_daily_embeds.coro(cog)

        assert events == [("fetch_message", 20)]
        assert cog.db.resets == []
        assert cog.db.deactivated == []

    asyncio.run(scenario())
