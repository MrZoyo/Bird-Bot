"""Persistent lifecycle of room invitations, independent of display-board expiry."""

from typing import Any

from .db_connect import connect_database
from .db_lifecycle import BaseDatabaseManager
from .schema_migrations import SchemaMigration, add_column_if_missing, apply_schema_migrations


async def initialize_invitation_schema(db):
    await db.execute('''CREATE TABLE IF NOT EXISTS user_teamup_stats (
        user_id INTEGER PRIMARY KEY, teamup_count INTEGER DEFAULT 0, last_teamup_at TIMESTAMP
    )''')
    await db.execute('''
        CREATE TABLE IF NOT EXISTS teamup_invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, channel_id INTEGER NOT NULL,
            voice_channel_id INTEGER NOT NULL, message_content TEXT NOT NULL,
            player_count INTEGER DEFAULT 1, game_type TEXT,
            created_at TIMESTAMP NOT NULL, expires_at TIMESTAMP NOT NULL,
            invitation_message_id INTEGER, invitation_channel_id INTEGER
        )
    ''')
    await apply_schema_migrations(db, 'room_invitations', [
        SchemaMigration(1, 'Explicit invitation lifecycle and durable message synchronization', _migrate_lifecycle),
    ])


async def _migrate_lifecycle(db):
    for name, definition in (
        ('status', "TEXT NOT NULL DEFAULT 'ended'"),
        ('end_reason', 'TEXT'), ('ended_at', 'TEXT'),
        ('message_sync', "TEXT NOT NULL DEFAULT 'done'"),
        ('sync_attempts', 'INTEGER NOT NULL DEFAULT 0'),
        ('sync_error', 'TEXT'), ('next_sync_at', 'TEXT'),
    ):
        await add_column_if_missing(db, 'teamup_invitations', name, definition)
    # Only migrate still-live, identifiable legacy invitations. Never resurrect
    # old records merely because their Discord message still has buttons.
    await db.execute('''
        UPDATE teamup_invitations SET status='active'
        WHERE invitation_message_id IS NOT NULL
          AND invitation_channel_id IS NOT NULL
          AND expires_at > datetime('now', 'localtime')
          AND id IN (SELECT MAX(id) FROM teamup_invitations GROUP BY voice_channel_id)
    ''')
    await db.execute('''
        UPDATE teamup_invitations
        SET end_reason='legacy_expired', ended_at=datetime('now'),
            message_sync=CASE WHEN invitation_message_id IS NULL THEN 'done'
                WHEN invitation_channel_id IS NULL THEN 'blocked' ELSE 'pending' END,
            sync_error=CASE WHEN invitation_message_id IS NOT NULL AND invitation_channel_id IS NULL
                THEN 'invalid' ELSE NULL END
        WHERE status='ended'
    ''')
    # Old rows used the server's local clock. New lifecycle timestamps are UTC.
    await db.execute("UPDATE teamup_invitations SET created_at=datetime(created_at, 'utc')")
    await db.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_invitation_per_room
        ON teamup_invitations(voice_channel_id) WHERE status='active'
    ''')
    await db.execute('''
        CREATE INDEX IF NOT EXISTS invitation_message_lookup
        ON teamup_invitations(invitation_message_id)
    ''')


async def _rows(db, sql, params=()):
    async with db.execute(sql, params) as cursor:
        names = [column[0] for column in cursor.description]
        return [dict(zip(names, row)) for row in await cursor.fetchall()]


class InvitationDatabaseManager(BaseDatabaseManager):
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self):
        async with connect_database(self.db_path) as db:
            await db.execute('BEGIN IMMEDIATE')
            await initialize_invitation_schema(db)
            await db.commit()

    async def prepare(self, *, user_id, channel_id, voice_channel_id, content,
                      player_count=1, game_type=None) -> dict[str, Any]:
        async with connect_database(self.db_path) as db:
            async with db.execute('''
                INSERT INTO teamup_invitations
                    (user_id, channel_id, voice_channel_id, message_content,
                     player_count, game_type, created_at, expires_at,
                     invitation_channel_id, status)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?, 'pending')
            ''', (user_id, channel_id, voice_channel_id, content, player_count, game_type, channel_id)) as cursor:
                invitation_id = cursor.lastrowid
            await db.commit()
        return await self.get(invitation_id)

    async def get(self, invitation_id):
        async with connect_database(self.db_path) as db:
            rows = await _rows(db, 'SELECT * FROM teamup_invitations WHERE id=?', (invitation_id,))
            return rows[0] if rows else None

    async def get_by_message(self, message_id):
        async with connect_database(self.db_path) as db:
            rows = await _rows(db, '''SELECT * FROM teamup_invitations
                WHERE invitation_message_id=? ORDER BY id DESC LIMIT 1''', (message_id,))
            return rows[0] if rows else None

    async def current(self, voice_channel_id):
        async with connect_database(self.db_path) as db:
            rows = await _rows(db, '''SELECT * FROM teamup_invitations
                WHERE voice_channel_id=? AND status='active' ''', (voice_channel_id,))
            return rows[0] if rows else None

    async def activate(self, invitation_id, message_id):
        """Attach the exact message, then atomically replace an earlier invitation.

        A recovered old send can never replace a newer successfully published
        invitation, even if that newer invitation has already ended.
        """
        async with connect_database(self.db_path) as db:
            await db.execute('BEGIN IMMEDIATE')
            rows = await _rows(db, 'SELECT * FROM teamup_invitations WHERE id=?', (invitation_id,))
            if not rows or rows[0]['status'] != 'pending':
                await db.rollback()
                return False
            row = rows[0]
            newer = await _rows(db, '''SELECT id FROM teamup_invitations
                WHERE voice_channel_id=? AND id>? AND invitation_message_id IS NOT NULL LIMIT 1''',
                (row['voice_channel_id'], invitation_id))
            if newer:
                await db.execute('''UPDATE teamup_invitations
                    SET invitation_message_id=?, status='ended', end_reason='superseded',
                        ended_at=datetime('now'), message_sync='pending' WHERE id=?''',
                    (message_id, invitation_id))
            else:
                await db.execute('''UPDATE teamup_invitations
                    SET status='ended', end_reason='superseded', ended_at=datetime('now'),
                        message_sync='pending', sync_attempts=0, next_sync_at=NULL
                    WHERE voice_channel_id=? AND status='active' ''', (row['voice_channel_id'],))
                await db.execute('''UPDATE teamup_invitations
                    SET invitation_message_id=?, status='active' WHERE id=?''', (message_id, invitation_id))
            await db.execute('''INSERT INTO user_teamup_stats (user_id, teamup_count, last_teamup_at)
                VALUES (?, 1, datetime('now', 'localtime'))
                ON CONFLICT(user_id) DO UPDATE SET teamup_count=teamup_count+1,
                    last_teamup_at=excluded.last_teamup_at''', (row['user_id'],))
            await db.commit()
            return not newer

    async def end(self, invitation_id, reason='full'):
        async with connect_database(self.db_path) as db:
            async with db.execute('''UPDATE teamup_invitations
                SET status='ended', end_reason=?, ended_at=datetime('now'),
                    message_sync='pending', sync_attempts=0, next_sync_at=NULL
                WHERE id=? AND status='active' ''', (reason, invitation_id)) as cursor:
                changed = cursor.rowcount == 1
            await db.commit()
            return changed

    async def abandon(self, invitation_id, reason='publish_failed'):
        async with connect_database(self.db_path) as db:
            await db.execute('''UPDATE teamup_invitations
                SET status='ended', end_reason=?, ended_at=datetime('now')
                WHERE id=? AND status='pending' ''', (reason, invitation_id))
            await db.commit()

    async def active(self):
        async with connect_database(self.db_path) as db:
            return await _rows(db, "SELECT * FROM teamup_invitations WHERE status='active' ORDER BY id DESC")

    async def pending_publications(self):
        async with connect_database(self.db_path) as db:
            return await _rows(db, '''SELECT * FROM teamup_invitations
                WHERE status='pending' AND created_at < datetime('now', '-2 minutes')
                ORDER BY id LIMIT 20''')

    async def record_recovery_failure(self, invitation_id):
        async with connect_database(self.db_path) as db:
            await db.execute('''UPDATE teamup_invitations
                SET sync_attempts=sync_attempts+1,
                    status=CASE WHEN sync_attempts>=2 THEN 'ended' ELSE 'pending' END,
                    end_reason=CASE WHEN sync_attempts>=2 THEN 'publish_unconfirmed' ELSE NULL END,
                    ended_at=CASE WHEN sync_attempts>=2 THEN datetime('now') ELSE NULL END
                WHERE id=? AND status='pending' ''', (invitation_id,))
            await db.commit()

    async def pending_sync(self, voice_channel_id=None):
        where = '' if voice_channel_id is None else ' AND voice_channel_id=?'
        params = () if voice_channel_id is None else (voice_channel_id,)
        async with connect_database(self.db_path) as db:
            return await _rows(db, '''SELECT * FROM teamup_invitations
                WHERE status='ended' AND message_sync='pending'
                AND (next_sync_at IS NULL OR next_sync_at <= datetime('now'))'''
                + where + ' ORDER BY id LIMIT 25', params)

    async def record_sync(self, invitation_id, outcome):
        async with connect_database(self.db_path) as db:
            if outcome in ('updated', 'missing'):
                await db.execute('''UPDATE teamup_invitations SET message_sync='done',
                    sync_error=NULL, next_sync_at=NULL WHERE id=?''', (invitation_id,))
            else:
                await db.execute('''UPDATE teamup_invitations
                    SET sync_attempts=sync_attempts+1, sync_error=?,
                        message_sync=CASE WHEN ? IN ('forbidden', 'invalid') OR sync_attempts>=2
                            THEN 'blocked' ELSE 'pending' END,
                        next_sync_at=datetime('now', '+1 minute')
                    WHERE id=?''', (outcome, outcome, invitation_id))
            await db.commit()

    async def cleanup_history(self):
        async with connect_database(self.db_path) as db:
            async with db.execute('''DELETE FROM teamup_invitations
                WHERE status='ended' AND message_sync='done'
                AND ended_at < datetime('now', '-14 days')''') as cursor:
                count = cursor.rowcount
            await db.commit()
            return count
