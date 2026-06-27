import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

from .db_connect import connect_database
from .db_lifecycle import BaseDatabaseManager
from .log_helpers import fmt_channel, fmt_user


class AchievementDatabaseManager(BaseDatabaseManager):
    def __init__(self, db_path: str, config: dict = None):
        self.db_path = db_path
        self.config = config or {}
        self._persistent_connection: Optional[aiosqlite.Connection] = None
        self._persistent_connection_lock = asyncio.Lock()

        # Map achievement types from config to database column names
        self.type_mapping = {
            'reaction': 'reaction_count',
            'message': 'message_count',
            'time_spent': 'time_spent',
            'checkin_sum': 'checkin_sum',
            'checkin_combo': 'checkin_combo'
        }

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
        self, sql: str, parameters: Tuple[Any, ...] = ()
    ) -> Optional[Tuple]:
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            return await self._fetchone_on_connection(db, sql, parameters)

    async def _fetchall(self, sql: str, parameters: Tuple[Any, ...] = ()) -> List[Tuple]:
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            return await self._fetchall_on_connection(db, sql, parameters)

    async def initialize_database(self) -> None:
        """Create necessary achievement-related database tables if they don't exist."""
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                # Main achievements table
                await self._execute_on_connection(db, '''
                    CREATE TABLE IF NOT EXISTS achievements (
                        user_id INTEGER PRIMARY KEY,
                        message_count INTEGER DEFAULT 0,
                        reaction_count INTEGER DEFAULT 0,
                        time_spent INTEGER DEFAULT 0,
                        giveaway_count INTEGER DEFAULT 0
                    )
                ''')

                # Monthly achievements table
                await self._execute_on_connection(db, '''
                    CREATE TABLE IF NOT EXISTS monthly_achievements (
                        user_id INTEGER NOT NULL,
                        year INTEGER NOT NULL,
                        month INTEGER NOT NULL,
                        message_count INTEGER DEFAULT 0,
                        reaction_count INTEGER DEFAULT 0,
                        time_spent INTEGER DEFAULT 0,
                        giveaway_count INTEGER DEFAULT 0,
                        PRIMARY KEY (user_id, year, month)
                    )
                ''')

                # Voice channel entries table
                await self._execute_on_connection(db, '''
                    CREATE TABLE IF NOT EXISTS voice_channel_entries (
                        user_id INTEGER NOT NULL,
                        channel_id INTEGER NOT NULL,
                        start_time TIMESTAMP NOT NULL,
                        PRIMARY KEY (user_id, channel_id)
                    )
                ''')

                # Achievement operation log table
                await self._execute_on_connection(db, '''
                    CREATE TABLE IF NOT EXISTS achievement_operation (
                        user_id INTEGER NOT NULL,
                        target_user_id INTEGER NOT NULL,
                        operation TEXT NOT NULL,
                        message_count INTEGER DEFAULT 0,
                        reaction_count INTEGER DEFAULT 0,
                        time_spent INTEGER DEFAULT 0,
                        giveaway_count INTEGER DEFAULT 0,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # Create indexes for better performance
                await self._execute_on_connection(
                    db,
                    "CREATE INDEX IF NOT EXISTS idx_achievements_message_count "
                    "ON achievements(message_count DESC)",
                )
                await self._execute_on_connection(
                    db,
                    "CREATE INDEX IF NOT EXISTS idx_achievements_reaction_count "
                    "ON achievements(reaction_count DESC)",
                )
                await self._execute_on_connection(
                    db,
                    "CREATE INDEX IF NOT EXISTS idx_achievements_time_spent "
                    "ON achievements(time_spent DESC)",
                )
                await self._execute_on_connection(
                    db,
                    "CREATE INDEX IF NOT EXISTS idx_achievements_giveaway_count "
                    "ON achievements(giveaway_count DESC)",
                )
                await self._execute_on_connection(
                    db,
                    "CREATE INDEX IF NOT EXISTS idx_monthly_achievements_date "
                    "ON monthly_achievements(year, month)",
                )
                await self._execute_on_connection(
                    db,
                    "CREATE INDEX IF NOT EXISTS idx_voice_entries_user_channel "
                    "ON voice_channel_entries(user_id, channel_id)",
                )

                await db.commit()
            except Exception:
                await db.rollback()
                raise

    def _get_column_name(self, achievement_type: str) -> str:
        """Convert achievement type from config to database column name."""
        return self.type_mapping.get(achievement_type, achievement_type)

    def _get_achievement_types_from_config(self) -> List[str]:
        """Extract all achievement types from configuration."""
        types = set()
        for achievement in self.config.get('achievements_ranking', []):
            types.add(achievement.get('type'))
        return list(types)

    async def get_user_achievements(self, user_id: int) -> Dict[str, int]:
        """Get user's achievement counts."""
        try:
            result = await self._fetchone(
                "SELECT message_count, reaction_count, time_spent, giveaway_count "
                "FROM achievements WHERE user_id = ?",
                (user_id,),
            )

            # Get checkin data
            checkin_data = await self.get_user_checkin_data(user_id)

            if result:
                return {
                    'message_count': result[0],
                    'reaction_count': result[1],
                    'time_spent': result[2],
                    'giveaway_count': result[3],
                    'checkin_sum': checkin_data['checkin_sum'],
                    'checkin_combo': checkin_data['checkin_combo']
                }

            return {
                'message_count': 0,
                'reaction_count': 0,
                'time_spent': 0,
                'giveaway_count': 0,
                'checkin_sum': checkin_data['checkin_sum'],
                'checkin_combo': checkin_data['checkin_combo']
            }
        except Exception as e:
            logging.error("Error getting user achievements for %s: %s", fmt_user(user_id), e)
            return {
                'message_count': 0,
                'reaction_count': 0,
                'time_spent': 0,
                'giveaway_count': 0,
                'checkin_sum': 0,
                'checkin_combo': 0
            }

    async def get_monthly_achievements(self, user_id: int, year: int, month: int) -> Dict[str, int]:
        """Get user's monthly achievement counts."""
        try:
            result = await self._fetchone(
                "SELECT message_count, reaction_count, time_spent, giveaway_count "
                "FROM monthly_achievements "
                "WHERE user_id = ? AND year = ? AND month = ?",
                (user_id, year, month),
            )

            # Get monthly checkin data
            monthly_checkin_data = await self.get_monthly_checkin_data(
                user_id, year, month
            )

            if result:
                return {
                    'message_count': result[0],
                    'reaction_count': result[1],
                    'time_spent': result[2],
                    'giveaway_count': result[3],
                    'checkin_sum': monthly_checkin_data['checkin_sum'],
                    'checkin_combo': monthly_checkin_data['checkin_combo']
                }

            return {
                'message_count': 0,
                'reaction_count': 0,
                'time_spent': 0,
                'giveaway_count': 0,
                'checkin_sum': monthly_checkin_data['checkin_sum'],
                'checkin_combo': monthly_checkin_data['checkin_combo']
            }
        except Exception as e:
            logging.error(
                "Error getting monthly achievements for %s (%s-%s): %s",
                fmt_user(user_id),
                year,
                month,
                e,
            )
            return {
                'message_count': 0,
                'reaction_count': 0,
                'time_spent': 0,
                'giveaway_count': 0,
                'checkin_sum': 0,
                'checkin_combo': 0
            }

    async def create_user_if_not_exists(self, user_id: int) -> bool:
        """Create a user record if it doesn't exist."""
        try:
            await self._execute_write(
                "INSERT OR IGNORE INTO achievements (user_id) VALUES (?)",
                (user_id,),
            )
            return True
        except Exception as e:
            logging.error("Error creating user record for %s: %s", fmt_user(user_id), e)
            return False

    async def create_monthly_user_if_not_exists(self, user_id: int, year: int, month: int) -> bool:
        """Create a monthly user record if it doesn't exist."""
        try:
            await self._execute_write(
                "INSERT OR IGNORE INTO monthly_achievements "
                "(user_id, year, month) VALUES (?, ?, ?)",
                (user_id, year, month),
            )
            return True
        except Exception as e:
            logging.error(
                "Error creating monthly user record for %s (%s-%s): %s",
                fmt_user(user_id),
                year,
                month,
                e,
            )
            return False

    async def update_achievement_count(
        self,
        user_id: int,
        achievement_type: str,
        amount: int,
    ) -> bool:
        """Update user's achievement count."""
        column_name = self._get_column_name(achievement_type)
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                # Create user if not exists
                await self._execute_on_connection(
                    db,
                    "INSERT OR IGNORE INTO achievements (user_id) VALUES (?)",
                    (user_id,),
                )

                # Update achievement count
                await self._execute_on_connection(
                    db,
                    f"UPDATE achievements SET {column_name} = {column_name} + ? "
                    "WHERE user_id = ?",
                    (amount, user_id),
                )
                await db.commit()
                return True
            except Exception as e:
                await db.rollback()
                logging.error("Error updating achievement count for %s: %s", fmt_user(user_id), e)
                return False

    async def update_monthly_achievement_count(
        self,
        user_id: int,
        achievement_type: str,
        amount: int,
        year: int,
        month: int,
    ) -> bool:
        """Update user's monthly achievement count."""
        column_name = self._get_column_name(achievement_type)
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                # Create monthly user if not exists
                await self._execute_on_connection(
                    db,
                    "INSERT OR IGNORE INTO monthly_achievements "
                    "(user_id, year, month) VALUES (?, ?, ?)",
                    (user_id, year, month),
                )

                # Update monthly achievement count
                await self._execute_on_connection(
                    db,
                    f"UPDATE monthly_achievements SET {column_name} = {column_name} + ? "
                    "WHERE user_id = ? AND year = ? AND month = ?",
                    (amount, user_id, year, month),
                )
                await db.commit()
                return True
            except Exception as e:
                await db.rollback()
                logging.error(
                    "Error updating monthly achievement count for %s (%s-%s): %s",
                    fmt_user(user_id),
                    year,
                    month,
                    e,
                )
                return False

    async def get_leaderboard(
        self,
        achievement_type: str,
        limit: int = 10,
    ) -> List[Tuple[int, int]]:
        """Get leaderboard for a specific achievement type."""
        # Handle checkin types separately
        if achievement_type in ['checkin_sum', 'checkin_combo']:
            return await self.get_checkin_leaderboard(achievement_type, limit)

        column_name = self._get_column_name(achievement_type)
        try:
            return await self._fetchall(
                f"SELECT user_id, {column_name} FROM achievements "
                f"WHERE {column_name} > 0 ORDER BY {column_name} DESC LIMIT ?",
                (limit,),
            )
        except Exception as e:
            logging.error(f"Error getting leaderboard for {achievement_type}: {e}")
            return []

    async def get_monthly_leaderboard(
        self,
        year: int,
        month: int,
        achievement_type: str,
        limit: int = 10,
    ) -> List[Tuple[int, int]]:
        """Get monthly leaderboard for a specific achievement type."""
        # Handle checkin types separately
        if achievement_type in ['checkin_sum', 'checkin_combo']:
            return await self.get_monthly_checkin_leaderboard(year, month, achievement_type, limit)

        column_name = self._get_column_name(achievement_type)
        try:
            return await self._fetchall(
                f"SELECT user_id, {column_name} FROM monthly_achievements "
                f"WHERE year = ? AND month = ? AND {column_name} > 0 "
                f"ORDER BY {column_name} DESC LIMIT ?",
                (year, month, limit),
            )
        except Exception as e:
            logging.error(
                f"Error getting monthly leaderboard for {achievement_type} "
                f"({year}-{month}): {e}"
            )
            return []

    async def get_user_rank(self, user_id: int, achievement_type: str) -> Tuple[int, int]:
        """Get user's rank and total participants for a specific achievement type."""
        column_name = self._get_column_name(achievement_type)
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                # Get user's count
                user_result = await self._fetchone_on_connection(
                    db,
                    f"SELECT {column_name} FROM achievements WHERE user_id = ?",
                    (user_id,),
                )
                user_count = user_result[0] if user_result else 0

                # Get rank
                rank_result = await self._fetchone_on_connection(
                    db,
                    f"SELECT COUNT(*) FROM achievements WHERE {column_name} > ?",
                    (user_count,),
                )
                rank = rank_result[0] + 1 if rank_result else 1

                # Get total participants
                total_result = await self._fetchone_on_connection(
                    db,
                    f"SELECT COUNT(*) FROM achievements WHERE {column_name} > 0",
                )
                total = total_result[0] if total_result else 0

                return rank, total
            except Exception as e:
                logging.error("Error getting user rank for %s: %s", fmt_user(user_id), e)
                return 0, 0

    async def start_voice_session(self, user_id: int, channel_id: int) -> bool:
        """Start a voice session for a user."""
        try:
            current_time = datetime.now(timezone.utc)
            await self._execute_write(
                "REPLACE INTO voice_channel_entries "
                "(user_id, channel_id, start_time) VALUES (?, ?, ?)",
                (user_id, channel_id, current_time.isoformat()),
            )
            return True
        except Exception as e:
            logging.error(
                "Error starting voice session for %s in %s: %s",
                fmt_user(user_id),
                fmt_channel(channel_id),
                e,
            )
            return False

    async def end_voice_session(self, user_id: int, channel_id: int) -> int:
        """End a voice session and return time spent in seconds."""
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                # Get session start time
                entry = await self._fetchone_on_connection(
                    db,
                    "SELECT start_time FROM voice_channel_entries "
                    "WHERE user_id = ? AND channel_id = ?",
                    (user_id, channel_id),
                )

                if not entry:
                    return 0

                start_time = datetime.fromisoformat(entry[0])
                current_time = datetime.now(timezone.utc)
                time_spent = int((current_time - start_time).total_seconds())

                # Delete the entry
                await self._execute_on_connection(
                    db,
                    "DELETE FROM voice_channel_entries "
                    "WHERE user_id = ? AND channel_id = ?",
                    (user_id, channel_id),
                )
                await db.commit()

                return time_spent
            except Exception as e:
                await db.rollback()
                logging.error(
                    "Error ending voice session for %s in %s: %s",
                    fmt_user(user_id),
                    fmt_channel(channel_id),
                    e,
                )
                return 0

    async def get_active_voice_sessions(self, user_id: int) -> List[Tuple[int, str]]:
        """Get all active voice sessions for a user."""
        try:
            return await self._fetchall(
                "SELECT channel_id, start_time FROM voice_channel_entries WHERE user_id = ?",
                (user_id,),
            )
        except Exception as e:
            logging.error("Error getting active voice sessions for %s: %s", fmt_user(user_id), e)
            return []

    async def log_manual_operation(
        self,
        operator_id: int,
        target_id: int,
        operation: str,
        changes: Dict[str, int],
    ) -> bool:
        """Log a manual operation on achievements."""
        try:
            await self._execute_write(
                "INSERT INTO achievement_operation "
                "(user_id, target_user_id, operation, message_count, "
                "reaction_count, time_spent) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    operator_id,
                    target_id,
                    operation,
                    changes.get('message_count', 0),
                    changes.get('reaction_count', 0),
                    changes.get('time_spent', 0),
                ),
            )
            return True
        except Exception as e:
            logging.error(f"Error logging manual operation: {e}")
            return False

    async def apply_manual_changes(
        self,
        target_id: int,
        changes: Dict[str, int],
        operation: str,
    ) -> bool:
        """Apply manual changes to user achievements."""
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                # Create user if not exists
                await self._execute_on_connection(
                    db,
                    "INSERT OR IGNORE INTO achievements (user_id) VALUES (?)",
                    (target_id,),
                )

                # Apply changes based on operation
                if operation == 'increase':
                    await self._execute_on_connection(
                        db,
                        "UPDATE achievements SET "
                        "message_count = message_count + ?, "
                        "reaction_count = reaction_count + ?, "
                        "time_spent = time_spent + ? "
                        "WHERE user_id = ?",
                        (
                            changes.get('message_count', 0),
                            changes.get('reaction_count', 0),
                            changes.get('time_spent', 0),
                            target_id,
                        ),
                    )
                elif operation == 'decrease':
                    await self._execute_on_connection(
                        db,
                        "UPDATE achievements SET "
                        "message_count = message_count - ?, "
                        "reaction_count = reaction_count - ?, "
                        "time_spent = time_spent - ? "
                        "WHERE user_id = ?",
                        (
                            changes.get('message_count', 0),
                            changes.get('reaction_count', 0),
                            changes.get('time_spent', 0),
                            target_id,
                        ),
                    )

                await db.commit()
                return True
            except Exception as e:
                await db.rollback()
                logging.error(f"Error applying manual changes: {e}")
                return False

    async def get_all_operations(self) -> List[Tuple]:
        """Get all manual operations, ordered by timestamp DESC."""
        try:
            return await self._fetchall(
                "SELECT user_id, target_user_id, operation, message_count, "
                "reaction_count, time_spent, timestamp, giveaway_count "
                "FROM achievement_operation ORDER BY timestamp DESC"
            )
        except Exception as e:
            logging.error(f"Error getting all operations: {e}")
            return []

    async def cleanup_invalid_voice_sessions(self, valid_sessions: List[Tuple[int, int]]) -> bool:
        """Clean up voice sessions that are no longer valid."""
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                # Get all current sessions
                all_sessions = await self._fetchall_on_connection(
                    db,
                    "SELECT user_id, channel_id FROM voice_channel_entries",
                )

                # Find sessions to remove
                valid_set = set(valid_sessions)
                to_remove = [session for session in all_sessions if session not in valid_set]

                # Remove invalid sessions
                for user_id, channel_id in to_remove:
                    await self._execute_on_connection(
                        db,
                        "DELETE FROM voice_channel_entries WHERE user_id = ? AND channel_id = ?",
                        (user_id, channel_id),
                    )

                await db.commit()
                return True
            except Exception as e:
                await db.rollback()
                logging.error(f"Error cleaning up voice sessions: {e}")
                return False

    async def get_extended_leaderboard(
        self,
        achievement_type: str,
        limit: int = 40,
    ) -> List[Tuple[int, int]]:
        """Get extended leaderboard for a specific achievement type."""
        return await self.get_leaderboard(achievement_type, limit)

    async def get_extended_monthly_leaderboard(
        self,
        year: int,
        month: int,
        achievement_type: str,
        limit: int = 40,
    ) -> List[Tuple[int, int]]:
        """Get extended monthly leaderboard for a specific achievement type."""
        return await self.get_monthly_leaderboard(year, month, achievement_type, limit)

    async def get_all_leaderboards(
        self,
        achievement_types: List[str],
        limit: int = 40,
    ) -> Dict[str, List[Tuple[int, int]]]:
        """Get leaderboards for all achievement types."""
        result = {}
        for achievement_type in achievement_types:
            result[achievement_type] = await self.get_extended_leaderboard(achievement_type, limit)
        return result

    async def get_all_monthly_leaderboards(
        self,
        year: int,
        month: int,
        achievement_types: List[str],
        limit: int = 40,
    ) -> Dict[str, List[Tuple[int, int]]]:
        """Get monthly leaderboards for all achievement types."""
        result = {}
        for achievement_type in achievement_types:
            result[achievement_type] = await self.get_extended_monthly_leaderboard(
                year, month, achievement_type, limit
            )
        return result

    async def get_user_checkin_data(self, user_id: int) -> Dict[str, int]:
        """Get user's checkin data from shop tables."""
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                # Get total checkin count (sum)
                checkin_sum_result = await self._fetchone_on_connection(
                    db,
                    "SELECT COUNT(*) FROM shop_checkin_records WHERE user_id = ?",
                    (user_id,),
                )
                checkin_sum = checkin_sum_result[0] if checkin_sum_result else 0

                # Get max streak (combo)
                checkin_combo_result = await self._fetchone_on_connection(
                    db,
                    "SELECT max_streak FROM shop_user_checkin WHERE user_id = ?",
                    (user_id,),
                )
                checkin_combo = checkin_combo_result[0] if checkin_combo_result else 0

                return {
                    'checkin_sum': checkin_sum,
                    'checkin_combo': checkin_combo
                }
            except Exception as e:
                logging.error("Error getting checkin data for %s: %s", fmt_user(user_id), e)
                return {
                    'checkin_sum': 0,
                    'checkin_combo': 0
                }

    async def get_monthly_checkin_data(self, user_id: int, year: int, month: int) -> Dict[str, int]:
        """Get user's monthly checkin data from shop tables."""
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                month_prefix = f"{year}-{month:02d}-%"

                # Get monthly checkin count
                monthly_checkin_result = await self._fetchone_on_connection(
                    db,
                    "SELECT COUNT(*) FROM shop_checkin_records "
                    "WHERE user_id = ? AND checkin_date LIKE ?",
                    (user_id, month_prefix),
                )
                monthly_checkin = monthly_checkin_result[0] if monthly_checkin_result else 0

                # For monthly combo, calculate max consecutive days in that month.
                dates = await self._fetchall_on_connection(
                    db,
                    "SELECT checkin_date FROM shop_checkin_records "
                    "WHERE user_id = ? AND checkin_date LIKE ? ORDER BY checkin_date",
                    (user_id, month_prefix),
                )

                max_consecutive = 0
                current_consecutive = 0
                prev_date = None

                for date_tuple in dates:
                    date_str = date_tuple[0]
                    current_date = datetime.strptime(date_str, "%Y-%m-%d")

                    if prev_date is None:
                        current_consecutive = 1
                    elif (current_date - prev_date).days == 1:
                        current_consecutive += 1
                    else:
                        current_consecutive = 1

                    max_consecutive = max(max_consecutive, current_consecutive)
                    prev_date = current_date

                return {
                    'checkin_sum': monthly_checkin,
                    'checkin_combo': max_consecutive
                }
            except Exception as e:
                logging.error(
                    "Error getting monthly checkin data for %s (%s-%s): %s",
                    fmt_user(user_id),
                    year,
                    month,
                    e,
                )
                return {
                    'checkin_sum': 0,
                    'checkin_combo': 0
                }

    async def get_checkin_leaderboard(
        self,
        checkin_type: str,
        limit: int = 10,
    ) -> List[Tuple[int, int]]:
        """Get leaderboard for checkin achievements."""
        try:
            if checkin_type == 'checkin_sum':
                # Get total checkin count leaderboard
                return await self._fetchall(
                    "SELECT user_id, COUNT(*) as count FROM shop_checkin_records "
                    "GROUP BY user_id ORDER BY count DESC LIMIT ?",
                    (limit,),
                )

            if checkin_type == 'checkin_combo':
                # Get max streak leaderboard
                return await self._fetchall(
                    "SELECT user_id, max_streak FROM shop_user_checkin "
                    "WHERE max_streak > 0 ORDER BY max_streak DESC LIMIT ?",
                    (limit,),
                )

            return []
        except Exception as e:
            logging.error(f"Error getting checkin leaderboard for {checkin_type}: {e}")
            return []

    async def get_monthly_checkin_leaderboard(
        self,
        year: int,
        month: int,
        checkin_type: str,
        limit: int = 10,
    ) -> List[Tuple[int, int]]:
        """Get monthly leaderboard for checkin achievements."""
        try:
            month_prefix = f"{year}-{month:02d}-%"

            if checkin_type == 'checkin_sum':
                # Get monthly checkin count leaderboard
                return await self._fetchall(
                    "SELECT user_id, COUNT(*) as count FROM shop_checkin_records "
                    "WHERE checkin_date LIKE ? GROUP BY user_id "
                    "ORDER BY count DESC LIMIT ?",
                    (month_prefix, limit),
                )

            if checkin_type == 'checkin_combo':
                # For monthly combo, calculate max consecutive days per user.
                users = await self._fetchall(
                    "SELECT DISTINCT user_id FROM shop_checkin_records "
                    "WHERE checkin_date LIKE ?",
                    (month_prefix,),
                )

                user_combos = []
                for user_tuple in users:
                    user_id = user_tuple[0]
                    monthly_data = await self.get_monthly_checkin_data(
                        user_id, year, month
                    )
                    combo = monthly_data['checkin_combo']
                    if combo > 0:
                        user_combos.append((user_id, combo))

                # Sort by combo descending and limit
                user_combos.sort(key=lambda x: x[1], reverse=True)
                return user_combos[:limit]

            return []
        except Exception as e:
            logging.error(
                f"Error getting monthly checkin leaderboard for {checkin_type} "
                f"({year}-{month}): {e}"
            )
            return []
