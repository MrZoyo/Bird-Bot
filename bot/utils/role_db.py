# bot/utils/role_db.py
import aiosqlite
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple, Any


class RoleDatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize_database(self) -> None:
        """Create necessary role-related database tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            # Role views tables for different role types
            await db.execute('''
                CREATE TABLE IF NOT EXISTS role_views (
                    message_id TEXT PRIMARY KEY,
                    channel_id TEXT
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS starsign_views (
                    message_id TEXT PRIMARY KEY,
                    channel_id TEXT
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS mbti_views (
                    message_id TEXT PRIMARY KEY,
                    channel_id TEXT
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS gender_views (
                    message_id TEXT PRIMARY KEY,
                    channel_id TEXT
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS signature_views (
                    message_id TEXT PRIMARY KEY,
                    channel_id TEXT
                )
            ''')
            
            # User signatures table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_signatures (
                    user_id INTEGER PRIMARY KEY,
                    signature TEXT,
                    change_time1 TIMESTAMP,
                    change_time2 TIMESTAMP,
                    change_time3 TIMESTAMP,
                    is_disabled BOOLEAN DEFAULT FALSE
                )
            ''')

            await db.commit()

    async def save_role_view(self, message_id: int, channel_id: int, table: str = 'role_views') -> bool:
        """Save a role view message to the database."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(f'INSERT INTO {table} (message_id, channel_id) VALUES (?, ?)',
                                 (message_id, channel_id))
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error saving role view to {table}: {e}")
                return False

    async def remove_role_view(self, message_id: int, channel_id: int, table: str = 'role_views') -> bool:
        """Remove a role view message from the database."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(f'DELETE FROM {table} WHERE message_id = ? AND channel_id = ?',
                                 (message_id, channel_id))
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error removing role view from {table}: {e}")
                return False

    async def get_all_role_views(self, table: str = 'role_views') -> List[Tuple[int, int]]:
        """Get all role view messages from the database."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute(f'SELECT message_id, channel_id FROM {table}')
                return await cursor.fetchall()
            except Exception as e:
                logging.error(f"Error getting role views from {table}: {e}")
                return []

    async def get_user_achievement_progress(self, user_id: int, achievement_type: str) -> Optional[int]:
        """Get user's progress for a specific achievement type."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                if achievement_type in ['checkin_sum', 'checkin_combo']:
                    return await self._get_checkin_progress(user_id, achievement_type)
                else:
                    # Map achievement type to database column
                    column_mapping = {
                        'reaction': 'reaction_count',
                        'message': 'message_count',
                        'time_spent': 'time_spent',
                        'giveaway': 'giveaway_count'
                    }
                    column_name = column_mapping.get(achievement_type, achievement_type)
                    
                    cursor = await db.execute(f"SELECT {column_name} FROM achievements WHERE user_id = ?", (user_id,))
                    result = await cursor.fetchone()
                    
                    if result and result[0] is not None:
                        # Convert time_spent from seconds to minutes if needed
                        if achievement_type == 'time_spent':
                            return result[0] // 60
                        return result[0]
                    return None
            except Exception as e:
                logging.error(f"Error getting achievement progress for {user_id}, type {achievement_type}: {e}")
                return None

    async def _get_checkin_progress(self, user_id: int, checkin_type: str) -> Optional[int]:
        """Get user's checkin progress from shop tables."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                if checkin_type == 'checkin_sum':
                    cursor = await db.execute("SELECT COUNT(*) FROM shop_checkin_records WHERE user_id = ?", (user_id,))
                    result = await cursor.fetchone()
                    return result[0] if result else 0
                elif checkin_type == 'checkin_combo':
                    cursor = await db.execute("SELECT max_streak FROM shop_user_checkin WHERE user_id = ?", (user_id,))
                    result = await cursor.fetchone()
                    return result[0] if result else 0
                return None
            except Exception as e:
                logging.error(f"Error getting checkin progress for {user_id}, type {checkin_type}: {e}")
                return None

    async def check_voice_time_requirement(self, user_id: int, required_time: int) -> Tuple[bool, int]:
        """Check if user meets voice time requirement for signature feature."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute(
                    "SELECT time_spent FROM achievements WHERE user_id = ?",
                    (user_id,)
                )
                result = await cursor.fetchone()

                if not result or not result[0]:
                    return False, 0

                # Convert seconds to minutes
                current_time = result[0] // 60
                return current_time >= required_time, current_time
            except Exception as e:
                logging.error(f"Error checking voice time requirement for {user_id}: {e}")
                return False, 0

    # Signature-related methods
    async def get_user_signature(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user's signature information."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute('''
                    SELECT signature, change_time1, change_time2, change_time3, is_disabled
                    FROM user_signatures 
                    WHERE user_id = ?
                ''', (user_id,))
                result = await cursor.fetchone()
                
                if result:
                    return {
                        'signature': result[0],
                        'change_time1': result[1],
                        'change_time2': result[2],
                        'change_time3': result[3],
                        'is_disabled': result[4]
                    }
                return None
            except Exception as e:
                logging.error(f"Error getting signature for {user_id}: {e}")
                return None

    async def update_user_signature(self, user_id: int, signature: str, time_slot: int) -> bool:
        """Update user's signature and record the change time."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                current_time = datetime.now(timezone.utc).isoformat()
                
                if time_slot == 1:
                    await db.execute('''
                        INSERT INTO user_signatures (user_id, signature, change_time1, is_disabled)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET 
                        signature = ?, change_time1 = ?
                    ''', (user_id, signature, current_time, False, signature, current_time))
                elif time_slot == 2:
                    await db.execute('''
                        UPDATE user_signatures 
                        SET signature = ?, change_time2 = ?
                        WHERE user_id = ?
                    ''', (signature, current_time, user_id))
                elif time_slot == 3:
                    await db.execute('''
                        UPDATE user_signatures 
                        SET signature = ?, change_time3 = ?
                        WHERE user_id = ?
                    ''', (signature, current_time, user_id))
                
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error updating signature for {user_id}: {e}")
                return False

    async def get_signature_remaining_changes(self, user_id: int) -> int:
        """Calculate remaining signature changes for a user."""
        signature_data = await self.get_user_signature(user_id)
        if not signature_data:
            return 3  # First time user gets 3 changes
        
        current_time = datetime.now(timezone.utc)
        times = [signature_data['change_time1'], signature_data['change_time2'], signature_data['change_time3']]
        
        # Count empty slots and slots older than 7 days
        remaining = 0
        for t in times:
            if not t:
                remaining += 1
            else:
                try:
                    time_obj = datetime.fromisoformat(t)
                    if (current_time - time_obj).days >= 7:
                        remaining += 1
                except (ValueError, TypeError):
                    remaining += 1
        
        return remaining

    async def find_available_time_slot(self, user_id: int) -> Optional[int]:
        """Find an available time slot for signature change."""
        signature_data = await self.get_user_signature(user_id)
        if not signature_data:
            return 1  # First time user uses slot 1
        
        current_time = datetime.now(timezone.utc)
        times = [
            signature_data['change_time1'], 
            signature_data['change_time2'], 
            signature_data['change_time3']
        ]
        
        # Check for empty slots first
        for i, t in enumerate(times, 1):
            if not t:
                return i
        
        # Check for slots older than 7 days
        oldest_time = None
        oldest_slot = None
        for i, t in enumerate(times, 1):
            if t:
                try:
                    time_obj = datetime.fromisoformat(t)
                    days_passed = (current_time - time_obj).days
                    if days_passed >= 7:
                        if oldest_time is None or time_obj < oldest_time:
                            oldest_time = time_obj
                            oldest_slot = i
                except (ValueError, TypeError):
                    return i  # Treat invalid time as available slot
        
        return oldest_slot

    async def toggle_signature_permission(self, user_id: int, disable: bool) -> bool:
        """Toggle a user's signature permission."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO user_signatures (user_id, is_disabled)
                    VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET is_disabled = ?
                ''', (user_id, disable, disable))
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error toggling signature permission for {user_id}: {e}")
                return False

    async def clear_user_signature(self, user_id: int) -> bool:
        """Clear user's signature and change history."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    UPDATE user_signatures
                    SET signature = NULL,
                        change_time1 = NULL,
                        change_time2 = NULL,
                        change_time3 = NULL
                    WHERE user_id = ?
                ''', (user_id,))
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error clearing signature for {user_id}: {e}")
                return False