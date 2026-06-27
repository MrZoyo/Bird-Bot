import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

from .db_connect import connect_database
from .db_lifecycle import BaseDatabaseManager


class ShopDatabaseManager(BaseDatabaseManager):
    def __init__(self, db_path: str, config: dict = None):
        self.db_path = db_path
        self.config = config or {}
        self.makeup_limit = self.config.get('makeup_checkin_limit_per_month', 3)
        self._persistent_connection: Optional[aiosqlite.Connection] = None
        self._persistent_connection_lock = asyncio.Lock()

    async def _execute_on_connection(
        self,
        db: aiosqlite.Connection,
        sql: str,
        parameters: Tuple[Any, ...] = (),
    ) -> None:
        cursor = await db.execute(sql, parameters)
        await cursor.close()

    async def _fetchone_on_connection(
        self,
        db: aiosqlite.Connection,
        sql: str,
        parameters: Tuple[Any, ...] = (),
    ) -> Optional[Tuple]:
        cursor = await db.execute(sql, parameters)
        try:
            return await cursor.fetchone()
        finally:
            await cursor.close()

    async def _fetchall_on_connection(
        self,
        db: aiosqlite.Connection,
        sql: str,
        parameters: Tuple[Any, ...] = (),
    ) -> List[Tuple]:
        cursor = await db.execute(sql, parameters)
        try:
            return await cursor.fetchall()
        finally:
            await cursor.close()

    async def _execute_write(self, sql: str, parameters: Tuple[Any, ...] = ()) -> None:
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                await self._execute_on_connection(db, sql, parameters)
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    async def _fetchone(
        self,
        sql: str,
        parameters: Tuple[Any, ...] = (),
    ) -> Optional[Tuple]:
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            return await self._fetchone_on_connection(db, sql, parameters)

    async def _fetchall(self, sql: str, parameters: Tuple[Any, ...] = ()) -> List[Tuple]:
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            return await self._fetchall_on_connection(db, sql, parameters)

    async def initialize_database(self) -> None:
        """Create necessary shop-related database tables if they don't exist."""
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                # User balance table
                await self._execute_on_connection(db, '''
                    CREATE TABLE IF NOT EXISTS shop_user_balance (
                        user_id INTEGER PRIMARY KEY,
                        balance INTEGER DEFAULT 0
                    )
                ''')

                # User check-in history table
                await self._execute_on_connection(db, '''
                    CREATE TABLE IF NOT EXISTS shop_user_checkin (
                        user_id INTEGER PRIMARY KEY,
                        last_checkin TEXT,
                        streak INTEGER DEFAULT 0,
                        max_streak INTEGER DEFAULT 0
                    )
                ''')

                # Shop transaction history table
                await self._execute_on_connection(db, '''
                    CREATE TABLE IF NOT EXISTS shop_transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        timestamp TEXT NOT NULL,
                        operation_type TEXT NOT NULL,
                        amount INTEGER NOT NULL,
                        new_balance INTEGER NOT NULL,
                        operator_id INTEGER NOT NULL,
                        note TEXT
                    )
                ''')

                # Daily check-in records table
                await self._execute_on_connection(db, '''
                    CREATE TABLE IF NOT EXISTS shop_checkin_records (
                        user_id INTEGER NOT NULL,
                        checkin_date TEXT NOT NULL,
                        checkin_timestamp TEXT NOT NULL,
                        is_makeup INTEGER DEFAULT 0,
                        PRIMARY KEY (user_id, checkin_date)
                    )
                ''')

                # Makeup check-in tracking table
                await self._execute_on_connection(db, '''
                    CREATE TABLE IF NOT EXISTS shop_makeup_checkin (
                        user_id INTEGER PRIMARY KEY,
                        makeup_1 TEXT,
                        makeup_2 TEXT,
                        makeup_3 TEXT,
                        makeup_4 TEXT,
                        makeup_5 TEXT
                    )
                ''')

                # Checkin embeds table for managing daily embed panels
                await self._execute_on_connection(db, '''
                    CREATE TABLE IF NOT EXISTS shop_checkin_embeds (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        channel_id INTEGER NOT NULL,
                        message_id INTEGER NOT NULL,
                        created_date TEXT NOT NULL,
                        is_active INTEGER DEFAULT 1,
                        today_checkin_count INTEGER DEFAULT 0,
                        today_first_checkin_user_id INTEGER,
                        UNIQUE (channel_id, created_date)
                    )
                ''')

                await db.commit()
            except Exception:
                await db.rollback()
                raise

    async def get_user_balance(self, user_id: int) -> int:
        """Get a user's current balance."""
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                result = await self._fetchone_on_connection(
                    db,
                    'SELECT balance FROM shop_user_balance WHERE user_id = ?',
                    (user_id,),
                )

                if result is None:
                    await self._execute_on_connection(
                        db,
                        'INSERT INTO shop_user_balance (user_id, balance) VALUES (?, ?)',
                        (user_id, 0),
                    )
                    await db.commit()
                    return 0

                return result[0]
            except Exception:
                await db.rollback()
                raise

    async def update_user_balance(self, user_id: int, amount: int) -> int:
        """Update a user's balance by the given amount (positive or negative)."""
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                await self._execute_on_connection(
                    db,
                    'INSERT OR IGNORE INTO shop_user_balance (user_id, balance) '
                    'VALUES (?, ?)',
                    (user_id, 0),
                )
                await self._execute_on_connection(
                    db,
                    'UPDATE shop_user_balance SET balance = balance + ? '
                    'WHERE user_id = ?',
                    (amount, user_id),
                )
                result = await self._fetchone_on_connection(
                    db,
                    'SELECT balance FROM shop_user_balance WHERE user_id = ?',
                    (user_id,),
                )
                await db.commit()
                return result[0] if result else 0
            except Exception:
                await db.rollback()
                raise

    async def get_checkin_status(self, user_id: int) -> dict:
        """Get a user's check-in status including last check-in date and streaks."""
        result = await self._fetchone(
            'SELECT last_checkin, streak, max_streak '
            'FROM shop_user_checkin WHERE user_id = ?',
            (user_id,),
        )

        if result is None:
            return {
                "last_checkin": None,
                "streak": 0,
                "max_streak": 0
            }
        return {
            "last_checkin": result[0],
            "streak": result[1],
            "max_streak": result[2]
        }

    async def record_checkin(self, user_id: int) -> dict:
        """Record a check-in for the user and update streak information."""
        today_date = datetime.now().date()
        today = today_date.isoformat()

        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                status_row = await self._fetchone_on_connection(
                    db,
                    'SELECT last_checkin, streak, max_streak '
                    'FROM shop_user_checkin WHERE user_id = ?',
                    (user_id,),
                )
                if status_row is None:
                    last_checkin = None
                    streak = 0
                    max_streak = 0
                else:
                    last_checkin = status_row[0]
                    streak = status_row[1]
                    max_streak = status_row[2]

                if last_checkin:
                    last_date = datetime.fromisoformat(last_checkin).date()

                    if last_date == today_date:
                        return {
                            "already_checked_in": True,
                            "last_checkin": last_checkin,
                            "streak": streak,
                            "max_streak": max_streak
                        }

                    if today_date - last_date <= timedelta(days=1):
                        streak += 1
                        max_streak = max(streak, max_streak)
                    else:
                        streak = 1
                else:
                    streak = 1
                    max_streak = 1

                await self._execute_on_connection(db, '''
                    INSERT INTO shop_user_checkin (
                        user_id, last_checkin, streak, max_streak
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        last_checkin = ?,
                        streak = ?,
                        max_streak = ?
                ''', (user_id, today, streak, max_streak, today, streak, max_streak))

                now_timestamp = datetime.now().isoformat()
                await self._execute_on_connection(db, '''
                    INSERT OR IGNORE INTO shop_checkin_records (
                        user_id, checkin_date, checkin_timestamp, is_makeup
                    )
                    VALUES (?, ?, ?, ?)
                ''', (user_id, today, now_timestamp, 0))

                await db.commit()
                return {
                    "already_checked_in": False,
                    "last_checkin": today,
                    "streak": streak,
                    "max_streak": max_streak
                }
            except Exception:
                await db.rollback()
                raise

    async def record_transaction(
        self,
        user_id: int,
        operation_type: str,
        amount: int,
        new_balance: int,
        operator_id: int,
        note: str = None,
    ):
        """Record a balance transaction in the history."""
        timestamp = datetime.now().isoformat()
        await self._execute_write(
            '''
            INSERT INTO shop_transactions
            (user_id, timestamp, operation_type, amount, new_balance, operator_id, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (user_id, timestamp, operation_type, amount, new_balance, operator_id, note),
        )

    async def update_user_balance_with_record(
        self,
        user_id: int,
        amount: int,
        operation_type: str,
        operator_id: int,
        note: str = None,
    ):
        """Update user balance and record the transaction."""
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                await self._execute_on_connection(
                    db,
                    'INSERT OR IGNORE INTO shop_user_balance (user_id, balance) '
                    'VALUES (?, ?)',
                    (user_id, 0),
                )
                await self._execute_on_connection(
                    db,
                    'UPDATE shop_user_balance SET balance = balance + ? '
                    'WHERE user_id = ?',
                    (amount, user_id),
                )
                balance_row = await self._fetchone_on_connection(
                    db,
                    'SELECT balance FROM shop_user_balance WHERE user_id = ?',
                    (user_id,),
                )
                new_balance = balance_row[0] if balance_row else 0
                timestamp = datetime.now().isoformat()

                await self._execute_on_connection(
                    db,
                    '''
                    INSERT INTO shop_transactions
                    (
                        user_id, timestamp, operation_type, amount,
                        new_balance, operator_id, note
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        user_id,
                        timestamp,
                        operation_type,
                        amount,
                        new_balance,
                        operator_id,
                        note,
                    ),
                )
                await db.commit()
                return new_balance
            except Exception:
                await db.rollback()
                raise

    async def get_transaction_history(
        self,
        user_id: int,
        limit: int = 10,
        offset: int = 0,
        exclude_checkin: bool = False,
    ):
        """Get paginated transaction history for a user."""
        exclude_clause = "AND operation_type != 'checkin'" if exclude_checkin else ""
        return await self._fetchall(
            f'''
            SELECT id, timestamp, operation_type, amount, new_balance, operator_id, note
            FROM shop_transactions
            WHERE user_id = ? {exclude_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            ''',
            (user_id, limit, offset),
        )

    async def get_transaction_count(
        self,
        user_id: int,
        exclude_checkin: bool = False,
    ):
        """Get the total number of transactions for a user."""
        exclude_clause = "AND operation_type != 'checkin'" if exclude_checkin else ""
        result = await self._fetchone(
            f'''
            SELECT COUNT(*) FROM shop_transactions
            WHERE user_id = ? {exclude_clause}
            ''',
            (user_id,),
        )
        return result[0] if result else 0

    async def get_checkin_history_by_month(self, user_id: int, limit: int = 24):
        """Get check-in history organized by month.

        Returns a list of tuples: [(year-month, [days]), ...]
        Sorted from newest to oldest month.
        """
        results = await self._fetchall(
            '''
            SELECT checkin_date FROM shop_checkin_records
            WHERE user_id = ?
            ORDER BY checkin_date DESC
            ''',
            (user_id,),
        )

        if not results:
            return []

        # Group by month
        monthly_history = defaultdict(list)
        for (date_str,) in results:
            try:
                date_obj = datetime.fromisoformat(date_str)
                year_month = date_obj.strftime('%Y-%m')
                day = date_obj.day

                monthly_history[year_month].append(str(day))
            except (ValueError, TypeError):
                continue

        history_list = [(month, days) for month, days in monthly_history.items()]
        history_list.sort(reverse=True)
        return history_list[:limit]

    async def get_makeup_count_this_month(self, user_id: int) -> int:
        """Get the number of makeup check-ins used this month."""
        current_month = datetime.now().strftime('%Y-%m')
        result = await self._fetchone(
            'SELECT makeup_1, makeup_2, makeup_3, makeup_4, makeup_5 '
            'FROM shop_makeup_checkin WHERE user_id = ?',
            (user_id,),
        )

        if not result:
            return 0

        count = 0
        for makeup_time in result:
            if makeup_time:
                try:
                    makeup_date = datetime.fromisoformat(makeup_time)
                    if makeup_date.strftime('%Y-%m') == current_month:
                        count += 1
                except (ValueError, TypeError):
                    continue

        return count

    async def get_remaining_makeup_count(self, user_id: int) -> int:
        """Get the remaining makeup check-ins for this month."""
        used_count = await self.get_makeup_count_this_month(user_id)
        return max(0, self.makeup_limit - used_count)

    async def get_first_checkin_date(self, user_id: int) -> Optional[str]:
        """Get the date of user's first check-in (excluding makeup check-ins)."""
        result = await self._fetchone(
            'SELECT checkin_date FROM shop_checkin_records '
            'WHERE user_id = ? AND is_makeup = 0 '
            'ORDER BY checkin_date ASC LIMIT 1',
            (user_id,),
        )
        return result[0] if result else None

    async def find_latest_missed_checkin(
        self,
        user_id: int,
        days_back: int = 180,
    ) -> Optional[str]:
        """Find the latest missed check-in date within the specified days back.

        Returns:
            str: The date string (YYYY-MM-DD) of the latest missed check-in,
            or None if no missed days found.
        """
        first_checkin_str = await self.get_first_checkin_date(user_id)
        if not first_checkin_str:
            return None

        first_checkin_date = datetime.fromisoformat(first_checkin_str).date()
        end_date = datetime.now().date()
        start_date = max(end_date - timedelta(days=days_back), first_checkin_date)

        rows = await self._fetchall(
            'SELECT checkin_date FROM shop_checkin_records '
            'WHERE user_id = ? AND checkin_date >= ? AND checkin_date <= ?',
            (user_id, start_date.isoformat(), end_date.isoformat()),
        )
        checkin_dates = {row[0] for row in rows}

        current_date = end_date - timedelta(days=1)
        while current_date >= start_date:
            date_str = current_date.isoformat()
            if date_str not in checkin_dates:
                return date_str
            current_date -= timedelta(days=1)

        return None

    async def add_makeup_record(self, user_id: int, makeup_date: str) -> bool:
        """Add a makeup check-in record.

        Args:
            user_id: The user ID
            makeup_date: The date being made up (YYYY-MM-DD format)

        Returns:
            bool: True if successful, False if no available makeup slots
        """
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                result = await self._fetchone_on_connection(
                    db,
                    'SELECT makeup_1, makeup_2, makeup_3, makeup_4, makeup_5 '
                    'FROM shop_makeup_checkin WHERE user_id = ?',
                    (user_id,),
                )
                now_timestamp = datetime.now().isoformat()

                if result:
                    slot = self._select_makeup_slot(result)
                    if slot is None:
                        return False

                    await self._execute_on_connection(
                        db,
                        f'UPDATE shop_makeup_checkin SET {slot} = ? WHERE user_id = ?',
                        (now_timestamp, user_id),
                    )
                else:
                    await self._execute_on_connection(
                        db,
                        'INSERT INTO shop_makeup_checkin '
                        '(user_id, makeup_1, makeup_2, makeup_3, makeup_4, makeup_5) '
                        'VALUES (?, ?, ?, ?, ?, ?)',
                        (user_id, now_timestamp, None, None, None, None),
                    )

                await self._execute_on_connection(
                    db,
                    'INSERT OR IGNORE INTO shop_checkin_records '
                    '(user_id, checkin_date, checkin_timestamp, is_makeup) '
                    'VALUES (?, ?, ?, ?)',
                    (user_id, makeup_date, now_timestamp, 1),
                )

                await self._recalculate_checkin_streak_on_connection(db, user_id)
                await db.commit()
                return True
            except Exception:
                await db.rollback()
                raise

    def _select_makeup_slot(self, result: Tuple) -> Optional[str]:
        makeup_1, makeup_2, makeup_3, makeup_4, makeup_5 = result

        if not makeup_1:
            return 'makeup_1'
        if not makeup_2:
            return 'makeup_2'
        if not makeup_3:
            return 'makeup_3'
        if not makeup_4:
            return 'makeup_4'
        if not makeup_5:
            return 'makeup_5'

        current_month = datetime.now().strftime('%Y-%m')
        oldest_slot = None
        oldest_time = None

        for slot_name, time_str in [
            ('makeup_1', makeup_1),
            ('makeup_2', makeup_2),
            ('makeup_3', makeup_3),
            ('makeup_4', makeup_4),
            ('makeup_5', makeup_5)
        ]:
            if not time_str:
                continue
            try:
                time_obj = datetime.fromisoformat(time_str)
                if time_obj.strftime('%Y-%m') == current_month:
                    continue
                if oldest_time is None or time_obj < oldest_time:
                    oldest_time = time_obj
                    oldest_slot = slot_name
            except (ValueError, TypeError):
                return slot_name

        return oldest_slot

    async def recalculate_checkin_streak(self, user_id: int) -> None:
        """Recalculate user's check-in streak after makeup."""
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                await self._recalculate_checkin_streak_on_connection(db, user_id)
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    async def _recalculate_checkin_streak_on_connection(
        self,
        db: aiosqlite.Connection,
        user_id: int,
    ) -> None:
        rows = await self._fetchall_on_connection(
            db,
            'SELECT checkin_date FROM shop_checkin_records '
            'WHERE user_id = ? ORDER BY checkin_date DESC',
            (user_id,),
        )
        dates = [row[0] for row in rows]

        if not dates:
            return

        today = datetime.now().date()
        current_streak = 0
        max_streak = 0
        temp_streak = 0

        expected_date = today
        for date_str in dates:
            check_date = datetime.fromisoformat(date_str).date()
            if check_date == expected_date or (
                expected_date == today
                and check_date == today - timedelta(days=1)
            ):
                current_streak = 1
                expected_date = check_date - timedelta(days=1)
                break

        for date_str in dates:
            check_date = datetime.fromisoformat(date_str).date()
            if check_date == expected_date:
                current_streak += 1
                expected_date = check_date - timedelta(days=1)
            elif check_date < expected_date:
                break

        prev_date = None
        for date_str in reversed(dates):
            check_date = datetime.fromisoformat(date_str).date()
            if prev_date is None or check_date == prev_date + timedelta(days=1):
                temp_streak += 1
                max_streak = max(max_streak, temp_streak)
            else:
                temp_streak = 1
            prev_date = check_date

        latest_checkin = dates[0]
        await self._execute_on_connection(db, '''
            INSERT INTO shop_user_checkin (user_id, last_checkin, streak, max_streak)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                last_checkin = ?,
                streak = ?,
                max_streak = ?
        ''', (
            user_id,
            latest_checkin,
            current_streak,
            max_streak,
            latest_checkin,
            current_streak,
            max_streak,
        ))

    # === Checkin Embed Management Methods ===

    async def create_checkin_embed_record(
        self,
        channel_id: int,
        message_id: int,
        date_str: str,
    ) -> bool:
        """Create a checkin embed record, replacing same channel/date rows."""
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                await self._execute_on_connection(db, '''
                    DELETE FROM shop_checkin_embeds
                    WHERE channel_id = ? AND created_date = ?
                ''', (channel_id, date_str))

                await self._execute_on_connection(db, '''
                    INSERT INTO shop_checkin_embeds (
                        channel_id, message_id, created_date,
                        is_active, today_checkin_count
                    )
                    VALUES (?, ?, ?, 1, 0)
                ''', (channel_id, message_id, date_str))
                await db.commit()
                return True
            except Exception as e:
                await db.rollback()
                logging.error(f"Error creating checkin embed record: {e}")
                return False

    async def get_active_checkin_embeds(self) -> List[Dict[str, Any]]:
        """Get all active checkin embeds."""
        try:
            rows = await self._fetchall(
                '''
                SELECT
                    id, channel_id, message_id, created_date,
                    today_checkin_count, today_first_checkin_user_id
                FROM shop_checkin_embeds
                WHERE is_active = 1
                '''
            )

            result = []
            for row in rows:
                result.append({
                    'id': row[0],
                    'channel_id': row[1],
                    'message_id': row[2],
                    'created_date': row[3],
                    'today_checkin_count': row[4],
                    'today_first_checkin_user_id': row[5]
                })
            return result
        except Exception as e:
            logging.error(f"Error getting active checkin embeds: {e}")
            return []

    async def deactivate_checkin_embed(self, embed_id: int) -> bool:
        """Deactivate a checkin embed."""
        try:
            await self._execute_write(
                '''
                UPDATE shop_checkin_embeds
                SET is_active = 0
                WHERE id = ?
                ''',
                (embed_id,),
            )
            return True
        except Exception as e:
            logging.error(f"Error deactivating checkin embed: {e}")
            return False

    async def update_embed_checkin_stats(self, embed_id: int, user_id: int) -> bool:
        """Update embed checkin statistics when someone checks in."""
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                result = await self._fetchone_on_connection(
                    db,
                    '''
                    SELECT today_checkin_count, today_first_checkin_user_id
                    FROM shop_checkin_embeds
                    WHERE id = ?
                    ''',
                    (embed_id,),
                )

                if result:
                    current_count, first_user = result
                    new_count = current_count + 1
                    first_checkin_user = first_user or user_id

                    await self._execute_on_connection(db, '''
                        UPDATE shop_checkin_embeds
                        SET today_checkin_count = ?,
                            today_first_checkin_user_id = ?
                        WHERE id = ?
                    ''', (new_count, first_checkin_user, embed_id))
                    await db.commit()
                    return True

                return False
            except Exception as e:
                await db.rollback()
                logging.error(f"Error updating embed checkin stats: {e}")
                return False

    async def reset_daily_embed_stats(self, date_str: str) -> bool:
        """Reset daily statistics for all embeds on date change."""
        try:
            await self._execute_write(
                '''
                UPDATE shop_checkin_embeds
                SET created_date = ?,
                    today_checkin_count = 0,
                    today_first_checkin_user_id = NULL
                WHERE is_active = 1
                ''',
                (date_str,),
            )
            return True
        except Exception as e:
            logging.error(f"Error resetting daily embed stats: {e}")
            return False

    async def get_today_checkin_count(self, date_str: str) -> int:
        """Get total checkin count for today across all users."""
        try:
            result = await self._fetchone(
                '''
                SELECT COUNT(*) FROM shop_checkin_records
                WHERE checkin_date = ?
                ''',
                (date_str,),
            )
            return result[0] if result else 0
        except Exception as e:
            logging.error(f"Error getting today checkin count: {e}")
            return 0

    async def get_today_first_checkin_user(self, date_str: str) -> Optional[int]:
        """Get the first user who checked in today."""
        try:
            result = await self._fetchone(
                '''
                SELECT user_id FROM shop_checkin_records
                WHERE checkin_date = ?
                ORDER BY checkin_timestamp ASC
                LIMIT 1
                ''',
                (date_str,),
            )
            return result[0] if result else None
        except Exception as e:
            logging.error(f"Error getting today first checkin user: {e}")
            return None
