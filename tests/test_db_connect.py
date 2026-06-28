import os
import sqlite3
import stat

import pytest

from bot.utils.db_connect import (
    DB_CREATE_KEY_FILE_ENV,
    DB_KEY_ENV,
    DB_KEY_FILE_ENV,
    DB_REQUIRE_ENCRYPTION_ENV,
    connect_database,
    database_encryption_enabled,
    get_database_key,
)
from runtime_env import load_env_file
from tools.encrypt_database import encrypt_database


def _clear_database_key_env(monkeypatch):
    monkeypatch.delenv(DB_KEY_ENV, raising=False)
    monkeypatch.delenv(DB_KEY_FILE_ENV, raising=False)
    monkeypatch.delenv(DB_CREATE_KEY_FILE_ENV, raising=False)
    monkeypatch.delenv(DB_REQUIRE_ENCRYPTION_ENV, raising=False)


def test_connect_database_uses_plain_sqlite_without_key(tmp_path, monkeypatch):
    _clear_database_key_env(monkeypatch)

    db_path = tmp_path / "plain.db"

    async def scenario():
        async with connect_database(db_path) as db:
            await db.execute("CREATE TABLE sample (value TEXT)")
            await db.execute("INSERT INTO sample(value) VALUES ('ok')")
            await db.commit()

    import asyncio

    asyncio.run(scenario())

    assert database_encryption_enabled() is False
    assert sqlite3.connect(db_path).execute("SELECT value FROM sample").fetchone() == ("ok",)


def test_connect_database_requires_key_when_enforced(monkeypatch):
    _clear_database_key_env(monkeypatch)
    monkeypatch.setenv(DB_REQUIRE_ENCRYPTION_ENV, "1")

    with pytest.raises(RuntimeError, match="requires DCGSH_DB_KEY"):
        connect_database(":memory:")


def test_database_key_file_can_be_generated_on_first_use(tmp_path, monkeypatch):
    _clear_database_key_env(monkeypatch)
    key_file = tmp_path / "secrets" / "db.key"
    monkeypatch.setenv(DB_KEY_FILE_ENV, str(key_file))
    monkeypatch.setenv(DB_CREATE_KEY_FILE_ENV, "1")

    key = get_database_key()

    assert key_file.exists()
    assert key_file.read_text(encoding="utf-8").strip() == key
    assert len(key) >= 64
    assert database_encryption_enabled() is True
    assert get_database_key() == key
    if os.name == "posix":
        assert stat.S_IMODE(key_file.stat().st_mode) == 0o600


def test_missing_database_key_file_requires_explicit_generation(tmp_path, monkeypatch):
    _clear_database_key_env(monkeypatch)
    key_file = tmp_path / "missing.key"
    monkeypatch.setenv(DB_KEY_FILE_ENV, str(key_file))

    with pytest.raises(RuntimeError, match=DB_CREATE_KEY_FILE_ENV):
        get_database_key()

    assert not key_file.exists()


def test_load_env_file_resolves_local_key_file_path(tmp_path, monkeypatch):
    _clear_database_key_env(monkeypatch)
    env_file = tmp_path / ".env"
    key_file = tmp_path / ".local_secrets" / "local-test-db.key"
    environ = {}
    env_file.write_text(
        "\n".join(
            [
                f"{DB_KEY_FILE_ENV}={key_file.relative_to(tmp_path).as_posix()}",
                f"{DB_REQUIRE_ENCRYPTION_ENV}=1",
            ]
        ),
        encoding="utf-8",
    )

    load_env_file(env_file, environ=environ)

    assert environ[DB_KEY_FILE_ENV] == str(key_file.resolve())
    assert environ[DB_REQUIRE_ENCRYPTION_ENV] == "1"


def test_load_env_file_keeps_existing_environment_by_default(tmp_path, monkeypatch):
    _clear_database_key_env(monkeypatch)
    env_file = tmp_path / ".env"
    environ = {DB_KEY_FILE_ENV: "configured-by-launcher"}
    env_file.write_text(f"{DB_KEY_FILE_ENV}=local.key\n", encoding="utf-8")

    load_env_file(env_file, environ=environ)

    assert environ[DB_KEY_FILE_ENV] == "configured-by-launcher"


def test_encrypt_database_outputs_sqlcipher_database(tmp_path, monkeypatch):
    pytest.importorskip("sqlcipher3")
    _clear_database_key_env(monkeypatch)
    monkeypatch.setenv(DB_KEY_ENV, "unit-test-key")

    source = tmp_path / "plain.db"
    destination = tmp_path / "encrypted.db"
    plain = sqlite3.connect(source)
    plain.execute("CREATE TABLE sample (value TEXT)")
    plain.execute("INSERT INTO sample(value) VALUES ('secret')")
    plain.commit()
    plain.close()

    encrypt_database(source, destination)

    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(destination).execute("SELECT value FROM sample").fetchone()

    async def scenario():
        async with connect_database(destination) as db:
            cursor = await db.execute("SELECT value FROM sample")
            row = await cursor.fetchone()
            await cursor.close()
            return row

    import asyncio

    assert asyncio.run(scenario()) == ("secret",)
