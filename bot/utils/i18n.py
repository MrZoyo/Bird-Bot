# bot/utils/i18n.py
"""Runtime i18n resolver for user-facing text.

Usage:
    from bot.utils.i18n import t
    t('role.starsign.aries')                # -> "白羊座"
    t('role.signature.success', name='...')  # -> format_map kwargs

This module resolves a *single* server-wide locale driven by
``main.locale`` (default ``zh_CN``). It is distinct from Discord's
per-client slash-command localization, which is handled under P1-7 via
a ``CommandTree.Translator``; do not route slash metadata through here.

Fallback chain on a missing key:
    <requested lang> -> 'zh_CN' (baseline) -> KeyError

``zh_CN`` is the only delivered language in this PR (P1-6 decision B2),
so for now the chain only performs real fallback when a caller passes
an explicit non-default ``lang=`` and the key is missing there.
"""
from typing import Any, List, Optional

from bot.utils.config import config


def t(key: str, *, lang: Optional[str] = None, **kwargs: Any) -> str:
    """Resolve a dot-path key against the active locale.

    ``key`` is ``'<namespace>.<path>'`` where ``<namespace>`` picks the
    YAML file under ``bot/locales/<lang>/<namespace>.yaml`` and
    ``<path>`` is navigated as nested dict keys. Trailing node must be
    a string.

    ``**kwargs`` is applied via ``str.format_map`` so translators can
    write ``"已为你添加了星座：{name}"`` and callers pass ``name=...``.

    Raises ``KeyError`` (with the dot-path and every tried language)
    when the key resolves to nothing in any language in the fallback
    chain; never returns the raw key as a silent fallback.
    """
    if '.' not in key:
        raise KeyError(f"i18n key {key!r} must be 'namespace.path'")

    namespace, _, rest = key.partition('.')
    path = rest.split('.')

    tried: List[str] = []
    for try_lang in _fallback_chain(lang):
        if try_lang in tried:
            continue
        tried.append(try_lang)
        tree = config.get_locale(namespace, try_lang)
        value = _walk(tree, path)
        if isinstance(value, str):
            return value.format_map(kwargs) if kwargs else value

    raise KeyError(
        f"i18n key {key!r} missing in locales; tried languages: {tried}"
    )


def _fallback_chain(lang: Optional[str]) -> List[str]:
    default = config.get_config('main').get('locale', 'zh_CN')
    requested = lang or default
    return [requested, 'zh_CN']


def _walk(tree: Any, path: List[str]) -> Any:
    node = tree
    for segment in path:
        if not isinstance(node, dict) or segment not in node:
            return None
        node = node[segment]
    return node
