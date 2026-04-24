#!/usr/bin/env python3
"""Seed DB-bound fields from tools/migration_db_seed.json into SQLite.

Companion to tools/migrate_config_to_yaml.py (see REFACTORING_PLAN.md
§P1-6 steps 0 / 5). Run *after* the migration script has produced
``tools/migration_db_seed.json`` and *before* restarting the bot.

The upgrade protocol is, strictly:

    git pull
    uv pip sync requirements.lock
    python tools/migrate_config_to_yaml.py
    python tools/seed_db.py         # <-- this script
    # restart bot

Skipping this step would leave the two DB-backed maps empty:
  - voicechannel.channel_configs → auto-create rooms stop working
  - tickets.ticket_types     → every ticket type disappears

What this script does not do (by design):
  - It does not auto-discover seed data; operators must have run the
    migration script first.
  - It does not bootstrap from cog first start — too easy to hide a
    mistake inside a cog's init path (see PLAN step 0 rationale).
  - It does not clear the destination tables. Re-running is safe (the
    underlying CRUD is upsert) but does NOT remove rows that exist in
    the DB but are missing from the seed file.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_FILE = REPO_ROOT / 'tools' / 'migration_db_seed.json'

# Import via the repo so we pick up the same DB managers the bot uses.
sys.path.insert(0, str(REPO_ROOT))

from bot.utils.config import config  # noqa: E402
from bot.utils.voice_channel_db import VoiceChannelDatabaseManager  # noqa: E402
from bot.utils.tickets_db import TicketsDatabaseManager  # noqa: E402


async def seed_voicechannel(db_path: str, payload: Dict[str, Any]) -> int:
    """Load voicechannel.channel_configs into the channel_configs table."""
    channel_configs = payload.get('channel_configs', {}) or {}
    if not channel_configs:
        return 0
    db = VoiceChannelDatabaseManager(db_path)
    await db.initialize_database()  # idempotent; safe if cog has already run
    count = 0
    for channel_id_raw, cfg in channel_configs.items():
        channel_id = int(channel_id_raw)
        name_prefix = cfg.get('name_prefix', '')
        room_type = cfg.get('type', 'public')
        await db.upsert_channel_config(channel_id, name_prefix, room_type)
        count += 1
    return count


async def seed_tickets(db_path: str, payload: Dict[str, Any]) -> int:
    """Load tickets.ticket_types into the ticket_types table."""
    ticket_types = payload.get('ticket_types', {}) or {}
    if not ticket_types:
        return 0
    db = TicketsDatabaseManager(db_path)
    await db.initialize_database()
    count = 0
    for type_name, type_data in ticket_types.items():
        await db.upsert_ticket_type(type_name, type_data)
        count += 1
    return count


async def run() -> int:
    if not SEED_FILE.exists():
        print(
            f"Seed file not found: {SEED_FILE.relative_to(REPO_ROOT)}\n"
            "Did you run `python tools/migrate_config_to_yaml.py` first?",
            file=sys.stderr,
        )
        return 1

    seed = json.loads(SEED_FILE.read_text(encoding='utf-8'))
    if not seed:
        print("Seed file is empty — nothing to seed.")
        return 0

    db_path = config.get_config('main').get('db_path')
    if not db_path:
        print(
            "main.db_path is empty; cannot seed. "
            "Check bot/config/main.yaml (or config_main.json fallback).",
            file=sys.stderr,
        )
        return 1

    # Match the map in tools/field_classification.yaml. Add a handler here
    # whenever a new cog gains DB-bound fields during future migrations.
    seed_handlers = {
        'voicechannel': seed_voicechannel,
        'tickets': seed_tickets,
    }

    total = 0
    for cog_name, payload in seed.items():
        handler = seed_handlers.get(cog_name)
        if handler is None:
            print(
                f"Warning: no seed handler for '{cog_name}' "
                f"(keys={list(payload.keys())}); skipped.",
                file=sys.stderr,
            )
            continue
        count = await handler(db_path, payload)
        total += count
        print(f"  seeded {cog_name}: {count} row(s)")

    print(f"Seeded {total} row(s) across {len(seed_handlers)} handler(s).")
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(run()))
