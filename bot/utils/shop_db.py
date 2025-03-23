# bot/utils/shop_db.py
import aiosqlite
from datetime import datetime, timedelta
import logging
from collections import defaultdict
from typing import Optional, Dict, List, Any


class ShopDatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize_database(self) -> None:
        """Create necessary shop-related database tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            # User balance table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS shop_user_balance (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER DEFAULT 0
                )
            ''')

            # User check-in history table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS shop_user_checkin (
                    user_id INTEGER PRIMARY KEY,
                    last_checkin TEXT,
                    streak INTEGER DEFAULT 0,
                    max_streak INTEGER DEFAULT 0
                )
            ''')
            await db.commit()

            # Shop transaction history table
            await db.execute('''
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

            # Daily check-in records table (new)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS shop_checkin_records (
                    user_id INTEGER NOT NULL,
                    checkin_date TEXT NOT NULL,
                    checkin_timestamp TEXT NOT NULL,
                    PRIMARY KEY (user_id, checkin_date)
                )
            ''')
            await db.commit()

    async def get_user_balance(self, user_id: int) -> int:
        """Get a user's current balance."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT balance FROM shop_user_balance WHERE user_id = ?', (user_id,))
            result = await cursor.fetchone()

            if result is None:
                await db.execute('INSERT INTO shop_user_balance (user_id, balance) VALUES (?, ?)', (user_id, 0))
                await db.commit()
                return 0
            return result[0]

    async def update_user_balance(self, user_id: int, amount: int) -> int:
        """Update a user's balance by the given amount (positive or negative)."""
        async with aiosqlite.connect(self.db_path) as db:
            current_balance = await self.get_user_balance(user_id)
            new_balance = current_balance + amount

            await db.execute('UPDATE shop_user_balance SET balance = ? WHERE user_id = ?',
                             (new_balance, user_id))
            await db.commit()
            return new_balance

    async def get_checkin_status(self, user_id: int) -> dict:
        """Get a user's check-in status including last check-in date, streak, and max streak."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT last_checkin, streak, max_streak FROM shop_user_checkin WHERE user_id = ?',
                (user_id,))
            result = await cursor.fetchone()

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
        today = datetime.now().date().isoformat()
        status = await self.get_checkin_status(user_id)

        # Default values for a new user
        last_checkin = status["last_checkin"]
        streak = status["streak"]
        max_streak = status["max_streak"]

        # Check if this is a consecutive check-in
        if last_checkin:
            last_date = datetime.fromisoformat(last_checkin).date()
            today_date = datetime.now().date()

            if last_date == today_date:
                # Already checked in today
                return {
                    "already_checked_in": True,
                    "last_checkin": last_checkin,
                    "streak": streak,
                    "max_streak": max_streak
                }

            # Check if this check-in continues the streak (yesterday or today)
            if today_date - last_date <= timedelta(days=1):
                streak += 1
                max_streak = max(streak, max_streak)
            else:
                # Streak broken
                streak = 1
        else:
            # First check-in ever
            streak = 1
            max_streak = 1

        # Update the shop_user_checkin database
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO shop_user_checkin (user_id, last_checkin, streak, max_streak) 
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    last_checkin = ?,
                    streak = ?,
                    max_streak = ?
            ''', (user_id, today, streak, max_streak, today, streak, max_streak))

            # Also record the check-in in shop_checkin_records for history tracking
            now_timestamp = datetime.now().isoformat()
            await db.execute('''
                INSERT OR IGNORE INTO shop_checkin_records (user_id, checkin_date, checkin_timestamp) 
                VALUES (?, ?, ?)
            ''', (user_id, today, now_timestamp))

            await db.commit()

        return {
            "already_checked_in": False,
            "last_checkin": today,
            "streak": streak,
            "max_streak": max_streak
        }

    async def record_transaction(self, user_id: int, operation_type: str, amount: int,
                                 new_balance: int, operator_id: int, note: str = None):
        """Record a balance transaction in the history."""
        timestamp = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO shop_transactions 
                (user_id, timestamp, operation_type, amount, new_balance, operator_id, note)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, timestamp, operation_type, amount, new_balance, operator_id, note))
            await db.commit()

    async def update_user_balance_with_record(self, user_id: int, amount: int,
                                              operation_type: str, operator_id: int, note: str = None):
        """Update user balance and record the transaction."""
        new_balance = await self.update_user_balance(user_id, amount)
        await self.record_transaction(
            user_id, operation_type, amount, new_balance, operator_id, note
        )
        return new_balance

    async def get_transaction_history(self, user_id: int, limit: int = 10, offset: int = 0,
                                      exclude_checkin: bool = False):
        """Get paginated transaction history for a user."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT id, timestamp, operation_type, amount, new_balance, operator_id, note
                FROM shop_transactions
                WHERE user_id = ? {}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            '''.format("AND operation_type != 'checkin'" if exclude_checkin else ""),
                                      (user_id, limit, offset))
            return await cursor.fetchall()

    async def get_transaction_count(self, user_id: int, exclude_checkin: bool = False):
        """Get the total number of transactions for a user."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT COUNT(*) FROM shop_transactions 
                WHERE user_id = ? {}
            '''.format("AND operation_type != 'checkin'" if exclude_checkin else ""),
                                      (user_id,))
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def get_checkin_history_by_month(self, user_id: int, limit: int = 24):
        """Get check-in history organized by month.

        Returns a list of tuples: [(year-month, [days]), ...]
        Sorted from newest to oldest month.
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT checkin_date FROM shop_checkin_records
                WHERE user_id = ?
                ORDER BY checkin_date DESC
            ''', (user_id,))
            results = await cursor.fetchall()

            if not results:
                return []

            # Group by month
            monthly_history = defaultdict(list)
            for (date_str,) in results:
                # Parse the date
                try:
                    date_obj = datetime.fromisoformat(date_str)
                    year_month = date_obj.strftime('%Y-%m')
                    day = date_obj.day

                    monthly_history[year_month].append(str(day))
                except (ValueError, TypeError):
                    # Skip invalid dates
                    continue

            # Convert to sorted list of tuples
            history_list = [(month, days) for month, days in monthly_history.items()]
            history_list.sort(reverse=True)  # Sort newest to oldest

            # Limit the number of months returned if needed
            return history_list[:limit]

