# bot/utils/tickets_new_db.py
import json
import sqlite3
import aiosqlite
import logging
from datetime import datetime
from typing import Optional, List, Tuple, Dict


class TicketsNewDatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize_database(self) -> None:
        """Create necessary database tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            # New tickets table for thread-based system
            await db.execute('''
                CREATE TABLE IF NOT EXISTS tickets_new (
                    thread_id INTEGER PRIMARY KEY,
                    ticket_number INTEGER NOT NULL,
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
                    is_accepted BOOLEAN NOT NULL DEFAULT 0,
                    ticket_channel_id INTEGER NOT NULL
                )
            ''')
            
            # Add ticket_number column if it doesn't exist (for existing databases)
            try:
                await db.execute('ALTER TABLE tickets_new ADD COLUMN ticket_number INTEGER')
            except Exception:
                pass  # Column already exists

            # New ticket members table for thread-based system
            await db.execute('''
                CREATE TABLE IF NOT EXISTS ticket_new_members (
                    thread_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    added_by INTEGER NOT NULL,
                    added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (thread_id, user_id),
                    FOREIGN KEY (thread_id) REFERENCES tickets_new(thread_id)
                )
            ''')
            
            # Ticket system configuration table
            await db.execute('''
                CREATE TABLE IF NOT EXISTS ticket_new_config (
                    id INTEGER PRIMARY KEY,
                    ticket_channel_id INTEGER,
                    info_channel_id INTEGER,
                    main_message_id INTEGER,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.commit()

    async def set_config(self, ticket_channel_id: int, info_channel_id: int, 
                        main_message_id: Optional[int] = None) -> bool:
        """Set or update ticket system configuration."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Check if config exists
                cursor = await db.execute('SELECT id FROM ticket_new_config LIMIT 1')
                exists = await cursor.fetchone()
                
                if exists:
                    # Update existing config
                    await db.execute('''
                        UPDATE ticket_new_config 
                        SET ticket_channel_id = ?, info_channel_id = ?, 
                            main_message_id = ?, updated_at = datetime('now')
                        WHERE id = ?
                    ''', (ticket_channel_id, info_channel_id, main_message_id, exists[0]))
                else:
                    # Insert new config
                    await db.execute('''
                        INSERT INTO ticket_new_config (
                            ticket_channel_id, info_channel_id, main_message_id,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, datetime('now'), datetime('now'))
                    ''', (ticket_channel_id, info_channel_id, main_message_id))
                
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error setting ticket config: {e}")
                return False

    async def get_config(self) -> Optional[Dict]:
        """Get ticket system configuration."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute('''
                    SELECT ticket_channel_id, info_channel_id, main_message_id
                    FROM ticket_new_config 
                    ORDER BY updated_at DESC LIMIT 1
                ''')
                result = await cursor.fetchone()
                
                if result:
                    return {
                        'ticket_channel_id': result[0],
                        'info_channel_id': result[1],
                        'main_message_id': result[2]
                    }
                return None
            except Exception as e:
                logging.error(f"Error getting ticket config: {e}")
                return None

    async def create_ticket(self, thread_id: int, message_id: int,
                            creator_id: int, type_name: str, 
                            ticket_channel_id: int, ticket_number: int) -> bool:
        """Create a new ticket and add creator as first member."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO tickets_new (
                        thread_id, ticket_number, message_id, creator_id, type_name, 
                        ticket_channel_id, created_at, is_closed, is_accepted
                    ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), 0, 0)
                ''', (thread_id, ticket_number, message_id, creator_id, type_name, ticket_channel_id))

                # Add creator as first member
                await db.execute('''
                    INSERT INTO ticket_new_members (thread_id, user_id, added_by, added_at)
                    VALUES (?, ?, ?, datetime('now'))
                ''', (thread_id, creator_id, creator_id))

                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error creating ticket: {e}")
                return False

    async def check_member_exists(self, thread_id: int, user_id: int) -> bool:
        """Check if a user is already a member of the ticket."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT 1 FROM ticket_new_members 
                WHERE thread_id = ? AND user_id = ?
            ''', (thread_id, user_id))
            result = await cursor.fetchone()
            return bool(result)

    async def check_ticket_status(self, thread_id: int) -> Tuple[bool, bool]:
        """Check if ticket exists and if it's closed."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT is_closed FROM tickets_new WHERE thread_id = ?
            ''', (thread_id,))
            result = await cursor.fetchone()

            if not result:
                return False, False  # Ticket doesn't exist
            return True, bool(result[0])  # Returns (exists, is_closed)

    async def add_ticket_member(self, thread_id: int, user_id: int,
                                added_by: int) -> bool:
        """Add a member to a ticket if they're not already in it."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # First check if ticket exists and is not closed
                ticket_exists, is_closed = await self.check_ticket_status(thread_id)
                if not ticket_exists:
                    return False
                if is_closed:
                    return False

                # Check if member already exists
                if await self.check_member_exists(thread_id, user_id):
                    return False

                # Add new member
                await db.execute('''
                    INSERT INTO ticket_new_members (thread_id, user_id, added_by, added_at)
                    VALUES (?, ?, ?, datetime('now'))
                ''', (thread_id, user_id, added_by))
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error adding ticket member: {e}")
                return False

    async def accept_ticket(self, thread_id: int, accepted_by: int) -> bool:
        """Mark a ticket as accepted if it's not already accepted."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Check if ticket is already accepted
                cursor = await db.execute('''
                    SELECT is_accepted, is_closed FROM tickets_new 
                    WHERE thread_id = ?
                ''', (thread_id,))
                result = await cursor.fetchone()
                if not result:
                    return False
                if result[0] or result[1]:  # is_accepted or is_closed
                    return False

                # Update ticket
                await db.execute('''
                    UPDATE tickets_new 
                    SET accepted_by = ?, 
                        accepted_at = datetime('now'),
                        is_accepted = 1
                    WHERE thread_id = ?
                ''', (accepted_by, thread_id))
                await db.commit()
                return True
            except Exception as e:
                logging.error(f"Error accepting ticket: {e}")
                return False

    async def close_ticket(self, thread_id: int, closed_by: int,
                           reason: str) -> bool:
        """Close a ticket if it's not already closed."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute('''
                    SELECT is_closed FROM tickets_new WHERE thread_id = ?
                ''', (thread_id,))
                result = await cursor.fetchone()
                if not result or result[0]:  # Doesn't exist or already closed
                    return False

                await db.execute('''
                    UPDATE tickets_new 
                    SET closed_by = ?,
                        closed_at = datetime('now'),
                        close_reason = ?,
                        is_closed = 1
                    WHERE thread_id = ?
                ''', (closed_by, reason, thread_id))
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
            await cursor.execute('SELECT COUNT(*) FROM tickets_new')
            total_tickets = (await cursor.fetchone())[0]

            # Get active tickets
            await cursor.execute('SELECT COUNT(*) FROM tickets_new WHERE is_closed = 0')
            active_tickets = (await cursor.fetchone())[0]

            # Get closed tickets
            await cursor.execute('SELECT COUNT(*) FROM tickets_new WHERE is_closed = 1')
            closed_tickets = (await cursor.fetchone())[0]

            # Get average response time
            await cursor.execute('''
                SELECT AVG(
                    CAST(
                        (JULIANDAY(accepted_at) - JULIANDAY(created_at)) * 24 * 60 AS INTEGER)
                    )
                FROM tickets_new 
                WHERE accepted_at IS NOT NULL
            ''')
            avg_response_time = (await cursor.fetchone())[0] or 0

            # Get tickets by type
            await cursor.execute('''
                SELECT type_name, COUNT(*) 
                FROM tickets_new 
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

    async def get_ticket_members(self, thread_id: int) -> List[Tuple[int, int, str]]:
        """Get all members of a ticket."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute('''
                    SELECT user_id, added_by, added_at
                    FROM ticket_new_members
                    WHERE thread_id = ?
                    ORDER BY added_at ASC
                ''', (thread_id,))
                return await cursor.fetchall()
            except Exception as e:
                logging.error(f"Error getting ticket members: {e}")
                return []

    async def get_active_tickets(self) -> List[dict]:
        """Get all active (not closed) tickets."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute('''
                    SELECT thread_id, message_id, creator_id, type_name, 
                           accepted_by, closed_at, is_accepted, is_closed
                    FROM tickets_new 
                    ORDER BY created_at DESC
                ''')
                rows = await cursor.fetchall()
                
                tickets = []
                for row in rows:
                    tickets.append({
                        'thread_id': row[0],
                        'message_id': row[1],
                        'creator_id': row[2],
                        'type_name': row[3],
                        'accepted_by': row[4],
                        'closed_at': row[5],
                        'is_accepted': row[6],
                        'is_closed': row[7]
                    })
                
                return tickets
            except Exception as e:
                logging.error(f"Error getting active tickets: {e}")
                return []

    async def clean_invalid_tickets(self, valid_thread_ids: List[int]) -> None:
        """Clean up tickets for threads that no longer exist."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    DELETE FROM ticket_new_members 
                    WHERE thread_id NOT IN ({})
                '''.format(','.join('?' * len(valid_thread_ids))), valid_thread_ids)

                await db.execute('''
                    DELETE FROM tickets_new 
                    WHERE thread_id NOT IN ({})
                '''.format(','.join('?' * len(valid_thread_ids))), valid_thread_ids)

                await db.commit()
            except Exception as e:
                logging.error(f"Error cleaning invalid tickets: {e}")

    async def get_ticket_number(self, thread_id: int = None) -> int:
        """Get next ticket number based on highest existing ticket number."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                SELECT MAX(ticket_number) FROM tickets_new WHERE ticket_number IS NOT NULL
            ''')
            max_number = await cursor.fetchone()
            return (max_number[0] or 0) + 1

    async def fetch_ticket(self, thread_id: int) -> Optional[dict]:
        """Fetch ticket details by thread ID."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('''
                SELECT thread_id, ticket_number, message_id, creator_id, type_name, 
                       is_accepted, is_closed, ticket_channel_id
                FROM tickets_new 
                WHERE thread_id = ?
            ''', (thread_id,))
            record = await cursor.fetchone()

            if record:
                return {
                    'thread_id': record[0],
                    'ticket_number': record[1],
                    'message_id': record[2],
                    'creator_id': record[3],
                    'type_name': record[4],
                    'is_accepted': record[5],
                    'is_closed': record[6],
                    'ticket_channel_id': record[7]
                }
            return None

    async def get_ticket_history(self, thread_id: int) -> dict:
        """
        Get complete ticket history including all metadata and members.
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # Get basic ticket info
            await cursor.execute('''
                SELECT thread_id, ticket_number, message_id, creator_id, type_name, 
                       created_at, accepted_by, accepted_at, closed_by, 
                       closed_at, close_reason, ticket_channel_id
                FROM tickets_new 
                WHERE thread_id = ?
            ''', (thread_id,))
            ticket_data = await cursor.fetchone()

            if not ticket_data:
                return None

            # Get ticket members
            await cursor.execute('''
                SELECT user_id, added_by, added_at 
                FROM ticket_new_members 
                WHERE thread_id = ? 
                ORDER BY added_at ASC
            ''', (thread_id,))
            members = await cursor.fetchall()

            # Format the data
            ticket_history = {
                "thread_id": ticket_data[0],
                "ticket_number": ticket_data[1],
                "message_id": ticket_data[2],
                "creator_id": ticket_data[3],
                "type_name": ticket_data[4],
                "created_at": ticket_data[5],
                "accepted_by": ticket_data[6],
                "accepted_at": ticket_data[7],
                "closed_by": ticket_data[8],
                "closed_at": ticket_data[9],
                "close_reason": ticket_data[10],
                "ticket_channel_id": ticket_data[11],
                "members": [
                    {
                        "user_id": member[0],
                        "added_by": member[1],
                        "added_at": member[2]
                    }
                    for member in members
                ]
            }

            return ticket_history

    async def fix_null_ticket_numbers(self) -> int:
        """Fix tickets with NULL ticket_number by assigning sequential numbers."""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Get all tickets with NULL ticket_number ordered by created_at
                cursor = await db.execute('''
                    SELECT thread_id, created_at 
                    FROM tickets_new 
                    WHERE ticket_number IS NULL 
                    ORDER BY created_at ASC
                ''')
                null_tickets = await cursor.fetchall()
                
                if not null_tickets:
                    return 0
                
                # Get the highest existing ticket_number
                cursor = await db.execute('''
                    SELECT MAX(ticket_number) FROM tickets_new WHERE ticket_number IS NOT NULL
                ''')
                max_number = await cursor.fetchone()
                start_number = (max_number[0] or 0) + 1
                
                # Update each ticket with sequential number
                fixed_count = 0
                for i, (thread_id, created_at) in enumerate(null_tickets):
                    await db.execute('''
                        UPDATE tickets_new 
                        SET ticket_number = ? 
                        WHERE thread_id = ?
                    ''', (start_number + i, thread_id))
                    fixed_count += 1
                
                await db.commit()
                return fixed_count
            except Exception as e:
                logging.error(f"Error fixing null ticket numbers: {e}")
                return 0

    async def update_ticket_message_id(self, thread_id: int, message_id: int) -> bool:
        """Update the message ID for a ticket."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE tickets_new SET message_id = ? WHERE thread_id = ?",
                    (message_id, thread_id)
                )
                await db.commit()
                return True
        except Exception as e:
            logging.error(f"Error updating ticket message ID: {e}")
            return False