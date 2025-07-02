# bot/cogs/teamup_display_cog.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
import re
from datetime import datetime, timedelta, timezone
import logging
from typing import Dict, List, Optional

from bot.utils import config
from bot.utils.channel_validator import check_channel_validity
from bot.utils.teamup_display_manager import TeamupDisplayManager


class TeamupDisplayCog(commands.Cog):
    """Teamup information display board functionality"""
    
    def __init__(self, bot):
        self.bot = bot
        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']
        self.db_manager = TeamupDisplayManager(self.db_path)
        
        self.conf = config.get_config('teamup_display')
        
        # Message configuration
        self.messages = self.conf['messages']
        
        # Display configuration
        self.display_config = self.conf['display']
        self.max_content_length = self.display_config['max_content_length']
        self.embed_color = self.display_config['embed_color']
        self.refresh_interval = self.display_config['refresh_interval_minutes']
        
        # Emoji configuration
        self.emojis = self.conf['emojis']
        
        # Start scheduled tasks
        self.refresh_displays.start()
    
    def cog_unload(self):
        """Stop scheduled tasks when unloading"""
        self.refresh_displays.cancel()
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize database when bot is ready"""
        await self.db_manager.init_tables()
        logging.info("TeamupDisplayCog is ready")
    
    @tasks.loop(minutes=2)
    async def refresh_displays(self):
        """Periodically refresh all display boards"""
        try:
            # Clean up expired invitations
            cleaned_count = await self.db_manager.cleanup_expired_invitations()
            if cleaned_count > 0:
                logging.info(f"Cleaned up {cleaned_count} expired teamup invitations")
            
            # Get all display boards and refresh them
            display_boards = await self.db_manager.get_all_display_boards()
            for channel_id, message_id in display_boards:
                await self.update_display_board(channel_id, message_id)
                
        except Exception as e:
            logging.error(f"Failed to refresh display boards: {e}")
    
    @refresh_displays.before_loop
    async def before_refresh(self):
        """Wait for bot to be ready before starting scheduled tasks"""
        await self.bot.wait_until_ready()
    
    def format_time_ago(self, created_at: str) -> str:
        """Format time using Discord's relative time display"""
        try:
            # Parse time string from database and convert to datetime object
            created_time = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
            # Use Discord's relative time formatting
            return discord.utils.format_dt(created_time, style='R')
        except Exception:
            return self.messages['time_just_now']
    
    async def create_display_embed(self) -> discord.Embed:
        """Create display board embed"""
        embed = discord.Embed(
            title=self.messages['display_title'],
            color=self.embed_color
        )
        
        # Get active teamup invitations
        invitations = await self.db_manager.get_active_invitations()
        
        if not invitations:
            embed.description = self.messages['no_teamup_message']
        else:
            # Get game type configurations
            game_types = await self.db_manager.get_all_game_types()
            
            # Group invitations by game type
            grouped_invitations = {}
            general_invitations = []
            
            for invitation in invitations:
                game_type = invitation.get('game_type')
                if game_type and game_type in game_types.values():
                    if game_type not in grouped_invitations:
                        grouped_invitations[game_type] = []
                    grouped_invitations[game_type].append(invitation)
                else:
                    general_invitations.append(invitation)
            
            # Build embed content
            embed_content = []
            
            # Display game types in configured order
            for channel_id, game_type in game_types.items():
                if game_type in grouped_invitations:
                    embed_content.append(f"\n**{game_type}**")
                    for i, invitation in enumerate(grouped_invitations[game_type]):
                        line = await self.format_invitation_line(invitation)
                        embed_content.append(line)
                        # Add space between invitations of the same type (but not after the last one)
                        if i < len(grouped_invitations[game_type]) - 1:
                            embed_content.append("")
            
            # Add general teamup section
            if general_invitations:
                embed_content.append(f"\n**{self.messages['general_teamup_title']}**")
                for i, invitation in enumerate(general_invitations):
                    line = await self.format_invitation_line(invitation)
                    embed_content.append(line)
                    # Add space between invitations of the same type (but not after the last one)
                    if i < len(general_invitations) - 1:
                        embed_content.append("")
            
            if embed_content:
                embed.description = "\n".join(embed_content)
            else:
                embed.description = self.messages['no_teamup_message']
        
        # Add footer with bot avatar
        if self.bot.user.avatar:
            embed.set_footer(text=self.messages['footer_text'], icon_url=self.bot.user.avatar.url)
        else:
            embed.set_footer(text=self.messages['footer_text'])
        
        return embed
    
    async def format_invitation_line(self, invitation: Dict) -> str:
        """Format single invitation information line"""
        # Truncate message content
        content = invitation['message_content']
        if len(content) > self.max_content_length:
            content = content[:self.max_content_length-3] + "..."
        
        # Get voice channel
        voice_channel = self.bot.get_channel(invitation['voice_channel_id'])
        if not voice_channel:
            return ""
        
        # Get user
        user = self.bot.get_user(invitation['user_id'])
        username = user.display_name if user else self.messages['unknown_user']
        
        # Format time
        time_ago = self.format_time_ago(invitation['created_at'])
        
        # Create channel link
        guild_id = voice_channel.guild.id
        channel_link = f"https://discord.com/channels/{guild_id}/{invitation['voice_channel_id']}"
        
        # Format invitation lines using config templates
        line1 = self.messages['invitation_format']['line1'].format(
            search_emoji=self.emojis['search'],
            content=content
        )
        line2 = self.messages['invitation_format']['line2'].format(
            players_emoji=self.emojis['players'],
            room_count_prefix=self.messages['room_count_prefix'],
            player_count=invitation['player_count'],
            players_suffix=self.messages['players_suffix'],
            time_emoji=self.emojis['time'],
            time_ago=time_ago
        )
        line3 = self.messages['invitation_format']['line3'].format(
            link_emoji=self.emojis['link'],
            channel_link=channel_link
        )
        
        return f"{line1}\n{line2}\n{line3}"
    
    async def update_display_board(self, channel_id: int, message_id: int):
        """Update specified display board"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                logging.warning(f"Display board channel not found: {channel_id}")
                return
            
            try:
                message = await channel.fetch_message(message_id)
                embed = await self.create_display_embed()
                await message.edit(embed=embed)
            except discord.NotFound:
                logging.warning(f"Display board message not found: {message_id}")
                # Clean up invalid records in database
                await self.db_manager.remove_display_board(channel_id)
            except discord.Forbidden:
                logging.warning(f"No permission to edit display board message: {message_id}")
            
        except Exception as e:
            logging.error(f"Failed to update display board: {e}")
    
    async def add_teamup_to_display(self, user_id: int, channel_id: int, voice_channel_id: int, 
                                   message_content: str):
        """Add teamup information to display board"""
        try:
            # Get game type
            game_type = await self.db_manager.get_game_type_by_channel(channel_id)
            
            # Get actual player count from voice channel
            voice_channel = self.bot.get_channel(voice_channel_id)
            player_count = len(voice_channel.members) if voice_channel else 1
            
            # Add to database
            success = await self.db_manager.add_teamup_invitation(
                user_id, channel_id, voice_channel_id, message_content, player_count, game_type
            )
            
            if success:
                # Refresh all display boards
                display_boards = await self.db_manager.get_all_display_boards()
                for board_channel_id, message_id in display_boards:
                    await self.update_display_board(board_channel_id, message_id)
            
        except Exception as e:
            logging.error(f"Failed to add teamup information to display board: {e}")
    
    async def remove_teamup_from_display(self, user_id: int, voice_channel_id: int):
        """Remove teamup information from display board"""
        try:
            success = await self.db_manager.remove_teamup_invitation(user_id, voice_channel_id)
            
            if success:
                # Refresh all display boards
                display_boards = await self.db_manager.get_all_display_boards()
                for board_channel_id, message_id in display_boards:
                    await self.update_display_board(board_channel_id, message_id)
            
        except Exception as e:
            logging.error(f"Failed to remove teamup information from display board: {e}")
    
    
    @app_commands.command(
        name="teamup_init",
        description="Create teamup display board in specified channel"
    )
    @app_commands.describe(channel_id="Channel ID where to create the display board")
    async def teamup_init(self, interaction: discord.Interaction, channel_id: str):
        """Initialize teamup display board"""
        if not await check_channel_validity(interaction):
            return
        
        await interaction.response.defer()
        
        try:
            channel_id = int(channel_id)
            channel = self.bot.get_channel(channel_id)
            
            if not channel:
                await interaction.followup.send(self.messages['channel_not_found'], ephemeral=True)
                return
            
            # Check permissions
            if not channel.permissions_for(interaction.guild.me).send_messages:
                await interaction.followup.send(self.messages['permission_error'], ephemeral=True)
                return
            
            # Create display board embed
            embed = await self.create_display_embed()
            
            # Send message
            message = await channel.send(embed=embed)
            
            # Save to database
            success = await self.db_manager.save_display_board(channel_id, message.id)
            
            if success:
                await interaction.followup.send(
                    f"{self.messages['init_success']}\n"
                    f"{self.messages['board_created_in']} {channel.mention}"
                )
            else:
                await interaction.followup.send(self.messages['init_error'], ephemeral=True)
            
        except ValueError:
            await interaction.followup.send(self.messages['invalid_channel'], ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to create display board: {e}")
            await interaction.followup.send(self.messages['init_error'], ephemeral=True)
    
    @app_commands.command(
        name="teamup_type_add",
        description="Add game type with corresponding channel"
    )
    @app_commands.describe(
        channel_id="Channel ID for sending teamup messages",
        game_type="Game type name"
    )
    async def teamup_type_add(self, interaction: discord.Interaction, channel_id: str, game_type: str):
        """Add game type configuration"""
        if not await check_channel_validity(interaction):
            return
        
        await interaction.response.defer()
        
        try:
            channel_id = int(channel_id)
            channel = self.bot.get_channel(channel_id)
            
            if not channel:
                await interaction.followup.send(self.messages['channel_not_found'], ephemeral=True)
                return
            
            success = await self.db_manager.add_game_type(channel_id, game_type)
            
            if success:
                embed = await self.create_game_types_embed()
                embed.title = self.messages['type_add_success']
                embed.description = self.messages['channel_set_as_type'].format(
                    channel_mention=channel.mention, game_type=game_type
                ) + "\n\n" + (embed.description or "")
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(self.messages['type_add_error'], ephemeral=True)
            
        except ValueError:
            await interaction.followup.send(self.messages['invalid_channel'], ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to add game type: {e}")
            await interaction.followup.send(self.messages['type_add_error'], ephemeral=True)
    
    @app_commands.command(
        name="teamup_type_delete",
        description="Delete game type configuration"
    )
    @app_commands.describe(channel_id="Channel ID to delete configuration for")
    async def teamup_type_delete(self, interaction: discord.Interaction, channel_id: str):
        """Delete game type configuration"""
        if not await check_channel_validity(interaction):
            return
        
        await interaction.response.defer()
        
        try:
            channel_id = int(channel_id)
            success = await self.db_manager.remove_game_type(channel_id)
            
            if success:
                embed = await self.create_game_types_embed()
                embed.title = self.messages['type_delete_success']
                embed.description = self.messages['channel_type_deleted'].format(
                    channel_id=channel_id
                ) + "\n\n" + (embed.description or "")
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send(self.messages['type_delete_error'], ephemeral=True)
            
        except ValueError:
            await interaction.followup.send(self.messages['invalid_channel'], ephemeral=True)
        except Exception as e:
            logging.error(f"Failed to delete game type: {e}")
            await interaction.followup.send(self.messages['type_delete_error'], ephemeral=True)
    
    @app_commands.command(
        name="teamup_type_list",
        description="View all game type configurations"
    )
    async def teamup_type_list(self, interaction: discord.Interaction):
        """List all game type configurations"""
        if not await check_channel_validity(interaction):
            return
        
        await interaction.response.defer()
        embed = await self.create_game_types_embed()
        await interaction.followup.send(embed=embed)
    
    async def create_game_types_embed(self) -> discord.Embed:
        """Create game type configuration display embed"""
        embed = discord.Embed(
            title=self.messages['type_list_title'],
            color=self.embed_color
        )
        
        game_types = await self.db_manager.get_all_game_types()
        
        if not game_types:
            embed.description = self.messages['type_list_empty']
            return embed
        
        type_list = []
        for channel_id, game_type in game_types.items():
            channel = self.bot.get_channel(channel_id)
            if channel:
                type_list.append(f"• **{game_type}** - {channel.mention}")
            else:
                type_list.append(f"• **{game_type}** - <#{channel_id}> {self.messages['channel_not_exist']}")
        
        embed.description = "\n".join(type_list)
        return embed


async def setup(bot):
    await bot.add_cog(TeamupDisplayCog(bot))