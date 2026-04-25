import logging
from collections.abc import Iterable
from typing import Any


class BaseDatabaseManager:
    """Lifecycle contract for database managers.

    Current managers still open short-lived aiosqlite connections per method.
    The default close is intentionally a no-op so we can wire shutdown handling
    before migrating selected managers to persistent connections.
    """

    async def close(self) -> None:
        return None


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
