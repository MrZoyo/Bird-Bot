from types import SimpleNamespace

from bot.cogs.shop.modals import BalanceModifyModal, CheckinMakeupModal
from bot.cogs.shop.views import CheckinEmbedView
from bot.cogs.shop.views import TransactionHistoryView


SHOP_TEXT = {
    "shop.makeup_modal_title": "Makeup confirm",
    "shop.makeup_modal_info_label": "Makeup info",
    "shop.makeup_modal_info_format": (
        "remaining={remaining}; total={total}; cost={cost}; balance={balance}"
    ),
    "shop.makeup_modal_confirm_label": "Confirm",
    "shop.makeup_modal_confirm_placeholder": "type yes",
    "shop.modify_balance_modal_title": "Modify {user_name}",
    "shop.modify_balance_amount_label": "Amount",
    "shop.modify_balance_amount_placeholder": "amount placeholder",
    "shop.modify_balance_type_label": "Type",
    "shop.modify_balance_type_placeholder": "type placeholder",
    "shop.modify_balance_reason_label": "Reason",
    "shop.modify_balance_reason_placeholder": "reason placeholder",
    "shop.history_prev_button_emoji": "⬅️",
    "shop.history_next_button_emoji": "➡️",
    "shop.checkin_button_daily_text": "Daily",
    "shop.checkin_button_makeup_text": "Makeup",
    "shop.checkin_button_query_text": "Query",
    "shop.checkin_embed_title": "Checkin {date}",
    "shop.checkin_embed_description": "Intro",
    "shop.checkin_embed_count_field": "Count",
    "shop.checkin_embed_first_field": "First",
    "shop.checkin_embed_no_checkin": "none",
    "shop.checkin_embed_footer": "Footer",
}


def _modal_label_text(modal, component):
    return next(
        child.text for child in modal.children
        if getattr(child, "component", None) is component
    )


def test_makeup_modal_text_comes_from_locale(monkeypatch):
    monkeypatch.setattr("bot.cogs.shop.modals.t", lambda key, **kwargs: SHOP_TEXT[key])

    modal = CheckinMakeupModal(
        db=object(),
        user_id=123,
        conf={"makeup_checkin_limit_per_month": 3},
        remaining_count=2,
        balance=120,
        cost=50,
        missed_date="2026-04-28",
    )

    assert modal.title == "Makeup confirm"
    assert _modal_label_text(modal, modal.info_field) == "Makeup info"
    assert modal.info_field.default == "remaining=2; total=3; cost=50; balance=120"
    assert _modal_label_text(modal, modal.confirm_field) == "Confirm"
    assert modal.confirm_field.placeholder == "type yes"


def test_balance_modify_modal_text_comes_from_locale(monkeypatch):
    monkeypatch.setattr("bot.cogs.shop.modals.t", lambda key, **kwargs: SHOP_TEXT[key])
    target_user = SimpleNamespace(id=123, display_name="Alice")

    modal = BalanceModifyModal(
        db=object(),
        target_user=target_user,
        conf={},
        current_balance=42,
    )

    assert modal.title == "Modify Alice"
    assert _modal_label_text(modal, modal.amount) == "Amount (💰:42)"
    assert modal.amount.placeholder == "amount placeholder"
    assert _modal_label_text(modal, modal.operation_type) == "Type"
    assert modal.operation_type.placeholder == "type placeholder"
    assert _modal_label_text(modal, modal.reason) == "Reason"
    assert modal.reason.placeholder == "reason placeholder"


def test_transaction_history_button_emoji_comes_from_locale(monkeypatch):
    monkeypatch.setattr("bot.cogs.shop.views.t", lambda key, **kwargs: SHOP_TEXT[key])

    view = TransactionHistoryView(
        bot=object(),
        db=object(),
        target_user_id=123,
        viewer_id=456,
        conf={},
    )

    assert str(view.prev_button.emoji) == "⬅️"
    assert str(view.next_button.emoji) == "➡️"


def test_checkin_panel_uses_components_v2_media_and_separators(monkeypatch):
    monkeypatch.setattr("bot.cogs.shop.views.t", lambda key, **kwargs: SHOP_TEXT[key])

    view = CheckinEmbedView(
        cog=object(),
        bot=object(),
        db=object(),
        conf={"checkin_embed_color": "FFD700"},
        panel_date="2026-06-27",
        today_count=12,
        first_user_text="<@1>",
    )
    container = view.to_components()[0]

    assert view.has_components_v2() is True
    assert container["type"] == 17
    assert [component["type"] for component in container["components"]] == [10, 14, 12, 14, 10, 1]
    wide = "\u3000"
    assert f"**Count**{wide * 5}**First**\n12{wide * 10}<@1>" in container["components"][0]["content"]
    assert container["components"][2]["items"][0]["media"]["url"] == "attachment://checkin.png"
    assert [button["label"] for button in container["components"][5]["components"]] == [
        "Daily",
        "Makeup",
        "Query",
    ]


def test_checkin_panel_shows_zero_count_when_empty(monkeypatch):
    monkeypatch.setattr("bot.cogs.shop.views.t", lambda key, **kwargs: SHOP_TEXT[key])

    view = CheckinEmbedView(
        cog=object(),
        bot=object(),
        db=object(),
        conf={"checkin_embed_color": "FFD700"},
        panel_date="2026-06-27",
        today_count=0,
        first_user_text=None,
    )
    container = view.to_components()[0]

    wide = "\u3000"
    assert f"**Count**{wide * 5}**First**\n0{wide * 11}none" in container["components"][0]["content"]
