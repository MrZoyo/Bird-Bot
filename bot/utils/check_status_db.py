# bot/utils/check_status_db.py
import aiosqlite
from typing import List, Tuple


class CheckStatusDatabaseManager:
    """Voice-channel status samples (table ``status``).

    One row per scheduled sample (every 10 minutes by default) with the total
    number of people and active voice channels at that moment. Backs the
    ``/print_voice_status`` command for day/month/year charts.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize_database(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS status (
                    timestamp TEXT NOT NULL,
                    people INTEGER DEFAULT 0,
                    channels INTEGER DEFAULT 0
                )
            ''')
            await db.commit()

    async def record_status(self, timestamp: str, people: int, channels: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'INSERT INTO status (timestamp, people, channels) VALUES (?, ?, ?)',
                (timestamp, people, channels),
            )
            await db.commit()

    async def fetch_status_by_date_prefix(self, date_prefix: str) -> List[Tuple[str, int, int]]:
        """``date_prefix`` is matched against the leading portion of ``timestamp`` via LIKE ?%."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT timestamp, people, channels FROM status '
                'WHERE timestamp LIKE ? ORDER BY timestamp',
                (f'{date_prefix}%',),
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return rows
