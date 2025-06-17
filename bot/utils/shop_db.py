# bot/utils/shop_db.py
import aiosqlite
from datetime import datetime, timedelta
import logging
from collections import defaultdict
from typing import Optional, Dict, List, Any


class ShopDatabaseManager:
    def __init__(self, db_path: str, config: dict = None):
        self.db_path = db_path
        self.config = config or {}
        self.makeup_limit = self.config.get('makeup_checkin_limit_per_month', 3)

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
                    is_makeup INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, checkin_date)
                )
            ''')

            # Makeup check-in tracking table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS shop_makeup_checkin (
                    user_id INTEGER PRIMARY KEY,
                    makeup_1 TEXT,
                    makeup_2 TEXT,
                    makeup_3 TEXT,
                    makeup_4 TEXT,
                    makeup_5 TEXT
                )
            ''')
            await db.commit()

            # Add is_makeup column to existing records if not exists
            try:
                await db.execute('ALTER TABLE shop_checkin_records ADD COLUMN is_makeup INTEGER DEFAULT 0')
                await db.commit()
            except:
                # Column already exists
                pass
                
            # Add makeup_4 and makeup_5 columns to existing makeup table if not exists
            try:
                await db.execute('ALTER TABLE shop_makeup_checkin ADD COLUMN makeup_4 TEXT')
                await db.commit()
            except:
                # Column already exists
                pass
                
            try:
                await db.execute('ALTER TABLE shop_makeup_checkin ADD COLUMN makeup_5 TEXT')
                await db.commit()
            except:
                # Column already exists
                pass

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
                INSERT OR IGNORE INTO shop_checkin_records (user_id, checkin_date, checkin_timestamp, is_makeup) 
                VALUES (?, ?, ?, ?)
            ''', (user_id, today, now_timestamp, 0))

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

    async def get_makeup_count_this_month(self, user_id: int) -> int:
        """Get the number of makeup check-ins used this month."""
        current_month = datetime.now().strftime('%Y-%m')
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT makeup_1, makeup_2, makeup_3, makeup_4, makeup_5 FROM shop_makeup_checkin WHERE user_id = ?',
                (user_id,)
            )
            result = await cursor.fetchone()
            
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
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT checkin_date FROM shop_checkin_records WHERE user_id = ? AND is_makeup = 0 ORDER BY checkin_date ASC LIMIT 1',
                (user_id,)
            )
            result = await cursor.fetchone()
            return result[0] if result else None

    async def find_latest_missed_checkin(self, user_id: int, days_back: int = 30) -> Optional[str]:
        """Find the latest missed check-in date within the specified days back.
        
        Returns:
            str: The date string (YYYY-MM-DD) of the latest missed check-in, or None if no missed days found.
        """
        # Get user's first check-in date to avoid makeup before first manual check-in
        first_checkin_str = await self.get_first_checkin_date(user_id)
        if not first_checkin_str:
            return None  # No manual check-ins yet
        
        first_checkin_date = datetime.fromisoformat(first_checkin_str).date()
        end_date = datetime.now().date()
        start_date = max(end_date - timedelta(days=days_back), first_checkin_date)
        
        async with aiosqlite.connect(self.db_path) as db:
            # Get all check-in dates for the user within the range
            cursor = await db.execute(
                'SELECT checkin_date FROM shop_checkin_records WHERE user_id = ? AND checkin_date >= ? AND checkin_date <= ?',
                (user_id, start_date.isoformat(), end_date.isoformat())
            )
            checkin_dates = {row[0] for row in await cursor.fetchall()}
        
        # Find the latest missed date
        current_date = end_date - timedelta(days=1)  # Start from yesterday
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
        now_timestamp = datetime.now().isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Get current makeup records
            cursor = await db.execute(
                'SELECT makeup_1, makeup_2, makeup_3, makeup_4, makeup_5 FROM shop_makeup_checkin WHERE user_id = ?',
                (user_id,)
            )
            result = await cursor.fetchone()
            
            if result:
                makeup_1, makeup_2, makeup_3, makeup_4, makeup_5 = result
                
                # Find an empty slot or the oldest record to replace
                if not makeup_1:
                    slot = 'makeup_1'
                elif not makeup_2:
                    slot = 'makeup_2'
                elif not makeup_3:
                    slot = 'makeup_3'
                elif not makeup_4:
                    slot = 'makeup_4'
                elif not makeup_5:
                    slot = 'makeup_5'
                else:
                    # All slots occupied, find the oldest one in current month
                    current_month = datetime.now().strftime('%Y-%m')
                    oldest_slot = None
                    oldest_time = None
                    
                    for i, (slot_name, time_str) in enumerate([
                        ('makeup_1', makeup_1),
                        ('makeup_2', makeup_2), 
                        ('makeup_3', makeup_3),
                        ('makeup_4', makeup_4),
                        ('makeup_5', makeup_5)
                    ]):
                        if time_str:
                            try:
                                time_obj = datetime.fromisoformat(time_str)
                                if time_obj.strftime('%Y-%m') == current_month:
                                    # This is a current month record, can't replace
                                    continue
                                if oldest_time is None or time_obj < oldest_time:
                                    oldest_time = time_obj
                                    oldest_slot = slot_name
                            except (ValueError, TypeError):
                                # Invalid timestamp, can replace
                                oldest_slot = slot_name
                                break
                    
                    if oldest_slot is None:
                        # All slots are current month, no available slots
                        return False
                    
                    slot = oldest_slot
                
                # Update the record
                await db.execute(
                    f'UPDATE shop_makeup_checkin SET {slot} = ? WHERE user_id = ?',
                    (now_timestamp, user_id)
                )
            else:
                # Create new record
                await db.execute(
                    'INSERT INTO shop_makeup_checkin (user_id, makeup_1, makeup_2, makeup_3, makeup_4, makeup_5) VALUES (?, ?, ?, ?, ?, ?)',
                    (user_id, now_timestamp, None, None, None, None)
                )
            
            # Add the actual makeup check-in record
            await db.execute(
                'INSERT OR IGNORE INTO shop_checkin_records (user_id, checkin_date, checkin_timestamp, is_makeup) VALUES (?, ?, ?, ?)',
                (user_id, makeup_date, now_timestamp, 1)
            )
            
            await db.commit()
            
            # Recalculate and update streak after makeup
            await self.recalculate_checkin_streak(user_id)
            
            return True

    async def recalculate_checkin_streak(self, user_id: int) -> None:
        """Recalculate user's check-in streak after makeup."""
        async with aiosqlite.connect(self.db_path) as db:
            # Get all check-in dates for this user (including makeup), sorted by date
            cursor = await db.execute(
                'SELECT checkin_date FROM shop_checkin_records WHERE user_id = ? ORDER BY checkin_date DESC',
                (user_id,)
            )
            dates = [row[0] for row in await cursor.fetchall()]
            
            if not dates:
                return
            
            # Calculate current streak
            today = datetime.now().date()
            current_streak = 0
            max_streak = 0
            temp_streak = 0
            
            # Check for current streak (starting from today or yesterday)
            expected_date = today
            for date_str in dates:
                check_date = datetime.fromisoformat(date_str).date()
                if check_date == expected_date or (expected_date == today and check_date == today - timedelta(days=1)):
                    current_streak = 1
                    expected_date = check_date - timedelta(days=1)
                    break
            
            # Continue counting backward for current streak
            for date_str in dates:
                check_date = datetime.fromisoformat(date_str).date()
                if check_date == expected_date:
                    current_streak += 1
                    expected_date = check_date - timedelta(days=1)
                elif check_date < expected_date:
                    break
            
            # Calculate max streak by checking all dates
            prev_date = None
            for date_str in reversed(dates):  # Process chronologically
                check_date = datetime.fromisoformat(date_str).date()
                if prev_date is None or check_date == prev_date + timedelta(days=1):
                    temp_streak += 1
                    max_streak = max(max_streak, temp_streak)
                else:
                    temp_streak = 1
                prev_date = check_date
            
            # Get the latest check-in date
            latest_checkin = dates[0]
            
            # Update the shop_user_checkin table
            await db.execute('''
                INSERT INTO shop_user_checkin (user_id, last_checkin, streak, max_streak) 
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    last_checkin = ?,
                    streak = ?,
                    max_streak = ?
            ''', (user_id, latest_checkin, current_streak, max_streak, 
                  latest_checkin, current_streak, max_streak))
            
            await db.commit()

