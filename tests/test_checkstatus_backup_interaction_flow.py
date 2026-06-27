import asyncio
from pathlib import Path
from types import SimpleNamespace

from bot.cogs.backup import cog as backup_cog
from bot.cogs.backup.cog import BackupCog
from bot.cogs.check_status import cog as checkstatus_cog
from bot.cogs.check_status import views as checkstatus_views
from bot.cogs.check_status.cog import CheckStatusCog


CHECKSTATUS_TEXT = {
    "checkstatus.where_is_join_button_label": "Join",
    "checkstatus.where_is_not_found_message": "{name} not found",
    "checkstatus.where_is_title_message": "Where is {name}",
    "checkstatus.current_channel_name_message": "Channel",
    "checkstatus.current_channel_members_message": "Members",
    "checkstatus.error_generic": "error {error}",
    "checkstatus.voice_stats_title": "Voice Stats",
    "checkstatus.voice_stats_category_value": "people={people}; channels={channels}",
    "checkstatus.voice_stats_total_people_title": "Total People",
    "checkstatus.voice_stats_total_people_value": "{count}",
    "checkstatus.voice_stats_total_channels_title": "Total Channels",
    "checkstatus.voice_stats_total_channels_value": "{count}",
    "checkstatus.log_type_main": "main",
    "checkstatus.log_type_keyword": "keyword",
    "checkstatus.log_type_room": "room",
    "checkstatus.log_file_not_found": "{log_type_name} missing",
    "checkstatus.log_file_empty": "{log_type_name} empty",
    "checkstatus.log_too_long": "{log_type_name} too long",
    "checkstatus.log_last_lines": "{log_type_name} last {x}:\n{lines}",
}


def _translate(key, **kwargs):
    text = CHECKSTATUS_TEXT[key]
    return text.format(**kwargs) if kwargs else text


class FakeResponse:
    def __init__(self, events):
        self.events = events
        self.deferred = []
        self.messages = []

    async def defer(self, *, ephemeral=False, **kwargs):
        self.events.append(("defer", ephemeral))
        self.deferred.append({"ephemeral": ephemeral, **kwargs})

    async def send_message(self, content=None, *, embed=None, file=None, ephemeral=False, **kwargs):
        self.events.append(("response", content or (embed.title if embed else None)))
        self.messages.append({
            "content": content,
            "embed": embed,
            "file": file,
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
    def __init__(self, *, user=None, events):
        self.user = user or SimpleNamespace(id=1, display_name="Operator", name="operator")
        self.response = FakeResponse(events)
        self.followup = FakeFollowup(events)


def _install_checkstatus_translations(monkeypatch):
    monkeypatch.setattr(checkstatus_cog, "t", _translate)
    monkeypatch.setattr(checkstatus_views, "t", _translate)


def test_where_is_sends_voice_link_embed_and_join_button(monkeypatch):
    async def scenario():
        _install_checkstatus_translations(monkeypatch)
        events = []
        channel = SimpleNamespace(id=222, members=[])
        guild = SimpleNamespace(id=111)
        member = SimpleNamespace(
            id=123,
            display_name="Target",
            name="target",
            guild=guild,
            voice=SimpleNamespace(channel=channel),
        )
        channel.members = [
            member,
            SimpleNamespace(id=456, display_name="Friend", name="friend"),
        ]
        interaction = FakeInteraction(events=events)
        cog = object.__new__(CheckStatusCog)
        cog.bot = SimpleNamespace()

        await cog._send_where_is(interaction, member)

        assert events == [
            ("followup", "Where is Target"),
        ]
        message = interaction.followup.messages[0]
        assert message["ephemeral"] is True
        assert message["embed"].fields[0].value == "https://discord.com/channels/111/222"
        assert message["embed"].fields[1].value == "Target\nFriend"
        assert message["view"].children[0].label == "Join"

    asyncio.run(scenario())


def test_check_voice_status_counts_active_categories(monkeypatch):
    async def scenario():
        _install_checkstatus_translations(monkeypatch)
        events = []
        gaming = SimpleNamespace(name="Gaming")
        quiet = SimpleNamespace(name="Quiet")
        guild = SimpleNamespace(
            voice_channels=[
                SimpleNamespace(category=gaming, members=[object(), object()]),
                SimpleNamespace(category=gaming, members=[]),
                SimpleNamespace(category=quiet, members=[object()]),
            ],
        )
        cog = object.__new__(CheckStatusCog)
        cog.bot = SimpleNamespace(guilds=[guild])
        interaction = FakeInteraction(events=events)

        await CheckStatusCog.check_voice_status.callback(cog, interaction)

        assert events == [
            ("defer", False),
            ("followup", "Voice Stats"),
        ]
        embed = interaction.followup.messages[0]["embed"]
        assert embed.fields[0].name == "Gaming"
        assert embed.fields[0].value == "people=2; channels=1"
        assert embed.fields[1].name == "Quiet"
        assert embed.fields[1].value == "people=1; channels=1"
        assert embed.fields[-2].value == "3"
        assert embed.fields[-1].value == "2"

    asyncio.run(scenario())


def test_check_log_reads_requested_log_type_tail(monkeypatch, tmp_path):
    async def scenario():
        _install_checkstatus_translations(monkeypatch)

        async def check_channel_validity(interaction):
            return True

        monkeypatch.setattr(checkstatus_cog, "check_channel_validity", check_channel_validity)
        main_log = Path(tmp_path / "main.log")
        keyword_log = Path(tmp_path / "keyword.log")
        room_log = Path(tmp_path / "room.log")
        main_log.write_text("main\n", encoding="utf-8")
        keyword_log.write_text("one\ntwo\nthree\n", encoding="utf-8")
        room_log.write_text("room\n", encoding="utf-8")
        cog = object.__new__(CheckStatusCog)
        cog.logging_file = str(main_log)
        cog.keyword_log_file = str(keyword_log)
        cog.room_log_file = str(room_log)
        interaction = FakeInteraction(events=[])

        await CheckStatusCog.check_log.callback(cog, interaction, 2, "keyword")

        assert interaction.response.messages[0]["content"] == "keyword last 2:\ntwo\nthree\n"

    asyncio.run(scenario())


def test_backup_now_invokes_manual_backup_before_response(monkeypatch):
    async def scenario():
        async def check_channel_validity(interaction):
            return True

        monkeypatch.setattr(backup_cog, "check_channel_validity", check_channel_validity)
        events = []

        async def backup_database(*, manual=False):
            events.append(("backup", manual))

        cog = SimpleNamespace(backup_database=backup_database)
        interaction = FakeInteraction(events=events)

        await BackupCog.backup_now.callback(cog, interaction)

        assert events == [
            ("backup", True),
            ("response", "Database backup created"),
        ]

    asyncio.run(scenario())
