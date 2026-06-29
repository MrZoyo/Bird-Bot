import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import discord

from bot.cogs.giveaway import cog as giveaway_cog
from bot.cogs.giveaway import modals as giveaway_modals
from bot.cogs.giveaway import views as giveaway_views
from bot.cogs.giveaway.cog import GiveawayCog
from bot.cogs.giveaway.modals import GiveawayDraftState, GiveawayDraftView
from bot.cogs.giveaway.views import GiveawayPanelView, GiveawayParticipationView


GIVEAWAY_TEXT = {
    "giveaway.giveaway_join_button_label": "Join",
    "giveaway.giveaway_exit_button_label": "Exit",
    "giveaway.giveaway_already_joined_message": "already joined",
    "giveaway.giveaway_joined_message": "joined",
    "giveaway.giveaway_leave_message": "left",
    "giveaway.giveaway_not_access_message": "not eligible",
    "giveaway.giveaway_default_provider": "Default Provider",
    "giveaway.giveaway_embed_title_open": "Giveaway: {prizes}",
    "giveaway.giveaway_embed_end_label": "[ENDED] ",
    "giveaway.giveaway_embed_cancel_label": "[CANCEL] ",
    "giveaway.giveaway_embed_earlyend_label": "[EARLY] ",
    "giveaway.giveaway_embed_provider_title": "Provider",
    "giveaway.giveaway_embed_timeend_title": "Ends",
    "giveaway.giveaway_embed_winner_number_title": "Winners",
    "giveaway.giveaway_embed_participants_title": "Participants",
    "giveaway.giveaway_embed_participants_text": "in progress",
    "giveaway.giveaway_embed_description_title": "Description",
    "giveaway.giveaway_embed_footer": "ID {giveaway_id}",
    "giveaway.giveaway_embed_winner_title": "Winner list",
    "giveaway.giveaway_requirement_title": "Requirements",
    "giveaway.giveaway_requirement_text": "r={reaction_req}; m={message_req}; t={timespent_req}",
    "giveaway.giveaway_no_requirement_text": "none",
    "giveaway.giveaway_duration_label": "Duration",
    "giveaway.giveaway_winners_label": "Winners",
    "giveaway.giveaway_provider_label": "Provider",
    "giveaway.giveaway_description_default": "No description",
    "giveaway.giveaway_draft_edit_button": "Edit",
    "giveaway.giveaway_draft_limits_button": "Limits",
    "giveaway.giveaway_draft_image_button": "Image",
    "giveaway.giveaway_draft_publish_button": "Publish",
    "giveaway.giveaway_draft_owner_only_message": "owner only",
    "giveaway.giveaway_draft_no_image": "no image",
    "giveaway.giveaway_draft_title": "Draft",
    "giveaway.giveaway_draft_prizes_title": "Prize",
    "giveaway.giveaway_draft_missing_value": "missing",
    "giveaway.giveaway_draft_image_title": "Image",
    "giveaway.giveaway_already_published_message": "already published",
    "giveaway.giveaway_draft_missing_basic_message": "missing basic",
    "giveaway.giveaway_channel_missing_message": "missing channel",
    "giveaway.giveaway_published_title": "Published",
    "giveaway.giveaway_published_message": "published {giveaway_id}",
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

    async def defer(self, *, ephemeral=False, **kwargs):
        self._done = True
        self.events.append(("defer", ephemeral, kwargs))

    async def edit_message(self, *, content=None, view=None, **kwargs):
        self._done = True
        self.events.append(("edit_message", content, type(view).__name__ if view else None))
        self.messages.append({
            "content": content,
            "view": view,
            **kwargs,
        })


class FakeInteraction:
    def __init__(self, user, events):
        self.user = user
        self.response = FakeResponse(events)
        self.followup = FakeFollowup(events)
        self.edits = []

    async def edit_original_response(self, **kwargs):
        self.edits.append(kwargs)


@dataclass
class FakeUser:
    id: int
    display_name: str
    name: str
    mention: str


class FakeFollowup:
    def __init__(self, events):
        self.events = events
        self.messages = []

    async def send(self, content=None, *, ephemeral=False, **kwargs):
        self.events.append(("followup", content, ephemeral))
        self.messages.append({
            "content": content,
            "ephemeral": ephemeral,
            **kwargs,
        })


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


class FakePublishChannel:
    def __init__(self, channel_id, events):
        self.id = channel_id
        self.events = events
        self.send_kwargs = None

    async def send(self, **kwargs):
        self.events.append(("channel_send", kwargs))
        self.send_kwargs = kwargs
        return SimpleNamespace(id=901, attachments=[])


class FakeBot:
    def __init__(self, *, channel=None, cog=None):
        self.user = SimpleNamespace(avatar=SimpleNamespace(url="https://example.com/bot.png"))
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


class FakeDraftDB:
    def __init__(self):
        self.insert_args = None
        self.insert_kwargs = None

    async def fetch_all_giveaway_ids(self):
        return []

    async def insert_giveaway(self, *args, **kwargs):
        self.insert_args = args
        self.insert_kwargs = kwargs


class FakeDraftCog:
    def __init__(self):
        self.giveaways = {}
        self.saved = []

    async def save_giveaways(self, giveaway_id, view):
        self.saved.append((giveaway_id, view))


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


def _fake_t(key, **kwargs):
    value = GIVEAWAY_TEXT[key]
    return value.format_map(kwargs) if kwargs else value


def _build_participation_view(monkeypatch, events, fake_cog):
    _install_view_config(monkeypatch)
    message = FakeMessage(900, events)
    channel = FakeChannel(10, message, events)
    bot = FakeBot(channel=channel, cog=fake_cog)
    view = GiveawayParticipationView(bot, "ga-1", channel.id)
    view.message_id = message.id
    return view, message


def _walk_components(components):
    for component in components:
        yield component
        yield from _walk_components(component.get("components") or [])
        if component.get("accessory"):
            yield from _walk_components([component["accessory"]])


def test_giveaway_panel_uses_embed_image_and_disabled_button(monkeypatch):
    _install_view_config(monkeypatch)
    bot = FakeBot()
    record = {
        "giveaway_id": "ga-1",
        "starttime": "2026-06-29T12:00:00",
        "duration": 60,
        "winner_number": 2,
        "prizes": "Prize",
        "description": "Desc",
        "reaction_req": 1,
        "message_req": 2,
        "timespent_req": 180,
        "provider": "Provider",
        "image_url": "https://example.com/prize.png",
    }

    view = GiveawayPanelView(
        bot,
        "ga-1",
        10,
        record=record,
        participant_count=3,
        status="cancelled",
        disabled=True,
    )
    components = view.to_components()
    button = next(component for component in _walk_components(components) if component["type"] == 2)
    embed = view.format_embed()

    assert components[0]["type"] == 1
    assert embed.title == "[CANCEL] Giveaway: Prize"
    assert embed.description is None
    assert embed.color == discord.Color.orange()
    assert [field.name for field in embed.fields[:4]] == [
        "Provider",
        "Ends",
        "Winners",
        "Participants",
    ]
    assert embed.fields[0].inline is False
    assert embed.fields[0].value == "Provider"
    assert embed.fields[1].inline is True
    assert embed.fields[2].value == "2"
    assert embed.fields[3].value == "3"
    assert embed.fields[4].name == "Requirements"
    assert embed.fields[5].name == "Description"
    assert embed.image.url == "https://example.com/prize.png"
    assert embed.thumbnail.url == "https://example.com/bot.png"
    assert button["custom_id"] == "participate_ga-1"
    assert button["disabled"] is True


def test_giveaway_panel_uses_legacy_empty_participant_text(monkeypatch):
    _install_view_config(monkeypatch)
    bot = FakeBot()
    record = {
        "giveaway_id": "ga-1",
        "starttime": "2026-06-29T12:00:00",
        "duration": 60,
        "winner_number": 1,
        "prizes": "Prize",
        "description": "",
        "reaction_req": 0,
        "message_req": 0,
        "timespent_req": 0,
        "provider": "Provider",
    }

    view = GiveawayPanelView(
        bot,
        "ga-1",
        10,
        record=record,
        participant_count=0,
    )
    embed = view.format_embed()

    assert embed.fields[3].name == "Participants"
    assert embed.fields[3].value == "in progress"


def test_giveaway_panel_keeps_image_for_ended_state_from_attachment_filename(monkeypatch):
    _install_view_config(monkeypatch)
    bot = FakeBot()
    record = {
        "giveaway_id": "ga-1",
        "starttime": "2026-06-29T12:00:00",
        "duration": 60,
        "winner_number": 1,
        "prizes": "Prize",
        "description": "",
        "reaction_req": 0,
        "message_req": 0,
        "timespent_req": 0,
        "provider": "Provider",
        "image_url": None,
        "image_filename": "prize.png",
    }

    view = GiveawayPanelView(
        bot,
        "ga-1",
        10,
        record=record,
        participant_count=2,
        status="ended",
        winners=["<@101>"],
        disabled=True,
    )
    embed = view.format_embed()

    assert embed.image.url == "attachment://prize.png"
    assert embed.title == "[ENDED] Giveaway: Prize"


def test_giveaway_draft_uses_embed_panel(monkeypatch):
    _install_view_config(monkeypatch)
    monkeypatch.setattr(giveaway_modals, "t", _fake_t)
    state = GiveawayDraftState(
        creator_id=123,
        giveaway_channel_id=10,
        default_provider="Default Provider",
        duration_text="30m",
        duration_minutes=30,
        winner_number=1,
        prizes="Prize",
        description="Desc",
        image_filename="prize.png",
    )

    view = GiveawayDraftView(FakeBot(), FakeDraftDB(), state)
    components = view.to_components()
    embed = view.format_embed()

    assert components[0]["type"] == 1
    assert embed.title == "Draft"
    assert [field.name for field in embed.fields[:4]] == [
        "Prize",
        "Duration",
        "Provider",
        "Winners",
    ]
    assert embed.fields[0].inline is False
    assert embed.fields[0].value == "Prize"
    assert embed.fields[1].value == "30m"
    assert embed.fields[-1].name == "Image"
    assert embed.fields[-1].value == "prize.png"


def test_giveaway_draft_publish_sends_v2_panel_and_persists(monkeypatch):
    async def scenario():
        _install_view_config(monkeypatch)
        monkeypatch.setattr(giveaway_modals, "t", _fake_t)
        events = []
        channel = FakePublishChannel(10, events)
        cog = FakeDraftCog()
        bot = FakeBot(channel=channel, cog=cog)
        db = FakeDraftDB()
        state = GiveawayDraftState(
            creator_id=123,
            giveaway_channel_id=10,
            default_provider="Default Provider",
            duration_text="30m",
            duration_minutes=30,
            winner_number=1,
            prizes="Prize",
            description="Desc",
        )
        view = GiveawayDraftView(bot, db, state)
        interaction = FakeInteraction(FakeUser(123, "User", "user", "<@123>"), events)

        await view.publish(interaction)

        assert events[0] == ("defer", False, {})
        assert channel.send_kwargs["embed"].title == "Giveaway: Prize"
        assert channel.send_kwargs["view"].to_components()[0]["type"] == 1
        assert db.insert_args[0] == cog.saved[0][0]
        assert db.insert_args[4] == 1
        assert db.insert_args[5] == "Prize"
        assert db.insert_kwargs["provider"] == "Default Provider"
        assert db.insert_kwargs["ui_version"] == 2
        assert cog.giveaways[db.insert_args[0]].message_id == 901
        assert interaction.edits[0]["content"] is None
        assert interaction.edits[0]["embed"].title == "Published"
        assert interaction.edits[0]["view"].to_components() == []

    asyncio.run(scenario())


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
        assert message.edits[0]["embed"].fields[0].value == "in progress"

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

        async def check_channel_validity(interaction, *args, **kwargs):
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
        assert interaction.response.messages[0]["ephemeral"] is False

    asyncio.run(scenario())


def test_end_giveaway_draws_notifies_updates_db_then_disables_message(monkeypatch):
    async def scenario():
        _install_view_config(monkeypatch)

        async def check_channel_validity(interaction, *args, **kwargs):
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
