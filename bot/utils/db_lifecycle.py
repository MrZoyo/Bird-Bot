import asyncio
import logging
from collections.abc import Iterable
from typing import Any

import aiosqlite


class BaseDatabaseManager:
    """Lifecycle contract for database managers.

    Most managers still open short-lived aiosqlite connections per method.
    Managers migrated during P2-1 can opt into the persistent connection helper
    below while the rest keep their existing behavior.
    """

    def _get_persistent_connection_lock(self) -> asyncio.Lock:
        lock = getattr(self, "_persistent_connection_lock", None)
        if lock is None:
            lock = asyncio.Lock()
            self._persistent_connection_lock = lock
        return lock

    async def _get_persistent_connection(self) -> aiosqlite.Connection:
        connection = getattr(self, "_persistent_connection", None)
        if connection is not None:
            return connection

        db_path = getattr(self, "db_path", None)
        if not db_path:
            raise RuntimeError(
                f"{self.__class__.__name__} requires db_path for a persistent connection"
            )

        connection = await aiosqlite.connect(db_path)
        self._persistent_connection = connection
        return connection

    async def close(self) -> None:
        lock = getattr(self, "_persistent_connection_lock", None)
        if lock is None:
            connection = getattr(self, "_persistent_connection", None)
            if connection is not None:
                await connection.close()
                self._persistent_connection = None
            return

        async with lock:
            connection = getattr(self, "_persistent_connection", None)
            if connection is not None:
                await connection.close()
                self._persistent_connection = None


def collect_database_managers_from_cogs(cogs: Iterable[Any]) -> list[BaseDatabaseManager]:
    managers: list[BaseDatabaseManager] = []
    seen_ids: set[int] = set()

    for cog in cogs:
        for value in vars(cog).values():
            if not isinstance(value, BaseDatabaseManager):
                continue

            value_id = id(value)
            if value_id in seen_ids:
                continue

            seen_ids.add(value_id)
            managers.append(value)

    return managers


async def close_database_managers(managers: Iterable[BaseDatabaseManager]) -> None:
    for manager in managers:
        try:
            await manager.close()
        except Exception:
            logging.exception(
                "Failed to close database manager %s",
                manager.__class__.__name__,
            )
