# bot/utils/privateroom_db.py
import discord
import aiosqlite
from datetime import datetime, timedelta
import logging
import json
from typing import Dict, List, Optional, Tuple, Any


class PrivateRoomDatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize_database(self) -> None:
        """创建私人房间相关的数据库表"""
        async with aiosqlite.connect(self.db_path) as db:
            # 系统配置表 - 存储 category_id 和商店相关信息
            await db.execute('''
                CREATE TABLE IF NOT EXISTS privateroom_config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')

            # 私人房间表 - 存储所有私人房间信息
            await db.execute('''
                CREATE TABLE IF NOT EXISTS privateroom_rooms (
                    room_id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')

            # 保存店铺消息位置
            await db.execute('''
                CREATE TABLE IF NOT EXISTS privateroom_shop_messages (
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (channel_id, message_id)
                )
            ''')

            # 私房设置保存表 - 保存用户的房间权限和名称设置
            await db.execute('''
                CREATE TABLE IF NOT EXISTS privateroom_saved_settings (
                    user_id INTEGER PRIMARY KEY,
                    saved_at TEXT NOT NULL,
                    channel_name TEXT,
                    settings_data TEXT NOT NULL,
                    original_room_id INTEGER,
                    expires_at TEXT
                )
            ''')

            await db.commit()

    async def get_config_value(self, key: str) -> Optional[str]:
        """从配置表中获取一个值"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT value FROM privateroom_config WHERE key = ?', (key,))
            result = await cursor.fetchone()
            return result[0] if result else None

    async def set_config_value(self, key: str, value: str) -> None:
        """设置配置表中的值"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO privateroom_config (key, value) 
                VALUES (?, ?) 
                ON CONFLICT(key) DO UPDATE SET value = ?
            ''', (key, value, value))
            await db.commit()

    async def get_category_id(self) -> Optional[int]:
        """获取私人房间分类ID"""
        category_id = await self.get_config_value('category_id')
        return int(category_id) if category_id else None

    async def set_category_id(self, category_id: int) -> None:
        """设置私人房间分类ID"""
        await self.set_config_value('category_id', str(category_id))

    async def save_shop_message(self, channel_id: int, message_id: int) -> None:
        """保存商店消息信息"""
        current_time = datetime.now().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO privateroom_shop_messages (channel_id, message_id, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(channel_id, message_id) DO UPDATE SET created_at = ?
            ''', (channel_id, message_id, current_time, current_time))
            await db.commit()

    async def get_shop_messages(self) -> List[Tuple[int, int]]:
        """获取所有商店消息"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT channel_id, message_id FROM privateroom_shop_messages')
            return await cursor.fetchall()

    async def delete_shop_messages(self) -> None:
        """删除所有商店消息记录"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM privateroom_shop_messages')
            await db.commit()

    async def create_room(self, room_id: int, user_id: int,
                          start_date: datetime, end_date: datetime) -> None:
        """创建新的私人房间记录"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO privateroom_rooms 
                (room_id, user_id, start_date, end_date, is_active)
                VALUES (?, ?, ?, ?, 1)
            ''', (room_id, user_id, start_date.isoformat(), end_date.isoformat()))
            await db.commit()

    async def get_deleted_room_by_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取用户之前删除的但仍在有效期内的私人房间"""
        now = datetime.now()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT room_id, user_id, start_date, end_date
                FROM privateroom_rooms
                WHERE user_id = ? AND is_active = 0 
                AND datetime(end_date) > datetime(?)
                ORDER BY start_date DESC LIMIT 1
            ''', (user_id, now.isoformat()))
            row = await cursor.fetchone()

            if not row:
                return None

            return {
                'room_id': row[0],
                'user_id': row[1],
                'start_date': datetime.fromisoformat(row[2]),
                'end_date': datetime.fromisoformat(row[3])
            }

    async def get_expired_rooms(self) -> List[Dict[str, Any]]:
        """获取所有已过期的活跃房间"""
        now = datetime.now()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT room_id, user_id, start_date, end_date
                FROM privateroom_rooms
                WHERE is_active = 1 AND datetime(end_date) <= datetime(?)
            ''', (now.isoformat(),))
            rows = await cursor.fetchall()

            result = []
            for row in rows:
                result.append({
                    'room_id': row[0],
                    'user_id': row[1],
                    'start_date': datetime.fromisoformat(row[2]),
                    'end_date': datetime.fromisoformat(row[3])
                })

            return result

    async def deactivate_room(self, room_id: int) -> None:
        """将房间标记为非活跃（过期）"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE privateroom_rooms 
                SET is_active = 0
                WHERE room_id = ?
            ''', (room_id,))
            await db.commit()

    async def reset_privateroom_system(self) -> None:
        """重置整个私人房间系统（删除所有数据）"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM privateroom_config')
            await db.execute('DELETE FROM privateroom_rooms')
            await db.execute('DELETE FROM privateroom_shop_messages')
            await db.commit()

    async def get_active_room_by_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取用户当前活跃的私人房间"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT room_id, user_id, start_date, end_date
                FROM privateroom_rooms
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            row = await cursor.fetchone()

            if not row:
                return None

            return {
                'room_id': row[0],
                'user_id': row[1],
                'start_date': datetime.fromisoformat(row[2]),
                'end_date': datetime.fromisoformat(row[3])
            }

    async def mark_room_inactive(self, room_id: int) -> None:
        """Mark a room as inactive (for when the channel is deleted)"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE privateroom_rooms 
                SET is_active = 0
                WHERE room_id = ?
            ''', (room_id,))
            await db.commit()

    async def restore_room(self, old_room_id: int, new_room_id: int) -> None:
        """Restore a previously inactive room using a new channel ID"""
        async with aiosqlite.connect(self.db_path) as db:
            # Get the original room info
            cursor = await db.execute('''
                SELECT user_id, start_date, end_date
                FROM privateroom_rooms
                WHERE room_id = ? AND is_active = 1
            ''', (old_room_id,))
            row = await cursor.fetchone()

            if not row:
                raise ValueError(f"Active room with ID {old_room_id} not found")

            user_id, start_date, end_date = row

            # Update the room ID in the existing record and ensure it's active
            await db.execute('''
                UPDATE privateroom_rooms 
                SET room_id = ?, is_active = 1
                WHERE room_id = ? AND is_active = 1
            ''', (new_room_id, old_room_id))

            await db.commit()

    async def get_inactive_valid_room(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a user's inactive room that's still within its validity period"""
        now = datetime.now()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT room_id, user_id, start_date, end_date
                FROM privateroom_rooms
                WHERE user_id = ? AND is_active = 0 
                AND datetime(end_date) > datetime(?)
                ORDER BY start_date DESC LIMIT 1
            ''', (user_id, now.isoformat()))
            row = await cursor.fetchone()

            if not row:
                return None

            return {
                'room_id': row[0],
                'user_id': row[1],
                'start_date': datetime.fromisoformat(row[2]),
                'end_date': datetime.fromisoformat(row[3])
            }

    async def check_shop_message_exists(self, channel_id: int, message_id: int, bot) -> bool:
        """检查商店消息是否仍存在于Discord中"""
        channel = bot.get_channel(channel_id)
        if not channel:
            return False

        try:
            message = await channel.fetch_message(message_id)
            return message is not None
        except (discord.NotFound, discord.Forbidden):
            return False
        except Exception as e:
            logging.error(f"Error checking shop message: {e}")
            return False

    async def remove_shop_message(self, channel_id: int, message_id: int) -> None:
        """从数据库中移除单个商店消息记录"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'DELETE FROM privateroom_shop_messages WHERE channel_id = ? AND message_id = ?',
                (channel_id, message_id)
            )
            await db.commit()

    async def clean_nonexistent_shop_messages(self, bot) -> int:
        """清理数据库中不再存在于Discord的商店消息

        返回: 被清理的消息数量
        """
        shop_messages = await self.get_shop_messages()
        removed_count = 0

        for channel_id, message_id in shop_messages:
            exists = await self.check_shop_message_exists(channel_id, message_id, bot)
            if not exists:
                await self.remove_shop_message(channel_id, message_id)
                removed_count += 1

        return removed_count

    async def get_active_rooms_count(self) -> int:
        """Get the total count of active private rooms"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT COUNT(*) FROM privateroom_rooms WHERE is_active = 1')
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def get_paginated_active_rooms(self, page: int = 1, items_per_page: int = 10) -> tuple:
        """Get paginated active rooms
        Returns: (rooms, total_count)
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Get total count first
            cursor = await db.execute(
                'SELECT COUNT(*) FROM privateroom_rooms WHERE is_active = 1'
            )
            total_count = (await cursor.fetchone())[0]

            # Get paginated rooms
            offset = (page - 1) * items_per_page
            cursor = await db.execute('''
                SELECT room_id, user_id, start_date, end_date
                FROM privateroom_rooms
                WHERE is_active = 1
                ORDER BY end_date ASC
                LIMIT ? OFFSET ?
            ''', (items_per_page, offset))

            rooms = await cursor.fetchall()
            return rooms, total_count

    async def save_user_room_settings(self, user_id: int, settings_data: Dict[str, Any], 
                                     original_room_id: Optional[int] = None) -> None:
        """保存用户的房间设置（权限和名称）"""
        current_time = datetime.now().isoformat()
        # 设置过期时间为6个月后
        expires_at = (datetime.now() + timedelta(days=180)).isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO privateroom_saved_settings 
                (user_id, saved_at, channel_name, settings_data, original_room_id, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    saved_at = ?,
                    channel_name = ?,
                    settings_data = ?,
                    original_room_id = ?,
                    expires_at = ?
            ''', (
                user_id, current_time, settings_data.get("channel_name"), 
                json.dumps(settings_data), original_room_id, expires_at,
                current_time, settings_data.get("channel_name"),
                json.dumps(settings_data), original_room_id, expires_at
            ))
            await db.commit()

    async def get_user_saved_settings(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取用户保存的房间设置"""
        now = datetime.now()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT saved_at, channel_name, settings_data, original_room_id
                FROM privateroom_saved_settings
                WHERE user_id = ? AND (expires_at IS NULL OR datetime(expires_at) > datetime(?))
            ''', (user_id, now.isoformat()))
            row = await cursor.fetchone()
            
            if not row:
                return None
            
            try:
                settings_data = json.loads(row[2])
                return {
                    "saved_at": row[0],
                    "channel_name": row[1],
                    "settings_data": settings_data,
                    "original_room_id": row[3]
                }
            except json.JSONDecodeError:
                logging.error(f"Failed to parse saved settings for user {user_id}")
                return None

    async def delete_user_saved_settings(self, user_id: int) -> None:
        """删除用户保存的房间设置"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM privateroom_saved_settings WHERE user_id = ?', (user_id,))
            await db.commit()

    async def clean_expired_settings(self) -> int:
        """清理过期的保存设置，返回清理数量"""
        now = datetime.now()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT COUNT(*) FROM privateroom_saved_settings 
                WHERE expires_at IS NOT NULL AND datetime(expires_at) <= datetime(?)
            ''', (now.isoformat(),))
            count = (await cursor.fetchone())[0]
            
            await db.execute('''
                DELETE FROM privateroom_saved_settings 
                WHERE expires_at IS NOT NULL AND datetime(expires_at) <= datetime(?)
            ''', (now.isoformat(),))
            await db.commit()
            
            return count

    async def extend_room_validity(self, room_id: int, new_end_date: datetime) -> None:
        """延长房间的有效期
        
        Args:
            room_id: 房间ID
            new_end_date: 新的结束日期
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                UPDATE privateroom_rooms 
                SET end_date = ?
                WHERE room_id = ?
            ''', (new_end_date.isoformat(), room_id))
            await db.commit()
