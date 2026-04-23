#!/usr/bin/env python3
"""Static locale-key consistency checker (P1-4 companion).

Walks ``bot/cogs/*.py`` for two patterns and cross-references their keys
against the YAML locale files under ``bot/locales/zh_CN/``:

1. ``t('cog.path')`` / ``t("cog.path")`` — runtime i18n calls handled by
   ``bot.utils.i18n.t``. Each key must resolve to a string leaf in the
   corresponding ``bot/locales/<lang>/<cog>.yaml``.

2. ``locale_str("english", key="cog.path")`` — slash-command metadata
   keys resolved by ``bot.utils.slash_translator.SlashTranslator``. Each
   key must resolve to a string leaf in ``bot/locales/<lang>/commands.yaml``.

For each lang directory under ``bot/locales/`` the checker reports:

* ``MISSING`` — a cog references a key that the locale file does not
  provide (a string leaf). These become runtime ``KeyError`` (for ``t()``)
  or ``Slash translator miss`` warnings at ``tree.sync`` time.
* ``ORPHAN`` — a locale string is not referenced by any cog. Informational;
  dead translations cost maintenance but don't break anything.

Dynamic lookups (``t(key_from_variable)``, conditional ternaries inside
the call) are *not* visited. The regex-based extractor only catches
literal string arguments — treat the output as a high-confidence
lower bound.

Exit 0 if no ``MISSING`` entries, 1 otherwise. Run from repo root:

    python tools/check_locales.py
    python tools/check_locales.py --lang zh_CN --verbose
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from ruamel.yaml import YAML


REPO_ROOT = Path(__file__).resolve().parent.parent
COGS_DIR = REPO_ROOT / 'bot' / 'cogs'
LOCALES_DIR = REPO_ROOT / 'bot' / 'locales'


# Conservative patterns — literal string only. Dynamic / ternary variants
# are intentionally not captured; see module docstring.
_T_CALL_RE = re.compile(r"""(?<![\w.])t\(\s*(['"])([^'"]+)\1""")
_LOCALE_STR_KEY_RE = re.compile(
    r'locale_str\(\s*(["\'])(?:[^"\'\\]|\\.)*\1\s*,\s*key=\s*(["\'])([^"\']+)\2'
)


def extract_cog_keys() -> Tuple[Set[str], Set[str]]:
    """Return (t_keys, locale_str_keys) found across ``bot/cogs/*.py``."""
    t_keys: Set[str] = set()
    loc_keys: Set[str] = set()
    for path in sorted(COGS_DIR.glob('*.py')):
        src = path.read_text(encoding='utf-8')
        for m in _T_CALL_RE.finditer(src):
            key = m.group(2)
            if '.' in key:
                t_keys.add(key)
        for m in _LOCALE_STR_KEY_RE.finditer(src):
            key = m.group(3)
            if '.' in key:
                loc_keys.add(key)
    return t_keys, loc_keys


def load_locale_leaves(path: Path) -> Set[str]:
    """Return every dot-path that resolves to a string leaf in ``path``.

    Non-string leaves (lists, sub-dicts) are ignored since ``t()`` and
    ``locale_str`` both expect string terminal nodes.
    """
    yaml = YAML(typ='rt')
    with path.open(encoding='utf-8') as f:
        tree = yaml.load(f) or {}
    leaves: Set[str] = set()

    def walk(node: object, prefix: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{prefix}.{k}" if prefix else str(k))
        elif isinstance(node, str):
            leaves.add(prefix)

    walk(tree, '')
    return leaves


def collect_locale_leaves(lang_dir: Path) -> Dict[str, Set[str]]:
    """Map ``cog_name`` (yaml file stem) -> set of fully-qualified dot-paths."""
    result: Dict[str, Set[str]] = {}
    for yaml_path in sorted(lang_dir.glob('*.yaml')):
        name = yaml_path.stem  # e.g. 'ban' or 'commands'
        leaves = load_locale_leaves(yaml_path)
        result[name] = {f"{name}.{p}" for p in leaves}
    return result


def _report(name: str, missing: Iterable[str], orphan: Iterable[str],
            verbose: bool) -> int:
    missing_list = sorted(missing)
    orphan_list = sorted(orphan)

    if missing_list:
        print(f"  MISSING in {name}: {len(missing_list)}")
        for k in missing_list:
            print(f"    - {k}")
    elif verbose:
        print(f"  {name}: OK")

    if orphan_list and verbose:
        print(f"  ORPHAN in {name}: {len(orphan_list)} (info)")
        for k in orphan_list:
            print(f"    ~ {k}")

    return len(missing_list)


def check(lang: str, verbose: bool = False) -> int:
    """Run the check against ``bot/locales/<lang>/``.

    Returns the total number of MISSING keys across both t() and
    locale_str groups (0 = clean).
    """
    lang_dir = LOCALES_DIR / lang
    if not lang_dir.is_dir():
        print(f"locale dir not found: {lang_dir}", file=sys.stderr)
        return 1

    print(f"Scanning cogs under {COGS_DIR}…")
    t_keys, loc_keys = extract_cog_keys()
    print(f"  t() keys        : {len(t_keys)}")
    print(f"  locale_str keys : {len(loc_keys)}")

    print(f"\nLoading locale leaves from {lang_dir}…")
    leaves_by_file = collect_locale_leaves(lang_dir)

    total_missing = 0

    # --- t() side: per-cog lookup across cog-named YAML files ----------
    print("\nChecking t() keys against per-cog locale files:")
    by_ns: Dict[str, Set[str]] = {}
    for k in t_keys:
        ns = k.split('.', 1)[0]
        by_ns.setdefault(ns, set()).add(k)

    for ns in sorted(by_ns):
        available = leaves_by_file.get(ns, set())
        missing = by_ns[ns] - available
        orphan = available - by_ns[ns] if ns in leaves_by_file else set()
        total_missing += _report(f'{ns}.yaml', missing, orphan, verbose)

    referenced_namespaces = set(by_ns)
    for ns in sorted(leaves_by_file):
        if ns == 'commands':
            continue
        if ns not in referenced_namespaces:
            print(f"  NOTE: {ns}.yaml has no t() references "
                  f"({len(leaves_by_file[ns])} entries)")

    # --- locale_str side: commands.yaml holds every key ----------------
    print("\nChecking locale_str keys against commands.yaml:")
    cmd_leaves = leaves_by_file.get('commands', set())
    # commands.yaml keys are stored namespaced with a 'commands.' prefix
    # (load_locale_leaves prefixes with the file stem); strip it for the
    # comparison because locale_str keys don't have that prefix.
    cmd_available = {k.partition('.')[2] for k in cmd_leaves}
    loc_missing = loc_keys - cmd_available
    loc_orphan = cmd_available - loc_keys
    total_missing += _report('commands.yaml', loc_missing, loc_orphan,
                             verbose)

    if total_missing:
        print(f"\nRESULT: {total_missing} MISSING key(s). ❌")
    else:
        print("\nRESULT: All referenced keys are present. ✅")
    return total_missing


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument(
        '--lang', default='zh_CN',
        help="Locale to check (default: zh_CN).",
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help="Also list ORPHAN entries and OK namespaces.",
    )
    args = parser.parse_args(argv)
    return 1 if check(args.lang, verbose=args.verbose) else 0


if __name__ == '__main__':
    sys.exit(main())
