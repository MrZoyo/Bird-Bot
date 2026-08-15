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
    "ban.spam_defense_reason": "automatic spam defense in {channel}",
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
    bot: bool = False


class FakeChannel:
    def __init__(self, channel_id, *, senders=None, name="general"):
        self.id = channel_id
        self.name = name
        self.mention = f"<#{channel_id}>"
        self.senders = set(senders or [])

    def permissions_for(self, member):
        return SimpleNamespace(send_messages=member.id in self.senders)


class FakeGuild:
    def __init__(
        self,
        guild_id,
        events,
        *,
        ban_exception=None,
        owner_id=1,
        channels=None,
    ):
        self.id = guild_id
        self.name = "Test Guild"
        self.events = events
        self.ban_exception = ban_exception
        self.owner_id = owner_id
        self.channels = {channel.id: channel for channel in channels or []}
        self.bans = []
        self.unbans = []

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)

    async def ban(
        self,
        user,
        *,
        reason,
        delete_message_days=None,
        delete_message_seconds=None,
    ):
        delete_window = (
            delete_message_seconds
            if delete_message_seconds is not None
            else delete_message_days
        )
        self.events.append(("guild_ban", user.id, reason, delete_window))
        if self.ban_exception:
            raise self.ban_exception
        self.bans.append({
            "user_id": user.id,
            "reason": reason,
            "delete_message_days": delete_message_days,
            "delete_message_seconds": delete_message_seconds,
        })

    async def unban(self, user, *, reason):
        self.events.append(("guild_unban", user.id, reason))
        self.unbans.append({"user_id": user.id, "reason": reason})


class FakeBanDB:
    def __init__(self, events, *, existing_tempban=None, add_exception=None):
        self.events = events
        self.existing_tempban = existing_tempban
        self.add_exception = add_exception
        self.tempbans = []

    async def get_user_tempban(self, user_id, guild_id):
        self.events.append(("db_get_tempban", user_id, guild_id))
        return self.existing_tempban

    async def add_tempban(self, user_id, guild_id, banned_by, reason, unban_at, delete_message_days):
        self.events.append(("db_add_tempban", user_id, guild_id, banned_by, reason, delete_message_days))
        if self.add_exception:
            raise self.add_exception
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


def _build_cog(events, db, *, allowed=True, spam_defense=None):
    cog = object.__new__(BanCog)
    cog.db = db
    cog.config_data = {
        "admin_roles": [],
        "admin_users": [],
        "spam_defense": spam_defense or {},
    }
    cog.tempban_tasks = {}
    cog._spam_defense_pending_user_ids = set()
    bot_user = FakeUser(999, "Bot", "bot", "<@999>", bot=True)
    cog.bot = SimpleNamespace(user=bot_user, get_channel=lambda channel_id: None)

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


@dataclass
class FakeMessage:
    author: FakeUser
    guild: FakeGuild | None
    channel: FakeChannel
    content: str
    mention_everyone: bool = True
    webhook_id: int | None = None


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


def test_spam_defense_tempbans_then_records_schedules_and_notifies(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        monkeypatch.setattr(
            ban_cog.config,
            "get_config",
            lambda name="main": {"guild_id": 1, "admin_channel_id": 100},
        )
        events = []
        db = FakeBanDB(events)
        cog = _build_cog(
            events,
            db,
            spam_defense={
                "enabled": True,
                "tempban_duration": "1m",
                "delete_message_seconds": 3600,
            },
        )
        admin_channel = FakeChannel(100)
        source_channel = FakeChannel(200)
        guild = FakeGuild(1, events, owner_id=10, channels=[admin_channel])
        user = FakeUser(20, "Spammer", "spammer", "<@20>")
        message = FakeMessage(user, guild, source_channel, "spam @everyone")

        await BanCog.on_message(cog, message)

        assert [event[0] for event in events] == [
            "db_get_tempban",
            "dm",
            "guild_ban",
            "db_add_tempban",
            "schedule",
            "notify",
        ]
        reason = "automatic spam defense in <#200>"
        assert events[1] == ("dm", 20, reason, "1m")
        assert events[2] == (
            "guild_ban",
            20,
            f"Automatic @everyone spam defense: {reason} (Duration: 1m)",
            3600,
        )
        assert events[3] == ("db_add_tempban", 20, 1, 999, reason, 0)
        assert events[4] == ("schedule", 1, 20, 77)
        assert events[5] == ("notify", 20, reason, "1m")
        assert cog._spam_defense_pending_user_ids == set()

    asyncio.run(scenario())


def test_spam_defense_supports_legacy_delete_message_days(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        monkeypatch.setattr(
            ban_cog.config,
            "get_config",
            lambda name="main": {"guild_id": 1, "admin_channel_id": None},
        )
        events = []
        db = FakeBanDB(events)
        cog = _build_cog(
            events,
            db,
            spam_defense={
                "enabled": True,
                "tempban_duration": "1m",
                "delete_message_days": 2,
            },
        )
        guild = FakeGuild(1, events)
        user = FakeUser(20, "Spammer", "spammer", "<@20>")

        await BanCog.on_message(
            cog,
            FakeMessage(user, guild, FakeChannel(200), "spam @everyone"),
        )

        assert events[2][-1] == 2 * 86400
        assert events[3] == (
            "db_add_tempban",
            20,
            1,
            999,
            "automatic spam defense in <#200>",
            2,
        )

    asyncio.run(scenario())


def test_spam_defense_rejects_invalid_delete_message_seconds(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        monkeypatch.setattr(
            ban_cog.config,
            "get_config",
            lambda name="main": {"guild_id": 1, "admin_channel_id": None},
        )
        events = []
        cog = _build_cog(
            events,
            FakeBanDB(events),
            spam_defense={
                "enabled": True,
                "tempban_duration": "1m",
                "delete_message_seconds": 604801,
            },
        )

        await BanCog.on_message(
            cog,
            FakeMessage(
                FakeUser(20, "Spammer", "spammer", "<@20>"),
                FakeGuild(1, events),
                FakeChannel(200),
                "spam @everyone",
            ),
        )

        assert events == []

    asyncio.run(scenario())


def test_spam_defense_ignores_non_pinging_everyone_text(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeBanDB(events)
        cog = _build_cog(
            events,
            db,
            spam_defense={"enabled": True, "tempban_duration": "1m"},
        )
        guild = FakeGuild(1, events)
        user = FakeUser(20, "User", "user", "<@20>")
        channel = FakeChannel(200)

        await BanCog.on_message(
            cog,
            FakeMessage(user, guild, channel, "plain @everyone text", mention_everyone=False),
        )
        await BanCog.on_message(
            cog,
            FakeMessage(user, guild, channel, "actual @here ping", mention_everyone=True),
        )

        assert events == []

    asyncio.run(scenario())


def test_spam_defense_exempts_all_admin_paths(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        monkeypatch.setattr(
            ban_cog.config,
            "get_config",
            lambda name="main": {"guild_id": 1, "admin_channel_id": 100},
        )
        events = []
        db = FakeBanDB(events)
        cog = _build_cog(
            events,
            db,
            spam_defense={"enabled": True, "tempban_duration": "1m"},
        )
        cog.config_data["admin_roles"] = [500]
        cog.config_data["admin_users"] = [30]
        admin_channel = FakeChannel(100, senders={40})
        source_channel = FakeChannel(200)
        guild = FakeGuild(1, events, owner_id=10, channels=[admin_channel])
        users = [
            FakeUser(10, "Owner", "owner", "<@10>"),
            FakeUser(
                20,
                "Discord Admin",
                "discord-admin",
                "<@20>",
                guild_permissions=SimpleNamespace(administrator=True),
            ),
            FakeUser(30, "Configured User", "configured-user", "<@30>"),
            FakeUser(
                31,
                "Configured Role",
                "configured-role",
                "<@31>",
                roles=[SimpleNamespace(id=500)],
            ),
            FakeUser(40, "Channel Admin", "channel-admin", "<@40>"),
        ]

        for user in users:
            await BanCog.on_message(
                cog,
                FakeMessage(user, guild, source_channel, "allowed @everyone"),
            )

        assert events == []

    asyncio.run(scenario())


def test_spam_defense_forbidden_does_not_record_or_notify(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        monkeypatch.setattr(
            ban_cog.config,
            "get_config",
            lambda name="main": {"guild_id": 1, "admin_channel_id": None},
        )
        events = []
        forbidden = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "no")
        db = FakeBanDB(events)
        cog = _build_cog(
            events,
            db,
            spam_defense={"enabled": True, "tempban_duration": "1m"},
        )
        guild = FakeGuild(1, events, ban_exception=forbidden)
        user = FakeUser(20, "Spammer", "spammer", "<@20>")

        await BanCog.on_message(
            cog,
            FakeMessage(user, guild, FakeChannel(200), "spam @everyone"),
        )

        assert [event[0] for event in events] == [
            "db_get_tempban",
            "dm",
            "guild_ban",
        ]
        assert db.tempbans == []

    asyncio.run(scenario())


def test_spam_defense_rolls_back_ban_when_db_write_fails(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        monkeypatch.setattr(
            ban_cog.config,
            "get_config",
            lambda name="main": {"guild_id": 1, "admin_channel_id": None},
        )
        events = []
        db = FakeBanDB(events, add_exception=RuntimeError("db unavailable"))
        cog = _build_cog(
            events,
            db,
            spam_defense={"enabled": True, "tempban_duration": "1m"},
        )
        guild = FakeGuild(1, events)
        user = FakeUser(20, "Spammer", "spammer", "<@20>")

        await BanCog.on_message(
            cog,
            FakeMessage(user, guild, FakeChannel(200), "spam @everyone"),
        )

        assert [event[0] for event in events] == [
            "db_get_tempban",
            "dm",
            "guild_ban",
            "db_add_tempban",
            "guild_unban",
        ]
        assert guild.unbans[0]["user_id"] == 20

    asyncio.run(scenario())
