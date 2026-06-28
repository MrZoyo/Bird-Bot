from bot.utils.i18n import t


RANK_BUTTON_EMOJIS = {
    'all': '🟣',
    'reaction': '🔴',
    'message': '🟡',
    'time_spent': '🔵',
    'checkin_sum': '🟠',
    'checkin_combo': '🟢',
}


def rank_button_parts(achievement_type: str, label: str) -> tuple[str | None, str]:
    """Return the canonical button emoji and a clean text label.

    Locale/config values may already include the colored circle prefix. The
    Discord button has a first-class emoji field, so strip that prefix from the
    label to avoid rendering duplicate circles.
    """
    emoji = RANK_BUTTON_EMOJIS.get(achievement_type)
    if not emoji:
        return None, label

    label = label.strip()
    for known_emoji in RANK_BUTTON_EMOJIS.values():
        prefix = f'{known_emoji} '
        if label.startswith(prefix):
            return emoji, label[len(prefix):]
        if label == known_emoji:
            return emoji, ''

    return emoji, label


def rank_button_display_name(achievement_type: str, label: str) -> str:
    emoji, clean_label = rank_button_parts(achievement_type, label)
    return f'{emoji} {clean_label}' if emoji else clean_label


def rank_type_button_labels() -> dict[str, str]:
    return {
        'reaction': t('achievements.rank.type_button_labels.reaction'),
        'message': t('achievements.rank.type_button_labels.message'),
        'time_spent': t('achievements.rank.type_button_labels.time_spent'),
        'checkin_sum': t('achievements.rank.type_button_labels.checkin_sum'),
        'checkin_combo': t('achievements.rank.type_button_labels.checkin_combo'),
    }


def rank_intro_type_buttons() -> dict[str, str]:
    return {
        'reaction': t('achievements.rank.intro_type_buttons.reaction'),
        'message': t('achievements.rank.intro_type_buttons.message'),
        'time_spent': t('achievements.rank.intro_type_buttons.time_spent'),
        'checkin_sum': t('achievements.rank.intro_type_buttons.checkin_sum'),
        'checkin_combo': t('achievements.rank.intro_type_buttons.checkin_combo'),
    }
