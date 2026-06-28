import ast
from pathlib import Path
from types import SimpleNamespace

from bot.cogs.achievement.views import RankView
from bot.cogs.privateroom.modals import PurchaseModal
from bot.cogs.privateroom.views import PrivateRoomShopView
from bot.cogs.welcome.views import WelcomeDMView
from bot.utils import achievement_visibility


ACHIEVEMENT_RANK_TEXT = {
    "achievements.rank.all_button_label": "🟣 All rankings",
    "achievements.rank.type_button_labels.reaction": "🔴 Reactions",
    "achievements.rank.type_button_labels.message": "🟡 Messages",
    "achievements.rank.type_button_labels.time_spent": "🔵 Voice",
    "achievements.rank.type_button_labels.checkin_sum": "🟠 Checkins",
    "achievements.rank.type_button_labels.checkin_combo": "🟢 Streaks",
}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


PRIVATEROOM_TEXT = {
    "privateroom.messages.modal_title": "Purchase confirm",
    "privateroom.messages.modal_label": "Type yes",
    "privateroom.messages.modal_placeholder": "yes",
    "privateroom.messages.renewal_modal_title": "Renew confirm",
    "privateroom.messages.renewal_modal_label": "Type renew",
    "privateroom.messages.renewal_modal_placeholder": "renew",
    "privateroom.messages.shop_button_label": "Buy room",
    "privateroom.messages.shop_renewal_button_label": "Renew room",
    "privateroom.messages.shop_restore_button_label": "Restore room",
    "privateroom.messages.shop_title": "Room shop",
    "privateroom.messages.shop_description": (
        "cost={points_cost}; duration={duration}; hours={hours_threshold}; "
        "booster={booster_hours}; available={available_rooms}/{max_rooms}"
    ),
    "privateroom.messages.shop_footer": "Rooms expire automatically.",
}


def _modal_label_text(modal, component):
    return next(
        child.text for child in modal.children
        if getattr(child, "component", None) is component
    )


def test_privateroom_purchase_modal_text_comes_from_locale(monkeypatch):
    monkeypatch.setattr(
        "bot.cogs.privateroom.modals.t",
        lambda key, **kwargs: PRIVATEROOM_TEXT[key],
    )
    cog = SimpleNamespace(conf={})

    purchase_modal = PurchaseModal(cog=cog, cost=100, balance=200)
    renewal_modal = PurchaseModal(cog=cog, cost=100, balance=200, is_renewal=True)

    assert purchase_modal.title == "Purchase confirm"
    assert _modal_label_text(purchase_modal, purchase_modal.confirmation) == "Type yes"
    assert purchase_modal.confirmation.placeholder == "yes"
    assert renewal_modal.title == "Renew confirm"
    assert _modal_label_text(renewal_modal, renewal_modal.confirmation) == "Type renew"
    assert renewal_modal.confirmation.placeholder == "renew"


def test_privateroom_shop_panel_uses_components_v2_with_separator(monkeypatch):
    monkeypatch.setattr(
        "bot.cogs.privateroom.views.t",
        lambda key, **kwargs: PRIVATEROOM_TEXT[key],
    )
    cog = SimpleNamespace(
        bot=SimpleNamespace(user=SimpleNamespace(avatar=None)),
        conf={
            "points_cost": 100,
            "room_duration_days": 30,
            "voice_hours_threshold": 10,
            "booster_discount_hours": 2,
            "max_rooms": 40,
        },
    )

    view = PrivateRoomShopView(cog, available_rooms=33)
    payload = view.to_components()
    container = payload[0]

    assert view.has_components_v2() is True
    assert container["type"] == 17
    assert container["components"][0]["content"].startswith("### Room shop")
    assert container["components"][1]["type"] == 14
    assert container["components"][1]["divider"] is True
    assert container["components"][2]["content"] == "-# Rooms expire automatically."
    assert [button["label"] for button in container["components"][3]["components"]] == [
        "Buy room",
        "Renew room",
        "Restore room",
    ]


def test_welcome_dm_button_text_comes_from_locale(monkeypatch):
    monkeypatch.setattr(
        "bot.cogs.welcome.views.t",
        lambda key, **kwargs: "Member #{member_count}".format(**kwargs),
    )

    view = WelcomeDMView(member_count=42)

    assert view.children[0].label == "Member #42"


def test_achievement_rank_buttons_come_from_locale(monkeypatch):
    monkeypatch.setattr(
        "bot.cogs.achievement.views.t",
        lambda key, **kwargs: ACHIEVEMENT_RANK_TEXT[key],
    )
    monkeypatch.setattr(
        "bot.cogs.achievement.rank_locale.t",
        lambda key, **kwargs: ACHIEVEMENT_RANK_TEXT[key],
    )
    monkeypatch.setattr(
        "bot.cogs.achievement.views.config.get_config",
        lambda name: {"achievements_ranking_emoji": [":first_place:"]},
    )

    achievement_cog = SimpleNamespace(
        get_visible_achievement_rankings=lambda: [{"type": "reaction"}],
        get_visible_achievement_type_names=lambda: {"reaction": "Reaction"},
    )
    bot = SimpleNamespace(get_cog=lambda name: achievement_cog)

    view = RankView(bot=bot, year=None, month=None, all_rankings={})

    assert view.all_button.label == "All rankings"
    assert str(view.all_button.emoji) == "🟣"
    assert view.type_buttons[0].label == "Reactions"
    assert str(view.type_buttons[0].emoji) == "🔴"


def test_modal_text_inputs_use_discord_27_label_wrappers():
    offenders = []
    for path in sorted((PROJECT_ROOT / "bot").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_text_input = (
                isinstance(func, ast.Attribute) and func.attr == "TextInput"
            ) or (
                isinstance(func, ast.Name) and func.id == "TextInput"
            )
            if is_text_input and any(keyword.arg == "label" for keyword in node.keywords):
                offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}")

    assert offenders == []


def test_giveaway_achievement_type_is_retired_even_when_giveaway_feature_is_enabled(monkeypatch):
    monkeypatch.setattr(
        achievement_visibility.config,
        "is_feature_enabled",
        lambda feature_name, default=True: feature_name != "shop",
    )

    hidden_types = achievement_visibility.resolve_hidden_achievement_types()

    assert "giveaway" in hidden_types
    assert "checkin_sum" in hidden_types
    assert "checkin_combo" in hidden_types
    assert achievement_visibility.filter_visible_achievement_rankings(
        [
            {"type": "message", "name": "Messages"},
            {"type": "giveaway", "name": "Giveaways"},
            {"type": "checkin_sum", "name": "Checkins"},
        ],
        hidden_types,
    ) == [
        {"type": "message", "name": "Messages"},
    ]
