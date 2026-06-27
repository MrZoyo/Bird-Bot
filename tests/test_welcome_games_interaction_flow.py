import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

from bot.cogs.games.dnd import cog as dnd_cog
from bot.cogs.games.dnd.cog import DnDCog
from bot.cogs.games.spymode import views as spymode_views
from bot.cogs.games.spymode.views import SpyModeView
from bot.cogs.welcome import cog as welcome_cog
from bot.cogs.welcome import views as welcome_views
from bot.cogs.welcome.cog import WelcomeCog


WELCOME_TEXT = {
    "welcome.dm.description0_title": "Welcome",
    "welcome.dm.description1_title": "Intro",
    "welcome.dm.description1": "hi {user}",
    "welcome.dm.description2_title": "Info",
    "welcome.dm.description2": "read this",
    "welcome.dm.rules_title": "Rules",
    "welcome.dm.rules_text": "rules",
    "welcome.dm.footer": "footer",
    "welcome.dm.member_count_button": "Members {member_count}",
}

SPYMODE_TEXT = {
    "spymode.blue_team_button_label": "Blue",
    "spymode.red_team_button_label": "Red",
    "spymode.random_button_label": "Random",
    "spymode.result_button_label": "Result",
    "spymode.spymode_wrong_channel_message": "wrong channel",
    "spymode.full_team_message": "full",
    "spymode.spymode_wrong_user_message": "wrong user",
    "spymode.spymode_wrong_start_message": "wrong start",
    "spymode.spymode_embed_title": "Game {game_id}",
    "spymode.spymode_embed_start_title": "Started {game_id}",
    "spymode.spymode_embed_end_title": "Ended {game_id}",
    "spymode.spymode_embed_saved_title": "Saved {game_id}",
    "spymode.spymode_gameinfo": "{name} {team_size} {spy}",
    "spymode.blue_team_name": "Blue {team_size}",
    "spymode.red_team_name": "Red {team_size}",
    "spymode.spymode_embed_footer": "footer",
    "spymode.blue_team_result": "Blue spies",
    "spymode.red_team_result": "Red spies",
    "spymode.you_are_spy": "spy",
    "spymode.you_are_not_spy": "not spy",
}


def _translate(mapping):
    def translator(key, **kwargs):
        text = mapping[key]
        return text.format(**kwargs) if kwargs else text

    return translator


class FakeResponse:
    def __init__(self, events):
        self.events = events
        self.messages = []
        self.deferred = []

    async def defer(self, *, ephemeral=False, **kwargs):
        self.events.append(("defer", ephemeral))
        self.deferred.append({"ephemeral": ephemeral, **kwargs})

    async def send_message(self, content=None, *, ephemeral=False, **kwargs):
        self.events.append(("response", content))
        self.messages.append({
            "content": content,
            "ephemeral": ephemeral,
            **kwargs,
        })


class FakeFollowup:
    def __init__(self, events):
        self.events = events
        self.messages = []

    async def send(self, content=None, *, embed=None, view=None, ephemeral=False, **kwargs):
        self.events.append(("followup", content or (embed.title if embed else None)))
        self.messages.append({
            "content": content,
            "embed": embed,
            "view": view,
            "ephemeral": ephemeral,
            **kwargs,
        })


class FakeInteraction:
    def __init__(self, *, user, message=None, events):
        self.user = user
        self.message = message
        self.response = FakeResponse(events)
        self.followup = FakeFollowup(events)


class FakeEditableMessage:
    def __init__(self, events):
        self.events = events
        self.edits = []

    async def edit(self, *, embed=None, view=None, **kwargs):
        self.events.append(("message_edit", embed.title if embed else None, type(view).__name__))
        self.edits.append({
            "embed": embed,
            "view": view,
            **kwargs,
        })


@dataclass
class FakeSpyUser:
    id: int
    display_name: str
    name: str
    mention: str
    voice: object
    dms: list = field(default_factory=list)

    async def send(self, content=None, *, embed=None, **kwargs):
        self.dms.append({
            "content": content,
            "embed": embed,
            **kwargs,
        })


def test_welcome_dm_builds_embed_and_member_count_view(monkeypatch):
    async def scenario():
        monkeypatch.setattr(welcome_cog, "t", _translate(WELCOME_TEXT))
        monkeypatch.setattr(welcome_views, "t", _translate(WELCOME_TEXT))
        cog = object.__new__(WelcomeCog)
        cog.bot = SimpleNamespace(user=SimpleNamespace(avatar=None))
        cog.dm_config = {
            "color": [1, 2, 3],
            "rules_channel_id": 777,
        }
        cog.welcome_dm_image = "/tmp/does-not-exist-welcome-dm.png"
        rules_channel = SimpleNamespace(id=777, mention="<#777>")
        guild = SimpleNamespace(
            member_count=42,
            get_channel=lambda channel_id: rules_channel if channel_id == 777 else None,
        )
        sent_messages = []
        member = SimpleNamespace(
            id=123,
            display_name="User",
            name="user",
            mention="<@123>",
            display_avatar=SimpleNamespace(url="https://example.com/avatar.png"),
            guild=guild,
            send=lambda **kwargs: sent_messages.append(kwargs),
        )

        async def send(**kwargs):
            sent_messages.append(kwargs)

        member.send = send

        await cog.send_welcome_dm(member)

        assert len(sent_messages) == 1
        embed = sent_messages[0]["embed"]
        view = sent_messages[0]["view"]
        assert embed.author.name == "Welcome"
        assert embed.fields[0].value == "hi <@123>"
        assert embed.fields[-1].value == "rules\n<#777>"
        assert view.children[0].label == "Members 42"
        assert view.children[0].disabled is True

    asyncio.run(scenario())


def test_spymode_join_buttons_then_random_button_send_spy_dms(monkeypatch):
    async def scenario():
        monkeypatch.setattr(spymode_views, "t", _translate(SPYMODE_TEXT))
        monkeypatch.setattr(spymode_views.random, "sample", lambda seq, count: list(seq)[:count])
        events = []
        voice_channel = SimpleNamespace(id=10, name="voice")
        voice_state = SimpleNamespace(channel=voice_channel)
        command_user = FakeSpyUser(1, "BlueUser", "blue", "<@1>", voice_state)
        red_user = FakeSpyUser(2, "RedUser", "red", "<@2>", voice_state)
        message = FakeEditableMessage(events)
        view = SpyModeView(
            bot=SimpleNamespace(),
            team_size=1,
            spy=1,
            command_user=command_user,
            voice_channel=voice_channel,
            game_id=12345,
        )

        await view.join_blue_team(
            FakeInteraction(user=command_user, message=message, events=events),
            view.children[0],
        )
        await view.join_red_team(
            FakeInteraction(user=red_user, message=message, events=events),
            view.children[1],
        )
        await view.random_spy(
            FakeInteraction(user=command_user, message=message, events=events),
            view.children[2],
        )

        event_names = [event[0] for event in events]
        assert event_names == [
            "defer",
            "message_edit",
            "defer",
            "message_edit",
            "defer",
            "message_edit",
        ]
        assert view.blue_team == [command_user]
        assert view.red_team == [red_user]
        assert view.spies == [command_user, red_user]
        assert command_user.dms[0]["content"] == "spy"
        assert red_user.dms[0]["content"] == "spy"
        assert view.children[0].disabled is True
        assert view.children[1].disabled is True
        assert view.children[2].label == "Result"

    asyncio.run(scenario())


def test_dnd_roll_command_returns_deterministic_result_table(monkeypatch):
    async def scenario():
        rolls = iter([2, 3])
        monkeypatch.setattr(dnd_cog.random, "randint", lambda low, high: next(rolls))
        events = []
        cog = object.__new__(DnDCog)
        interaction = FakeInteraction(
            user=SimpleNamespace(id=1),
            events=events,
        )

        await DnDCog.dnd_roll.callback(cog, interaction, "2d6+1", 1)

        assert events == [
            ("response", interaction.response.messages[0]["content"]),
        ]
        content = interaction.response.messages[0]["content"]
        assert "**Results**" in content
        assert "|    6 |+2d6:2+3=5,+1," in content

    asyncio.run(scenario())
