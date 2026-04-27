# bot/utils/notebook_db.py
import aiosqlite
from datetime import datetime
from typing import List, Optional, Tuple

from .db_lifecycle import BaseDatabaseManager


class NotebookDatabaseManager(BaseDatabaseManager):
    """Administrative event log (tables ``event_logs`` + ``admins``).

    ``event_logs.count`` is a per-``event_member`` monotonically increasing
    serial number so admins can reference a log by its visible number.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize_database(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS event_logs (
                    add_time TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    event_member TEXT NOT NULL,
                    event_description TEXT NOT NULL,
                    count INTEGER DEFAULT 1
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    user_id TEXT NOT NULL
                )
            ''')
            await db.commit()

    async def insert_event_and_ensure_admin(
        self,
        operator_id,
        event_member,
        event_description: str,
    ) -> int:
        """Insert a log entry and promote the operator to admin on first use.

        Returns the assigned ``count`` (serial number for this event_member).
        Done within a single connection so the MAX/INSERT pair sees a stable
        view, matching the previous in-cog behaviour.
        """
        add_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')  # microseconds

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT MAX(count) FROM event_logs WHERE event_member = ?',
                (event_member,),
            )
            max_count = await cursor.fetchone()
            await cursor.close()
            count = 1 if max_count[0] is None else max_count[0] + 1

            await db.execute(
                'INSERT INTO event_logs '
                '(add_time, operator, event_member, event_description, count) '
                'VALUES (?, ?, ?, ?, ?)',
                (add_time, operator_id, event_member, event_description, count),
            )

            cursor = await db.execute(
                'SELECT 1 FROM admins WHERE user_id = ?',
                (operator_id,),
            )
            already_admin = await cursor.fetchone()
            await cursor.close()
            if already_admin is None:
                await db.execute('INSERT INTO admins (user_id) VALUES (?)', (operator_id,))

            await db.commit()
        return count

    async def is_admin(self, user_id) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT 1 FROM admins WHERE user_id = ?',
                (user_id,),
            )
            record = await cursor.fetchone()
            await cursor.close()
        return record is not None

    async def fetch_events_for_member(self, event_member) -> List[Tuple]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT add_time, operator, event_member, event_description, count '
                'FROM event_logs WHERE event_member = ? ORDER BY add_time DESC',
                (event_member,),
            )
            records = await cursor.fetchall()
            await cursor.close()
        return records

    async def fetch_event_summary_all(self) -> List[Tuple]:
        """One row per event_member: (latest_time, event_member, log_count)."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT MAX(add_time) AS latest_time, event_member, COUNT(event_member) '
                'FROM event_logs GROUP BY event_member ORDER BY latest_time DESC'
            )
            records = await cursor.fetchall()
            await cursor.close()
        return records

    async def fetch_event_details(
        self, event_member, event_serial_number
    ) -> Optional[Tuple]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT add_time, operator, event_member, event_description '
                'FROM event_logs WHERE event_member = ? AND count = ?',
                (event_member, event_serial_number),
            )
            record = await cursor.fetchone()
            await cursor.close()
        return record

    async def delete_event(self, event_member, event_serial_number) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'DELETE FROM event_logs WHERE event_member = ? AND count = ?',
                (event_member, event_serial_number),
            )
            await db.commit()
