import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

from bot.cogs.shop import modals as shop_modals
from bot.cogs.shop import views as shop_views
from bot.cogs.shop.modals import CheckinMakeupModal
from bot.cogs.shop.views import CheckinEmbedView


SHOP_TEXT = {
    "shop.checkin_button_daily_text": "Daily",
    "shop.checkin_button_makeup_text": "Makeup",
    "shop.checkin_button_query_text": "Query",
    "shop.checkin_embed_title": "Checkin panel {date}",
    "shop.checkin_embed_description": "Panel intro",
    "shop.checkin_embed_count_field": "Count",
    "shop.checkin_embed_first_field": "First",
    "shop.checkin_embed_no_checkin": "none",
    "shop.checkin_embed_footer": "Panel footer",
    "shop.checkin_daily_not_in_voice_private": "not in voice",
    "shop.checkin_daily_success_private": "daily reward {reward}",
    "shop.checkin_daily_already_private": "already checked",
    "shop.checkin_private_embed_title": "Checkin {user_name}",
    "shop.checkin_embed_balance": "balance={balance}",
    "shop.checkin_embed_streak": "streak={streak}",
    "shop.checkin_embed_max_streak": "max={max_streak}",
    "shop.checkin_footer": "reward={reward}",
    "shop.makeup_checkin_no_quota_description": "no quota {limit}",
    "shop.makeup_checkin_no_missed_days_description": "no missed days",
    "shop.makeup_checkin_insufficient_balance_description": "need {cost}, balance {balance}",
    "shop.makeup_modal_title": "Makeup confirm",
    "shop.makeup_modal_info_label": "Makeup info",
    "shop.makeup_modal_info_format": "remaining={remaining}; total={total}; cost={cost}; balance={balance}",
    "shop.makeup_modal_confirm_label": "Confirm",
    "shop.makeup_modal_confirm_placeholder": "type yes",
    "shop.makeup_modal_invalid_confirm": "invalid confirm",
    "shop.makeup_modal_success_private": "makeup {date} cost {cost}",
}


class FakeResponse:
    def __init__(self, events):
        self.events = events
        self.messages = []
        self.modals = []
        self.deferred = []

    async def send_message(self, content=None, *, embed=None, ephemeral=False, **kwargs):
        self.events.append(("response", content))
        self.messages.append({
            "content": content,
            "embed": embed,
            "ephemeral": ephemeral,
            **kwargs,
        })

    async def send_modal(self, modal):
        self.events.append(("modal", type(modal).__name__))
        self.modals.append(modal)

    async def defer(self, *, ephemeral=False, **kwargs):
        self.events.append(("defer", ephemeral))
        self.deferred.append({"ephemeral": ephemeral, **kwargs})


class FakeFollowup:
    def __init__(self, events):
        self.events = events
        self.messages = []

    async def send(self, content=None, *, embed=None, ephemeral=False, **kwargs):
        self.events.append(("followup", content))
        self.messages.append({
            "content": content,
            "embed": embed,
            "ephemeral": ephemeral,
            **kwargs,
        })


class FakeInteraction:
    def __init__(self, user, events):
        self.user = user
        self.response = FakeResponse(events)
        self.followup = FakeFollowup(events)


@dataclass
class FakeUser:
    id: int = 123
    display_name: str = "Zoyo"
    name: str = "zoyo_raw"
    avatar: object | None = None
    voice: object | None = field(default_factory=lambda: SimpleNamespace(channel=SimpleNamespace(id=77)))


class FakeShopDB:
    def __init__(
            self,
            events,
            *,
            checkin_result=None,
            balance=100,
            remaining_count=1,
            missed_date="2026-04-22",
            makeup_success=True,
    ):
        self.events = events
        self.checkin_result = checkin_result or {
            "already_checked_in": False,
            "streak": 3,
            "max_streak": 5,
        }
        self.balance = balance
        self.remaining_count = remaining_count
        self.missed_date = missed_date
        self.makeup_success = makeup_success
        self.transactions = []

    async def record_checkin(self, user_id):
        self.events.append(("record_checkin", user_id))
        return self.checkin_result

    async def update_user_balance_with_record(self, user_id, amount, operation_type, operator_id, note):
        self.events.append(("charge", user_id, amount, operation_type, note))
        self.transactions.append((user_id, amount, operation_type, operator_id, note))
        self.balance += amount
        return self.balance

    async def get_user_balance(self, user_id):
        self.events.append(("balance", user_id))
        return self.balance

    async def get_checkin_status(self, user_id):
        self.events.append(("status", user_id))
        return {
            "streak": self.checkin_result.get("streak", 0),
            "max_streak": self.checkin_result.get("max_streak", 0),
            "last_checkin": "2026-04-23",
        }

    async def get_remaining_makeup_count(self, user_id):
        self.events.append(("remaining_makeup", user_id))
        return self.remaining_count

    async def find_latest_missed_checkin(self, user_id):
        self.events.append(("missed_date", user_id))
        return self.missed_date

    async def add_makeup_record(self, user_id, missed_date):
        self.events.append(("add_makeup", user_id, missed_date))
        return self.makeup_success


class FakeShopCog:
    def __init__(self, events):
        self.events = events

    async def update_checkin_embeds_after_checkin(self, user_id):
        self.events.append(("refresh_embeds", user_id))


def _install_translations(monkeypatch):
    monkeypatch.setattr(shop_views, "t", lambda key, **kwargs: SHOP_TEXT[key])
    monkeypatch.setattr(shop_modals, "t", lambda key, **kwargs: SHOP_TEXT[key])


def _build_checkin_view(events, db):
    return CheckinEmbedView(
        cog=FakeShopCog(events),
        bot=SimpleNamespace(user=SimpleNamespace(avatar=None)),
        db=db,
        conf={
            "checkin_daily_reward": 20,
            "makeup_checkin_limit_per_month": 2,
            "makeup_checkin_cost": 50,
            "checkin_embed_color": "FFD700",
        },
    )


async def _click(view, custom_id, interaction):
    button = next(
        child for child in view.walk_children()
        if getattr(child, "custom_id", None) == custom_id
    )
    await button.callback(interaction)


def test_daily_checkin_requires_voice_channel(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeShopDB(events)
        view = _build_checkin_view(events, db)
        interaction = FakeInteraction(FakeUser(voice=None), events)

        await _click(view, "checkin_daily", interaction)

        assert interaction.response.messages == [
            {"content": "not in voice", "embed": None, "ephemeral": True},
        ]
        assert events == [("response", "not in voice")]
        assert db.transactions == []

    asyncio.run(scenario())


def test_daily_checkin_responds_before_refreshing_panel(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeShopDB(events, balance=100)
        view = _build_checkin_view(events, db)
        interaction = FakeInteraction(FakeUser(), events)

        await _click(view, "checkin_daily", interaction)

        assert events == [
            ("record_checkin", 123),
            ("charge", 123, 20, "checkin", "Daily check-in (streak: 3)"),
            ("response", "daily reward 20"),
            ("refresh_embeds", 123),
        ]
        assert db.transactions[0][1] == 20
        assert interaction.response.messages[0]["ephemeral"] is True
        embed = interaction.response.messages[0]["embed"]
        assert embed.title == "Checkin Zoyo"
        assert [field.value for field in embed.fields] == [
            "balance=120",
            "streak=3",
            "max=5",
        ]

    asyncio.run(scenario())


def test_makeup_button_opens_modal_without_charging(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeShopDB(events, balance=80, remaining_count=1, missed_date="2026-04-22")
        view = _build_checkin_view(events, db)
        interaction = FakeInteraction(FakeUser(), events)

        await _click(view, "checkin_makeup", interaction)

        assert events == [
            ("remaining_makeup", 123),
            ("missed_date", 123),
            ("balance", 123),
            ("modal", "CheckinMakeupModal"),
        ]
        assert isinstance(interaction.response.modals[0], CheckinMakeupModal)
        assert db.transactions == []

    asyncio.run(scenario())


def test_makeup_modal_charges_after_recording_makeup(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeShopDB(events, balance=80, makeup_success=True)
        modal = CheckinMakeupModal(
            db=db,
            user_id=123,
            conf={"makeup_checkin_limit_per_month": 2},
            remaining_count=1,
            balance=80,
            cost=50,
            missed_date="2026-04-22",
        )
        modal.confirm_field._value = "yes"
        interaction = FakeInteraction(FakeUser(), events)

        await modal.on_submit(interaction)

        assert events == [
            ("defer", True),
            ("balance", 123),
            ("add_makeup", 123, "2026-04-22"),
            ("charge", 123, -50, "makeup_checkin", "Makeup check-in for 2026-04-22"),
            ("followup", "makeup 2026-04-22 cost 50"),
        ]
        assert db.transactions[0][1] == -50
        assert interaction.followup.messages[0]["ephemeral"] is True

    asyncio.run(scenario())


def test_makeup_modal_does_not_charge_when_makeup_record_fails(monkeypatch):
    async def scenario():
        _install_translations(monkeypatch)
        events = []
        db = FakeShopDB(events, balance=80, makeup_success=False)
        modal = CheckinMakeupModal(
            db=db,
            user_id=123,
            conf={"makeup_checkin_limit_per_month": 2},
            remaining_count=1,
            balance=80,
            cost=50,
            missed_date="2026-04-22",
        )
        modal.confirm_field._value = "yes"
        interaction = FakeInteraction(FakeUser(), events)

        await modal.on_submit(interaction)

        assert events == [
            ("defer", True),
            ("balance", 123),
            ("add_makeup", 123, "2026-04-22"),
            ("followup", "no quota 2"),
        ]
        assert db.transactions == []
        assert interaction.followup.messages[0]["ephemeral"] is True

    asyncio.run(scenario())
