"""SQLite connection helper with optional SQLCipher support.

Plain SQLite remains the default for local tests and development. Production
deployments can enable at-rest encryption by setting ``DCGSH_DB_KEY`` or
``DCGSH_DB_KEY_FILE``. Set ``DCGSH_DB_REQUIRE_ENCRYPTION=1`` to fail fast when
no key is configured.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType
from typing import Any

import aiosqlite


DB_KEY_ENV = "DCGSH_DB_KEY"
DB_KEY_FILE_ENV = "DCGSH_DB_KEY_FILE"
DB_REQUIRE_ENCRYPTION_ENV = "DCGSH_DB_REQUIRE_ENCRYPTION"


def _truthy(value: str | None) -> bool:
    return bool(value and value.lower() in {"1", "true", "yes", "on"})


def database_encryption_required() -> bool:
    return _truthy(os.getenv(DB_REQUIRE_ENCRYPTION_ENV))


def get_database_key() -> str | None:
    key_file = os.getenv(DB_KEY_FILE_ENV)
    if key_file:
        key = Path(key_file).read_text(encoding="utf-8").strip()
        if not key:
            raise RuntimeError(f"{DB_KEY_FILE_ENV} points to an empty key file")
        return key

    key = os.getenv(DB_KEY_ENV)
    if key:
        return key

    if database_encryption_required():
        raise RuntimeError(
            f"{DB_REQUIRE_ENCRYPTION_ENV}=1 requires {DB_KEY_ENV} or {DB_KEY_FILE_ENV}"
        )

    return None


def database_encryption_enabled() -> bool:
    return bool(get_database_key())


def connect_database(
    database: str | bytes | Path,
    *,
    iter_chunk_size: int = 64,
    **kwargs: Any,
) -> aiosqlite.Connection:
    """Return an aiosqlite connection, keyed with SQLCipher when configured."""
    key = get_database_key()
    if not key:
        return aiosqlite.connect(
            database,
            iter_chunk_size=iter_chunk_size,
            **kwargs,
        )

    def connector():
        sqlcipher = _load_sqlcipher_module()
        connection = sqlcipher.connect(str(database), **kwargs)
        _configure_sqlcipher_connection(connection, key)
        return connection

    return aiosqlite.Connection(connector, iter_chunk_size)


def _load_sqlcipher_module() -> ModuleType:
    try:
        import sqlcipher3
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Database encryption is enabled, but sqlcipher3 is not installed. "
            "Install project dependencies or run: pip install sqlcipher3==0.6.2"
        ) from exc
    return sqlcipher3


def _configure_sqlcipher_connection(connection: Any, key: str) -> None:
    connection.execute(f"PRAGMA key = {_sql_literal(key)}")
    # Force a schema read so a wrong key or a non-SQLCipher backend fails
    # before the caller starts running feature-specific SQL.
    connection.execute("SELECT count(*) FROM sqlite_master").fetchone()


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
