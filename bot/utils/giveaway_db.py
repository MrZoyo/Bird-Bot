import aiosqlite
import logging
from typing import Any, Dict, List, Optional, Tuple

from .db_connect import connect_database
from .db_lifecycle import BaseDatabaseManager
from .schema_migrations import (
    SchemaMigration,
    add_column_if_missing,
    apply_schema_migrations,
)


GIVEAWAY_COLUMNS = (
    'giveaway_id',
    'message_id',
    'starttime',
    'duration',
    'winner_number',
    'prizes',
    'description',
    'creator_id',
    'reaction_req',
    'message_req',
    'timespent_req',
    'participant_ids',
    'winner_ids',
    'is_end',
    'provider',
    'image_url',
    'image_filename',
    'ui_version',
)


class GiveawayDatabaseManager(BaseDatabaseManager):
    """Database operations for the giveaway system.

    Tables owned here:
      - ``giveaway``        : one row per giveaway (definition + state)
      - ``giveaway_views``  : persisted view metadata so panels restore after restart

    Giveaway participation no longer writes achievement counters. Historical
    ``giveaway_count`` columns may remain in existing databases, but runtime
    code does not expose them as achievements.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize_database(self) -> None:
        async with connect_database(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS giveaway (
                    giveaway_id INTEGER NOT NULL,
                    message_id TEXT NOT NULL,
                    starttime TEXT NOT NULL,
                    duration INTEGER NOT NULL,
                    winner_number INTEGER NOT NULL,
                    prizes TEXT NOT NULL,
                    description TEXT,
                    creator_id TEXT NOT NULL,
                    reaction_req INTEGER DEFAULT 0,
                    message_req INTEGER DEFAULT 0,
                    timespent_req INTEGER DEFAULT 0,
                    participant_ids TEXT,
                    winner_ids TEXT,
                    is_end BOOLEAN DEFAULT 0,
                    provider TEXT,
                    image_url TEXT,
                    image_filename TEXT,
                    ui_version INTEGER DEFAULT 1
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS giveaway_views (
                    giveaway_id TEXT PRIMARY KEY,
                    giveaway_channel_id TEXT,
                    message_id TEXT
                )
            ''')
            await apply_schema_migrations(
                db,
                namespace='giveaway',
                migrations=[
                    SchemaMigration(
                        version=1,
                        description='add provider, image, and ui version fields',
                        migrate=self._migrate_giveaway_panel_fields,
                    ),
                ],
            )
            await db.commit()

    async def _migrate_giveaway_panel_fields(
        self,
        db: aiosqlite.Connection,
    ) -> None:
        columns_to_add = [
            ('provider', 'TEXT'),
            ('image_url', 'TEXT'),
            ('image_filename', 'TEXT'),
            ('ui_version', 'INTEGER DEFAULT 1'),
        ]
        for column_name, column_definition in columns_to_add:
            await add_column_if_missing(
                db,
                table_name='giveaway',
                column_name=column_name,
                column_definition=column_definition,
            )

    # ------------------------------------------------------------------
    # giveaway table
    # ------------------------------------------------------------------

    async def insert_giveaway(
        self,
        giveaway_id,
        message_id,
        starttime,
        duration,
        winner_number,
        prizes,
        description,
        creator_id,
        winner_ids,
        reaction_req,
        message_req,
        timespent_req,
        provider=None,
        image_url=None,
        image_filename=None,
        ui_version=1,
    ) -> None:
        async with connect_database(self.db_path) as db:
            await db.execute(
                'INSERT INTO giveaway '
                '(giveaway_id, message_id, starttime, duration, winner_number, '
                'prizes, description, creator_id, winner_ids, '
                'reaction_req, message_req, timespent_req, '
                'provider, image_url, image_filename, ui_version) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (giveaway_id, message_id, starttime, duration, winner_number,
                 prizes, description, creator_id, winner_ids,
                 reaction_req, message_req, timespent_req,
                 provider, image_url, image_filename, ui_version),
            )
            await db.commit()

    async def fetch_giveaway(self, giveaway_id) -> Optional[Dict[str, Any]]:
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(
                f"SELECT {', '.join(GIVEAWAY_COLUMNS)} FROM giveaway WHERE giveaway_id = ?",
                (giveaway_id,),
            )
            record = await cursor.fetchone()
            await cursor.close()

        if record is None:
            return None

        return {
            'giveaway_id': record[0],
            'message_id': record[1],
            'starttime': record[2],
            'duration': record[3],
            'winner_number': record[4],
            'prizes': record[5],
            'description': record[6],
            'creator_id': record[7],
            'reaction_req': record[8],
            'message_req': record[9],
            'timespent_req': record[10],
            'participant_ids': record[11],
            'winner_ids': record[12],
            'is_end': record[13],
            'provider': record[14],
            'image_url': record[15],
            'image_filename': record[16],
            'ui_version': record[17],
        }

    async def fetch_all_giveaway_ids(self) -> List[str]:
        async with connect_database(self.db_path) as db:
            cursor = await db.execute('SELECT giveaway_id FROM giveaway')
            rows = await cursor.fetchall()
            await cursor.close()
        return [row[0] for row in rows]

    async def fetch_all_giveaways(self, include_ended: bool = True) -> List[Tuple]:
        """Raw row tuples; ordering matches the giveaway table's column order."""
        column_sql = ', '.join(GIVEAWAY_COLUMNS)
        query = (
            f'SELECT {column_sql} FROM giveaway'
            if include_ended
            else f'SELECT {column_sql} FROM giveaway WHERE is_end = 0'
        )
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(query)
            records = await cursor.fetchall()
            await cursor.close()
        return records

    async def update_giveaway_winners(self, giveaway_id, winners: List) -> None:
        """Store winners (comma-joined) and mark ended."""
        async with connect_database(self.db_path) as db:
            await db.execute(
                'UPDATE giveaway SET winner_ids = ?, is_end = 1 WHERE giveaway_id = ?',
                (",".join(str(w) for w in winners), giveaway_id),
            )
            await db.commit()

    async def mark_giveaway_as_ended(self, giveaway_id) -> None:
        async with connect_database(self.db_path) as db:
            await db.execute(
                'UPDATE giveaway SET is_end = 1 WHERE giveaway_id = ?',
                (giveaway_id,),
            )
            await db.commit()

    async def update_giveaway_description(self, giveaway_id, new_description) -> None:
        async with connect_database(self.db_path) as db:
            await db.execute(
                'UPDATE giveaway SET description = ? WHERE giveaway_id = ?',
                (new_description, giveaway_id),
            )
            await db.commit()

    async def update_giveaway_duration(self, giveaway_id, new_duration) -> None:
        async with connect_database(self.db_path) as db:
            await db.execute(
                'UPDATE giveaway SET duration = ? WHERE giveaway_id = ?',
                (new_duration, giveaway_id),
            )
            await db.commit()

    async def update_giveaway_message_id(self, giveaway_id, message_id) -> None:
        async with connect_database(self.db_path) as db:
            await db.execute(
                'UPDATE giveaway SET message_id = ? WHERE giveaway_id = ?',
                (message_id, giveaway_id),
            )
            await db.commit()

    # ------------------------------------------------------------------
    # participants (stored as comma-joined string in giveaway.participant_ids)
    # ------------------------------------------------------------------

    async def fetch_participant_ids(self, giveaway_id) -> List[str]:
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(
                'SELECT participant_ids FROM giveaway WHERE giveaway_id = ?',
                (giveaway_id,),
            )
            record = await cursor.fetchone()
            await cursor.close()

        if record is None or record[0] is None:
            return []
        return [pid for pid in record[0].split(',') if pid]

    async def is_participant(self, giveaway_id, participant_id) -> bool:
        participant_ids = await self.fetch_participant_ids(giveaway_id)
        return str(participant_id) in participant_ids

    async def add_participant(self, giveaway_id, participant_id) -> None:
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(
                'SELECT participant_ids FROM giveaway WHERE giveaway_id = ?',
                (giveaway_id,),
            )
            record = await cursor.fetchone()
            await cursor.close()

            current = record[0] if record else None
            new_ids = str(participant_id) if current is None else f"{current},{participant_id}"
            await db.execute(
                'UPDATE giveaway SET participant_ids = ? WHERE giveaway_id = ?',
                (new_ids, giveaway_id),
            )
            await db.commit()

    async def remove_participant(self, giveaway_id, participant_id) -> None:
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(
                'SELECT participant_ids FROM giveaway WHERE giveaway_id = ?',
                (giveaway_id,),
            )
            record = await cursor.fetchone()
            await cursor.close()

            if record is None or record[0] is None:
                logging.error(f"No participant_ids found for giveaway_id {giveaway_id}")
                return

            current = record[0].split(',')
            if str(participant_id) in current:
                current.remove(str(participant_id))
            await db.execute(
                'UPDATE giveaway SET participant_ids = ? WHERE giveaway_id = ?',
                (','.join(current), giveaway_id),
            )
            await db.commit()

    async def fetch_winner_ids(self, giveaway_id) -> List[int]:
        """Winner rows may hold either raw ids or '<@id>' mentions; normalize to ints."""
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(
                'SELECT winner_ids FROM giveaway WHERE giveaway_id = ?',
                (giveaway_id,),
            )
            record = await cursor.fetchone()
            await cursor.close()

        if record is None or record[0] is None:
            return []
        return [int(mention.strip('<@>')) for mention in record[0].split(',') if mention]

    # ------------------------------------------------------------------
    # eligibility (raw SQL only; interaction replies belong in the cog)
    # ------------------------------------------------------------------

    async def fetch_giveaway_requirements(
        self, giveaway_id
    ) -> Optional[Tuple[int, int, int]]:
        """Return (reaction_req, message_req, timespent_req) or None if the giveaway is missing."""
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(
                'SELECT reaction_req, message_req, timespent_req '
                'FROM giveaway WHERE giveaway_id = ?',
                (giveaway_id,),
            )
            record = await cursor.fetchone()
            await cursor.close()
        return record  # type: ignore[return-value]

    async def fetch_user_achievements(
        self, user_id
    ) -> Optional[Tuple]:
        """Return legacy achievement counters used for giveaway entry requirements."""
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(
                'SELECT * FROM achievements WHERE user_id = ?',
                (user_id,),
            )
            record = await cursor.fetchone()
            await cursor.close()
        return record

    # ------------------------------------------------------------------
    # giveaway_views table
    # ------------------------------------------------------------------

    async def save_giveaway_view(
        self, giveaway_id, giveaway_channel_id, message_id
    ) -> None:
        async with connect_database(self.db_path) as db:
            await db.execute(
                'REPLACE INTO giveaway_views (giveaway_id, giveaway_channel_id, message_id) '
                'VALUES (?, ?, ?)',
                (giveaway_id, giveaway_channel_id, message_id),
            )
            await db.commit()

    async def load_giveaway_views(self) -> List[Tuple[str, str, str]]:
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(
                'SELECT giveaway_id, giveaway_channel_id, message_id FROM giveaway_views'
            )
            records = await cursor.fetchall()
            await cursor.close()
        return records

    async def cleanup_ended_giveaway_views(self) -> None:
        async with connect_database(self.db_path) as db:
            await db.execute('''
                DELETE FROM giveaway_views
                WHERE giveaway_id IN (
                    SELECT giveaway_id FROM giveaway WHERE is_end = 1
                )
            ''')
            await db.commit()
