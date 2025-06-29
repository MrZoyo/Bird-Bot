# bot/utils/ban_db.py
import aiosqlite
import logging
from datetime import datetime
from typing import Optional, List, Tuple


class BanDatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize_database(self) -> None:
        """Create necessary database tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            # Tempbans table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS tempbans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    banned_by INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    banned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    unban_at TIMESTAMP NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    delete_message_days INTEGER DEFAULT 0,
                    UNIQUE(user_id, guild_id, is_active)
                )
            ''')
            
            # Create index for faster queries
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_tempbans_active 
                ON tempbans(is_active, unban_at)
            ''')
            
            await db.commit()

    async def add_tempban(self, user_id: int, guild_id: int, banned_by: int, 
                         reason: str, unban_at: datetime, delete_message_days: int = 0) -> int:
        """Add a new tempban record."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                INSERT INTO tempbans (user_id, guild_id, banned_by, reason, unban_at, delete_message_days)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, guild_id, banned_by, reason, unban_at, delete_message_days))
            
            await db.commit()
            return cursor.lastrowid

    async def get_active_tempbans(self, guild_id: Optional[int] = None) -> List[Tuple]:
        """Get all active tempbans, optionally filtered by guild."""
        async with aiosqlite.connect(self.db_path) as db:
            if guild_id:
                cursor = await db.execute('''
                    SELECT id, user_id, guild_id, banned_by, reason, banned_at, unban_at, delete_message_days
                    FROM tempbans 
                    WHERE is_active = 1 AND guild_id = ?
                    ORDER BY unban_at ASC
                ''', (guild_id,))
            else:
                cursor = await db.execute('''
                    SELECT id, user_id, guild_id, banned_by, reason, banned_at, unban_at, delete_message_days
                    FROM tempbans 
                    WHERE is_active = 1
                    ORDER BY unban_at ASC
                ''')
            
            return await cursor.fetchall()

    async def get_expired_tempbans(self) -> List[Tuple]:
        """Get all expired tempbans that are still active."""
        current_time = datetime.utcnow()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT id, user_id, guild_id, banned_by, reason, banned_at, unban_at, delete_message_days
                FROM tempbans 
                WHERE is_active = 1 AND unban_at <= ?
                ORDER BY unban_at ASC
            ''', (current_time,))
            
            return await cursor.fetchall()

    async def deactivate_tempban(self, tempban_id: int) -> bool:
        """Mark a tempban as inactive (completed)."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                UPDATE tempbans 
                SET is_active = 0 
                WHERE id = ?
            ''', (tempban_id,))
            
            await db.commit()
            return cursor.rowcount > 0

    async def deactivate_tempban_by_user(self, user_id: int, guild_id: int) -> bool:
        """Mark a user's active tempban as inactive (for manual unban)."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                UPDATE tempbans 
                SET is_active = 0 
                WHERE user_id = ? AND guild_id = ? AND is_active = 1
            ''', (user_id, guild_id))
            
            await db.commit()
            return cursor.rowcount > 0

    async def get_user_tempban(self, user_id: int, guild_id: int) -> Optional[Tuple]:
        """Get a user's active tempban record."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT id, user_id, guild_id, banned_by, reason, banned_at, unban_at, delete_message_days
                FROM tempbans 
                WHERE user_id = ? AND guild_id = ? AND is_active = 1
            ''', (user_id, guild_id))
            
            return await cursor.fetchone()

    async def cleanup_old_records(self, days_old: int = 30) -> int:
        """Clean up old inactive tempban records older than specified days."""
        cutoff_date = datetime.utcnow().replace(day=datetime.utcnow().day - days_old)
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                DELETE FROM tempbans 
                WHERE is_active = 0 AND unban_at < ?
            ''', (cutoff_date,))
            
            await db.commit()
            return cursor.rowcount

    async def get_tempban_stats(self, guild_id: int) -> dict:
        """Get tempban statistics for a guild."""
        async with aiosqlite.connect(self.db_path) as db:
            # Active tempbans count
            cursor = await db.execute('''
                SELECT COUNT(*) FROM tempbans 
                WHERE guild_id = ? AND is_active = 1
            ''', (guild_id,))
            active_count = (await cursor.fetchone())[0]
            
            # Total tempbans count (last 30 days)
            thirty_days_ago = datetime.utcnow().replace(day=datetime.utcnow().day - 30)
            cursor = await db.execute('''
                SELECT COUNT(*) FROM tempbans 
                WHERE guild_id = ? AND banned_at >= ?
            ''', (guild_id, thirty_days_ago))
            recent_count = (await cursor.fetchone())[0]
            
            return {
                'active_tempbans': active_count,
                'recent_tempbans': recent_count
            }