# bot/utils/teamup_display_manager.py
import aiosqlite
import discord
from datetime import datetime, timezone
import logging
from typing import Optional, List, Dict, Tuple


class TeamupDisplayManager:
    """Database operations manager for teamup display board functionality"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    async def init_tables(self):
        """Initialize database tables"""
        async with aiosqlite.connect(self.db_path) as db:
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
            
            # Teamup invitation table (for display board)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS teamup_invitations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    voice_channel_id INTEGER NOT NULL,
                    message_content TEXT NOT NULL,
                    player_count INTEGER DEFAULT 1,
                    game_type TEXT,
                    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    expires_at TIMESTAMP NOT NULL
                )
            ''')
            
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
        async with aiosqlite.connect(self.db_path) as db:
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
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT message_id, channel_id FROM teamup_displays WHERE channel_id = ?
            ''', (channel_id,))
            result = await cursor.fetchone()
            return result if result else None
    
    async def remove_display_board(self, channel_id: int) -> bool:
        """Remove display board information"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('DELETE FROM teamup_displays WHERE channel_id = ?', (channel_id,))
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Failed to remove display board: {e}")
                return False
    
    async def add_game_type(self, channel_id: int, game_type: str) -> bool:
        """Add game type configuration"""
        async with aiosqlite.connect(self.db_path) as db:
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
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('DELETE FROM teamup_game_types WHERE channel_id = ?', (channel_id,))
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Failed to remove game type: {e}")
                return False
    
    async def get_all_game_types(self) -> Dict[int, str]:
        """Get all game type configurations"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT channel_id, game_type FROM teamup_game_types ORDER BY display_order
            ''')
            results = await cursor.fetchall()
            return {channel_id: game_type for channel_id, game_type in results}
    
    async def get_game_type_by_channel(self, channel_id: int) -> Optional[str]:
        """Get game type by channel ID"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT game_type FROM teamup_game_types WHERE channel_id = ?
            ''', (channel_id,))
            result = await cursor.fetchone()
            return result[0] if result else None
    
    async def add_teamup_invitation(self, user_id: int, channel_id: int, voice_channel_id: int, 
                                   message_content: str, player_count: int = 1, 
                                   game_type: str = None) -> bool:
        """Add or update teamup invitation"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Calculate expiration time (5 minutes later)
                expires_at = datetime.now(timezone.utc).replace(microsecond=0)
                expires_at = expires_at.replace(tzinfo=None)  # Remove timezone info to match database format
                
                # Remove old records for the same voice channel (any user)
                await db.execute('''
                    DELETE FROM teamup_invitations 
                    WHERE voice_channel_id = ?
                ''', (voice_channel_id,))
                
                # Insert new record
                await db.execute('''
                    INSERT INTO teamup_invitations 
                    (user_id, channel_id, voice_channel_id, message_content, player_count, game_type, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime(?, '+5 minutes'))
                ''', (user_id, channel_id, voice_channel_id, message_content, player_count, game_type, 
                      datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                
                await db.commit()
                
                # Update user statistics
                await self.update_user_stats(user_id)
                
                return True
            except Exception as e:
                logging.error(f"Failed to add teamup invitation: {e}")
                return False
    
    async def remove_teamup_invitation(self, user_id: int, voice_channel_id: int) -> bool:
        """Remove teamup invitation if user is the latest poster for this voice channel"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Check if this user is the latest poster for this voice channel
                cursor = await db.execute('''
                    SELECT user_id FROM teamup_invitations 
                    WHERE voice_channel_id = ? 
                    ORDER BY created_at DESC LIMIT 1
                ''', (voice_channel_id,))
                result = await cursor.fetchone()
                
                # Only allow removal if this user is the latest poster
                if result and result[0] == user_id:
                    await db.execute('''
                        DELETE FROM teamup_invitations 
                        WHERE voice_channel_id = ?
                    ''', (voice_channel_id,))
                    await db.commit()
                    return True
                else:
                    return False
            except Exception as e:
                logging.error(f"Failed to remove teamup invitation: {e}")
                return False
    
    async def cleanup_expired_invitations(self) -> int:
        """Clean up expired teamup invitations and return count of cleaned items"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute('''
                    DELETE FROM teamup_invitations 
                    WHERE expires_at <= datetime('now', 'localtime')
                ''')
                await db.commit()
                return cursor.rowcount
            except Exception as e:
                logging.error(f"Failed to cleanup expired invitations: {e}")
                return 0
    
    async def get_active_invitations(self) -> List[Dict]:
        """Get all active teamup invitations"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT user_id, channel_id, voice_channel_id, message_content, 
                       player_count, game_type, created_at, expires_at
                FROM teamup_invitations 
                WHERE expires_at > datetime('now', 'localtime')
                ORDER BY created_at DESC
            ''')
            results = await cursor.fetchall()
            
            invitations = []
            for row in results:
                invitations.append({
                    'user_id': row[0],
                    'channel_id': row[1],
                    'voice_channel_id': row[2],
                    'message_content': row[3],
                    'player_count': row[4],
                    'game_type': row[5],
                    'created_at': row[6],
                    'expires_at': row[7]
                })
            
            return invitations
    
    async def update_user_stats(self, user_id: int) -> bool:
        """Update user teamup statistics"""
        async with aiosqlite.connect(self.db_path) as db:
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
                logging.error(f"Failed to update user stats: {e}")
                return False
    
    async def get_user_stats(self, user_id: int) -> Tuple[int, Optional[str]]:
        """Get user teamup statistics"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT teamup_count, last_teamup_at FROM user_teamup_stats WHERE user_id = ?
            ''', (user_id,))
            result = await cursor.fetchone()
            return result if result else (0, None)
    
    async def get_all_display_boards(self) -> List[Tuple[int, int]]:
        """Get all display board information"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT channel_id, message_id FROM teamup_displays')
            results = await cursor.fetchall()
            return results