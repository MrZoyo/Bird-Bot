# bot/utils/voice_channel_db.py
import aiosqlite
import logging
from typing import List, Optional, Tuple


class VoiceChannelDatabaseManager:
    """Temporary voice channels (table ``temp_channels``).

    One row per auto-created room from the voice channel cog. Carries:
      - creator_id / created_at
      - control_panel_message_id / control_panel_channel_id (the text-chat
        panel attached to the voice channel; NULL until the panel is sent,
        NULL again after the room is cleaned up)
      - is_soundboard_enabled (BOOL)
      - current_room_type: 'public' or 'private'
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize_database(self) -> None:
        """Create the temp_channels table and migrate any missing columns.

        Kept here because the live schema has grown over time; migrations are
        done in-place so existing deployments don't need to rebuild the table.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS temp_channels (
                    channel_id INTEGER PRIMARY KEY,
                    creator_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    control_panel_message_id INTEGER,
                    control_panel_channel_id INTEGER,
                    is_soundboard_enabled BOOLEAN DEFAULT 1,
                    current_room_type TEXT DEFAULT 'public'
                );
            ''')

            cursor = await db.execute("PRAGMA table_info(temp_channels)")
            existing_columns = {row[1] for row in await cursor.fetchall()}
            await cursor.close()

            columns_to_add = [
                ("control_panel_message_id", "INTEGER"),
                ("control_panel_channel_id", "INTEGER"),
                ("is_soundboard_enabled", "BOOLEAN DEFAULT 1"),
                ("current_room_type", "TEXT DEFAULT 'public'"),
            ]
            for col_name, col_type in columns_to_add:
                if col_name not in existing_columns:
                    logging.info(f"[MIGRATION] Adding column {col_name} to temp_channels")
                    await db.execute(f"ALTER TABLE temp_channels ADD COLUMN {col_name} {col_type}")

            await db.commit()

    async def insert_temp_channel(
        self,
        channel_id: int,
        creator_id: int,
        soundboard_enabled: bool,
        room_type: str,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'INSERT INTO temp_channels '
                '(channel_id, creator_id, is_soundboard_enabled, current_room_type) '
                'VALUES (?, ?, ?, ?)',
                (channel_id, creator_id, 1 if soundboard_enabled else 0, room_type),
            )
            await db.commit()

    async def set_room_type(self, channel_id: int, room_type: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE temp_channels SET current_room_type = ? WHERE channel_id = ?',
                (room_type, channel_id),
            )
            await db.commit()

    async def set_soundboard(self, channel_id: int, enabled: bool) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE temp_channels SET is_soundboard_enabled = ? WHERE channel_id = ?',
                (1 if enabled else 0, channel_id),
            )
            await db.commit()

    async def set_control_panel(
        self, channel_id: int, panel_message_id: int, panel_channel_id: int
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE temp_channels '
                'SET control_panel_message_id = ?, control_panel_channel_id = ? '
                'WHERE channel_id = ?',
                (panel_message_id, panel_channel_id, channel_id),
            )
            await db.commit()

    async def clear_control_panel(self, channel_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE temp_channels '
                'SET control_panel_message_id = NULL, control_panel_channel_id = NULL '
                'WHERE channel_id = ?',
                (channel_id,),
            )
            await db.commit()

    async def delete_temp_channel(self, channel_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'DELETE FROM temp_channels WHERE channel_id = ?',
                (channel_id,),
            )
            await db.commit()

    async def exists(self, channel_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT 1 FROM temp_channels WHERE channel_id = ?',
                (channel_id,),
            )
            result = await cursor.fetchone()
            await cursor.close()
        return result is not None

    async def fetch_all_channel_ids(self) -> List[int]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT channel_id FROM temp_channels')
            rows = await cursor.fetchall()
            await cursor.close()
        return [row[0] for row in rows]

    async def fetch_all_records(self) -> List[Tuple]:
        """All columns, ordered newest-first. Used by /check_temp_channel_records."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                'SELECT * FROM temp_channels ORDER BY created_at DESC'
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return rows

    async def fetch_control_panels(self) -> List[Tuple]:
        """Rows with a control panel message attached; used to restore views on startup.

        Columns: (channel_id, creator_id, control_panel_message_id,
        is_soundboard_enabled, current_room_type).
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT channel_id, creator_id, control_panel_message_id,
                       is_soundboard_enabled, current_room_type
                FROM temp_channels
                WHERE control_panel_message_id IS NOT NULL
            ''')
            rows = await cursor.fetchall()
            await cursor.close()
        return rows
