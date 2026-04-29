from bot.utils.i18n import t


def rank_type_button_labels() -> dict[str, str]:
    return {
        'reaction': t('achievements.rank.type_button_labels.reaction'),
        'message': t('achievements.rank.type_button_labels.message'),
        'time_spent': t('achievements.rank.type_button_labels.time_spent'),
        'giveaway': t('achievements.rank.type_button_labels.giveaway'),
        'checkin_sum': t('achievements.rank.type_button_labels.checkin_sum'),
        'checkin_combo': t('achievements.rank.type_button_labels.checkin_combo'),
    }


def rank_intro_type_buttons() -> dict[str, str]:
    return {
        'reaction': t('achievements.rank.intro_type_buttons.reaction'),
        'message': t('achievements.rank.intro_type_buttons.message'),
        'time_spent': t('achievements.rank.intro_type_buttons.time_spent'),
        'giveaway': t('achievements.rank.intro_type_buttons.giveaway'),
        'checkin_sum': t('achievements.rank.intro_type_buttons.checkin_sum'),
        'checkin_combo': t('achievements.rank.intro_type_buttons.checkin_combo'),
    }
