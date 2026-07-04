import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import discord

from bot.cogs.invite_guard import cog as invite_guard_cog
from bot.cogs.invite_guard.cog import InviteCleanerSettings, InviteGuardCog


NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


class FakeBot:
    def __init__(self, guild):
        self.guild = guild
        self.owner_ids = set()
        self.admin_channel = None

    def get_guild(self, guild_id):
        return self.guild if self.guild.id == guild_id else None

    def get_channel(self, channel_id):
        if self.admin_channel and self.admin_channel.id == channel_id:
            return self.admin_channel
        return None

    async def is_owner(self, user):
        return getattr(user, "id", None) in self.owner_ids


class FakeGuild:
    def __init__(self, invites):
        self.id = 123
        self.name = "Test Guild"
        self._invites = invites
        self.members = {}

    async def invites(self):
        return self._invites

    def get_member(self, user_id):
        return self.members.get(user_id)

    async def fetch_member(self, user_id):
        member = self.members.get(user_id)
        if member is None:
            raise discord.NotFound(SimpleNamespace(status=404, reason="missing"), "not found")
        return member


class FakeInvite:
    def __init__(self, code, created_at, *, inviter=None, delete_exception=None):
        self.code = code
        self.created_at = created_at
        self.inviter = inviter
        self.uses = 0
        self.max_age = 2_592_000
        self.delete_exception = delete_exception
        self.deleted_reasons = []

    async def delete(self, *, reason=None):
        if self.delete_exception:
            raise self.delete_exception
        self.deleted_reasons.append(reason)


class FakeResponse:
    def __init__(self, events):
        self.events = events

    async def defer(self, *, ephemeral=False, thinking=False):
        self.events.append(("defer", ephemeral, thinking))


class FakeFollowup:
    def __init__(self, events):
        self.events = events
        self.messages = []

    async def send(self, content=None, *, ephemeral=False):
        self.events.append(("followup", content, ephemeral))
        self.messages.append({"content": content, "ephemeral": ephemeral})


class FakeInteraction:
    def __init__(self, events):
        self.user = SimpleNamespace(id=10, display_name="Admin", name="admin")
        self.channel_id = 999
        self.response = FakeResponse(events)
        self.followup = FakeFollowup(events)


def _settings(**overrides):
    data = {
        "enabled": True,
        "guild_id": 123,
        "max_age_days": 3,
        "interval_hours": 24,
        "dry_run": False,
        "invite_code_whitelist": frozenset(),
        "invite_creator_whitelist": frozenset(),
        "audit_reason": "cleanup after {max_age_days} days",
    }
    data.update(overrides)
    return InviteCleanerSettings(**data)


def _build_cog(bot):
    cog = object.__new__(InviteGuardCog)
    cog.bot = bot
    cog.settings = _settings()
    return cog


def _http_exception():
    response = SimpleNamespace(status=500, reason="server error")
    return discord.HTTPException(response, "boom")


def test_run_cleanup_deletes_only_expired_non_whitelisted_invites():
    async def scenario():
        old = FakeInvite("old", NOW - timedelta(days=4), inviter=SimpleNamespace(id=1, name="user"))
        young = FakeInvite("young", NOW - timedelta(days=2))
        no_created_at = FakeInvite("missing", None)
        code_whitelist = FakeInvite("official", NOW - timedelta(days=30))
        user_whitelist = FakeInvite("admin-made", NOW - timedelta(days=30), inviter=SimpleNamespace(id=42, name="admin"))
        guild = FakeGuild([old, young, no_created_at, code_whitelist, user_whitelist])
        cog = _build_cog(FakeBot(guild))

        summary = await cog.run_cleanup(
            now=NOW,
            settings=_settings(
                invite_code_whitelist=frozenset({"official"}),
                invite_creator_whitelist=frozenset({42}),
            ),
        )

        assert summary.scanned == 5
        assert summary.deleted == 1
        assert summary.skipped_young == 1
        assert summary.skipped_missing_created_at == 1
        assert summary.skipped_whitelist == 2
        assert summary.failed == 0
        assert old.deleted_reasons == ["cleanup after 3 days"]
        assert young.deleted_reasons == []
        assert no_created_at.deleted_reasons == []
        assert code_whitelist.deleted_reasons == []
        assert user_whitelist.deleted_reasons == []

    asyncio.run(scenario())


def test_dry_run_reports_would_delete_without_deleting():
    async def scenario():
        old = FakeInvite("old", NOW - timedelta(days=4))
        guild = FakeGuild([old])
        cog = _build_cog(FakeBot(guild))

        summary = await cog.run_cleanup(now=NOW, dry_run=True, settings=_settings())

        assert summary.scanned == 1
        assert summary.deleted == 0
        assert summary.would_delete == 1
        assert old.deleted_reasons == []

    asyncio.run(scenario())


def test_single_delete_failure_does_not_stop_remaining_invites():
    async def scenario():
        failing = FakeInvite("failing", NOW - timedelta(days=4), delete_exception=_http_exception())
        ok = FakeInvite("ok", NOW - timedelta(days=5))
        guild = FakeGuild([failing, ok])
        cog = _build_cog(FakeBot(guild))

        summary = await cog.run_cleanup(now=NOW, settings=_settings())

        assert summary.scanned == 2
        assert summary.deleted == 1
        assert summary.failed == 1
        assert ok.deleted_reasons == ["cleanup after 3 days"]

    asyncio.run(scenario())


def test_admin_channel_access_whitelists_invite_creator(monkeypatch):
    async def scenario():
        monkeypatch.setitem(invite_guard_cog.config.get_config('main'), 'admin_channel_id', 999)
        creator = SimpleNamespace(id=42, display_name="Admin", name="admin")
        member = SimpleNamespace(
            id=42,
            display_name="Admin",
            name="admin",
            guild_permissions=SimpleNamespace(administrator=False),
        )
        old = FakeInvite("admin-made", NOW - timedelta(days=30), inviter=creator)
        guild = FakeGuild([old])
        guild.members[42] = member
        bot = FakeBot(guild)
        bot.admin_channel = SimpleNamespace(
            id=999,
            name="admin",
            permissions_for=lambda checked_member: SimpleNamespace(view_channel=checked_member.id == 42),
        )
        cog = _build_cog(bot)

        summary = await cog.run_cleanup(now=NOW, settings=_settings())

        assert summary.skipped_whitelist == 1
        assert summary.deleted == 0
        assert old.deleted_reasons == []

    asyncio.run(scenario())


def test_manual_command_uses_admin_channel_check_and_returns_summary(monkeypatch):
    async def scenario():
        async def allow_channel(interaction):
            return True

        def fake_summary(self, summary):
            return f"scanned={summary.scanned} deleted={summary.deleted} dry_run={summary.dry_run}"

        monkeypatch.setattr(invite_guard_cog, "check_channel_validity", allow_channel)
        monkeypatch.setattr(InviteGuardCog, "_format_summary", fake_summary)

        events = []
        old = FakeInvite("old", NOW - timedelta(days=4))
        guild = FakeGuild([old])
        cog = _build_cog(FakeBot(guild))
        cog._load_settings = lambda: _settings()
        interaction = FakeInteraction(events)

        await InviteGuardCog.invite_cleanup.callback(cog, interaction, True)

        assert events == [
            ("defer", True, True),
            ("followup", "scanned=1 deleted=0 dry_run=True", True),
        ]
        assert old.deleted_reasons == []

    asyncio.run(scenario())
