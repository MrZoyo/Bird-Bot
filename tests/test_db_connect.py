import os
import sqlite3

import pytest

from bot.utils.db_connect import connect_database, database_encryption_enabled
from tools.encrypt_database import encrypt_database


def test_connect_database_uses_plain_sqlite_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("DCGSH_DB_KEY", raising=False)
    monkeypatch.delenv("DCGSH_DB_KEY_FILE", raising=False)
    monkeypatch.delenv("DCGSH_DB_REQUIRE_ENCRYPTION", raising=False)

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
    monkeypatch.delenv("DCGSH_DB_KEY", raising=False)
    monkeypatch.delenv("DCGSH_DB_KEY_FILE", raising=False)
    monkeypatch.setenv("DCGSH_DB_REQUIRE_ENCRYPTION", "1")

    with pytest.raises(RuntimeError, match="requires DCGSH_DB_KEY"):
        connect_database(":memory:")


def test_encrypt_database_outputs_sqlcipher_database(tmp_path, monkeypatch):
    pytest.importorskip("sqlcipher3")
    monkeypatch.setenv("DCGSH_DB_KEY", "unit-test-key")
    monkeypatch.delenv("DCGSH_DB_KEY_FILE", raising=False)
    monkeypatch.delenv("DCGSH_DB_REQUIRE_ENCRYPTION", raising=False)

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
