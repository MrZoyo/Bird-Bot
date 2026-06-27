import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

import discord

from bot.cogs.ban import cog as ban_cog
from bot.cogs.ban.cog import BanCog


BAN_TEXT = {
    "ban.no_permission": "no permission",
    "ban.invalid_duration": "invalid duration",
    "ban.duration_too_short": "duration too short",
    "ban.invalid_delete_days": "invalid delete days",
    "ban.user_already_tempbanned": "already tempbanned {user}",
    "ban.tempban_success": "tempbanned {user} for {duration}",
    "ban.ban_failed_permissions": "ban forbidden",
    "ban.ban_failed_error": "ban http error",
}


class FakeResponse:
    def __init__(self, events):
        self.events = events
        self.messages = []

    async def send_message(self, content=None, *, ephemeral=False, **kwargs):
        self.events.append(("response", content))
        self.messages.append({
            "content": content,
            "ephemeral": ephemeral,
            **kwargs,
        })


class FakeInteraction:
    def __init__(self, *, user, guild, events):
        self.user = user
        self.guild = guild
        self.response = FakeResponse(events)


@dataclass
class FakeUser:
    id: int
    display_name: str
    name: str
    mention: str
    roles: list = field(default_factory=list)
    guild_permissions: object = field(default_factory=lambda: SimpleNamespace(administrator=False))


class FakeGuild:
    def __init__(self, guild_id, events, *, ban_exception=None):
        self.id = guild_id
        self.name = "Test Guild"
        self.events = events
        self.ban_exception = ban_exception
        self.bans = []

    async def ban(self, user, *, reason, delete_message_days):
        self.events.append(("guild_ban", user.id, reason, delete_message_days))
        if self.ban_exception:
            raise self.ban_exception
        self.bans.append({
            "user_id": user.id,
            "reason": reason,
            "delete_message_days": delete_message_days,
        })


class FakeBanDB:
    def __init__(self, events, *, existing_tempban=None):
        self.events = events
        self.existing_tempban = existing_tempban
        self.tempbans = []

    async def get_user_tempban(self, user_id, guild_id):
        self.events.append(("db_get_tempban", user_id, guild_id))
        return self.existing_tempban

    async def add_tempban(self, user_id, guild_id, banned_by, reason, unban_at, delete_message_days):
        self.events.append(("db_add_tempban", user_id, guild_id, banned_by, reason, delete_message_days))
        self.tempbans.append({
            "user_id": user_id,
            "guild_id": guild_id,
            "banned_by": banned_by,
            "reason": reason,
            "unban_at": unban_at,
            "delete_message_days": delete_message_days,
        })
        return 77


def _install_translations(monkeypatch):
    monkeypatch.setattr(ban_cog, "t", lambda key, **kwargs: BAN_TEXT[key])


def _build_cog(events, db, *, allowed=True):
    cog = object.__new__(BanCog)
    cog.db = db
    cog.config_data = {"admin_roles": [], "admin_users": []}
    cog.tempban_tasks = {}

    async def has_ban_permission(interaction):
        events.append(("permission", interaction.user.id))
        return allowed

    async def send_tempban_dm(user, guild, reason, duration, unban_time):
        events.append(("dm", user.id, reason, duration))

    async def schedule_unban_with_db(guild, user, unban_time, tempban_id):
        events.append(("schedule", guild.id, user.id, tempban_id))

    async def send_ban_notification(user, reason, duration=None, unban_time=None):
        events.append(("notify", user.id, reason, duration))

    cog.has_ban_permission = has_ban_permission
    cog.send_tempban_dm = send_tempban_dm
    cog.schedule_unban_with_db = schedule_unban_with_db
    cog.send_ban_notification = send_ban_notification
    return cog


async def _run_tempban(cog, interaction, target, duration="1h", reason="rule", delete_message_days=1):
    await BanCog.tempban_command.callback(
        cog,
        interaction,
        target,
        duration,
        reason,
        delete_message_days,
    )


def test_tempban_rejects_without_permission(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeBanDB(events)
        cog = _build_cog(events, db, allowed=False)
        moderator = FakeUser(10, "Mod", "mod", "<@10>")
        target = FakeUser(20, "Target", "target", "<@20>")
        guild = FakeGuild(1, events)
        interaction = FakeInteraction(user=moderator, guild=guild, events=events)

        await _run_tempban(cog, interaction, target)

        assert events == [
            ("permission", 10),
            ("response", "no permission"),
        ]
        assert db.tempbans == []
        assert guild.bans == []

    asyncio.run(scenario())


def test_tempban_rejects_invalid_duration_before_db_lookup(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeBanDB(events)
        cog = _build_cog(events, db, allowed=True)
        moderator = FakeUser(10, "Mod", "mod", "<@10>")
        target = FakeUser(20, "Target", "target", "<@20>")
        guild = FakeGuild(1, events)
        interaction = FakeInteraction(user=moderator, guild=guild, events=events)

        await _run_tempban(cog, interaction, target, duration="forever")

        assert events == [
            ("permission", 10),
            ("response", "invalid duration"),
        ]
        assert db.tempbans == []
        assert guild.bans == []

    asyncio.run(scenario())


def test_tempban_rejects_existing_active_tempban_before_dm_or_ban(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeBanDB(events, existing_tempban=(77, 20, 1))
        cog = _build_cog(events, db, allowed=True)
        moderator = FakeUser(10, "Mod", "mod", "<@10>")
        target = FakeUser(20, "Target", "target", "<@20>")
        guild = FakeGuild(1, events)
        interaction = FakeInteraction(user=moderator, guild=guild, events=events)

        await _run_tempban(cog, interaction, target)

        assert events == [
            ("permission", 10),
            ("db_get_tempban", 20, 1),
            ("response", "already tempbanned <@20>"),
        ]
        assert db.tempbans == []
        assert guild.bans == []

    asyncio.run(scenario())


def test_tempban_success_dms_before_ban_then_records_and_notifies(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeBanDB(events)
        cog = _build_cog(events, db, allowed=True)
        moderator = FakeUser(10, "Mod", "mod", "<@10>")
        target = FakeUser(20, "Target", "target", "<@20>")
        guild = FakeGuild(1, events)
        interaction = FakeInteraction(user=moderator, guild=guild, events=events)

        await _run_tempban(cog, interaction, target, duration="2h", reason="spam", delete_message_days=3)

        event_names = [event[0] for event in events]
        assert event_names == [
            "permission",
            "db_get_tempban",
            "dm",
            "guild_ban",
            "db_add_tempban",
            "schedule",
            "response",
            "notify",
        ]
        assert events[2] == ("dm", 20, "spam", "2h")
        assert events[3] == ("guild_ban", 20, "Temporary ban: spam (Duration: 2h)", 3)
        assert events[4] == ("db_add_tempban", 20, 1, 10, "spam", 3)
        assert interaction.response.messages[0]["content"] == "tempbanned <@20> for 2h"

    asyncio.run(scenario())


def test_tempban_forbidden_after_dm_does_not_record_or_schedule(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeBanDB(events)
        forbidden = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "no")
        cog = _build_cog(events, db, allowed=True)
        moderator = FakeUser(10, "Mod", "mod", "<@10>")
        target = FakeUser(20, "Target", "target", "<@20>")
        guild = FakeGuild(1, events, ban_exception=forbidden)
        interaction = FakeInteraction(user=moderator, guild=guild, events=events)

        await _run_tempban(cog, interaction, target)

        event_names = [event[0] for event in events]
        assert event_names == [
            "permission",
            "db_get_tempban",
            "dm",
            "guild_ban",
            "response",
        ]
        assert interaction.response.messages[0]["content"] == "ban forbidden"
        assert db.tempbans == []

    asyncio.run(scenario())
