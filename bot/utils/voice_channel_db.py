# bot/utils/voice_channel_db.py
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import aiosqlite

from .db_lifecycle import BaseDatabaseManager


class VoiceChannelDatabaseManager(BaseDatabaseManager):
    """Voice channel state tables.

    Two tables live here:

    ``temp_channels`` — one row per auto-created room:
      - creator_id / created_at
      - control_panel_message_id / control_panel_channel_id (NULL until the
        panel is sent, NULL again after cleanup)
      - is_soundboard_enabled (BOOL)
      - current_room_type: 'public' or 'private'

    ``channel_configs`` — one row per "entry" voice channel (the channels
    users join to spin up their own temp room). Migrated out of
    ``config_voicechannel.json`` in the P1-6 config 2.0 sprint
    (P2-5 judged this map DB-appropriate: frequent runtime CRUD and a
    dict shape that scales with deployment).
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._persistent_connection: Optional[aiosqlite.Connection] = None
        self._persistent_connection_lock = asyncio.Lock()

    async def _execute_write(self, sql: str, parameters: Tuple[Any, ...] = ()) -> None:
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            cursor = None
            try:
                cursor = await db.execute(sql, parameters)
                await db.commit()
            except Exception:
                await db.rollback()
                raise
            finally:
                if cursor is not None:
                    await cursor.close()

    async def _fetchone(
        self, sql: str, parameters: Tuple[Any, ...] = ()
    ) -> Optional[Tuple]:
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            cursor = await db.execute(sql, parameters)
            try:
                return await cursor.fetchone()
            finally:
                await cursor.close()

    async def _fetchall(self, sql: str, parameters: Tuple[Any, ...] = ()) -> List[Tuple]:
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            cursor = await db.execute(sql, parameters)
            try:
                return await cursor.fetchall()
            finally:
                await cursor.close()

    async def initialize_database(self) -> None:
        """Create the voice channel tables and migrate any missing columns.

        Kept here because the live schema has grown over time; migrations
        are done in-place so existing deployments don't need to rebuild.
        """
        async with self._get_persistent_connection_lock():
            db = await self._get_persistent_connection()
            try:
                cursor = await db.execute('''
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
                await cursor.close()

                cursor = await db.execute("PRAGMA table_info(temp_channels)")
                try:
                    existing_columns = {row[1] for row in await cursor.fetchall()}
                finally:
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
                        cursor = await db.execute(
                            f"ALTER TABLE temp_channels ADD COLUMN {col_name} {col_type}"
                        )
                        await cursor.close()

                # channel_configs: the "entry-channel → auto-room template" map
                # that used to live under voicechannel.channel_configs in JSON.
                cursor = await db.execute('''
                    CREATE TABLE IF NOT EXISTS channel_configs (
                        channel_id INTEGER PRIMARY KEY,
                        name_prefix TEXT NOT NULL,
                        type TEXT NOT NULL
                    );
                ''')
                await cursor.close()

                await db.commit()
            except Exception:
                await db.rollback()
                raise

    # ---- channel_configs CRUD ------------------------------------------

    async def list_channel_configs(self) -> Dict[int, Dict[str, str]]:
        """Return all entry-channel configs as ``{channel_id: {name_prefix, type}}``.

        Matches the in-memory shape the cog previously loaded from JSON,
        so the rest of the voice_channel_cog can keep using
        ``self.channel_configs[channel_id]['name_prefix' | 'type']``
        unchanged after this migration.
        """
        rows = await self._fetchall(
            'SELECT channel_id, name_prefix, type FROM channel_configs'
        )
        return {
            row[0]: {'name_prefix': row[1], 'type': row[2]}
            for row in rows
        }

    async def upsert_channel_config(
        self, channel_id: int, name_prefix: str, room_type: str
    ) -> None:
        """INSERT or UPDATE an entry-channel config row.

        Used by /set_create_room_channel. Runs as a single statement so
        concurrent toggles are race-free.
        """
        await self._execute_write(
            '''
            INSERT INTO channel_configs (channel_id, name_prefix, type)
            VALUES (?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                name_prefix = excluded.name_prefix,
                type = excluded.type
            ''',
            (channel_id, name_prefix, room_type),
        )

    async def delete_channel_config(self, channel_id: int) -> None:
        await self._execute_write(
            'DELETE FROM channel_configs WHERE channel_id = ?',
            (channel_id,),
        )

    async def insert_temp_channel(
        self,
        channel_id: int,
        creator_id: int,
        soundboard_enabled: bool,
        room_type: str,
    ) -> None:
        await self._execute_write(
            'INSERT INTO temp_channels '
            '(channel_id, creator_id, is_soundboard_enabled, current_room_type) '
            'VALUES (?, ?, ?, ?)',
            (channel_id, creator_id, 1 if soundboard_enabled else 0, room_type),
        )

    async def set_room_type(self, channel_id: int, room_type: str) -> None:
        await self._execute_write(
            'UPDATE temp_channels SET current_room_type = ? WHERE channel_id = ?',
            (room_type, channel_id),
        )

    async def set_soundboard(self, channel_id: int, enabled: bool) -> None:
        await self._execute_write(
            'UPDATE temp_channels SET is_soundboard_enabled = ? WHERE channel_id = ?',
            (1 if enabled else 0, channel_id),
        )

    async def set_control_panel(
        self, channel_id: int, panel_message_id: int, panel_channel_id: int
    ) -> None:
        await self._execute_write(
            'UPDATE temp_channels '
            'SET control_panel_message_id = ?, control_panel_channel_id = ? '
            'WHERE channel_id = ?',
            (panel_message_id, panel_channel_id, channel_id),
        )

    async def clear_control_panel(self, channel_id: int) -> None:
        await self._execute_write(
            'UPDATE temp_channels '
            'SET control_panel_message_id = NULL, control_panel_channel_id = NULL '
            'WHERE channel_id = ?',
            (channel_id,),
        )

    async def delete_temp_channel(self, channel_id: int) -> None:
        await self._execute_write(
            'DELETE FROM temp_channels WHERE channel_id = ?',
            (channel_id,),
        )

    async def exists(self, channel_id: int) -> bool:
        result = await self._fetchone(
            'SELECT 1 FROM temp_channels WHERE channel_id = ?',
            (channel_id,),
        )
        return result is not None

    async def fetch_all_channel_ids(self) -> List[int]:
        rows = await self._fetchall('SELECT channel_id FROM temp_channels')
        return [row[0] for row in rows]

    async def fetch_all_records(self) -> List[Tuple]:
        """All columns, ordered newest-first. Used by /check_temp_channel_records."""
        return await self._fetchall(
            'SELECT * FROM temp_channels ORDER BY created_at DESC'
        )

    async def fetch_control_panels(self) -> List[Tuple]:
        """Rows with a control panel message attached; used to restore views on startup.

        Columns: (channel_id, creator_id, control_panel_message_id,
        is_soundboard_enabled, current_room_type).
        """
        return await self._fetchall('''
            SELECT channel_id, creator_id, control_panel_message_id,
                   is_soundboard_enabled, current_room_type
            FROM temp_channels
            WHERE control_panel_message_id IS NOT NULL
        ''')
