"""Encrypt an existing SQLite database with SQLCipher.

The key is read from ``DCGSH_DB_KEY`` or ``DCGSH_DB_KEY_FILE``. The key is
never printed and should not be stored in YAML or committed files.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

import sqlcipher3

from bot.utils.db_connect import get_database_key


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def encrypt_database(source: Path, destination: Path, *, overwrite: bool = False) -> None:
    key = get_database_key()
    if not key:
        raise RuntimeError("Set DCGSH_DB_KEY or DCGSH_DB_KEY_FILE before encrypting the database")

    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("source and destination must be different paths")
    if not source.exists():
        raise FileNotFoundError(source)
    if destination.exists():
        if not overwrite:
            raise FileExistsError(f"{destination} already exists; pass --overwrite to replace it")
        destination.unlink()

    destination.parent.mkdir(parents=True, exist_ok=True)

    # Validate that the source is a readable plaintext SQLite database before
    # creating the encrypted copy.
    plain = sqlite3.connect(source)
    try:
        plain.execute("SELECT count(*) FROM sqlite_master").fetchone()
    finally:
        plain.close()

    connection = sqlcipher3.connect(str(source))
    try:
        connection.execute(
            f"ATTACH DATABASE {_sql_literal(str(destination))} AS encrypted KEY {_sql_literal(key)}"
        )
        connection.execute("SELECT sqlcipher_export('encrypted')")
        connection.execute("DETACH DATABASE encrypted")
    finally:
        connection.close()

    encrypted = sqlcipher3.connect(str(destination))
    try:
        encrypted.execute(f"PRAGMA key = {_sql_literal(key)}")
        encrypted.execute("SELECT count(*) FROM sqlite_master").fetchone()
    finally:
        encrypted.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Encrypt a plaintext SQLite database with SQLCipher.")
    parser.add_argument("source", type=Path, help="Plain SQLite database path, for example data/bot.db")
    parser.add_argument("destination", type=Path, help="Encrypted output database path")
    parser.add_argument("--overwrite", action="store_true", help="Replace destination if it already exists")
    parser.add_argument("--backup-source", type=Path, help="Optional plaintext backup copy path before encryption")
    args = parser.parse_args(argv)

    if args.backup_source:
        backup_path = args.backup_source.resolve()
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        if backup_path.exists() and not args.overwrite:
            raise FileExistsError(f"{backup_path} already exists; pass --overwrite to replace it")
        shutil.copy2(args.source, backup_path)

    encrypt_database(args.source, args.destination, overwrite=args.overwrite)
    print(f"Encrypted database written to {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
