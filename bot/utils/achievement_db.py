# bot/utils/achievement_db.py
import aiosqlite
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple, Any


class AchievementDatabaseManager:
    def __init__(self, db_path: str, config: dict = None):
        self.db_path = db_path
        self.config = config or {}
        
        # Map achievement types from config to database column names
        self.type_mapping = {
            'reaction': 'reaction_count',
            'message': 'message_count', 
            'time_spent': 'time_spent',
            'giveaway': 'giveaway_count',
            'checkin_sum': 'checkin_sum',
            'checkin_combo': 'checkin_combo'
        }

    async def initialize_database(self) -> None:
        """Create necessary achievement-related database tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            # Main achievements table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS achievements (
                    user_id INTEGER PRIMARY KEY,
                    message_count INTEGER DEFAULT 0,
                    reaction_count INTEGER DEFAULT 0,
                    time_spent INTEGER DEFAULT 0,
                    giveaway_count INTEGER DEFAULT 0
                )
            ''')

            # Monthly achievements table
            await db.execute('''
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
            await db.execute('''
                CREATE TABLE IF NOT EXISTS voice_channel_entries (
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    PRIMARY KEY (user_id, channel_id)
                )
            ''')

            # Achievement operation log table
            await db.execute('''
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
            await db.execute('CREATE INDEX IF NOT EXISTS idx_achievements_message_count ON achievements(message_count DESC)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_achievements_reaction_count ON achievements(reaction_count DESC)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_achievements_time_spent ON achievements(time_spent DESC)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_achievements_giveaway_count ON achievements(giveaway_count DESC)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_monthly_achievements_date ON monthly_achievements(year, month)')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_voice_entries_user_channel ON voice_channel_entries(user_id, channel_id)')

            await db.commit()

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
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute(
                    "SELECT message_count, reaction_count, time_spent, giveaway_count FROM achievements WHERE user_id = ?",
                    (user_id,)
                )
                result = await cursor.fetchone()
                
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
                else:
                    return {
                        'message_count': 0,
                        'reaction_count': 0,
                        'time_spent': 0,
                        'giveaway_count': 0,
                        'checkin_sum': checkin_data['checkin_sum'],
                        'checkin_combo': checkin_data['checkin_combo']
                    }
            except Exception as e:
                logging.error(f"Error getting user achievements for {user_id}: {e}")
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
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute(
                    "SELECT message_count, reaction_count, time_spent, giveaway_count FROM monthly_achievements WHERE user_id = ? AND year = ? AND month = ?",
                    (user_id, year, month)
                )
                result = await cursor.fetchone()
                
                # Get monthly checkin data
                monthly_checkin_data = await self.get_monthly_checkin_data(user_id, year, month)
                
                if result:
                    return {
                        'message_count': result[0],
                        'reaction_count': result[1],
                        'time_spent': result[2],
                        'giveaway_count': result[3],
                        'checkin_sum': monthly_checkin_data['checkin_sum'],
                        'checkin_combo': monthly_checkin_data['checkin_combo']
                    }
                else:
                    return {
                        'message_count': 0,
                        'reaction_count': 0,
                        'time_spent': 0,
                        'giveaway_count': 0,
                        'checkin_sum': monthly_checkin_data['checkin_sum'],
                        'checkin_combo': monthly_checkin_data['checkin_combo']
                    }
            except Exception as e:
                logging.error(f"Error getting monthly achievements for {user_id} ({year}-{month}): {e}")
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
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    "INSERT OR IGNORE INTO achievements (user_id) VALUES (?)",
                    (user_id,)
                )
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error creating user record for {user_id}: {e}")
                return False

    async def create_monthly_user_if_not_exists(self, user_id: int, year: int, month: int) -> bool:
        """Create a monthly user record if it doesn't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    "INSERT OR IGNORE INTO monthly_achievements (user_id, year, month) VALUES (?, ?, ?)",
                    (user_id, year, month)
                )
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error creating monthly user record for {user_id} ({year}-{month}): {e}")
                return False

    async def update_achievement_count(self, user_id: int, achievement_type: str, amount: int) -> bool:
        """Update user's achievement count."""
        column_name = self._get_column_name(achievement_type)
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Create user if not exists
                await self.create_user_if_not_exists(user_id)
                
                # Update achievement count
                await db.execute(
                    f"UPDATE achievements SET {column_name} = {column_name} + ? WHERE user_id = ?",
                    (amount, user_id)
                )
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error updating achievement count for {user_id}: {e}")
                return False

    async def update_monthly_achievement_count(self, user_id: int, achievement_type: str, amount: int, year: int, month: int) -> bool:
        """Update user's monthly achievement count."""
        column_name = self._get_column_name(achievement_type)
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Create monthly user if not exists
                await self.create_monthly_user_if_not_exists(user_id, year, month)
                
                # Update monthly achievement count
                await db.execute(
                    f"UPDATE monthly_achievements SET {column_name} = {column_name} + ? WHERE user_id = ? AND year = ? AND month = ?",
                    (amount, user_id, year, month)
                )
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error updating monthly achievement count for {user_id} ({year}-{month}): {e}")
                return False

    async def get_leaderboard(self, achievement_type: str, limit: int = 10) -> List[Tuple[int, int]]:
        """Get leaderboard for a specific achievement type."""
        # Handle checkin types separately
        if achievement_type in ['checkin_sum', 'checkin_combo']:
            return await self.get_checkin_leaderboard(achievement_type, limit)
        
        column_name = self._get_column_name(achievement_type)
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute(
                    f"SELECT user_id, {column_name} FROM achievements WHERE {column_name} > 0 ORDER BY {column_name} DESC LIMIT ?",
                    (limit,)
                )
                return await cursor.fetchall()
            except Exception as e:
                logging.error(f"Error getting leaderboard for {achievement_type}: {e}")
                return []

    async def get_monthly_leaderboard(self, year: int, month: int, achievement_type: str, limit: int = 10) -> List[Tuple[int, int]]:
        """Get monthly leaderboard for a specific achievement type."""
        # Handle checkin types separately
        if achievement_type in ['checkin_sum', 'checkin_combo']:
            return await self.get_monthly_checkin_leaderboard(year, month, achievement_type, limit)
        
        column_name = self._get_column_name(achievement_type)
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute(
                    f"SELECT user_id, {column_name} FROM monthly_achievements WHERE year = ? AND month = ? AND {column_name} > 0 ORDER BY {column_name} DESC LIMIT ?",
                    (year, month, limit)
                )
                return await cursor.fetchall()
            except Exception as e:
                logging.error(f"Error getting monthly leaderboard for {achievement_type} ({year}-{month}): {e}")
                return []

    async def get_user_rank(self, user_id: int, achievement_type: str) -> Tuple[int, int]:
        """Get user's rank and total participants for a specific achievement type."""
        column_name = self._get_column_name(achievement_type)
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Get user's count
                cursor = await db.execute(
                    f"SELECT {column_name} FROM achievements WHERE user_id = ?",
                    (user_id,)
                )
                user_result = await cursor.fetchone()
                user_count = user_result[0] if user_result else 0
                
                # Get rank
                cursor = await db.execute(
                    f"SELECT COUNT(*) FROM achievements WHERE {column_name} > ?",
                    (user_count,)
                )
                rank_result = await cursor.fetchone()
                rank = rank_result[0] + 1 if rank_result else 1
                
                # Get total participants
                cursor = await db.execute(
                    f"SELECT COUNT(*) FROM achievements WHERE {column_name} > 0"
                )
                total_result = await cursor.fetchone()
                total = total_result[0] if total_result else 0
                
                return rank, total
            except Exception as e:
                logging.error(f"Error getting user rank for {user_id}: {e}")
                return 0, 0

    async def start_voice_session(self, user_id: int, channel_id: int) -> bool:
        """Start a voice session for a user."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                current_time = datetime.now(timezone.utc)
                await db.execute(
                    "REPLACE INTO voice_channel_entries (user_id, channel_id, start_time) VALUES (?, ?, ?)",
                    (user_id, channel_id, current_time.isoformat())
                )
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error starting voice session for {user_id}: {e}")
                return False

    async def end_voice_session(self, user_id: int, channel_id: int) -> int:
        """End a voice session and return time spent in seconds."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Get session start time
                cursor = await db.execute(
                    "SELECT start_time FROM voice_channel_entries WHERE user_id = ? AND channel_id = ?",
                    (user_id, channel_id)
                )
                entry = await cursor.fetchone()
                
                if not entry:
                    return 0
                
                start_time = datetime.fromisoformat(entry[0])
                current_time = datetime.now(timezone.utc)
                time_spent = int((current_time - start_time).total_seconds())
                
                # Delete the entry
                await db.execute(
                    "DELETE FROM voice_channel_entries WHERE user_id = ? AND channel_id = ?",
                    (user_id, channel_id)
                )
                await db.commit()
                
                return time_spent
            except Exception as e:
                logging.error(f"Error ending voice session for {user_id}: {e}")
                return 0

    async def get_active_voice_sessions(self, user_id: int) -> List[Tuple[int, str]]:
        """Get all active voice sessions for a user."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute(
                    "SELECT channel_id, start_time FROM voice_channel_entries WHERE user_id = ?",
                    (user_id,)
                )
                return await cursor.fetchall()
            except Exception as e:
                logging.error(f"Error getting active voice sessions for {user_id}: {e}")
                return []

    async def log_manual_operation(self, operator_id: int, target_id: int, operation: str, changes: Dict[str, int]) -> bool:
        """Log a manual operation on achievements."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    "INSERT INTO achievement_operation (user_id, target_user_id, operation, message_count, reaction_count, time_spent, giveaway_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (operator_id, target_id, operation, 
                     changes.get('message_count', 0), 
                     changes.get('reaction_count', 0), 
                     changes.get('time_spent', 0), 
                     changes.get('giveaway_count', 0))
                )
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error logging manual operation: {e}")
                return False

    async def apply_manual_changes(self, target_id: int, changes: Dict[str, int], operation: str) -> bool:
        """Apply manual changes to user achievements."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Create user if not exists
                await self.create_user_if_not_exists(target_id)
                
                # Apply changes based on operation
                if operation == 'increase':
                    await db.execute(
                        "UPDATE achievements SET message_count = message_count + ?, reaction_count = reaction_count + ?, time_spent = time_spent + ?, giveaway_count = giveaway_count + ? WHERE user_id = ?",
                        (changes.get('message_count', 0), changes.get('reaction_count', 0), 
                         changes.get('time_spent', 0), changes.get('giveaway_count', 0), target_id)
                    )
                elif operation == 'decrease':
                    await db.execute(
                        "UPDATE achievements SET message_count = message_count - ?, reaction_count = reaction_count - ?, time_spent = time_spent - ?, giveaway_count = giveaway_count - ? WHERE user_id = ?",
                        (changes.get('message_count', 0), changes.get('reaction_count', 0), 
                         changes.get('time_spent', 0), changes.get('giveaway_count', 0), target_id)
                    )
                
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error applying manual changes: {e}")
                return False

    async def get_all_operations(self) -> List[Tuple]:
        """Get all manual operations, ordered by timestamp DESC."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute(
                    "SELECT user_id, target_user_id, operation, message_count, reaction_count, time_spent, timestamp, giveaway_count FROM achievement_operation ORDER BY timestamp DESC"
                )
                return await cursor.fetchall()
            except Exception as e:
                logging.error(f"Error getting all operations: {e}")
                return []

    async def cleanup_invalid_voice_sessions(self, valid_sessions: List[Tuple[int, int]]) -> bool:
        """Clean up voice sessions that are no longer valid."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Get all current sessions
                cursor = await db.execute("SELECT user_id, channel_id FROM voice_channel_entries")
                all_sessions = await cursor.fetchall()
                
                # Find sessions to remove
                valid_set = set(valid_sessions)
                to_remove = [session for session in all_sessions if session not in valid_set]
                
                # Remove invalid sessions
                for user_id, channel_id in to_remove:
                    await db.execute(
                        "DELETE FROM voice_channel_entries WHERE user_id = ? AND channel_id = ?",
                        (user_id, channel_id)
                    )
                
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error cleaning up voice sessions: {e}")
                return False

    async def get_extended_leaderboard(self, achievement_type: str, limit: int = 40) -> List[Tuple[int, int]]:
        """Get extended leaderboard for a specific achievement type."""
        return await self.get_leaderboard(achievement_type, limit)

    async def get_extended_monthly_leaderboard(self, year: int, month: int, achievement_type: str, limit: int = 40) -> List[Tuple[int, int]]:
        """Get extended monthly leaderboard for a specific achievement type."""
        return await self.get_monthly_leaderboard(year, month, achievement_type, limit)

    async def get_all_leaderboards(self, achievement_types: List[str], limit: int = 40) -> Dict[str, List[Tuple[int, int]]]:
        """Get leaderboards for all achievement types."""
        result = {}
        for achievement_type in achievement_types:
            result[achievement_type] = await self.get_extended_leaderboard(achievement_type, limit)
        return result

    async def get_all_monthly_leaderboards(self, year: int, month: int, achievement_types: List[str], limit: int = 40) -> Dict[str, List[Tuple[int, int]]]:
        """Get monthly leaderboards for all achievement types."""
        result = {}
        for achievement_type in achievement_types:
            result[achievement_type] = await self.get_extended_monthly_leaderboard(year, month, achievement_type, limit)
        return result

    async def check_column_exists(self, table_name: str, column_name: str) -> bool:
        """Check if a column exists in a table."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute(f"PRAGMA table_info({table_name})")
                columns = await cursor.fetchall()
                return any(column[1] == column_name for column in columns)
            except Exception as e:
                logging.error(f"Error checking column existence: {e}")
                return False

    async def add_column_if_not_exists(self, table_name: str, column_name: str, column_type: str = "INTEGER DEFAULT 0") -> bool:
        """Add a column to a table if it doesn't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                if not await self.check_column_exists(table_name, column_name):
                    await db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                    await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error adding column {column_name} to {table_name}: {e}")
                return False

    async def get_user_checkin_data(self, user_id: int) -> Dict[str, int]:
        """Get user's checkin data from shop tables."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Get total checkin count (sum)
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM shop_checkin_records WHERE user_id = ?",
                    (user_id,)
                )
                checkin_sum_result = await cursor.fetchone()
                checkin_sum = checkin_sum_result[0] if checkin_sum_result else 0
                
                # Get max streak (combo)
                cursor = await db.execute(
                    "SELECT max_streak FROM shop_user_checkin WHERE user_id = ?",
                    (user_id,)
                )
                checkin_combo_result = await cursor.fetchone()
                checkin_combo = checkin_combo_result[0] if checkin_combo_result else 0
                
                return {
                    'checkin_sum': checkin_sum,
                    'checkin_combo': checkin_combo
                }
            except Exception as e:
                logging.error(f"Error getting checkin data for {user_id}: {e}")
                return {
                    'checkin_sum': 0,
                    'checkin_combo': 0
                }

    async def get_monthly_checkin_data(self, user_id: int, year: int, month: int) -> Dict[str, int]:
        """Get user's monthly checkin data from shop tables."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Get monthly checkin count
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM shop_checkin_records WHERE user_id = ? AND checkin_date LIKE ?",
                    (user_id, f"{year}-{month:02d}-%")
                )
                monthly_checkin_result = await cursor.fetchone()
                monthly_checkin = monthly_checkin_result[0] if monthly_checkin_result else 0
                
                # For monthly combo, we need to calculate the max consecutive days in that month
                cursor = await db.execute(
                    "SELECT checkin_date FROM shop_checkin_records WHERE user_id = ? AND checkin_date LIKE ? ORDER BY checkin_date",
                    (user_id, f"{year}-{month:02d}-%")
                )
                dates = await cursor.fetchall()
                
                # Calculate max consecutive days in the month
                max_consecutive = 0
                current_consecutive = 0
                prev_date = None
                
                for date_tuple in dates:
                    date_str = date_tuple[0]
                    current_date = datetime.strptime(date_str, "%Y-%m-%d")
                    
                    if prev_date is None:
                        current_consecutive = 1
                    else:
                        if (current_date - prev_date).days == 1:
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
                logging.error(f"Error getting monthly checkin data for {user_id} ({year}-{month}): {e}")
                return {
                    'checkin_sum': 0,
                    'checkin_combo': 0
                }

    async def get_checkin_leaderboard(self, checkin_type: str, limit: int = 10) -> List[Tuple[int, int]]:
        """Get leaderboard for checkin achievements."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                if checkin_type == 'checkin_sum':
                    # Get total checkin count leaderboard
                    cursor = await db.execute(
                        "SELECT user_id, COUNT(*) as count FROM shop_checkin_records GROUP BY user_id ORDER BY count DESC LIMIT ?",
                        (limit,)
                    )
                elif checkin_type == 'checkin_combo':
                    # Get max streak leaderboard
                    cursor = await db.execute(
                        "SELECT user_id, max_streak FROM shop_user_checkin WHERE max_streak > 0 ORDER BY max_streak DESC LIMIT ?",
                        (limit,)
                    )
                else:
                    return []
                
                return await cursor.fetchall()
            except Exception as e:
                logging.error(f"Error getting checkin leaderboard for {checkin_type}: {e}")
                return []

    async def get_monthly_checkin_leaderboard(self, year: int, month: int, checkin_type: str, limit: int = 10) -> List[Tuple[int, int]]:
        """Get monthly leaderboard for checkin achievements."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                if checkin_type == 'checkin_sum':
                    # Get monthly checkin count leaderboard
                    cursor = await db.execute(
                        "SELECT user_id, COUNT(*) as count FROM shop_checkin_records WHERE checkin_date LIKE ? GROUP BY user_id ORDER BY count DESC LIMIT ?",
                        (f"{year}-{month:02d}-%", limit)
                    )
                    return await cursor.fetchall()
                elif checkin_type == 'checkin_combo':
                    # For monthly combo leaderboard, we need to calculate max consecutive days for each user
                    cursor = await db.execute(
                        "SELECT DISTINCT user_id FROM shop_checkin_records WHERE checkin_date LIKE ?",
                        (f"{year}-{month:02d}-%",)
                    )
                    users = await cursor.fetchall()
                    
                    user_combos = []
                    for user_tuple in users:
                        user_id = user_tuple[0]
                        monthly_data = await self.get_monthly_checkin_data(user_id, year, month)
                        combo = monthly_data['checkin_combo']
                        if combo > 0:
                            user_combos.append((user_id, combo))
                    
                    # Sort by combo descending and limit
                    user_combos.sort(key=lambda x: x[1], reverse=True)
                    return user_combos[:limit]
                else:
                    return []
            except Exception as e:
                logging.error(f"Error getting monthly checkin leaderboard for {checkin_type} ({year}-{month}): {e}")
                return []