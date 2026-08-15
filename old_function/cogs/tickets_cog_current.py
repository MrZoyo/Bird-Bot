import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from typing import Tuple

import aiofiles
import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from bot.utils import config, check_channel_validity, TicketsDatabaseManager, MediaHandler
from bot.utils.file_utils import generate_file_tree


class TicketsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.main_config = config.get_config('main')
        # Archive function doesn't need tickets config, only main config
        self.db_path = self.main_config['db_path']
        self.guild_id = self.main_config['guild_id']
        self.guild = None
        self.db = TicketsDatabaseManager(self.db_path)

    async def cog_load(self):
        """Initialize the cog and database."""
        await self.db.initialize_database()

    async def check_ticket_channel(self, interaction):
        """Check if command is used in the ticket creation channel"""
        return await check_channel_validity(interaction)
    
    async def get_all_tickets_in_category(self, category_channel_ids):
        """Get ALL tickets (closed and active) in the specified category."""
        if not category_channel_ids:
            return []
        
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Create placeholders for the IN clause
                placeholders = ','.join('?' for _ in category_channel_ids)
                
                cursor = await db.execute(f'''
                    SELECT channel_id, message_id, creator_id, type_name, created_at, 
                           accepted_by, accepted_at, closed_by, closed_at, close_reason, is_closed
                    FROM tickets 
                    WHERE channel_id IN ({placeholders})
                    ORDER BY created_at DESC
                ''', category_channel_ids)
                rows = await cursor.fetchall()
                
                tickets = []
                for row in rows:
                    tickets.append({
                        'channel_id': row[0],
                        'message_id': row[1],
                        'creator_id': row[2],
                        'type_name': row[3],
                        'created_at': row[4],
                        'accepted_by': row[5],
                        'accepted_at': row[6],
                        'closed_by': row[7],
                        'closed_at': row[8],
                        'close_reason': row[9],
                        'is_closed': row[10]
                    })
                
                return tickets
                
            except Exception as e:
                logging.error(f"Error getting all tickets in category: {e}")
                return []

    @app_commands.command(
        name="tickets_archive",
        description="强制归档指定分类中的所有工单（包括活跃和已关闭的工单）"
    )
    @app_commands.describe(category="要归档的分类频道")
    async def archive_tickets(self, interaction: discord.Interaction, category: discord.CategoryChannel):
        """Archive ALL tickets to files."""
        await interaction.response.defer()

        try:
            # Use the provided category parameter
            
            # Get all channels in the specified category
            category_channel_ids = [channel.id for channel in category.channels if isinstance(channel, discord.TextChannel)]
            
            # Get ALL tickets in this category (closed and active)
            all_tickets = await self.get_all_tickets_in_category(category_channel_ids)
            
            if not all_tickets:
                await interaction.followup.send(
                    f"在分类 `{category.name}` 中没有找到工单需要归档。",
                    ephemeral=True
                )
                return

            # Create archive directory if it doesn't exist
            archive_dir = Path("./archives/tickets")
            archive_dir.mkdir(parents=True, exist_ok=True)
            
            archived_count = 0
            active_tickets_count = 0
            closed_tickets_count = 0
            total_files_downloaded = 0
            total_files_skipped = 0
            errors = []

            # Initialize media handler
            media_handler = MediaHandler(
                archive_path=str(archive_dir),
                size_limit=50 * 1024 * 1024  # 50MB limit
            )

            for ticket_data in all_tickets:
                try:
                    channel_id = ticket_data['channel_id']
                    ticket_number = ticket_data.get('ticket_number', channel_id)
                    type_name = ticket_data.get('type_name', 'unknown')
                    creator_id = ticket_data.get('creator_id')
                    
                    # Get channel
                    channel = self.bot.get_channel(channel_id)
                    if not channel:
                        errors.append(f"工单 #{ticket_number}: 频道不存在")
                        continue

                    # Create ticket-specific archive directory
                    ticket_dir_name = f"ticket_{channel_id}"
                    ticket_archive_dir = archive_dir / ticket_dir_name
                    ticket_archive_dir.mkdir(exist_ok=True)

                    # Create ticket data JSON
                    ticket_data_json = {
                        "ticket_number": ticket_number,
                        "type_name": type_name,
                        "creator_id": creator_id,
                        "channel_id": channel_id,
                        "archived_at": datetime.now().isoformat(),
                        "category": category.name,
                        "ticket_status": {
                            "is_closed": bool(ticket_data.get('is_closed', False)),
                            "created_at": ticket_data.get('created_at'),
                            "accepted_by": ticket_data.get('accepted_by'),
                            "accepted_at": ticket_data.get('accepted_at'),
                            "closed_by": ticket_data.get('closed_by'),
                            "closed_at": ticket_data.get('closed_at'),
                            "close_reason": ticket_data.get('close_reason')
                        },
                        "messages": [],
                        "members": [],
                        "attachments": []
                    }

                    # Get ticket messages and download attachments
                    try:
                        downloaded_files = []
                        skipped_files = []
                        
                        async for message in channel.history(limit=None, oldest_first=True):
                            message_data = {
                                "id": message.id,
                                "author": {
                                    "id": message.author.id,
                                    "name": message.author.display_name,
                                    "username": message.author.name
                                },
                                "content": message.content,
                                "timestamp": message.created_at.isoformat(),
                                "attachments": [],
                                "embeds": []
                            }
                            
                            # Handle attachments with file download
                            if message.attachments:
                                for attachment in message.attachments:
                                    attachment_data = {
                                        "filename": attachment.filename,
                                        "size": attachment.size,
                                        "url": attachment.url,
                                        "downloaded": False,
                                        "local_path": None
                                    }
                                    
                                    # Try to download file using MediaHandler
                                    download_result = await media_handler.download_media(
                                        attachment.url, 
                                        ticket_dir_name
                                    )
                                    
                                    if download_result and download_result.get('downloaded'):
                                        attachment_data["downloaded"] = True
                                        attachment_data["local_path"] = download_result["local_path"]
                                        downloaded_files.append(attachment.filename)
                                    else:
                                        skipped_files.append(attachment.filename)
                                    
                                    message_data["attachments"].append(attachment_data)
                            
                            # Handle embeds
                            if message.embeds:
                                for embed in message.embeds:
                                    embed_data = {
                                        "title": embed.title,
                                        "description": embed.description,
                                        "color": embed.color.value if embed.color else None,
                                        "timestamp": embed.timestamp.isoformat() if embed.timestamp else None,
                                        "fields": [{"name": field.name, "value": field.value, "inline": field.inline} for field in embed.fields]
                                    }
                                    if embed.image:
                                        embed_data["image"] = embed.image.url
                                    if embed.thumbnail:
                                        embed_data["thumbnail"] = embed.thumbnail.url
                                    message_data["embeds"].append(embed_data)
                            
                            ticket_data_json["messages"].append(message_data)
                        
                        # Update global counters
                        total_files_downloaded += len(downloaded_files)
                        total_files_skipped += len(skipped_files)
                        
                        ticket_data_json["attachments"] = {
                            "downloaded": downloaded_files,
                            "skipped": skipped_files,
                            "total_downloaded": len(downloaded_files),
                            "total_skipped": len(skipped_files)
                        }
                        
                    except Exception as e:
                        errors.append(f"工单 #{ticket_number}: 无法获取消息历史 - {str(e)}")

                    # Get ticket members
                    try:
                        members = await self.db.get_ticket_members(channel_id)
                        for member_id, added_by, added_at in members:
                            member = self.guild.get_member(member_id)
                            ticket_data_json["members"].append({
                                "id": member_id,
                                "name": member.display_name if member else f"未知用户 {member_id}",
                                "added_by": added_by,
                                "added_at": added_at
                            })
                    except Exception as e:
                        errors.append(f"工单 #{ticket_number}: 无法获取工单成员 - {str(e)}")

                    # Write ticket data JSON
                    ticket_data_path = ticket_archive_dir / "ticket_data.json"
                    async with aiofiles.open(ticket_data_path, 'w', encoding='utf-8') as f:
                        await f.write(json.dumps(ticket_data_json, indent=2, ensure_ascii=False))

                    archived_count += 1
                    
                    # Count ticket status
                    if ticket_data.get('is_closed'):
                        closed_tickets_count += 1
                    else:
                        active_tickets_count += 1
                    
                    logging.info(f"Archived ticket #{ticket_number} to {ticket_archive_dir}")

                except Exception as e:
                    errors.append(f"工单 #{ticket_data.get('ticket_number', 'unknown')}: {str(e)}")
                    logging.error(f"Error archiving ticket {ticket_data.get('channel_id')}: {e}")

            # Send result
            result_message = f"✅ 成功强制归档了分类 `{category.name}` 中的 {archived_count} 个工单到 `./archives/tickets/` 目录。"
            result_message += f"\n\n📊 工单统计:"
            result_message += f"\n  - 已关闭工单: {closed_tickets_count} 个"
            result_message += f"\n  - 活跃工单: {active_tickets_count} 个"
            
            # Add file statistics
            if total_files_downloaded > 0 or total_files_skipped > 0:
                result_message += f"\n\n📁 文件统计:"
                if total_files_downloaded > 0:
                    result_message += f"\n  - 已下载: {total_files_downloaded} 个文件"
                if total_files_skipped > 0:
                    result_message += f"\n  - 已跳过: {total_files_skipped} 个文件 (超过50MB限制)"
            
            if errors:
                result_message += f"\n\n⚠️ {len(errors)} 个工单归档失败:"
                for error in errors[:5]:  # Limit to first 5 errors
                    result_message += f"\n- {error}"
                if len(errors) > 5:
                    result_message += f"\n... 还有 {len(errors) - 5} 个错误"

            await interaction.followup.send(result_message, ephemeral=True)

        except Exception as e:
            logging.error(f"Error in archive_tickets: {e}")
            await interaction.followup.send(
                f"归档过程中发生错误: {str(e)}",
                ephemeral=True
            )

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize guild on bot ready."""
        self.guild = self.bot.get_guild(self.guild_id)
        if not self.guild:
            logging.error("Could not find configured guild")
            return

        logging.info("Ticket archive system initialized successfully")