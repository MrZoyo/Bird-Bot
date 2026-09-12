"""Invite credit ledger, frozen monthly results, and reward notification state."""
from datetime import datetime

import aiosqlite

from .db_connect import connect_database
from .db_lifecycle import BaseDatabaseManager
from .invite_months import month_bounds, month_key, shift_month


async def create_monthly_tables(db: aiosqlite.Connection) -> None:
    statements = [
        '''CREATE TABLE IF NOT EXISTS invite_monthly_tracking (
            guild_id INTEGER PRIMARY KEY, initial_month TEXT NOT NULL,
            next_month TEXT NOT NULL, timezone TEXT NOT NULL, started_at TEXT NOT NULL
        )''',
        '''CREATE TABLE IF NOT EXISTS invite_monthly_credits (
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
            inviter_id INTEGER NOT NULL, amount INTEGER NOT NULL CHECK (amount > 0),
            credited_at REAL NOT NULL, source TEXT NOT NULL
        )''',
        '''CREATE INDEX IF NOT EXISTS idx_invite_monthly_credits
            ON invite_monthly_credits(guild_id, credited_at, inviter_id)''',
        '''CREATE TABLE IF NOT EXISTS invite_monthly_settlements (
            guild_id INTEGER NOT NULL, month TEXT NOT NULL, settled_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, month)
        )''',
        '''CREATE TABLE IF NOT EXISTS invite_monthly_rewards (
            guild_id INTEGER NOT NULL, month TEXT NOT NULL, user_id INTEGER NOT NULL,
            rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 10),
            total_count INTEGER NOT NULL CHECK (total_count > 0), points INTEGER NOT NULL,
            paid_at TEXT, dm_status TEXT NOT NULL DEFAULT 'pending', dm_message_id INTEGER,
            PRIMARY KEY (guild_id, month, user_id), UNIQUE (guild_id, month, rank)
        )''',
    ]
    for statement in statements:
        cursor = await db.execute(statement)
        await cursor.close()


async def record_monthly_credit(db, guild_id: int, inviter_id: int, amount: int, now: str, source: str):
    """Called inside the same transaction that increments lifetime invite counts."""
    instant = datetime.fromisoformat(now)
    if instant.tzinfo is None:
        raise ValueError('Invite credit timestamp must include its UTC offset')
    cursor = await db.execute(
        '''INSERT INTO invite_monthly_credits (guild_id, inviter_id, amount, credited_at, source)
           SELECT ?, ?, ?, ?, ? WHERE EXISTS
               (SELECT 1 FROM invite_monthly_tracking WHERE guild_id = ?)''',
        (guild_id, inviter_id, amount, instant.timestamp(), source, guild_id),
    )
    await cursor.close()


class InviteMonthlyDatabaseManager(BaseDatabaseManager):
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def ensure_tracking(self, guild_id: int, now: datetime, timezone_name: str) -> None:
        """Import existing lifetime counts into the first month exactly once."""
        key = month_key(now, timezone_name)
        async with connect_database(self.db_path) as db:
            await db.execute('BEGIN IMMEDIATE')
            cursor = await db.execute('SELECT timezone FROM invite_monthly_tracking WHERE guild_id=?', (guild_id,))
            existing = await cursor.fetchone()
            await cursor.close()
            if existing:
                if existing[0] != timezone_name:
                    raise ValueError('Changing the monthly invite timezone requires an explicit migration')
                await db.rollback()
                return
            await db.execute(
                'INSERT INTO invite_monthly_tracking VALUES (?, ?, ?, ?, ?)',
                (guild_id, key, key, timezone_name, now.isoformat()),
            )
            await db.execute(
                '''INSERT INTO invite_monthly_credits (guild_id, inviter_id, amount, credited_at, source)
                   SELECT guild_id, user_id, invited_count + pooled_count, ?, 'opening_balance'
                   FROM invite_users WHERE guild_id=? AND invited_count + pooled_count > 0''',
                (now.timestamp(), guild_id),
            )
            await db.commit()

    async def get_leaderboard(self, guild_id: int, key: str, timezone_name: str) -> list[dict]:
        start, end = month_bounds(key, timezone_name)
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(
                '''SELECT inviter_id, SUM(amount) AS total_count FROM invite_monthly_credits
                   WHERE guild_id=? AND credited_at>=? AND credited_at<?
                   GROUP BY inviter_id ORDER BY total_count DESC, inviter_id ASC''',
                (guild_id, start.timestamp(), end.timestamp()),
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return [dict(user_id=row[0], total_count=row[1]) for row in rows]

    async def next_unsettled_month(self, guild_id: int) -> str | None:
        async with connect_database(self.db_path) as db:
            cursor = await db.execute('SELECT next_month FROM invite_monthly_tracking WHERE guild_id=?', (guild_id,))
            row = await cursor.fetchone()
            await cursor.close()
        return row[0] if row else None

    async def freeze_results(self, guild_id: int, key: str, winners: list[dict], now: datetime) -> bool:
        if len(winners) > 10 or len({row['user_id'] for row in winners}) != len(winners):
            raise ValueError('Monthly results must contain at most ten distinct inviters')
        async with connect_database(self.db_path) as db:
            await db.execute('BEGIN IMMEDIATE')
            cursor = await db.execute(
                'SELECT next_month, timezone FROM invite_monthly_tracking WHERE guild_id=?', (guild_id,),
            )
            tracking = await cursor.fetchone()
            await cursor.close()
            if not tracking or key != tracking[0]:
                await db.rollback()
                return False
            if now < month_bounds(key, tracking[1])[1]:
                raise ValueError('Cannot settle an invitation month before it ends')
            await db.execute('INSERT INTO invite_monthly_settlements VALUES (?, ?, ?)',
                             (guild_id, key, now.isoformat()))
            for rank, row in enumerate(winners, 1):
                points = {1: 200, 2: 150, 3: 100}.get(rank, 60)
                await db.execute(
                    '''INSERT INTO invite_monthly_rewards
                       (guild_id, month, user_id, rank, total_count, points) VALUES (?, ?, ?, ?, ?, ?)''',
                    (guild_id, key, row['user_id'], rank, row['total_count'], points),
                )
            await db.execute('UPDATE invite_monthly_tracking SET next_month=? WHERE guild_id=?',
                             (shift_month(key, 1), guild_id))
            await db.commit()
        return True

    async def get_rewards(self, guild_id: int, *, pending_only: bool = False) -> list[dict]:
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(
                '''SELECT guild_id, month, user_id, rank, total_count, points, paid_at, dm_status, dm_message_id
                   FROM invite_monthly_rewards WHERE guild_id=?
                   AND (?=0 OR paid_at IS NULL OR dm_status='pending') ORDER BY month, rank''',
                (guild_id, int(pending_only)),
            )
            names = [column[0] for column in cursor.description]
            rows = [dict(zip(names, row)) for row in await cursor.fetchall()]
            await cursor.close()
        return rows

    async def mark_paid(self, reward: dict, now: datetime) -> None:
        async with connect_database(self.db_path) as db:
            await db.execute(
                'UPDATE invite_monthly_rewards SET paid_at=COALESCE(paid_at, ?) WHERE guild_id=? AND month=? AND user_id=?',
                (now.isoformat(), reward['guild_id'], reward['month'], reward['user_id']),
            )
            await db.commit()

    async def claim_notification(self, reward: dict) -> bool:
        # Claim before sending: a restart during an uncertain send must not spam
        # the winner. A sending row remains available for operator inspection.
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(
                '''UPDATE invite_monthly_rewards SET dm_status='sending'
                   WHERE guild_id=? AND month=? AND user_id=? AND paid_at IS NOT NULL AND dm_status='pending' ''',
                (reward['guild_id'], reward['month'], reward['user_id']),
            )
            claimed = cursor.rowcount == 1
            await cursor.close()
            await db.commit()
        return claimed

    async def finish_notification(self, reward: dict, status: str, message_id: int | None = None) -> None:
        if status not in {'sent', 'failed'}:
            raise ValueError('Invalid monthly notification outcome')
        async with connect_database(self.db_path) as db:
            await db.execute(
                '''UPDATE invite_monthly_rewards SET dm_status=?, dm_message_id=?
                   WHERE guild_id=? AND month=? AND user_id=? AND dm_status='sending' ''',
                (status, message_id, reward['guild_id'], reward['month'], reward['user_id']),
            )
            await db.commit()

    async def get_champion(self, guild_id: int, key: str) -> dict | None:
        async with connect_database(self.db_path) as db:
            cursor = await db.execute(
                'SELECT user_id, total_count FROM invite_monthly_rewards WHERE guild_id=? AND month=? AND rank=1',
                (guild_id, key),
            )
            row = await cursor.fetchone()
            await cursor.close()
        return dict(user_id=row[0], total_count=row[1]) if row else None
