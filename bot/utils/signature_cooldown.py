from typing import Any, Mapping


DEFAULT_SIGNATURE_MAX_CHANGES = 3
DEFAULT_SIGNATURE_COOLDOWN_DAYS = 7


def resolve_signature_cooldown_days(signature_config: Mapping[str, Any]) -> int:
    return normalize_signature_cooldown_days(signature_config.get("cooldown_days"))


def normalize_signature_cooldown_days(value: Any) -> int:
    return _positive_int(value, DEFAULT_SIGNATURE_COOLDOWN_DAYS)


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
