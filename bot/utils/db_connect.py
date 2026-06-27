"""SQLite connection helper with optional SQLCipher support.

Plain SQLite remains the default for local tests and development. Production
deployments can enable at-rest encryption by setting ``DCGSH_DB_KEY`` or
``DCGSH_DB_KEY_FILE``. Set ``DCGSH_DB_CREATE_KEY_FILE=1`` to generate a missing
key file on first use, and ``DCGSH_DB_REQUIRE_ENCRYPTION=1`` to fail fast when
no key is configured.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from types import ModuleType
from typing import Any

import aiosqlite


DB_KEY_ENV = "DCGSH_DB_KEY"
DB_KEY_FILE_ENV = "DCGSH_DB_KEY_FILE"
DB_CREATE_KEY_FILE_ENV = "DCGSH_DB_CREATE_KEY_FILE"
DB_REQUIRE_ENCRYPTION_ENV = "DCGSH_DB_REQUIRE_ENCRYPTION"


def _truthy(value: str | None) -> bool:
    return bool(value and value.lower() in {"1", "true", "yes", "on"})


def database_encryption_required() -> bool:
    return _truthy(os.getenv(DB_REQUIRE_ENCRYPTION_ENV))


def database_key_file_creation_enabled() -> bool:
    return _truthy(os.getenv(DB_CREATE_KEY_FILE_ENV))


def get_database_key() -> str | None:
    key_file = os.getenv(DB_KEY_FILE_ENV)
    if key_file:
        key_path = Path(key_file)
        if key_path.exists():
            return _read_database_key_file(key_path)
        if database_key_file_creation_enabled():
            return _create_database_key_file(key_path)
        raise RuntimeError(
            f"{DB_KEY_FILE_ENV} points to a missing key file: {key_path}. "
            f"Create it first or set {DB_CREATE_KEY_FILE_ENV}=1 for first-run generation."
        )

    key = os.getenv(DB_KEY_ENV)
    if key:
        return key

    if database_encryption_required():
        raise RuntimeError(
            f"{DB_REQUIRE_ENCRYPTION_ENV}=1 requires {DB_KEY_ENV} or {DB_KEY_FILE_ENV}"
        )

    return None


def _read_database_key_file(path: Path) -> str:
    try:
        key = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Failed to read database key file configured by {DB_KEY_FILE_ENV}: {path}") from exc
    if not key:
        raise RuntimeError(f"{DB_KEY_FILE_ENV} points to an empty key file")
    return key


def _create_database_key_file(path: Path) -> str:
    key = secrets.token_urlsafe(64)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        file_descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        return _read_database_key_file(path)
    except OSError as exc:
        raise RuntimeError(f"Failed to create database key file configured by {DB_KEY_FILE_ENV}: {path}") from exc

    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as file:
            file.write(f"{key}\n")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return key


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
