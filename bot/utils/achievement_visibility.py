from collections.abc import Mapping, Sequence
from typing import Any

from .config import config


FEATURE_LINKED_ACHIEVEMENT_TYPES = {
    'giveaway': {'giveaway'},
    'shop': {'checkin_sum', 'checkin_combo'},
}


def resolve_hidden_achievement_types() -> set[str]:
    hidden_types: set[str] = set()
    for feature_name, achievement_types in FEATURE_LINKED_ACHIEVEMENT_TYPES.items():
        if not config.is_feature_enabled(feature_name):
            hidden_types.update(achievement_types)
    return hidden_types


def is_achievement_type_visible(
    achievement_type: str | None,
    hidden_types: set[str] | None = None,
) -> bool:
    if achievement_type is None:
        return True
    hidden_types = hidden_types if hidden_types is not None else resolve_hidden_achievement_types()
    return achievement_type not in hidden_types


def filter_visible_achievements(
    achievements: Sequence[Mapping[str, Any]],
    hidden_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    hidden_types = hidden_types if hidden_types is not None else resolve_hidden_achievement_types()
    return [
        dict(achievement)
        for achievement in achievements
        if is_achievement_type_visible(achievement.get('type'), hidden_types)
    ]


def filter_visible_achievement_rankings(
    rankings: Sequence[Mapping[str, Any]],
    hidden_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    hidden_types = hidden_types if hidden_types is not None else resolve_hidden_achievement_types()
    return [
        dict(ranking)
        for ranking in rankings
        if is_achievement_type_visible(ranking.get('type'), hidden_types)
    ]


def filter_visible_achievement_type_names(
    type_names: Mapping[str, str],
    hidden_types: set[str] | None = None,
) -> dict[str, str]:
    hidden_types = hidden_types if hidden_types is not None else resolve_hidden_achievement_types()
    return {
        achievement_type: label
        for achievement_type, label in type_names.items()
        if is_achievement_type_visible(achievement_type, hidden_types)
    }


def filter_visible_role_types(
    role_types: Sequence[Mapping[str, Any]],
    hidden_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    hidden_types = hidden_types if hidden_types is not None else resolve_hidden_achievement_types()
    return [
        dict(role_type)
        for role_type in role_types
        if is_achievement_type_visible(role_type.get('type'), hidden_types)
    ]
