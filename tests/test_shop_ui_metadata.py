from types import SimpleNamespace

from bot.cogs.shop.modals import BalanceModifyModal, CheckinMakeupModal
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
}


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
    assert modal.info_field.label == "Makeup info"
    assert modal.info_field.default == "remaining=2; total=3; cost=50; balance=120"
    assert modal.confirm_field.label == "Confirm"
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
    assert modal.amount.label == "Amount (💰:42)"
    assert modal.amount.placeholder == "amount placeholder"
    assert modal.operation_type.label == "Type"
    assert modal.operation_type.placeholder == "type placeholder"
    assert modal.reason.label == "Reason"
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
