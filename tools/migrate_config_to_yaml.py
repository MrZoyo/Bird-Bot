#!/usr/bin/env python3
"""Migrate bot/config/config_<name>.json → YAML + locale + DB seed.

Per REFACTORING_PLAN.md §P1-6 step 5. Run once on the operator's box
during the upgrade protocol:

    git pull
    uv pip sync requirements.lock
    python tools/migrate_config_to_yaml.py
    # review tools/migration_report.md
    python tools/seed_db.py    # (once step 7 lands this tool)
    # restart bot

Outputs (see PLAN):
  - bot/config/<name>.yaml              (per-cog YAML config)
  - bot/config/<name>.yaml.example      (ID-sanitised template)
  - bot/locales/zh_CN/<name>.yaml       (user-facing text)
  - tools/migration_db_seed.json        (DB-bound fields; gitignored)
  - tools/migration_report.md           (per-field routing; gitignored)

The script is idempotent: rerunning overwrites the YAML / locale
outputs and rewrites the seed + report.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from ruamel.yaml import YAML


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / 'bot' / 'config'
LOCALE_DIR = REPO_ROOT / 'bot' / 'locales' / 'zh_CN'
CLASSIFY_FILE = REPO_ROOT / 'tools' / 'field_classification.yaml'
SEED_FILE = REPO_ROOT / 'tools' / 'migration_db_seed.json'
REPORT_FILE = REPO_ROOT / 'tools' / 'migration_report.md'

ID_KEY_PATTERNS = ('_id', '_ids', 'guild_id', 'channel_id', 'role_id', 'user_id')
LOCALE_KEY_SUFFIXES = (
    '_message',
    '_title',
    '_description',
    '_footer',
    '_label',
    '_text',
    '_button',
    '_placeholder',
    '_hint',
    '_notice',
)


def _new_yaml() -> YAML:
    yaml = YAML(typ='rt')
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    return yaml


def drop_comment_keys(obj: Any) -> Any:
    """Remove JSON ``_comment`` hacks; recurse into dicts / lists."""
    if isinstance(obj, dict):
        return {
            k: drop_comment_keys(v)
            for k, v in obj.items()
            if not k.startswith('_comment')
        }
    if isinstance(obj, list):
        return [drop_comment_keys(v) for v in obj]
    return obj


def load_classification() -> Dict[str, Dict[str, Any]]:
    if not CLASSIFY_FILE.exists():
        return {}
    with open(CLASSIFY_FILE, 'r', encoding='utf-8') as f:
        data = _new_yaml().load(f) or {}
    return {str(k): dict(v or {}) for k, v in data.items()}


def heuristic_is_locale(key: str, value: Any) -> bool:
    if key == 'messages' and isinstance(value, dict):
        return True
    if isinstance(value, str) and any(key.endswith(suf) for suf in LOCALE_KEY_SUFFIXES):
        return True
    return False


def heuristic_is_yaml(value: Any) -> bool:
    if isinstance(value, (bool, int, float)):
        return True
    if value is None:
        return True
    if isinstance(value, list) and all(isinstance(x, (int, float)) for x in value):
        return True
    return False


def sanitize_for_example(obj: Any) -> Any:
    """Replace secrets / IDs with placeholder values for .example output."""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if k == 'token':
                result[k] = 'YOUR_BOT_TOKEN'
                continue
            if any(pat in k for pat in ID_KEY_PATTERNS):
                result[k] = _sanitize_id_like(v)
                continue
            result[k] = sanitize_for_example(v)
        return result
    if isinstance(obj, list):
        return [sanitize_for_example(v) for v in obj]
    return obj


def _sanitize_id_like(v: Any) -> Any:
    if isinstance(v, int):
        return 1145141919810
    if isinstance(v, str) and v.isdigit():
        return '1145141919810'
    if isinstance(v, list):
        return [_sanitize_id_like(x) for x in v]
    return v


def classify_config(
    cog_name: str,
    data: Dict[str, Any],
    classification: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], List[Tuple[str, str, str]]]:
    """Partition a config's top-level keys into (yaml, locale, db, rows).

    `rows` are (key, routing, source) tuples for the migration report.
    Classification entries (lists under `yaml` / `locale` / `db`) take
    precedence over heuristics.
    """
    yaml_part: Dict[str, Any] = {}
    locale_part: Dict[str, Any] = {}
    db_part: Dict[str, Any] = {}
    rows: List[Tuple[str, str, str]] = []

    explicit_yaml: Set[str] = set(classification.get('yaml') or [])
    explicit_locale: Set[str] = set(classification.get('locale') or [])
    explicit_db: Set[str] = set(classification.get('db') or [])

    for key, value in data.items():
        if key in explicit_db:
            db_part[key] = value
            rows.append((key, 'db', 'classification'))
            continue
        if key in explicit_yaml:
            yaml_part[key] = value
            rows.append((key, 'yaml', 'classification'))
            continue
        if key in explicit_locale:
            locale_part[key] = value
            rows.append((key, 'locale', 'classification'))
            continue

        # Heuristics
        if heuristic_is_locale(key, value):
            locale_part[key] = value
            rows.append((key, 'locale', 'heuristic:locale'))
            continue
        if heuristic_is_yaml(value):
            yaml_part[key] = value
            rows.append((key, 'yaml', 'heuristic:scalar'))
            continue
        if isinstance(value, str):
            # String not caught by suffix heuristic, not in classification.
            # Default to locale (user-visible strings dominate this codebase),
            # but flag for review.
            locale_part[key] = value
            rows.append((key, 'locale?', 'heuristic:string-default'))
            continue

        # Dict / list of non-ints that isn't explicitly classified —
        # unclassified, dumped to yaml as a safe default but flagged.
        yaml_part[key] = value
        rows.append((key, 'yaml?', 'heuristic:unclassified'))

    return yaml_part, locale_part, db_part, rows


def dump_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        _new_yaml().dump(data, f)


def migrate_cog(
    cog_name: str,
    json_path: Path,
    classification: Dict[str, Any],
    seed: Dict[str, Any],
    report_rows: List[Tuple[str, str, str, str]],
) -> Dict[str, Any]:
    with open(json_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    clean = drop_comment_keys(raw)

    yaml_part, locale_part, db_part, rows = classify_config(
        cog_name, clean, classification.get(cog_name, {}),
    )

    for key, routing, source in rows:
        report_rows.append((cog_name, key, routing, source))

    if yaml_part:
        dump_yaml(CONFIG_DIR / f'{cog_name}.yaml', yaml_part)
        dump_yaml(
            CONFIG_DIR / f'{cog_name}.yaml.example',
            sanitize_for_example(yaml_part),
        )
    if locale_part:
        dump_yaml(LOCALE_DIR / f'{cog_name}.yaml', locale_part)
    if db_part:
        seed.setdefault(cog_name, {}).update(db_part)

    return {
        'yaml_keys': len(yaml_part),
        'locale_keys': len(locale_part),
        'db_keys': len(db_part),
    }


def write_report(rows: List[Tuple[str, str, str, str]], summary: Dict[str, Dict[str, int]]) -> None:
    lines = [
        '# Config migration report',
        '',
        'Generated by `tools/migrate_config_to_yaml.py`. Review any rows',
        'marked `locale?` or `yaml?` (heuristic guess) and move the field',
        'into `tools/field_classification.yaml` before the second pass.',
        '',
        '## Summary',
        '',
        '| Cog | yaml keys | locale keys | db keys |',
        '|---|---:|---:|---:|',
    ]
    for cog, s in sorted(summary.items()):
        lines.append(
            f"| {cog} | {s['yaml_keys']} | {s['locale_keys']} | {s['db_keys']} |"
        )
    lines += ['', '## Per-field routing', '']
    lines += ['| Cog | Key | Routing | Source |', '|---|---|---|---|']
    for cog, key, routing, source in rows:
        lines.append(f'| {cog} | `{key}` | {routing} | {source} |')

    REPORT_FILE.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--only',
        nargs='+',
        help="Restrict migration to the named cogs (e.g. --only spymode welcome)",
    )
    args = parser.parse_args()

    classification = load_classification()
    seed: Dict[str, Any] = {}
    report_rows: List[Tuple[str, str, str, str]] = []
    summary: Dict[str, Dict[str, int]] = {}

    json_files = sorted(CONFIG_DIR.glob('config_*.json'))
    if args.only:
        wanted = set(args.only)
        json_files = [p for p in json_files if p.stem.removeprefix('config_') in wanted]
        if not json_files:
            print(f"No matching configs for --only {sorted(wanted)}", file=sys.stderr)
            return 1

    if not json_files:
        print("No config_*.json files found under bot/config/", file=sys.stderr)
        return 1

    for json_path in json_files:
        cog_name = json_path.stem.removeprefix('config_')
        try:
            summary[cog_name] = migrate_cog(
                cog_name, json_path, classification, seed, report_rows,
            )
            print(f"  migrated {cog_name} ({summary[cog_name]})")
        except Exception as exc:  # noqa: BLE001 - one-shot tool, want a readable trace
            print(f"  FAILED {cog_name}: {exc}", file=sys.stderr)
            raise

    if seed:
        SEED_FILE.write_text(
            json.dumps(seed, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )

    write_report(report_rows, summary)
    print()
    print(f"Wrote {len(json_files)} YAML configs + locales.")
    if seed:
        print(f"Wrote DB seed: {SEED_FILE.relative_to(REPO_ROOT)}")
    print(f"Wrote report:  {REPORT_FILE.relative_to(REPO_ROOT)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
