import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import aiosqlite


MigrationHandler = Callable[[aiosqlite.Connection], Awaitable[None]]


@dataclass(frozen=True)
class SchemaMigration:
    version: int
    description: str
    migrate: MigrationHandler


async def apply_schema_migrations(
    db: aiosqlite.Connection,
    namespace: str,
    migrations: Sequence[SchemaMigration],
) -> None:
    """Apply pending SQLite schema migrations for one manager namespace.

    The caller owns the surrounding transaction and commit/rollback. Migration
    functions must be idempotent so existing deployments without a
    ``schema_version`` row can safely be marked as current after inspection.
    """
    _validate_namespace(namespace)
    ordered_migrations = sorted(migrations, key=lambda migration: migration.version)
    _validate_migrations(ordered_migrations)

    await _ensure_schema_version_table(db)
    current_version = await _get_schema_version(db, namespace)

    for migration in ordered_migrations:
        if migration.version <= current_version:
            continue

        logging.info(
            "Applying DB schema migration %s v%s: %s",
            namespace,
            migration.version,
            migration.description,
        )
        await migration.migrate(db)
        await _set_schema_version(db, namespace, migration)


async def add_column_if_missing(
    db: aiosqlite.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> bool:
    """Add a column if it is absent; return True when ALTER TABLE ran."""
    columns = await get_table_columns(db, table_name)
    if column_name in columns:
        return False

    table_sql = _quote_identifier(table_name)
    column_sql = _quote_identifier(column_name)
    await db.execute(
        f"ALTER TABLE {table_sql} ADD COLUMN {column_sql} {column_definition}"
    )
    return True


async def get_table_columns(
    db: aiosqlite.Connection,
    table_name: str,
) -> set[str]:
    table_sql = _quote_identifier(table_name)
    cursor = await db.execute(f"PRAGMA table_info({table_sql})")
    try:
        return {row[1] for row in await cursor.fetchall()}
    finally:
        await cursor.close()


async def _ensure_schema_version_table(db: aiosqlite.Connection) -> None:
    cursor = await db.execute('''
        CREATE TABLE IF NOT EXISTS schema_version (
            namespace TEXT PRIMARY KEY,
            version INTEGER NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        )
    ''')
    await cursor.close()


async def _get_schema_version(
    db: aiosqlite.Connection,
    namespace: str,
) -> int:
    cursor = await db.execute(
        'SELECT version FROM schema_version WHERE namespace = ?',
        (namespace,),
    )
    try:
        row: Optional[tuple[int]] = await cursor.fetchone()
    finally:
        await cursor.close()

    return row[0] if row else 0


async def _set_schema_version(
    db: aiosqlite.Connection,
    namespace: str,
    migration: SchemaMigration,
) -> None:
    updated_at = datetime.now(timezone.utc).isoformat()
    cursor = await db.execute(
        '''
        INSERT INTO schema_version (namespace, version, description, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(namespace) DO UPDATE SET
            version = excluded.version,
            description = excluded.description,
            updated_at = excluded.updated_at
        ''',
        (namespace, migration.version, migration.description, updated_at),
    )
    await cursor.close()


def _validate_migrations(migrations: Sequence[SchemaMigration]) -> None:
    seen_versions: set[int] = set()
    for migration in migrations:
        if migration.version <= 0:
            raise ValueError("Schema migration versions must be positive")
        if migration.version in seen_versions:
            raise ValueError(
                f"Duplicate schema migration version: {migration.version}"
            )
        seen_versions.add(migration.version)


def _validate_namespace(namespace: str) -> None:
    if not namespace:
        raise ValueError("Schema migration namespace cannot be empty")


def _quote_identifier(identifier: str) -> str:
    if not identifier or not all(char.isalnum() or char == '_' for char in identifier):
        raise ValueError(f"Unsafe SQLite identifier: {identifier!r}")
    return f'"{identifier}"'
