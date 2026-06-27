import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace

from bot.cogs.privateroom import cog as privateroom_cog
from bot.cogs.privateroom.cog import PrivateRoomCog


class FrozenDatetime(datetime):
    fixed_now = datetime(2026, 4, 23, 11, 44, 5)

    @classmethod
    def now(cls):
        return cls.fixed_now


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, content=None, *, embed=None, view=None, ephemeral=False, **kwargs):
        self.messages.append({
            "content": content,
            "embed": embed,
            "view": view,
            "ephemeral": ephemeral,
            **kwargs,
        })


class FakeResponse:
    def __init__(self):
        self.deferred = []

    async def defer(self, *, ephemeral=False, **kwargs):
        self.deferred.append({
            "ephemeral": ephemeral,
            **kwargs,
        })


class FakeInteraction:
    def __init__(self, user):
        self.user = user
        self.response = FakeResponse()
        self.followup = FakeFollowup()


@dataclass
class FakeUser:
    id: int = 123
    display_name: str = "Zoyo"
    name: str = "zoyo_raw"
    mention: str = "<@123>"
    avatar: object | None = None
    dms: list = field(default_factory=list)

    async def send(self, *, embed=None, view=None, **kwargs):
        self.dms.append({
            "embed": embed,
            "view": view,
            **kwargs,
        })


@dataclass
class FakeChannel:
    id: int = 555
    name: str = "private-room"
    jump_url: str = "https://discord.test/channels/1/555"
    mention: str = "<#555>"
    messages: list = field(default_factory=list)

    async def send(self, content=None, *, embed=None, view=None, **kwargs):
        message = SimpleNamespace(id=9001)
        self.messages.append({
            "content": content,
            "embed": embed,
            "view": view,
            **kwargs,
        })
        return message


class FakeBot:
    def __init__(self, channel):
        self.channel = channel
        self.user = SimpleNamespace(avatar=None)

    def get_channel(self, channel_id):
        if channel_id == self.channel.id:
            return self.channel
        return None


class FakePrivateRoomDB:
    def __init__(self, *, active_room, persisted_room, events):
        self.active_room = active_room
        self.persisted_room = persisted_room
        self.events = events
        self.extend_calls = []

    async def get_active_room_by_user(self, user_id):
        return self.active_room

    async def extend_room_validity(self, room_id, new_end_date):
        self.events.append(("extend", room_id, new_end_date))
        self.extend_calls.append((room_id, new_end_date))
        return self.persisted_room


class FakeShopDB:
    def __init__(self, *, balance, events):
        self.balance = balance
        self.events = events
        self.transactions = []

    async def get_user_balance(self, user_id):
        return self.balance

    async def update_user_balance_with_record(self, user_id, amount, operation_type, operator_id, description):
        self.events.append(("charge", user_id, amount, description))
        self.transactions.append({
            "user_id": user_id,
            "amount": amount,
            "operation_type": operation_type,
            "operator_id": operator_id,
            "description": description,
        })
        return self.balance + amount


class FakeSetupPrivateRoomDB:
    def __init__(self):
        self.saved_shop_messages = []

    async def get_category_id(self):
        return 42

    async def get_active_rooms_count(self):
        return 7

    async def save_shop_message(self, channel_id, message_id):
        self.saved_shop_messages.append((channel_id, message_id))


def _install_translations(monkeypatch):
    translations = {
        "privateroom.messages.error_insufficient_balance": "insufficient balance",
        "privateroom.messages.error_no_room_for_renewal": "no active room",
        "privateroom.messages.error_room_not_found": "room not found",
        "privateroom.messages.error_renewal_too_early": "too early {days_remaining}/{threshold}",
        "privateroom.messages.error_renewal_failed": "renewal failed",
        "privateroom.messages.renewal_success_title": "renewal ok",
        "privateroom.messages.renewal_room_success_title": "room renewal ok",
        "privateroom.messages.renewal_room_success_description": (
            "owner={owner}; days={extend_days}; until={new_end_date}"
        ),
        "privateroom.messages.renewal_room_success_footer": "renewal footer",
        "privateroom.messages.renewal_dm_success_title": "dm renewal ok",
        "privateroom.messages.renewal_dm_success_description": "days={extend_days}; until={new_end_date}",
        "privateroom.messages.renewal_dm_success_button": "open room",
        "privateroom.messages.setup_success": "setup in {channel}",
        "privateroom.messages.setup_fail": "setup failed: {error}",
        "privateroom.messages.error_no_category": "no category",
        "privateroom.messages.shop_cleaned_old": "cleaned {count}",
        "privateroom.messages.shop_button_label": "Buy room",
        "privateroom.messages.shop_renewal_button_label": "Renew room",
        "privateroom.messages.shop_restore_button_label": "Restore room",
        "privateroom.messages.shop_title": "Room shop",
        "privateroom.messages.shop_description": (
            "cost={points_cost}; duration={duration}; hours={hours_threshold}; "
            "booster={booster_hours}; available={available_rooms}/{max_rooms}"
        ),
        "privateroom.messages.shop_footer": "Room footer",
    }
    monkeypatch.setattr(privateroom_cog, "t", lambda key: translations[key])
    monkeypatch.setattr("bot.cogs.privateroom.views.t", lambda key, **kwargs: translations[key])


def _build_cog(*, channel, active_room, persisted_room, balance=2000):
    events = []
    cog = object.__new__(PrivateRoomCog)
    cog.bot = FakeBot(channel)
    cog.conf = {
        "renewal_days_threshold": 7,
        "renewal_extend_days": 31,
        "check_time_hour": 8,
    }
    cog.db = FakePrivateRoomDB(
        active_room=active_room,
        persisted_room=persisted_room,
        events=events,
    )
    cog.shop_db = FakeShopDB(balance=balance, events=events)
    return cog, events


def test_advance_renewal_uses_persisted_end_date_before_charging(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        monkeypatch.setattr(privateroom_cog, "datetime", FrozenDatetime)

        user = FakeUser()
        channel = FakeChannel()
        active_room = {
            "room_id": channel.id,
            "user_id": user.id,
            "end_date": datetime(2026, 3, 2, 8, 0, 0),
        }
        persisted_room = {
            **active_room,
            "end_date": datetime(2026, 5, 25, 8, 0, 0),
        }
        cog, events = _build_cog(
            channel=channel,
            active_room=active_room,
            persisted_room=persisted_room,
        )
        interaction = FakeInteraction(user)

        result = await cog.process_advance_renewal(interaction, cost=520)

        assert result is True
        assert cog.db.extend_calls == [
            (channel.id, datetime(2026, 5, 24, 8, 0, 0)),
        ]
        assert events[0][0] == "extend"
        assert events[1][0] == "charge"
        assert cog.shop_db.transactions[0]["amount"] == -520
        assert interaction.followup.messages[-1]["content"] == "renewal ok"
        assert channel.messages[0]["embed"].description.endswith("until=2026-05-25 08:00")
        assert user.dms[0]["embed"].description == "days=31; until=2026-05-25 08:00"

    asyncio.run(scenario())


def test_advance_renewal_does_not_charge_when_persisted_end_date_is_expired(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        monkeypatch.setattr(privateroom_cog, "datetime", FrozenDatetime)

        user = FakeUser()
        channel = FakeChannel()
        active_room = {
            "room_id": channel.id,
            "user_id": user.id,
            "end_date": datetime(2026, 3, 2, 8, 0, 0),
        }
        persisted_room = {
            **active_room,
            "end_date": datetime(2026, 4, 2, 8, 0, 0),
        }
        cog, events = _build_cog(
            channel=channel,
            active_room=active_room,
            persisted_room=persisted_room,
        )
        interaction = FakeInteraction(user)

        result = await cog.process_advance_renewal(interaction, cost=520)

        assert result is False
        assert events == [
            ("extend", channel.id, datetime(2026, 5, 24, 8, 0, 0)),
        ]
        assert cog.shop_db.transactions == []
        assert interaction.followup.messages[-1]["content"] == "renewal failed"
        assert channel.messages == []
        assert user.dms == []

    asyncio.run(scenario())


def test_setup_shop_sends_components_v2_panel_without_embed(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)

        async def allow_channel(_interaction):
            return True

        monkeypatch.setattr(privateroom_cog, "check_channel_validity", allow_channel)
        monkeypatch.setattr(privateroom_cog.discord, "TextChannel", FakeChannel)

        channel = FakeChannel(id=777, mention="<#777>")
        cog = object.__new__(PrivateRoomCog)
        cog.bot = FakeBot(channel)
        cog.conf = {
            "points_cost": 100,
            "room_duration_days": 30,
            "voice_hours_threshold": 10,
            "booster_discount_hours": 2,
            "max_rooms": 40,
        }
        cog.db = FakeSetupPrivateRoomDB()

        async def verify_shop_messages():
            return 0

        cog.verify_shop_messages = verify_shop_messages
        interaction = FakeInteraction(FakeUser())

        await PrivateRoomCog.setup_shop.callback(cog, interaction, channel)

        assert interaction.response.deferred == [{"ephemeral": True}]
        assert channel.messages[0]["embed"] is None
        view = channel.messages[0]["view"]
        assert view.has_components_v2() is True
        assert view.to_components()[0]["components"][1]["type"] == 14
        assert cog.db.saved_shop_messages == [(777, 9001)]
        assert interaction.followup.messages[-1]["content"] == "setup in <#777>"

    asyncio.run(scenario())
