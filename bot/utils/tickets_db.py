# bot/utils/tickets_db.py

import aiosqlite
import logging
from datetime import datetime
from typing import Optional, List, Tuple, Dict


class TicketsDatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize_database(self) -> None:
        """Create necessary database tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            # Tickets table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS tickets (
                    channel_id INTEGER PRIMARY KEY,
                    message_id INTEGER NOT NULL,
                    creator_id INTEGER NOT NULL,
                    type_name TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    accepted_by INTEGER,
                    accepted_at TIMESTAMP,
                    closed_by INTEGER,
                    closed_at TIMESTAMP,
                    close_reason TEXT,
                    is_closed BOOLEAN NOT NULL DEFAULT 0,
                    is_accepted BOOLEAN NOT NULL DEFAULT 0
                )
            ''')

            # Ticket members table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS ticket_members (
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    added_by INTEGER NOT NULL,
                    added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (channel_id, user_id),
                    FOREIGN KEY (channel_id) REFERENCES tickets(channel_id)
                )
            ''')
            await db.commit()

    async def create_ticket(self, channel_id: int, message_id: int,
                            creator_id: int, type_name: str) -> bool:
        """Create a new ticket and add creator as first member."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO tickets (
                        channel_id, message_id, creator_id, type_name, 
                        created_at, is_closed, is_accepted
                    ) VALUES (?, ?, ?, ?, datetime('now'), 0, 0)
                ''', (channel_id, message_id, creator_id, type_name))

                # Add creator as first member
                await db.execute('''
                    INSERT INTO ticket_members (channel_id, user_id, added_by, added_at)
                    VALUES (?, ?, ?, datetime('now'))
                ''', (channel_id, creator_id, creator_id))

                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error creating ticket: {e}")
                return False

    async def check_member_exists(self, channel_id: int, user_id: int) -> bool:
        """Check if a user is already a member of the ticket."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT 1 FROM ticket_members 
                WHERE channel_id = ? AND user_id = ?
            ''', (channel_id, user_id))
            result = await cursor.fetchone()
            return bool(result)

    async def check_ticket_status(self, channel_id: int) -> Tuple[bool, bool]:
        """Check if ticket exists and if it's closed."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT is_closed FROM tickets WHERE channel_id = ?
            ''', (channel_id,))
            result = await cursor.fetchone()

            if not result:
                return False, False  # Ticket doesn't exist
            return True, bool(result[0])  # Returns (exists, is_closed)

    async def add_ticket_member(self, channel_id: int, user_id: int,
                                added_by: int) -> bool:
        """Add a member to a ticket if they're not already in it."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # First check if ticket exists and is not closed
                ticket_exists, is_closed = await self.check_ticket_status(channel_id)
                if not ticket_exists:
                    return False
                if is_closed:
                    return False

                # Check if member already exists
                if await self.check_member_exists(channel_id, user_id):
                    return False

                # Add new member
                await db.execute('''
                    INSERT INTO ticket_members (channel_id, user_id, added_by, added_at)
                    VALUES (?, ?, ?, datetime('now'))
                ''', (channel_id, user_id, added_by))
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error adding ticket member: {e}")
                return False

    async def accept_ticket(self, channel_id: int, accepted_by: int) -> bool:
        """Mark a ticket as accepted if it's not already accepted."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Check if ticket is already accepted
                cursor = await db.execute('''
                    SELECT is_accepted, is_closed FROM tickets 
                    WHERE channel_id = ?
                ''', (channel_id,))
                result = await cursor.fetchone()
                if not result:
                    return False
                if result[0] or result[1]:  # is_accepted or is_closed
                    return False

                # Update ticket
                await db.execute('''
                    UPDATE tickets 
                    SET accepted_by = ?, 
                        accepted_at = datetime('now'),
                        is_accepted = 1
                    WHERE channel_id = ?
                ''', (accepted_by, channel_id))
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error accepting ticket: {e}")
                return False

    async def close_ticket(self, channel_id: int, closed_by: int,
                           reason: str) -> bool:
        """Close a ticket if it's not already closed."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute('''
                    SELECT is_closed FROM tickets WHERE channel_id = ?
                ''', (channel_id,))
                result = await cursor.fetchone()
                if not result or result[0]:  # Doesn't exist or already closed
                    return False

                await db.execute('''
                    UPDATE tickets 
                    SET closed_by = ?,
                        closed_at = datetime('now'),
                        close_reason = ?,
                        is_closed = 1
                    WHERE channel_id = ?
                ''', (closed_by, reason, channel_id))
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error closing ticket: {e}")
                return False

    async def get_ticket_stats(self) -> dict:
        """Get comprehensive ticket statistics."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # Get total tickets
            await cursor.execute('SELECT COUNT(*) FROM tickets')
            total_tickets = (await cursor.fetchone())[0]

            # Get active tickets
            await cursor.execute('SELECT COUNT(*) FROM tickets WHERE is_closed = 0')
            active_tickets = (await cursor.fetchone())[0]

            # Get closed tickets
            await cursor.execute('SELECT COUNT(*) FROM tickets WHERE is_closed = 1')
            closed_tickets = (await cursor.fetchone())[0]

            # Get average response time
            await cursor.execute('''
                SELECT AVG(
                    CAST(
                        (JULIANDAY(accepted_at) - JULIANDAY(created_at)) * 24 * 60 AS INTEGER)
                    )
                FROM tickets 
                WHERE accepted_at IS NOT NULL
            ''')
            avg_response_time = (await cursor.fetchone())[0] or 0

            # Get tickets by type
            await cursor.execute('''
                SELECT type_name, COUNT(*) 
                FROM tickets 
                GROUP BY type_name
            ''')
            tickets_by_type = await cursor.fetchall()

            return {
                'total': total_tickets,
                'active': active_tickets,
                'closed': closed_tickets,
                'avg_response_time': int(avg_response_time),
                'by_type': tickets_by_type
            }

    async def get_ticket_members(self, channel_id: int) -> List[Tuple[int, int, str]]:
        """Get all members of a ticket."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute('''
                    SELECT user_id, added_by, added_at
                    FROM ticket_members
                    WHERE channel_id = ?
                    ORDER BY added_at ASC
                ''', (channel_id,))
                return await cursor.fetchall()
            except Exception as e:
                logging.error(f"Error getting ticket members: {e}")
                return []

    async def get_active_tickets(self) -> List[Tuple]:
        """Get all active (not closed) tickets."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute('''
                    SELECT channel_id, message_id, creator_id, type_name, is_accepted
                    FROM tickets 
                    WHERE is_closed = 0
                    ORDER BY created_at DESC
                ''')
                return await cursor.fetchall()
            except Exception as e:
                logging.error(f"Error getting active tickets: {e}")
                return []

    async def clean_invalid_tickets(self, valid_channel_ids: List[int]) -> None:
        """Clean up tickets for channels that no longer exist."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    DELETE FROM ticket_members 
                    WHERE channel_id NOT IN ({})
                '''.format(','.join('?' * len(valid_channel_ids))), valid_channel_ids)

                await db.execute('''
                    DELETE FROM tickets 
                    WHERE channel_id NOT IN ({})
                '''.format(','.join('?' * len(valid_channel_ids))), valid_channel_ids)

                await db.commit()
            except Exception as e:
                logging.error(f"Error cleaning invalid tickets: {e}")

    async def get_ticket_number(self, channel_id: int) -> int:
        """Get ticket number from database based on channel ID."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT COUNT(*) 
                FROM tickets 
                WHERE channel_id <= ?
            ''', (channel_id,))
            count = await cursor.fetchone()
            return count[0] if count else 0
