# bot/utils/teamup_display_manager.py
import aiosqlite
import logging
from typing import Optional, List, Dict, Tuple

from .db_connect import connect_database
from .db_lifecycle import BaseDatabaseManager
from .invitation_db import InvitationDatabaseManager, initialize_invitation_schema
from .log_helpers import fmt_channel, fmt_user


class TeamupDisplayManager(BaseDatabaseManager):
    """Database operations manager for teamup display board functionality"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    async def init_tables(self):
        """Initialize database tables"""
        async with connect_database(self.db_path) as db:
            await db.execute('BEGIN IMMEDIATE')
            # Display board management table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS teamup_displays (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER UNIQUE NOT NULL,
                    message_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    updated_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
                )
            ''')

            # Game type and channel association table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS teamup_game_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER UNIQUE NOT NULL,
                    game_type TEXT NOT NULL,
                    display_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
                )
            ''')

            await initialize_invitation_schema(db)

            # User teamup statistics table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS user_teamup_stats (
                    user_id INTEGER PRIMARY KEY,
                    teamup_count INTEGER DEFAULT 0,
                    last_teamup_at TIMESTAMP
                )
            ''')

            await db.commit()
    
    async def save_display_board(self, channel_id: int, message_id: int) -> bool:
        """Save or update display board information"""
        async with connect_database(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT OR REPLACE INTO teamup_displays (channel_id, message_id, updated_at)
                    VALUES (?, ?, datetime('now', 'localtime'))
                ''', (channel_id, message_id))
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Failed to save display board: {e}")
                return False
    
    async def get_display_board(self, channel_id: int) -> Optional[Tuple[int, int]]:
        """Get display board information"""
        async with connect_database(self.db_path) as db:
            cursor = await db.execute('''
                SELECT message_id, channel_id FROM teamup_displays WHERE channel_id = ?
            ''', (channel_id,))
            result = await cursor.fetchone()
            return result if result else None
    
    async def remove_display_board(self, channel_id: int) -> bool:
        """Remove display board information"""
        async with connect_database(self.db_path) as db:
            try:
                await db.execute('DELETE FROM teamup_displays WHERE channel_id = ?', (channel_id,))
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Failed to remove display board: {e}")
                return False
    
    async def add_game_type(self, channel_id: int, game_type: str) -> bool:
        """Add game type configuration"""
        async with connect_database(self.db_path) as db:
            try:
                # Get current maximum display_order
                cursor = await db.execute('SELECT MAX(display_order) FROM teamup_game_types')
                max_order = await cursor.fetchone()
                next_order = (max_order[0] or 0) + 1
                
                await db.execute('''
                    INSERT OR REPLACE INTO teamup_game_types (channel_id, game_type, display_order)
                    VALUES (?, ?, ?)
                ''', (channel_id, game_type, next_order))
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Failed to add game type: {e}")
                return False
    
    async def remove_game_type(self, channel_id: int) -> bool:
        """Remove game type configuration"""
        async with connect_database(self.db_path) as db:
            try:
                await db.execute('DELETE FROM teamup_game_types WHERE channel_id = ?', (channel_id,))
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Failed to remove game type: {e}")
                return False
    
    async def get_all_game_types(self) -> Dict[int, str]:
        """Get all game type configurations"""
        async with connect_database(self.db_path) as db:
            cursor = await db.execute('''
                SELECT channel_id, game_type FROM teamup_game_types ORDER BY display_order
            ''')
            results = await cursor.fetchall()
            return {channel_id: game_type for channel_id, game_type in results}
    
    async def get_game_type_by_channel(self, channel_id: int) -> Optional[str]:
        """Get game type by channel ID"""
        async with connect_database(self.db_path) as db:
            cursor = await db.execute('''
                SELECT game_type FROM teamup_game_types WHERE channel_id = ?
            ''', (channel_id,))
            result = await cursor.fetchone()
            return result[0] if result else None
    
    async def cleanup_expired_invitations(self) -> int:
        """Compatibility name: only completed history expires, never active invites."""
        return await InvitationDatabaseManager(self.db_path).cleanup_history()

    async def get_active_invitations(self) -> List[Dict]:
        """Get all active teamup invitations"""
        return await InvitationDatabaseManager(self.db_path).active()

    async def update_user_stats(self, user_id: int) -> bool:
        """Update user teamup statistics"""
        async with connect_database(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT OR REPLACE INTO user_teamup_stats 
                    (user_id, teamup_count, last_teamup_at)
                    VALUES (
                        ?, 
                        COALESCE((SELECT teamup_count FROM user_teamup_stats WHERE user_id = ?), 0) + 1,
                        datetime('now', 'localtime')
                    )
                ''', (user_id, user_id))
                await db.commit()
                return True
            except Exception as e:
                logging.error("Failed to update teamup stats for %s: %s", fmt_user(user_id), e)
                return False
    
    async def get_user_stats(self, user_id: int) -> Tuple[int, Optional[str]]:
        """Get user teamup statistics"""
        async with connect_database(self.db_path) as db:
            cursor = await db.execute('''
                SELECT teamup_count, last_teamup_at FROM user_teamup_stats WHERE user_id = ?
            ''', (user_id,))
            result = await cursor.fetchone()
            return result if result else (0, None)
    
    async def get_all_display_boards(self) -> List[Tuple[int, int]]:
        """Get all display board information"""
        async with connect_database(self.db_path) as db:
            cursor = await db.execute('SELECT channel_id, message_id FROM teamup_displays')
            results = await cursor.fetchall()
            return results
