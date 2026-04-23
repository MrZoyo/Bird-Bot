# bot/utils/slash_translator.py
"""Slash command metadata translator (P1-7).

Discord's slash-command framework supports per-client localization by
attaching a ``Translator`` to the :class:`discord.app_commands.CommandTree`.
The client picks translations at runtime based on the viewer's Discord
language setting — orthogonal to ``bot.utils.i18n.t()``, which resolves
*response* text in the server-wide ``main.locale``.

Design choices (see REFACTORING_PLAN.md §P1-7):

* Only ``description`` / parameter descriptions are localized. Command
  ``name`` fields stay English because Discord enforces a strict charset
  (lowercase ASCII / digits / ``_`` / ``-``), and Chinese names would be
  rejected at registration. Accordingly, ``command_name`` / ``group_name``
  / ``parameter_name`` / ``choice_name`` contexts all return ``None``.
* Only ``zh_CN`` is delivered in the first cut (P1-6 decision B2). Any
  other Discord locale returns ``None`` so Discord falls back to the
  ``locale_str`` message (which we keep as the English literal).
* Call sites pass ``locale_str("english text", key="cog.command.field")``:
  ``message`` is the English fallback Discord shows to non-zh-CN clients;
  ``extras['key']`` is the dot-path into ``commands.yaml``. Strings that
  arrive without a ``key`` extra are skipped (no lookup attempted).
* Misses log a warning exactly once per (lang, key) pair to surface
  translation gaps without flooding logs; the translator itself still
  returns ``None`` so Discord's fallback kicks in.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Set, Tuple

from discord import Locale
from discord.app_commands import (
    Translator,
    TranslationContextLocation,
    locale_str,
)

from bot.utils.config import config


logger = logging.getLogger(__name__)


# Discord Locale -> repository locale slug. PLAN explicitly scopes this
# to zh-CN only; new languages later map Discord code to repo slug here.
_LOCALE_MAP: Dict[Locale, str] = {
    Locale.chinese: 'zh_CN',
}


# Contexts that reference command identifiers rather than user-facing
# prose. Discord rejects non-ASCII in these fields, so we never try to
# translate them.
_NAME_LIKE_CONTEXTS: Set[TranslationContextLocation] = {
    TranslationContextLocation.command_name,
    TranslationContextLocation.group_name,
    TranslationContextLocation.parameter_name,
    TranslationContextLocation.choice_name,
}


class SlashTranslator(Translator):
    """Resolve ``locale_str`` keys against ``bot/locales/<lang>/commands.yaml``."""

    def __init__(self) -> None:
        super().__init__()
        # One-shot miss dedup: avoid repeat warnings for the same key on
        # every subsequent command tree sync.
        self._warned: Set[Tuple[str, str]] = set()

    async def translate(
        self,
        string: locale_str,
        locale: Locale,
        context: Any,
    ) -> Optional[str]:
        if context.location in _NAME_LIKE_CONTEXTS:
            return None

        lang = _LOCALE_MAP.get(locale)
        if lang is None:
            return None

        key = string.extras.get('key') if isinstance(string.extras, dict) else None
        if not isinstance(key, str) or '.' not in key:
            # Without a lookup key we can't translate; Discord will use
            # the English string.message as-is. This is the expected path
            # for any locale_str(...) the decorator set without key=...
            return None

        namespace, _, rest = key.partition('.')
        tree = config.get_locale('commands', lang)
        node: Any = tree.get(namespace) if isinstance(tree, dict) else None
        for segment in rest.split('.'):
            if not isinstance(node, dict) or segment not in node:
                self._warn_once(lang, key, reason='key not found')
                return None
            node = node[segment]

        if not isinstance(node, str):
            self._warn_once(lang, key, reason='value is not a string')
            return None
        return node

    def _warn_once(self, lang: str, key: str, *, reason: str) -> None:
        ident = (lang, key)
        if ident in self._warned:
            return
        self._warned.add(ident)
        logger.warning(
            "Slash translator miss (%s): key=%r lang=%s", reason, key, lang
        )
