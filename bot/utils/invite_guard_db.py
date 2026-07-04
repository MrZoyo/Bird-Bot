from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiosqlite

from .db_connect import connect_database
from .db_lifecycle import BaseDatabaseManager
from .schema_migrations import SchemaMigration, add_column_if_missing, apply_schema_migrations


@dataclass(frozen=True)
class InviteLinkRecord:
    guild_id: int
    code: str
    channel_id: int | None
    inviter_id: int | None
    created_at: str | None
    max_age: int | None
    max_uses: int | None
    uses: int
    temporary: bool
    ignored: bool


@dataclass
class InviteLinkSyncSummary:
    scanned: int = 0
    inserted: int = 0
    updated: int = 0
    marked_inactive: int = 0


class InviteGuardDatabaseManager(BaseDatabaseManager):
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize_database(self) -> None:
        async with connect_database(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS invite_users (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    invited_count INTEGER DEFAULT 0,
                    invited_by_user_id INTEGER,
                    invited_by_code TEXT,
                    first_joined_at TEXT,
                    attributed_at TEXT,
                    attribution_status TEXT DEFAULT 'unattributed',
                    attribution_locked INTEGER DEFAULT 0,
                    allow_reattribution INTEGER DEFAULT 1,
                    join_count INTEGER DEFAULT 0,
                    leave_count INTEGER DEFAULT 0,
                    last_joined_at TEXT,
                    last_left_at TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (guild_id, user_id)
                )
            ''')
            await apply_schema_migrations(
                db,
                namespace='invite_guard',
                migrations=[
                    SchemaMigration(
                        version=1,
                        description='add pooled_count to invite_users for pooled attribution',
                        migrate=self._migrate_add_pooled_count,
                    ),
                ],
            )
            await db.execute('''
                CREATE TABLE IF NOT EXISTS invite_links (
                    guild_id INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    channel_id INTEGER,
                    inviter_id INTEGER,
                    created_at TEXT,
                    max_age INTEGER,
                    max_uses INTEGER,
                    uses INTEGER DEFAULT 0,
                    previous_uses INTEGER DEFAULT 0,
                    temporary INTEGER DEFAULT 0,
                    active INTEGER DEFAULT 1,
                    ignored INTEGER DEFAULT 0,
                    first_seen_at TEXT,
                    last_seen_at TEXT,
                    deleted_at TEXT,
                    PRIMARY KEY (guild_id, code)
                )
            ''')
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_invite_users_leaderboard
                ON invite_users(guild_id, invited_count DESC)
            ''')
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_invite_users_attributed
                ON invite_users(guild_id, invited_by_user_id, attribution_status)
            ''')
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_invite_links_inviter_active
                ON invite_links(guild_id, inviter_id, active)
            ''')
            await db.commit()

    async def _migrate_add_pooled_count(self, db: aiosqlite.Connection) -> None:
        await add_column_if_missing(db, 'invite_users', 'pooled_count', 'INTEGER DEFAULT 0')

    async def sync_invite_links(
        self,
        guild_id: int,
        records: list[InviteLinkRecord],
        now: str,
    ) -> InviteLinkSyncSummary:
        summary = InviteLinkSyncSummary(scanned=len(records))
        active_codes = {record.code for record in records}

        async with connect_database(self.db_path) as db:
            for record in records:
                existing = await self._fetch_link_row(db, guild_id, record.code)
                if existing is None:
                    await db.execute(
                        '''
                        INSERT INTO invite_links (
                            guild_id, code, channel_id, inviter_id, created_at,
                            max_age, max_uses, uses, previous_uses, temporary,
                            active, ignored, first_seen_at, last_seen_at, deleted_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, NULL)
                        ''',
                        (
                            guild_id,
                            record.code,
                            record.channel_id,
                            record.inviter_id,
                            record.created_at,
                            record.max_age,
                            record.max_uses,
                            record.uses,
                            record.uses,
                            int(record.temporary),
                            int(record.ignored),
                            now,
                            now,
                        ),
                    )
                    summary.inserted += 1
                    continue

                previous_uses = existing['uses']
                await db.execute(
                    '''
                    UPDATE invite_links
                    SET channel_id = ?,
                        inviter_id = ?,
                        created_at = COALESCE(?, created_at),
                        max_age = ?,
                        max_uses = ?,
                        previous_uses = ?,
                        uses = ?,
                        temporary = ?,
                        active = 1,
                        ignored = ?,
                        last_seen_at = ?,
                        deleted_at = NULL
                    WHERE guild_id = ? AND code = ?
                    ''',
                    (
                        record.channel_id,
                        record.inviter_id,
                        record.created_at,
                        record.max_age,
                        record.max_uses,
                        previous_uses,
                        record.uses,
                        int(record.temporary),
                        int(record.ignored),
                        now,
                        guild_id,
                        record.code,
                    ),
                )
                summary.updated += 1

            if active_codes:
                placeholders = ','.join('?' for _ in active_codes)
                cursor = await db.execute(
                    f'''
                    UPDATE invite_links
                    SET active = 0, deleted_at = COALESCE(deleted_at, ?)
                    WHERE guild_id = ?
                      AND active = 1
                      AND code NOT IN ({placeholders})
                    ''',
                    (now, guild_id, *active_codes),
                )
            else:
                cursor = await db.execute(
                    '''
                    UPDATE invite_links
                    SET active = 0, deleted_at = COALESCE(deleted_at, ?)
                    WHERE guild_id = ? AND active = 1
                    ''',
                    (now, guild_id),
                )
            summary.marked_inactive = cursor.rowcount
            await cursor.close()
            await db.commit()

        return summary

    async def upsert_invite_link(
        self,
        guild_id: int,
        record: InviteLinkRecord,
        now: str,
    ) -> None:
        async with connect_database(self.db_path) as db:
            existing = await self._fetch_link_row(db, guild_id, record.code)
            if existing is None:
                await db.execute(
                    '''
                    INSERT INTO invite_links (
                        guild_id, code, channel_id, inviter_id, created_at,
                        max_age, max_uses, uses, previous_uses, temporary,
                        active, ignored, first_seen_at, last_seen_at, deleted_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, NULL)
                    ''',
                    (
                        guild_id,
                        record.code,
                        record.channel_id,
                        record.inviter_id,
                        record.created_at,
                        record.max_age,
                        record.max_uses,
                        record.uses,
                        record.uses,
                        int(record.temporary),
                        int(record.ignored),
                        now,
                        now,
                    ),
                )
            else:
                await db.execute(
                    '''
                    UPDATE invite_links
                    SET channel_id = ?,
                        inviter_id = ?,
                        created_at = COALESCE(?, created_at),
                        max_age = ?,
                        max_uses = ?,
                        previous_uses = ?,
                        uses = ?,
                        temporary = ?,
                        active = 1,
                        ignored = ?,
                        last_seen_at = ?,
                        deleted_at = NULL
                    WHERE guild_id = ? AND code = ?
                    ''',
                    (
                        record.channel_id,
                        record.inviter_id,
                        record.created_at,
                        record.max_age,
                        record.max_uses,
                        existing['uses'],
                        record.uses,
                        int(record.temporary),
                        int(record.ignored),
                        now,
                        guild_id,
                        record.code,
                    ),
                )
            await db.commit()

    async def mark_invite_inactive(self, guild_id: int, code: str, now: str) -> None:
        async with connect_database(self.db_path) as db:
            await db.execute(
                '''
                UPDATE invite_links
                SET active = 0, deleted_at = COALESCE(deleted_at, ?)
                WHERE guild_id = ? AND code = ?
                ''',
                (now, guild_id, code),
            )
            await db.commit()

    async def record_member_join(self, guild_id: int, user_id: int, now: str) -> dict[str, Any]:
        async with connect_database(self.db_path) as db:
            await self._ensure_user_row(db, guild_id, user_id, now)
            await db.execute(
                '''
                UPDATE invite_users
                SET join_count = join_count + 1,
                    first_joined_at = COALESCE(first_joined_at, ?),
                    last_joined_at = ?,
                    updated_at = ?
                WHERE guild_id = ? AND user_id = ?
                ''',
                (now, now, now, guild_id, user_id),
            )
            await db.commit()
            return await self._get_user_record(db, guild_id, user_id)

    async def record_member_leave(self, guild_id: int, user_id: int, now: str) -> None:
        async with connect_database(self.db_path) as db:
            await self._ensure_user_row(db, guild_id, user_id, now)
            await db.execute(
                '''
                UPDATE invite_users
                SET leave_count = leave_count + 1,
                    last_left_at = ?,
                    updated_at = ?
                WHERE guild_id = ? AND user_id = ?
                ''',
                (now, now, guild_id, user_id),
            )
            await db.commit()

    async def attribute_member(
        self,
        guild_id: int,
        user_id: int,
        inviter_id: int,
        code: str,
        now: str,
    ) -> bool:
        async with connect_database(self.db_path) as db:
            await db.execute('BEGIN IMMEDIATE')
            await self._ensure_user_row(db, guild_id, user_id, now)
            await self._ensure_user_row(db, guild_id, inviter_id, now)
            user_record = await self._get_user_record(db, guild_id, user_id)

            if int(user_record['attribution_locked'] or 0):
                await db.rollback()
                return False
            if not int(user_record['allow_reattribution'] or 0):
                await db.rollback()
                return False

            await db.execute(
                '''
                UPDATE invite_users
                SET invited_by_user_id = ?,
                    invited_by_code = ?,
                    attributed_at = ?,
                    attribution_status = 'attributed',
                    attribution_locked = 1,
                    allow_reattribution = 0,
                    updated_at = ?
                WHERE guild_id = ? AND user_id = ?
                ''',
                (inviter_id, code, now, now, guild_id, user_id),
            )
            await db.execute(
                '''
                UPDATE invite_users
                SET invited_count = invited_count + 1,
                    updated_at = ?
                WHERE guild_id = ? AND user_id = ?
                ''',
                (now, guild_id, inviter_id),
            )
            await db.commit()
            return True

    async def pool_attribute_members(
        self,
        guild_id: int,
        member_ids: list[int],
        awards: list[tuple[int, str, int]],
        now: str,
    ) -> bool:
        """Attribute a batch of members to a 'pooled' status without a specific inviter.

        Used when multiple members join in the same settlement window and the total
        invite-use delta matches the batch size, but the exact member-to-invite
        mapping cannot be determined (more than one invite grew at once). Every
        member in ``member_ids`` is locked with attribution_status='pooled' and no
        invited_by_user_id/invited_by_code; every ``(inviter_id, code, delta)`` in
        ``awards`` accumulates ``pooled_count += delta`` on the inviter's row.

        Returns False (and rolls back) if any member in the batch is already
        attribution_locked or has allow_reattribution disabled at read-back time.
        """
        async with connect_database(self.db_path) as db:
            await db.execute('BEGIN IMMEDIATE')

            for member_id in member_ids:
                await self._ensure_user_row(db, guild_id, member_id, now)
                member_record = await self._get_user_record(db, guild_id, member_id)
                if int(member_record['attribution_locked'] or 0):
                    await db.rollback()
                    return False
                if not int(member_record['allow_reattribution'] or 0):
                    await db.rollback()
                    return False

            for member_id in member_ids:
                await db.execute(
                    '''
                    UPDATE invite_users
                    SET invited_by_user_id = NULL,
                        invited_by_code = NULL,
                        attribution_status = 'pooled',
                        attribution_locked = 1,
                        allow_reattribution = 0,
                        attributed_at = ?,
                        updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    ''',
                    (now, now, guild_id, member_id),
                )

            for inviter_id, _code, delta in awards:
                await self._ensure_user_row(db, guild_id, inviter_id, now)
                await db.execute(
                    '''
                    UPDATE invite_users
                    SET pooled_count = pooled_count + ?,
                        updated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    ''',
                    (delta, now, guild_id, inviter_id),
                )

            await db.commit()
            return True

    async def set_member_attribution_status(
        self,
        guild_id: int,
        user_id: int,
        status: str,
        *,
        code: str | None,
        inviter_id: int | None = None,
        allow_reattribution: bool,
        now: str,
    ) -> bool:
        async with connect_database(self.db_path) as db:
            await self._ensure_user_row(db, guild_id, user_id, now)
            user_record = await self._get_user_record(db, guild_id, user_id)
            if int(user_record['attribution_locked'] or 0):
                return False

            await db.execute(
                '''
                UPDATE invite_users
                SET invited_by_user_id = ?,
                    invited_by_code = ?,
                    attribution_status = ?,
                    attribution_locked = 0,
                    allow_reattribution = ?,
                    updated_at = ?
                WHERE guild_id = ? AND user_id = ?
                ''',
                (
                    inviter_id,
                    code,
                    status,
                    int(allow_reattribution),
                    now,
                    guild_id,
                    user_id,
                ),
            )
            await db.commit()
            return True

    async def get_user(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        async with connect_database(self.db_path) as db:
            return await self._get_user_record(db, guild_id, user_id)

    async def get_invite_link(self, guild_id: int, code: str) -> dict[str, Any] | None:
        async with connect_database(self.db_path) as db:
            return await self._fetch_link_row(db, guild_id, code)

    async def get_leaderboard(self, guild_id: int, limit: int) -> list[dict[str, Any]]:
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(
                '''
                SELECT
                    u.user_id,
                    u.invited_count,
                    u.pooled_count,
                    (u.invited_count + u.pooled_count) AS total_count,
                    COALESCE(active_links.active_count, 0) AS active_invite_count
                FROM invite_users u
                LEFT JOIN (
                    SELECT guild_id, inviter_id, COUNT(*) AS active_count
                    FROM invite_links
                    WHERE guild_id = ? AND active = 1 AND ignored = 0
                    GROUP BY guild_id, inviter_id
                ) active_links
                  ON active_links.guild_id = u.guild_id
                 AND active_links.inviter_id = u.user_id
                WHERE u.guild_id = ? AND (u.invited_count + u.pooled_count) > 0
                ORDER BY total_count DESC, u.user_id ASC
                LIMIT ?
                ''',
                (guild_id, guild_id, limit),
            )
            rows = await cursor.fetchall()
            await cursor.close()

        return [
            {
                'user_id': row[0],
                'invited_count': row[1],
                'pooled_count': row[2],
                'total_count': row[3],
                'active_invite_count': row[4],
            }
            for row in rows
        ]

    async def find_count_mismatches(self, guild_id: int) -> list[dict[str, Any]]:
        # Only reconciles invited_count (single-inviter attributed members). Pooled
        # attribution (pooled_count) has no per-member invited_by_user_id row to
        # recompute from by design, so it is intentionally excluded here.
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(
                '''
                WITH actual_counts AS (
                    SELECT guild_id, invited_by_user_id AS user_id, COUNT(*) AS actual_count
                    FROM invite_users
                    WHERE guild_id = ?
                      AND attribution_status = 'attributed'
                      AND attribution_locked = 1
                      AND invited_by_user_id IS NOT NULL
                    GROUP BY guild_id, invited_by_user_id
                ),
                compared AS (
                    SELECT
                        u.user_id,
                        u.invited_count AS stored_count,
                        COALESCE(a.actual_count, 0) AS actual_count
                    FROM invite_users u
                    LEFT JOIN actual_counts a
                      ON a.guild_id = u.guild_id
                     AND a.user_id = u.user_id
                    WHERE u.guild_id = ?
                    UNION
                    SELECT
                        a.user_id,
                        COALESCE(u.invited_count, 0) AS stored_count,
                        a.actual_count
                    FROM actual_counts a
                    LEFT JOIN invite_users u
                      ON u.guild_id = a.guild_id
                     AND u.user_id = a.user_id
                    WHERE a.guild_id = ?
                )
                SELECT user_id, stored_count, actual_count
                FROM compared
                WHERE stored_count != actual_count
                ORDER BY ABS(stored_count - actual_count) DESC, user_id ASC
                ''',
                (guild_id, guild_id, guild_id),
            )
            rows = await cursor.fetchall()
            await cursor.close()

        return [
            {
                'user_id': row[0],
                'stored_count': row[1],
                'actual_count': row[2],
            }
            for row in rows
        ]

    async def set_invite_ignored(self, guild_id: int, code: str, ignored: bool) -> bool:
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(
                '''
                UPDATE invite_links
                SET ignored = ?
                WHERE guild_id = ? AND code = ?
                ''',
                (int(ignored), guild_id, code),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def _ensure_user_row(
        self,
        db: aiosqlite.Connection,
        guild_id: int,
        user_id: int,
        now: str,
    ) -> None:
        await db.execute(
            '''
            INSERT INTO invite_users (
                guild_id, user_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO NOTHING
            ''',
            (guild_id, user_id, now, now),
        )

    async def _get_user_record(
        self,
        db: aiosqlite.Connection,
        guild_id: int,
        user_id: int,
    ) -> dict[str, Any] | None:
        cursor = await db.execute(
            '''
            SELECT
                guild_id,
                user_id,
                invited_count,
                pooled_count,
                invited_by_user_id,
                invited_by_code,
                first_joined_at,
                attributed_at,
                attribution_status,
                attribution_locked,
                allow_reattribution,
                join_count,
                leave_count,
                last_joined_at,
                last_left_at,
                created_at,
                updated_at
            FROM invite_users
            WHERE guild_id = ? AND user_id = ?
            ''',
            (guild_id, user_id),
        )
        try:
            row = await cursor.fetchone()
        finally:
            await cursor.close()
        if row is None:
            return None
        return _invite_user_row_to_dict(row)

    async def _fetch_link_row(
        self,
        db: aiosqlite.Connection,
        guild_id: int,
        code: str,
    ) -> dict[str, Any] | None:
        cursor = await db.execute(
            '''
            SELECT
                guild_id,
                code,
                channel_id,
                inviter_id,
                created_at,
                max_age,
                max_uses,
                uses,
                previous_uses,
                temporary,
                active,
                ignored,
                first_seen_at,
                last_seen_at,
                deleted_at
            FROM invite_links
            WHERE guild_id = ? AND code = ?
            ''',
            (guild_id, code),
        )
        try:
            row = await cursor.fetchone()
        finally:
            await cursor.close()
        if row is None:
            return None
        return _invite_link_row_to_dict(row)


def _invite_user_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        'guild_id': row[0],
        'user_id': row[1],
        'invited_count': row[2],
        'pooled_count': row[3],
        'invited_by_user_id': row[4],
        'invited_by_code': row[5],
        'first_joined_at': row[6],
        'attributed_at': row[7],
        'attribution_status': row[8],
        'attribution_locked': row[9],
        'allow_reattribution': row[10],
        'join_count': row[11],
        'leave_count': row[12],
        'last_joined_at': row[13],
        'last_left_at': row[14],
        'created_at': row[15],
        'updated_at': row[16],
    }


def _invite_link_row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        'guild_id': row[0],
        'code': row[1],
        'channel_id': row[2],
        'inviter_id': row[3],
        'created_at': row[4],
        'max_age': row[5],
        'max_uses': row[6],
        'uses': row[7],
        'previous_uses': row[8],
        'temporary': row[9],
        'active': row[10],
        'ignored': row[11],
        'first_seen_at': row[12],
        'last_seen_at': row[13],
        'deleted_at': row[14],
    }
