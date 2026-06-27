import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import discord

from bot.cogs.giveaway import cog as giveaway_cog
from bot.cogs.giveaway import views as giveaway_views
from bot.cogs.giveaway.cog import GiveawayCog
from bot.cogs.giveaway.views import GiveawayParticipationView


GIVEAWAY_TEXT = {
    "giveaway.giveaway_join_button_label": "Join",
    "giveaway.giveaway_exit_button_label": "Exit",
    "giveaway.giveaway_already_joined_message": "already joined",
    "giveaway.giveaway_joined_message": "joined",
    "giveaway.giveaway_leave_message": "left",
    "giveaway.giveaway_not_access_message": "not eligible",
    "giveaway.giveaway_embed_participants_title": "Participants",
    "giveaway.giveaway_end_message": "ended",
}


class FakeResponse:
    def __init__(self, events):
        self.events = events
        self.messages = []
        self._done = False

    def is_done(self):
        return self._done

    async def send_message(self, content=None, *, embed=None, view=None, ephemeral=False, **kwargs):
        self._done = True
        self.events.append(("response", content or (embed.title if embed else None)))
        self.messages.append({
            "content": content,
            "embed": embed,
            "view": view,
            "ephemeral": ephemeral,
            **kwargs,
        })


class FakeInteraction:
    def __init__(self, user, events):
        self.user = user
        self.response = FakeResponse(events)


@dataclass
class FakeUser:
    id: int
    display_name: str
    name: str
    mention: str


class FakeMessage:
    def __init__(self, message_id, events):
        self.id = message_id
        self.events = events
        self.embeds = [discord.Embed(title="Giveaway", color=discord.Color.blue())]
        self.embeds[0].add_field(name="Participants", value="0", inline=True)
        self.edits = []

    async def edit(self, *, embed=None, view=None, **kwargs):
        self.events.append(("message_edit", embed.title if embed else None, type(view).__name__))
        self.edits.append({
            "embed": embed,
            "view": view,
            **kwargs,
        })


class FakeChannel:
    def __init__(self, channel_id, message, events):
        self.id = channel_id
        self.message = message
        self.events = events

    async def fetch_message(self, message_id):
        self.events.append(("fetch_message", self.id, message_id))
        return self.message


class FakeBot:
    def __init__(self, *, channel=None, cog=None):
        self.user = SimpleNamespace(avatar=None)
        self.channel = channel
        self.cog = cog

    def get_channel(self, channel_id):
        if self.channel and channel_id == self.channel.id:
            return self.channel
        return None

    def get_cog(self, name):
        if name == "GiveawayCog":
            return self.cog
        return None


class FakeGiveawayCog:
    def __init__(self, events, *, joined=False, eligible=True, participant_count=0):
        self.events = events
        self.joined = joined
        self.eligible = eligible
        self.participant_count = participant_count
        self.added = []
        self.removed = []

    async def is_participant(self, giveaway_id, participant_id):
        self.events.append(("is_participant", giveaway_id, participant_id))
        return self.joined

    async def check_participant_eligibility(self, giveaway_id, participant_id, interaction):
        self.events.append(("eligibility", giveaway_id, participant_id))
        return self.eligible

    async def add_participant_to_giveaway(self, giveaway_id, participant_id, interaction):
        self.events.append(("add_participant", giveaway_id, participant_id))
        self.added.append((giveaway_id, participant_id))

    async def remove_participant_from_giveaway(self, giveaway_id, participant_id):
        self.events.append(("remove_participant", giveaway_id, participant_id))
        self.removed.append((giveaway_id, participant_id))

    async def get_participant_count(self, giveaway_id):
        self.events.append(("participant_count", giveaway_id))
        return self.participant_count

    async def fetch_giveaway(self, giveaway_id):
        self.events.append(("fetch_giveaway", giveaway_id))
        return {"is_end": False}


def _install_view_config(monkeypatch):
    monkeypatch.setattr(giveaway_views, "t", lambda key: GIVEAWAY_TEXT[key])
    monkeypatch.setattr(
        giveaway_views.config,
        "get_config",
        lambda name=None: {"giveaway_channel_id": 10},
    )


def _build_participation_view(monkeypatch, events, fake_cog):
    _install_view_config(monkeypatch)
    message = FakeMessage(900, events)
    channel = FakeChannel(10, message, events)
    bot = FakeBot(channel=channel, cog=fake_cog)
    view = GiveawayParticipationView(bot, "ga-1", channel.id)
    view.message_id = message.id
    return view, message


def test_giveaway_participate_adds_user_then_updates_participant_embed(monkeypatch):
    async def scenario():
        events = []
        fake_cog = FakeGiveawayCog(events, joined=False, eligible=True, participant_count=1)
        view, message = _build_participation_view(monkeypatch, events, fake_cog)
        interaction = FakeInteraction(FakeUser(123, "User", "user", "<@123>"), events)

        await view.participate(interaction)

        event_names = [event[0] for event in events]
        assert event_names == [
            "is_participant",
            "eligibility",
            "add_participant",
            "response",
            "fetch_message",
            "participant_count",
            "message_edit",
        ]
        assert fake_cog.added == [("ga-1", 123)]
        assert interaction.response.messages[0]["content"] == "joined"
        assert interaction.response.messages[0]["ephemeral"] is True
        assert message.edits[0]["embed"].fields[0].value == "1"

    asyncio.run(scenario())


def test_giveaway_exit_removes_user_before_response_and_embed_refresh(monkeypatch):
    async def scenario():
        events = []
        fake_cog = FakeGiveawayCog(events, joined=True, participant_count=0)
        view, message = _build_participation_view(monkeypatch, events, fake_cog)
        interaction = FakeInteraction(FakeUser(123, "User", "user", "<@123>"), events)

        await view.exit(interaction)

        event_names = [event[0] for event in events]
        assert event_names == [
            "fetch_giveaway",
            "is_participant",
            "remove_participant",
            "response",
            "fetch_message",
            "participant_count",
            "message_edit",
        ]
        assert fake_cog.removed == [("ga-1", 123)]
        assert interaction.response.messages[0]["content"] == "left"
        assert interaction.response.messages[0]["ephemeral"] is True
        assert message.edits[0]["embed"].fields[0].value == "0"

    asyncio.run(scenario())


def _build_command_cog(events, giveaway_details):
    cog = object.__new__(GiveawayCog)
    cog.giveaway_channel_id = 10
    cog.giveaway_embed_cancel_label = "[CANCEL] "
    cog.giveaway_embed_earlyend_label = "[END] "
    cog.giveaway_embed_winner_title = "Winners"
    cog.giveaway_embed_no_winner = "No winner"
    message = FakeMessage(giveaway_details["message_id"], events)
    channel = FakeChannel(10, message, events)
    cog.bot = FakeBot(channel=channel, cog=cog)

    async def fetch_giveaway(giveaway_id):
        events.append(("fetch_giveaway", giveaway_id))
        return giveaway_details

    async def mark_giveaway_as_ended(giveaway_id):
        events.append(("mark_ended", giveaway_id))

    async def draw_winners(giveaway_id, winner_number):
        events.append(("draw_winners", giveaway_id, winner_number))
        return [101]

    async def notify_winners(winners, prizes, giveaway_id):
        events.append(("notify_winners", winners, prizes, giveaway_id))

    async def update_giveaway(giveaway_id, winners):
        events.append(("update_giveaway", giveaway_id, winners))

    cog.fetch_giveaway = fetch_giveaway
    cog.mark_giveaway_as_ended = mark_giveaway_as_ended
    cog.draw_winners = draw_winners
    cog.notify_winners = notify_winners
    cog.update_giveaway = update_giveaway
    return cog, message


def test_cancel_giveaway_marks_ended_before_disabling_message(monkeypatch):
    async def scenario():
        _install_view_config(monkeypatch)

        async def check_channel_validity(interaction):
            return True

        monkeypatch.setattr(giveaway_cog, "check_channel_validity", check_channel_validity)
        events = []
        cog, message = _build_command_cog(events, {
            "message_id": 900,
            "is_end": False,
        })
        interaction = FakeInteraction(FakeUser(1, "Admin", "admin", "<@1>"), events)

        await GiveawayCog.cancel_giveaway.callback(cog, interaction, "ga-1")

        event_names = [event[0] for event in events]
        assert event_names == [
            "fetch_giveaway",
            "mark_ended",
            "fetch_message",
            "message_edit",
            "response",
        ]
        assert message.edits[0]["embed"].title == "[CANCEL] Giveaway"
        assert all(child.disabled for child in message.edits[0]["view"].children)
        assert interaction.response.messages[0]["content"] == "Giveaway ga-1 has been cancelled."
        assert interaction.response.messages[0]["ephemeral"] is True

    asyncio.run(scenario())


def test_end_giveaway_draws_notifies_updates_db_then_disables_message(monkeypatch):
    async def scenario():
        _install_view_config(monkeypatch)

        async def check_channel_validity(interaction):
            return True

        monkeypatch.setattr(giveaway_cog, "check_channel_validity", check_channel_validity)
        events = []
        cog, message = _build_command_cog(events, {
            "message_id": 900,
            "winner_number": 1,
            "prizes": "Prize",
            "is_end": False,
        })
        interaction = FakeInteraction(FakeUser(1, "Admin", "admin", "<@1>"), events)

        await GiveawayCog.end_giveaway.callback(cog, interaction, "ga-1")

        event_names = [event[0] for event in events]
        assert event_names == [
            "fetch_giveaway",
            "draw_winners",
            "notify_winners",
            "update_giveaway",
            "fetch_message",
            "message_edit",
            "response",
        ]
        assert events[3] == ("update_giveaway", "ga-1", [101])
        assert message.edits[0]["embed"].title == "[END] Giveaway"
        assert message.edits[0]["embed"].fields[-1].name == "Winners"
        assert message.edits[0]["embed"].fields[-1].value == "<@101>"
        assert all(child.disabled for child in message.edits[0]["view"].children)
        assert interaction.response.messages[0]["content"] == "Giveaway ga-1 has been ended early."

    asyncio.run(scenario())
