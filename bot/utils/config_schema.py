# bot/utils/config_schema.py
"""Dataclass-based config schemas + validation (P1-4).

This module owns the source of truth for config shape / required keys /
default values. ``bot.utils.config`` delegates to it during startup so the
actual YAML load path stays small.

Design notes:

* **Tolerant**. Missing required keys log a warning and the field is left
  as ``None`` (same behavior as the pre-schema ``_verify_main_config``);
  we don't raise, because a half-configured bot should still boot far
  enough for an operator to see what's missing in logs. The one
  exception is wrong-type values, which we also warn about without
  coercing — mismatched types are more likely a misconfigured YAML than
  a valid older deploy.
* **Schemas live next to their data, not in the loader.** Adding a new
  config means adding a dataclass here, not touching ``config.py``.
* **Dataclass-only (no pydantic).** We want zero new runtime deps and
  keep the validator a pure-Python helper. IDE hints + type-check come
  for free; runtime enforcement is handled by the ``validate_*``
  functions below.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---- Main config ---------------------------------------------------------


@dataclass
class MainConfig:
    """Schema for ``bot/config/main.yaml``.

    Required fields (``token``, ``logging_file``, ``db_path``, ``guild_id``)
    must be present — validation warns if any is missing. Optional fields
    use ``Optional[...] = None`` or ``dataclass.field(default=...)`` with
    runtime defaults applied by :func:`validate_main_config`.
    """

    token: Optional[str] = None
    logging_file: Optional[str] = None
    db_path: Optional[str] = None
    guild_id: Optional[int] = None

    # Optional — present on most real deploys but not strictly required.
    admin_channel_id: Optional[int] = None
    keyword_log_file: Optional[str] = None
    room_log_file: Optional[str] = None

    # Defaulted (P1-6 / P1-5).
    locale: str = 'zh_CN'
    log_backup_count: int = 14

    # Feature toggles (per-cog on/off). Empty dict = all cogs default ON
    # per ``Config.is_feature_enabled(feature, default=True)``.
    features: Dict[str, bool] = field(default_factory=dict)


# Keys the bot cannot sensibly run without.
_MAIN_REQUIRED: List[str] = [
    'token',
    'logging_file',
    'db_path',
    'guild_id',
]

# (key, default_value) pairs whose defaults are applied in-place if the
# key is missing. Ordering matters for readability only.
_MAIN_DEFAULTS: List[tuple] = [
    ('locale', 'zh_CN'),
    ('log_backup_count', 14),
]

# Expected type per key. Only listed when we're confident the wrong type
# is a misconfiguration, not a legacy-format fallback. Values wrapped in
# tuples mean ``isinstance`` accepts any member.
_MAIN_TYPES: Dict[str, Any] = {
    'token': str,
    'logging_file': str,
    'keyword_log_file': str,
    'room_log_file': str,
    'db_path': str,
    'guild_id': int,
    'admin_channel_id': int,
    'locale': str,
    'log_backup_count': int,
    'features': dict,
}


def validate_main_config(data: Dict[str, Any]) -> List[str]:
    """Inspect a loaded ``main.yaml`` dict and return warning strings.

    Side effect: applies defaults from ``_MAIN_DEFAULTS`` in-place (via
    ``setdefault``) and fills ``None`` for missing required keys — both
    preserve the pre-P1-4 behavior callers rely on. The return value is
    a (possibly empty) list of human-readable warnings the loader should
    surface.
    """
    warnings: List[str] = []

    if not isinstance(data, dict):
        return [f"main config is not a mapping: got {type(data).__name__}"]

    for key in _MAIN_REQUIRED:
        if key not in data or data.get(key) in (None, ''):
            warnings.append(
                f"Missing required key '{key}' in main configuration. "
                "Please add it."
            )
            data[key] = None

    for key, default in _MAIN_DEFAULTS:
        data.setdefault(key, default)

    for key, expected in _MAIN_TYPES.items():
        if key not in data or data[key] is None:
            continue
        if not isinstance(data[key], expected):
            warnings.append(
                f"main.{key} has unexpected type "
                f"{type(data[key]).__name__}; expected {expected.__name__}."
            )

    # features dict should map str -> bool; anything else is likely a typo
    # like leaving a flag set to "true" (string) instead of a YAML boolean.
    features = data.get('features')
    if isinstance(features, dict):
        for name, value in features.items():
            if not isinstance(value, bool):
                warnings.append(
                    f"main.features.{name} is not a boolean "
                    f"(got {type(value).__name__}); will be ignored as false."
                )

    return warnings
