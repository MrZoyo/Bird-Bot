import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import discord

from bot.cogs.invite_guard import cog as invite_guard_cog
from bot.cogs.invite_guard.cog import (
    InviteCleanerSettings,
    InviteGuardCog,
    InviteLeaderboardSettings,
    InviteSnapshot,
)
from bot.utils.invite_guard_db import InviteGuardDatabaseManager
from bot.utils.shop_db import ShopDatabaseManager


NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


class FakeBot:
    def __init__(self, guild):
        self.guild = guild
        self.owner_ids = set()
        self.admin_channel = None
        self.channels = {}
        self.user = SimpleNamespace(id=9999, display_avatar=SimpleNamespace(url="https://cdn.example.test/bot.png"))

    def get_guild(self, guild_id):
        return self.guild if self.guild.id == guild_id else None

    def get_channel(self, channel_id):
        if channel_id in self.channels:
            return self.channels[channel_id]
        if self.admin_channel and self.admin_channel.id == channel_id:
            return self.admin_channel
        return None

    async def fetch_channel(self, channel_id):
        channel = self.get_channel(channel_id)
        if channel is None:
            raise discord.NotFound(SimpleNamespace(status=404, reason="missing"), "not found")
        return channel

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
    def __init__(
        self,
        code,
        created_at,
        *,
        inviter=None,
        uses=0,
        guild=None,
        channel=None,
        delete_exception=None,
    ):
        self.code = code
        self.created_at = created_at
        self.inviter = inviter
        self.uses = uses
        self.max_age = 2_592_000
        self.max_uses = 0
        self.temporary = False
        self.guild = guild
        self.channel = channel
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


class FakeMessage:
    def __init__(self, message_id):
        self.id = message_id
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class FakeChannel:
    def __init__(self, channel_id, guild=None):
        self.id = channel_id
        self.name = "leaderboard"
        self.guild = guild
        self.mention = f"<#{channel_id}>"
        self.messages = {}
        self.sent_messages = []

    async def fetch_message(self, message_id):
        if message_id not in self.messages:
            raise discord.NotFound(SimpleNamespace(status=404, reason="missing"), "not found")
        return self.messages[message_id]

    async def send(self, content=None, **kwargs):
        message = FakeMessage(999)
        message.edits.append({"content": content, **kwargs})
        self.messages[message.id] = message
        self.sent_messages.append({"content": content, **kwargs})
        return message


class FakeShopDB:
    def __init__(self):
        self.transactions = []

    async def initialize_database(self):
        return None

    async def update_user_balance_with_record(self, user_id, amount, operation_type, operator_id, note=None):
        self.transactions.append(
            {
                "user_id": user_id,
                "amount": amount,
                "operation_type": operation_type,
                "operator_id": operator_id,
                "note": note,
            }
        )
        return sum(transaction["amount"] for transaction in self.transactions if transaction["user_id"] == user_id)


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


def _leaderboard_settings(**overrides):
    data = {
        "enabled": True,
        "guild_id": 123,
        "channel_id": None,
        "message_id": None,
        "interval_minutes": 5,
        "top_n": 15,
        "ignored_codes": frozenset(),
        "ignored_inviter_ids": frozenset(),
        "unknown_allow_reattribution": True,
        "ambiguous_allow_reattribution": True,
        "require_single_delta_for_attribution": True,
        "reward_points_per_invite": 60,
    }
    data.update(overrides)
    return InviteLeaderboardSettings(**data)


async def _build_leaderboard_cog(tmp_path, guild, settings=None):
    bot = FakeBot(guild)
    cog = _build_cog(bot)
    cog.leaderboard_settings = settings or _leaderboard_settings()
    cog.db = InviteGuardDatabaseManager(str(tmp_path / "invite_guard.db"))
    await cog.db.initialize_database()
    cog.shop_db = FakeShopDB()
    cog.invite_cache = {}
    cog._invite_cache_initialized = True
    cog._runtime_leaderboard_channel_id = cog.leaderboard_settings.channel_id
    cog._runtime_leaderboard_message_id = cog.leaderboard_settings.message_id
    cog._load_leaderboard_settings = lambda: cog.leaderboard_settings
    return cog


def _http_exception():
    response = SimpleNamespace(status=500, reason="server error")
    return discord.HTTPException(response, "boom")


def test_invite_guard_uses_main_guild_and_ignores_legacy_guild_overrides(monkeypatch):
    configs = {
        "main": {"guild_id": 111},
        "invite_guard": {
            "guild_id": 222,
            "leaderboard_guild_id": 333,
            "leaderboard_channel_id": 444,
            "reward_points_per_invite": 75,
        },
    }

    def fake_get_config(name, silent=False):
        return configs.get(name, {})

    monkeypatch.setattr(invite_guard_cog.config, "get_config", fake_get_config)
    monkeypatch.setenv("INVITE_LEADERBOARD_GUILD_ID", "555")
    monkeypatch.setenv("INVITE_CLEANER_GUILD_ID", "666")

    cog = object.__new__(InviteGuardCog)
    cleaner_settings = InviteGuardCog._load_settings(cog)
    leaderboard_settings = InviteGuardCog._load_leaderboard_settings(cog)

    assert cleaner_settings.guild_id == 111
    assert leaderboard_settings.guild_id == 111
    assert leaderboard_settings.channel_id == 444
    assert leaderboard_settings.top_n == 15
    assert leaderboard_settings.reward_points_per_invite == 75


def test_invite_guard_uses_main_guild(monkeypatch):
    configs = {
        "main": {"guild_id": 111},
        "invite_guard": {"leaderboard_channel_id": 444},
    }

    def fake_get_config(name, silent=False):
        return configs.get(name, {})

    monkeypatch.setattr(invite_guard_cog.config, "get_config", fake_get_config)

    cog = object.__new__(InviteGuardCog)
    cleaner_settings = InviteGuardCog._load_settings(cog)
    leaderboard_settings = InviteGuardCog._load_leaderboard_settings(cog)

    assert cleaner_settings.guild_id == 111
    assert leaderboard_settings.guild_id == 111
    assert leaderboard_settings.channel_id == 444
    assert leaderboard_settings.reward_points_per_invite == 60


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


def test_member_join_attributes_single_invite_delta_and_locks_rejoins(tmp_path):
    async def scenario():
        inviter = SimpleNamespace(id=100, display_name="Inviter", name="inviter")
        guild = FakeGuild([])
        member = SimpleNamespace(id=200, display_name="Newbie", name="newbie", guild=guild)
        cog = await _build_leaderboard_cog(tmp_path, guild)

        cog.invite_cache = {
            "abc": InviteSnapshot(code="abc", uses=0, inviter_id=100, ignored=False),
        }
        guild._invites = [
            FakeInvite("abc", NOW, inviter=inviter, uses=1, guild=guild),
        ]

        await InviteGuardCog.on_member_join(cog, member)

        joined = await cog.db.get_user(123, 200)
        inviter_record = await cog.db.get_user(123, 100)
        assert joined["attribution_status"] == "attributed"
        assert joined["attribution_locked"] == 1
        assert joined["allow_reattribution"] == 0
        assert joined["invited_by_user_id"] == 100
        assert inviter_record["invited_count"] == 1
        assert cog.shop_db.transactions == [
            {
                "user_id": 100,
                "amount": 60,
                "operation_type": "invite_reward",
                "operator_id": 9999,
                "note": "Invite reward: 200 via abc",
            }
        ]

        guild._invites = [
            FakeInvite("abc", NOW, inviter=inviter, uses=2, guild=guild),
        ]
        await InviteGuardCog.on_member_join(cog, member)

        joined_again = await cog.db.get_user(123, 200)
        inviter_again = await cog.db.get_user(123, 100)
        assert joined_again["join_count"] == 2
        assert inviter_again["invited_count"] == 1
        assert len(cog.shop_db.transactions) == 1

    asyncio.run(scenario())


def test_invite_reward_updates_shop_balance_and_transaction_history(tmp_path):
    async def scenario():
        inviter = SimpleNamespace(id=100, display_name="Inviter", name="inviter")
        guild = FakeGuild([])
        member = SimpleNamespace(id=200, display_name="Newbie", name="newbie", guild=guild)
        cog = await _build_leaderboard_cog(tmp_path, guild)
        cog.shop_db = ShopDatabaseManager(str(tmp_path / "invite_guard.db"))
        await cog.shop_db.initialize_database()

        cog.invite_cache = {
            "abc": InviteSnapshot(code="abc", uses=0, inviter_id=100, ignored=False),
        }
        guild._invites = [
            FakeInvite("abc", NOW, inviter=inviter, uses=1, guild=guild),
        ]

        try:
            await InviteGuardCog.on_member_join(cog, member)

            assert await cog.shop_db.get_user_balance(100) == 60
            history = await cog.shop_db.get_transaction_history(100)
            assert history[0][2] == "invite_reward"
            assert history[0][3] == 60
            assert history[0][5] == 9999
            assert history[0][6] == "Invite reward: 200 via abc"
        finally:
            await cog.shop_db.close()

    asyncio.run(scenario())


def test_ignored_join_can_be_reattributed_by_later_regular_invite(tmp_path):
    async def scenario():
        inviter = SimpleNamespace(id=100, display_name="Inviter", name="inviter")
        guild = FakeGuild([])
        member = SimpleNamespace(id=201, display_name="Later", name="later", guild=guild)
        cog = await _build_leaderboard_cog(
            tmp_path,
            guild,
            _leaderboard_settings(ignored_codes=frozenset({"birdgaming"})),
        )

        cog.invite_cache = {
            "birdgaming": InviteSnapshot(code="birdgaming", uses=0, inviter_id=None, ignored=True),
        }
        guild._invites = [
            FakeInvite("birdgaming", NOW, inviter=None, uses=1, guild=guild),
        ]

        await InviteGuardCog.on_member_join(cog, member)
        ignored = await cog.db.get_user(123, 201)
        assert ignored["attribution_status"] == "ignored"
        assert ignored["attribution_locked"] == 0
        assert ignored["allow_reattribution"] == 1

        cog.invite_cache = {
            "abc": InviteSnapshot(code="abc", uses=0, inviter_id=100, ignored=False),
        }
        guild._invites = [
            FakeInvite("abc", NOW, inviter=inviter, uses=1, guild=guild),
        ]

        await InviteGuardCog.on_member_join(cog, member)
        attributed = await cog.db.get_user(123, 201)
        inviter_record = await cog.db.get_user(123, 100)
        assert attributed["attribution_status"] == "attributed"
        assert attributed["attribution_locked"] == 1
        assert inviter_record["invited_count"] == 1
        assert len(cog.shop_db.transactions) == 1

    asyncio.run(scenario())


def test_ambiguous_join_does_not_increment_inviter_counts(tmp_path):
    async def scenario():
        inviter_a = SimpleNamespace(id=100, display_name="A", name="a")
        inviter_b = SimpleNamespace(id=101, display_name="B", name="b")
        guild = FakeGuild([])
        member = SimpleNamespace(id=202, display_name="Ambiguous", name="ambiguous", guild=guild)
        cog = await _build_leaderboard_cog(tmp_path, guild)

        cog.invite_cache = {
            "a": InviteSnapshot(code="a", uses=0, inviter_id=100, ignored=False),
            "b": InviteSnapshot(code="b", uses=0, inviter_id=101, ignored=False),
        }
        guild._invites = [
            FakeInvite("a", NOW, inviter=inviter_a, uses=1, guild=guild),
            FakeInvite("b", NOW, inviter=inviter_b, uses=1, guild=guild),
        ]

        await InviteGuardCog.on_member_join(cog, member)

        joined = await cog.db.get_user(123, 202)
        assert joined["attribution_status"] == "ambiguous"
        assert joined["attribution_locked"] == 0
        assert await cog.db.get_user(123, 100) is None
        assert await cog.db.get_user(123, 101) is None
        assert cog.shop_db.transactions == []

    asyncio.run(scenario())


def test_invite_sync_refreshes_configured_message(monkeypatch, tmp_path):
    async def scenario():
        async def allow_channel(interaction):
            return True

        monkeypatch.setattr(invite_guard_cog, "check_channel_validity", allow_channel)
        guild = FakeGuild([])
        channel = FakeChannel(555, guild)
        message = FakeMessage(777)
        channel.messages[777] = message

        cog = await _build_leaderboard_cog(
            tmp_path,
            guild,
            _leaderboard_settings(channel_id=555, message_id=777),
        )
        cog.bot.channels[555] = channel
        await cog.db.record_member_join(123, 200, NOW.isoformat())
        await cog.db.attribute_member(123, 200, 100, "abc", NOW.isoformat())

        events = []
        interaction = FakeInteraction(events)

        await InviteGuardCog.invite_sync.callback(cog, interaction)

        assert events[0] == ("defer", True, True)
        assert "邀请链接已同步，排行榜已刷新" in events[1][1]
        assert "message_id: 777" in events[1][1]
        assert message.edits
        edit = message.edits[-1]
        assert edit["content"] is None
        assert edit["embed"] is None
        assert edit["attachments"] == []
        view = edit["view"]
        assert view.has_components_v2() is True
        container = view.to_components()[0]
        assert container["accent_color"] == 0x7C3AED
        assert [component["type"] for component in container["components"]] == [10, 14, 9, 14, 10]
        header = container["components"][0]["content"]
        assert header.startswith("### 🏆 邀请排行榜\n更新于 <t:")
        assert header.rstrip().endswith(":R>")
        assert container["components"][1]["divider"] is True
        assert container["components"][2]["components"][0]["content"] == "🥇 <@100>  **1** 人"
        assert container["components"][2]["accessory"]["media"]["url"] == "https://cdn.example.test/bot.png"
        assert "active invite" not in container["components"][2]["components"][0]["content"]
        assert container["components"][3]["divider"] is True
        assert container["components"][4]["content"] == (
            "-# 每个新成员只会被第一次有效普通邀请计入一次，退出后重新加入不会重复计数。"
        )

    asyncio.run(scenario())


def test_invite_create_embed_creates_new_runtime_panel(monkeypatch, tmp_path):
    async def scenario():
        async def allow_channel(interaction):
            return True

        monkeypatch.setattr(invite_guard_cog, "check_channel_validity", allow_channel)
        guild = FakeGuild([])
        channel = FakeChannel(555, guild)

        cog = await _build_leaderboard_cog(tmp_path, guild, _leaderboard_settings(channel_id=444, message_id=777))
        cog.bot.channels[555] = channel
        await cog.db.record_member_join(123, 200, NOW.isoformat())
        await cog.db.attribute_member(123, 200, 100, "abc", NOW.isoformat())

        events = []
        interaction = FakeInteraction(events)

        await InviteGuardCog.invite_create_embed.callback(cog, interaction, channel)

        assert events[0] == ("defer", True, True)
        assert "邀请排行榜面板已创建" in events[1][1]
        assert "message_id: 999" in events[1][1]
        assert len(channel.sent_messages) == 1
        assert channel.sent_messages[0]["view"].has_components_v2() is True
        assert cog._runtime_leaderboard_channel_id == 555
        assert cog._runtime_leaderboard_message_id == 999

    asyncio.run(scenario())
