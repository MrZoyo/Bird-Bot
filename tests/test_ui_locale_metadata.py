from types import SimpleNamespace

from bot.cogs.achievement.views import RankView
from bot.cogs.privateroom.modals import PurchaseModal
from bot.cogs.welcome.views import WelcomeDMView


ACHIEVEMENT_RANK_TEXT = {
    "achievements.rank.all_button_label": "All rankings",
    "achievements.rank.type_button_labels.reaction": "Reactions",
    "achievements.rank.type_button_labels.message": "Messages",
    "achievements.rank.type_button_labels.time_spent": "Voice",
    "achievements.rank.type_button_labels.giveaway": "Giveaways",
    "achievements.rank.type_button_labels.checkin_sum": "Checkins",
    "achievements.rank.type_button_labels.checkin_combo": "Streaks",
}


PRIVATEROOM_TEXT = {
    "privateroom.messages.modal_title": "Purchase confirm",
    "privateroom.messages.modal_label": "Type yes",
    "privateroom.messages.modal_placeholder": "yes",
    "privateroom.messages.renewal_modal_title": "Renew confirm",
    "privateroom.messages.renewal_modal_label": "Type renew",
    "privateroom.messages.renewal_modal_placeholder": "renew",
}


def test_privateroom_purchase_modal_text_comes_from_locale(monkeypatch):
    monkeypatch.setattr(
        "bot.cogs.privateroom.modals.t",
        lambda key, **kwargs: PRIVATEROOM_TEXT[key],
    )
    cog = SimpleNamespace(conf={})

    purchase_modal = PurchaseModal(cog=cog, cost=100, balance=200)
    renewal_modal = PurchaseModal(cog=cog, cost=100, balance=200, is_renewal=True)

    assert purchase_modal.title == "Purchase confirm"
    assert purchase_modal.confirmation.label == "Type yes"
    assert purchase_modal.confirmation.placeholder == "yes"
    assert renewal_modal.title == "Renew confirm"
    assert renewal_modal.confirmation.label == "Type renew"
    assert renewal_modal.confirmation.placeholder == "renew"


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
    assert view.type_buttons[0].label == "Reactions"
