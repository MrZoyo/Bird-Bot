from discord.ext import commands
import asyncio
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

from bot.utils import config, check_channel_validity, TicketsNewDatabaseManager, MediaHandler
from bot.utils.config import Config


class EmbedColors:
    """Color constants for different ticket actions"""
    CREATE = discord.Color.blue()
    ACCEPT = discord.Color.green()
    CLOSE = discord.Color.red()
    ADD_TYPE = discord.Color.purple()
    EDIT_TYPE = discord.Color.gold()
    DELETE_TYPE = discord.Color.orange()
    ADD_USER = discord.Color.teal()
    DEFAULT = discord.Color.blurple()


class TicketCreateView(discord.ui.View):
    def __init__(self, cog, ticket_types):
        super().__init__(timeout=None)
        self.cog = cog
        self.ticket_types = ticket_types
        self.messages = cog.conf['messages']
        
        # Create buttons for each ticket type
        for type_name, type_data in ticket_types.items():
            color_map = {
                'r': discord.ButtonStyle.danger,
                'g': discord.ButtonStyle.success,
                'b': discord.ButtonStyle.primary,
                'grey': discord.ButtonStyle.secondary
            }
            
            button_style = color_map.get(type_data.get('button_color', 'b'), discord.ButtonStyle.primary)
            
            button = discord.ui.Button(
                style=button_style,
                label=type_name,
                custom_id=f'create_ticket_{type_name}'
            )
            
            # Create callback function
            async def button_callback(interaction, type_name=type_name):
                await self.create_ticket_callback(interaction, type_name)
            
            button.callback = button_callback
            self.add_item(button)

    async def create_ticket_callback(self, interaction: discord.Interaction, type_name: str):
        """Handle ticket creation button click"""
        try:
            user_id = interaction.user.id
            type_data = self.ticket_types[type_name]
            
            # Show confirmation modal
            modal = TicketConfirmModal(self.cog, type_name, type_data)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            logging.error(f"Error in create_ticket_callback: {e}")
            await interaction.response.send_message(
                self.messages['ticket_thread_create_error'], 
                ephemeral=True
            )


class TicketConfirmModal(discord.ui.Modal):
    def __init__(self, cog, type_name: str, type_data: dict):
        super().__init__(title=cog.conf['messages']['ticket_modal_confirm_title'].format(type_name=type_name))
        self.cog = cog
        self.type_name = type_name
        self.type_data = type_data
        self.messages = cog.conf['messages']
        
        self.confirm_input = discord.ui.TextInput(
            label=self.messages['ticket_modal_confirm_label'].format(type_name=type_name),
            placeholder=self.messages['ticket_modal_confirm_placeholder'],
            max_length=10,
            required=True
        )
        self.add_item(self.confirm_input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirm_input.value.lower() != "yes":
            await interaction.response.send_message(
                self.messages['ticket_confirmation_failed'], 
                ephemeral=True
            )
            return
        
        # Acknowledge the interaction immediately to prevent timeout
        await interaction.response.defer(ephemeral=True)
        
        # Create the ticket thread
        await self.cog.create_ticket_thread(interaction, self.type_name, self.type_data)


class TicketThreadView(discord.ui.View):
    def __init__(self, cog, thread_id: int, type_name: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.thread_id = thread_id
        self.type_name = type_name
        self.messages = cog.conf['messages']
        
        # Accept button
        accept_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label=self.messages['ticket_accept_button'],
            custom_id=f'accept_ticket_{thread_id}'
        )
        accept_button.callback = self.accept_callback
        self.add_item(accept_button)
        
        # Add user button
        add_user_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=self.messages['ticket_add_user_button'],
            custom_id=f'add_user_{thread_id}'
        )
        add_user_button.callback = self.add_user_callback
        self.add_item(add_user_button)
        
        # Close button
        close_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label=self.messages['ticket_close_button'],
            custom_id=f'close_ticket_{thread_id}'
        )
        close_button.callback = self.close_callback
        self.add_item(close_button)

    async def accept_callback(self, interaction: discord.Interaction):
        """Handle ticket acceptance"""
        try:
            if not await self.cog.is_admin_for_type(interaction.user, self.type_name):
                await interaction.response.send_message(
                    self.messages['ticket_admin_only'], 
                    ephemeral=True
                )
                return
            
            success = await self.cog.db_manager.accept_ticket(self.thread_id, interaction.user.id)
            if not success:
                await interaction.response.send_message(
                    self.messages['ticket_already_accepted'], 
                    ephemeral=True
                )
                return
            
            # Create accepted embed
            embed = discord.Embed(
                title=self.messages['ticket_accepted_title'],
                description=self.messages['ticket_accepted_content'].format(user=interaction.user.mention),
                color=EmbedColors.ACCEPT
            )
            
            # Update view to disable accept button
            new_view = TicketThreadView(self.cog, self.thread_id, self.type_name)
            new_view.children[0].disabled = True
            new_view.children[0].label = self.messages['ticket_accept_button_disabled']
            new_view.children[0].style = discord.ButtonStyle.success
            
            # Register the updated view for persistence
            self.cog.bot.add_view(new_view)
            
            await interaction.response.edit_message(view=new_view)
            await interaction.followup.send(embed=embed)
            
            # Log to info channel
            await self.cog.log_ticket_action('accept', self.thread_id, interaction.user)
            
            # Send DM to creator
            ticket_data = await self.cog.db_manager.fetch_ticket(self.thread_id)
            if ticket_data:
                creator = interaction.guild.get_member(ticket_data['creator_id'])
                if creator:
                    try:
                        dm_embed = discord.Embed(
                            title=self.messages['ticket_accepted_dm_title'],
                            description=self.messages['ticket_accepted_dm_content'].format(user=interaction.user.mention),
                            color=EmbedColors.ACCEPT
                        )
                        
                        # Create jump button view
                        dm_view = discord.ui.View()
                        jump_button = discord.ui.Button(
                            style=discord.ButtonStyle.link,
                            label=self.messages['ticket_jump_button'],
                            url=f"https://discord.com/channels/{interaction.guild.id}/{self.thread_id}"
                        )
                        dm_view.add_item(jump_button)
                        
                        await creator.send(embed=dm_embed, view=dm_view)
                    except:
                        pass  # DM failed, continue
                        
        except Exception as e:
            logging.error(f"Error in accept_callback: {e}")
            await interaction.response.send_message(
                self.messages['ticket_accept_get_info_error'], 
                ephemeral=True
            )

    async def add_user_callback(self, interaction: discord.Interaction):
        """Handle add user button"""
        modal = AddUserModal(self.cog, self.thread_id)
        await interaction.response.send_modal(modal)

    async def close_callback(self, interaction: discord.Interaction):
        """Handle close ticket button"""
        modal = CloseTicketModal(self.cog, self.thread_id)
        await interaction.response.send_modal(modal)


class AddUserModal(discord.ui.Modal):
    def __init__(self, cog, thread_id: int):
        super().__init__(title=cog.conf['messages']['add_user_modal_title'])
        self.cog = cog
        self.thread_id = thread_id
        self.messages = cog.conf['messages']
        
        self.user_input = discord.ui.TextInput(
            label=self.messages['add_user_modal_label'],
            placeholder=self.messages['add_user_modal_placeholder'],
            max_length=20,
            required=True
        )
        self.add_item(self.user_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_input.value)
            user = interaction.guild.get_member(user_id)
            
            if not user:
                await interaction.response.send_message(
                    self.messages['add_user_not_found'], 
                    ephemeral=True
                )
                return
            
            # Check if ticket is closed
            _, is_closed = await self.cog.db_manager.check_ticket_status(self.thread_id)
            if is_closed:
                await interaction.response.send_message(
                    self.messages['ticket_closed_no_modify'], 
                    ephemeral=True
                )
                return
            
            # Add user to database
            success = await self.cog.db_manager.add_ticket_member(
                self.thread_id, user_id, interaction.user.id
            )
            
            if not success:
                await interaction.response.send_message(
                    self.messages['add_user_already_added'], 
                    ephemeral=True
                )
                return
            
            # Add user to thread
            thread = interaction.guild.get_thread(self.thread_id)
            if thread:
                await thread.add_user(user)
            
            # Create success embed
            embed = discord.Embed(
                title=self.messages['add_user_success_title'],
                description=self.messages['add_user_success_content'].format(
                    user=user.mention, 
                    adder=interaction.user.mention
                ),
                color=EmbedColors.ADD_USER
            )
            
            await interaction.response.send_message(embed=embed)
            
            # Log action
            await self.cog.log_ticket_action('add_user', self.thread_id, interaction.user, extra_user=user)
            
            # Send DM to added user with jump button
            try:
                dm_embed = discord.Embed(
                    title=self.messages['add_user_dm_title'],
                    description=self.messages['add_user_dm_content'].format(thread=thread.mention if thread else f"<#{self.thread_id}>"),
                    color=EmbedColors.ADD_USER
                )
                
                # Create jump button view
                dm_view = discord.ui.View()
                jump_button = discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    label=self.messages['ticket_jump_button'],
                    url=f"https://discord.com/channels/{thread.guild.id}/{thread.id}" if thread else f"https://discord.com/channels/{interaction.guild.id}/{self.thread_id}"
                )
                dm_view.add_item(jump_button)
                
                await user.send(embed=dm_embed, view=dm_view)
            except:
                pass  # DM failed
                
        except ValueError:
            await interaction.response.send_message(
                self.messages['add_user_invalid_id'], 
                ephemeral=True
            )
        except Exception as e:
            logging.error(f"Error in AddUserModal: {e}")
            await interaction.response.send_message(
                self.messages['add_user_error'].format(error=str(e)), 
                ephemeral=True
            )


class CloseTicketModal(discord.ui.Modal):
    def __init__(self, cog, thread_id: int):
        super().__init__(title=cog.conf['messages']['close_modal_title'])
        self.cog = cog
        self.thread_id = thread_id
        self.messages = cog.conf['messages']
        
        self.reason_input = discord.ui.TextInput(
            label=self.messages['close_modal_label'],
            placeholder=self.messages['close_modal_placeholder'],
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=True
        )
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            reason = self.reason_input.value
            
            # Check if thread is already archived
            thread = interaction.guild.get_thread(self.thread_id)
            if thread and thread.archived:
                await interaction.response.send_message(
                    self.messages['ticket_already_closed'],
                    ephemeral=True
                )
                return
            
            # Close in database first
            success = await self.cog.db_manager.close_ticket(
                self.thread_id, interaction.user.id, reason
            )
            
            if not success:
                await interaction.response.send_message(
                    self.messages['ticket_close_stats_error'], 
                    ephemeral=True
                )
                return
            
            # Create close embed (for in-thread display)
            embed = discord.Embed(
                title=self.messages['close_dm_title'],
                description=self.messages['close_dm_content'].format(
                    closer=interaction.user.mention,
                    reason=reason
                ),
                color=EmbedColors.CLOSE
            )
            
            # Respond to interaction first
            await interaction.response.send_message(embed=embed)
            
            # Update the original ticket message to disable all buttons
            try:
                # Find the ticket control message
                ticket_data = await self.cog.db_manager.fetch_ticket(self.thread_id)
                if ticket_data and ticket_data.get('message_id'):
                    try:
                        control_message = await thread.fetch_message(ticket_data['message_id'])
                        
                        # Create disabled view
                        disabled_view = TicketThreadView(self.cog, self.thread_id, "")
                        for child in disabled_view.children:
                            child.disabled = True
                        
                        await control_message.edit(view=disabled_view)
                    except discord.NotFound:
                        pass  # Message was deleted
            except Exception as e:
                logging.error(f"Error disabling buttons after close: {e}")
            
            # Log action
            await self.cog.log_ticket_action('close', self.thread_id, interaction.user, reason=reason)
            
            # Lock and archive the thread after responding
            if thread:
                try:
                    await thread.edit(locked=True, archived=True)
                except discord.HTTPException as e:
                    logging.warning(f"Could not archive thread {self.thread_id}: {e}")
            
            # Send DM to creator
            ticket_data = await self.cog.db_manager.fetch_ticket(self.thread_id)
            if ticket_data:
                creator = interaction.guild.get_member(ticket_data['creator_id'])
                if creator:
                    try:
                        dm_embed = discord.Embed(
                            title=self.messages['close_dm_title'],
                            description=self.messages['close_dm_content'].format(
                                closer=interaction.user.mention,
                                reason=reason
                            ),
                            color=EmbedColors.CLOSE
                        )
                        
                        # Create jump button view
                        dm_view = discord.ui.View()
                        jump_button = discord.ui.Button(
                            style=discord.ButtonStyle.link,
                            label=self.messages['ticket_jump_button'],
                            url=f"https://discord.com/channels/{interaction.guild.id}/{self.thread_id}"
                        )
                        dm_view.add_item(jump_button)
                        
                        await creator.send(embed=dm_embed, view=dm_view)
                    except:
                        pass  # DM failed
                        
        except Exception as e:
            logging.error(f"Error in CloseTicketModal: {e}")
            # Try to respond if we haven't already
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        self.messages['ticket_close_error'], 
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        self.messages['ticket_close_error'], 
                        ephemeral=True
                    )
            except:
                pass  # Give up if both fail


class TicketsNewCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config()
        self.conf = self.config.get_config('tickets_new')
        self.main_conf = self.config.get_config('main')
        self.db_manager = TicketsNewDatabaseManager(self.main_conf['db_path'])
        
    async def cog_load(self):
        """Initialize the cog"""
        await self.db_manager.initialize_database()
        
        # Fix any tickets with NULL ticket_number
        fixed_count = await self.db_manager.fix_null_ticket_numbers()
        if fixed_count > 0:
            logging.info(f"Fixed {fixed_count} tickets with NULL ticket_number")
        
        logging.info("TicketsNewCog loaded successfully")

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize views on bot ready"""
        try:
            # Get config data from database
            config_data = await self.db_manager.get_config()
            if not config_data:
                logging.warning("TicketsNewCog: No config data found in database")
                return

            ticket_channel_id = config_data.get('ticket_channel_id')
            main_message_id = config_data.get('main_message_id')
            
            if not ticket_channel_id or not main_message_id:
                logging.warning("TicketsNewCog: Missing channel or message ID in config")
                return

            # Get the ticket channel and message
            ticket_channel = self.bot.get_channel(ticket_channel_id)
            if not ticket_channel:
                logging.error(f"TicketsNewCog: Could not find ticket channel {ticket_channel_id}")
                return

            try:
                main_message = await ticket_channel.fetch_message(main_message_id)
                
                # Create and register persistent view for main message
                ticket_types = self.conf.get('ticket_types', {})
                if ticket_types:
                    main_view = TicketCreateView(self, ticket_types)
                    self.bot.add_view(main_view)
                    
                    # Update the main message with current ticket types
                    await self.update_main_message(ticket_channel, main_message, ticket_types)
                    
                    logging.info(f"TicketsNewCog: Restored main ticket message with {len(ticket_types)} ticket types")
                
            except discord.NotFound:
                logging.warning(f"TicketsNewCog: Main message {main_message_id} not found")
            except Exception as e:
                logging.error(f"TicketsNewCog: Error updating main message: {e}")

            # Restore active ticket thread views and update button states
            active_tickets = await self.db_manager.get_active_tickets()
            restored_count = 0
            updated_count = 0
            
            # Process tickets in batches to avoid rate limits
            import asyncio
            batch_size = 3  # Smaller batch size for startup
            delay_between_batches = 1.5  # seconds
            
            logging.info(f"TicketsNewCog: Starting to restore {len(active_tickets)} ticket views with button updates...")
            
            for i in range(0, len(active_tickets), batch_size):
                batch = active_tickets[i:i + batch_size]
                
                for ticket_data in batch:
                    thread_id = ticket_data['thread_id']
                    type_name = ticket_data['type_name']
                    is_accepted = ticket_data.get('accepted_by') is not None
                    is_closed = ticket_data.get('is_closed', False)
                    
                    try:
                        thread = self.bot.get_channel(thread_id)
                        if thread and not thread.archived:  # Only process non-archived threads
                            # Create persistent view for ticket control buttons with correct state
                            ticket_view = TicketThreadView(self, thread_id, type_name)
                            
                            # Update button states based on ticket status
                            if is_accepted:
                                ticket_view.children[0].disabled = True  # Accept button
                                ticket_view.children[0].label = self.conf['messages']['ticket_accept_button_disabled']
                                ticket_view.children[0].style = discord.ButtonStyle.success
                            
                            if is_closed:
                                # Disable all buttons for closed tickets
                                for child in ticket_view.children:
                                    child.disabled = True
                            
                            self.bot.add_view(ticket_view)
                            restored_count += 1
                            
                            # Update the ticket message with correct button states
                            try:
                                await self.update_ticket_message_buttons(thread, ticket_data, ticket_view)
                                updated_count += 1
                            except Exception as e:
                                logging.warning(f"TicketsNewCog: Could not update buttons for ticket {thread_id}: {e}")
                            
                    except Exception as e:
                        logging.error(f"TicketsNewCog: Error restoring ticket {thread_id}: {e}")
                
                # Add delay between batches to avoid rate limits
                if i + batch_size < len(active_tickets):
                    await asyncio.sleep(delay_between_batches)
                    # Log progress for large numbers of tickets
                    if len(active_tickets) > 10:
                        progress = min(i + batch_size, len(active_tickets))
                        logging.info(f"TicketsNewCog: Processed {progress}/{len(active_tickets)} tickets...")
            
            if restored_count > 0:
                logging.info(f"TicketsNewCog: Restored {restored_count} active ticket thread views")
                logging.info(f"TicketsNewCog: Updated {updated_count} ticket message buttons")
                if updated_count < restored_count:
                    logging.info("TicketsNewCog: Some button updates failed - use /tickets_refresh_buttons if needed")
                
        except Exception as e:
            logging.error(f"TicketsNewCog on_ready error: {e}")

    async def update_main_message(self, channel, message, ticket_types):
        """Update the main ticket message with current types"""
        try:
            embed = discord.Embed(
                title=self.conf['messages']['ticket_main_title'],
                description=self.conf['messages']['ticket_main_description'],
                color=EmbedColors.CREATE
            )
            
            # Add bot avatar as thumbnail if available
            if self.bot.user.avatar:
                embed.set_thumbnail(url=self.bot.user.avatar.url)
            
            # Add fields for each ticket type
            for type_name, type_data in ticket_types.items():
                embed.add_field(
                    name=type_name,
                    value=type_data.get('description', '无描述'),
                    inline=False
                )
            
            embed.set_footer(text=self.conf['messages']['ticket_main_footer'])
            
            # Create new view with current ticket types
            view = TicketCreateView(self, ticket_types)
            await message.edit(embed=embed, view=view)
            
        except Exception as e:
            logging.error(f"Error updating main message: {e}")

    async def update_ticket_message_buttons(self, thread: discord.Thread, ticket_data: dict, view: discord.ui.View):
        """Update ticket message buttons based on current status"""
        try:
            message_id = ticket_data.get('message_id')
            if not message_id:
                return
            
            try:
                message = await thread.fetch_message(message_id)
                await message.edit(view=view)
            except discord.NotFound:
                logging.warning(f"Ticket message {message_id} not found in thread {thread.id}")
            except discord.HTTPException as e:
                logging.warning(f"Could not update ticket message {message_id}: {e}")
                
        except Exception as e:
            logging.error(f"Error updating ticket message buttons: {e}")

    async def is_admin_for_type(self, user: discord.Member, ticket_type: str = None) -> bool:
        """Check if user is admin for specific ticket type or globally"""
        # Check global admin roles
        for role_id in self.conf.get('admin_roles', []):
            if user.get_role(role_id):
                return True
        
        # Check global admin users
        if user.id in self.conf.get('admin_users', []):
            return True
        
        # Check type-specific admins if ticket_type provided
        if ticket_type and ticket_type in self.conf.get('ticket_types', {}):
            type_data = self.conf['ticket_types'][ticket_type]
            
            # Type-specific admin roles
            for role_id in type_data.get('admin_roles', []):
                if user.get_role(role_id):
                    return True
            
            # Type-specific admin users
            if user.id in type_data.get('admin_users', []):
                return True
        
        # Check Discord permissions
        return user.guild_permissions.manage_channels
    
    async def create_ticket_thread(self, interaction: discord.Interaction, type_name: str, type_data: dict):
        """Create a new ticket thread"""
        try:
            # Get ticket channel from config
            config_data = await self.db_manager.get_config()
            if not config_data or not config_data['ticket_channel_id']:
                await interaction.followup.send(
                    self.conf['messages']['old_system_no_new_channel'], 
                    ephemeral=True
                )
                return
            
            ticket_channel = interaction.guild.get_channel(config_data['ticket_channel_id'])
            if not ticket_channel:
                await interaction.followup.send(
                    self.conf['messages']['ticket_thread_not_found'], 
                    ephemeral=True
                )
                return
            
            # Generate ticket number
            ticket_number = await self.db_manager.get_ticket_number()
            thread_name = f"ticket-{ticket_number}"
            
            # Create thread
            message_content = f"**{self.conf['messages']['ticket_created_title'].format(number=ticket_number, type_name=type_name)}**\n\n{type_data['guide']}"
            
            # Send initial message to create thread from (will be deleted for privacy)
            initial_message = await ticket_channel.send(self.conf['messages'].get('ticket_creating', '创建工单中...'))
            
            # Create thread from message
            thread = await initial_message.create_thread(
                name=thread_name,
                auto_archive_duration=4320  # 3 days
            )
            
            # Delete the initial message for privacy (keep only the thread)
            try:
                await initial_message.delete()
            except discord.NotFound:
                pass  # Message already deleted
            
            # Add creator to thread
            await thread.add_user(interaction.user)
            
            # Create ticket in database (will update message ID later)
            success = await self.db_manager.create_ticket(
                thread.id, 0, interaction.user.id,  # Use 0 as temporary message ID
                type_name, ticket_channel.id, ticket_number
            )
            
            if not success:
                await thread.delete()
                await interaction.followup.send(
                    self.conf['messages']['ticket_create_db_error'], 
                    ephemeral=True
                )
                return
            
            # Create ticket embed
            embed = discord.Embed(
                title=self.conf['messages']['ticket_created_title'].format(
                    number=ticket_number, 
                    type_name=type_name
                ),
                description=type_data['guide'],
                color=EmbedColors.CREATE
            )
            
            embed.add_field(
                name=self.conf['messages']['ticket_created_creator'],
                value=interaction.user.mention,
                inline=True
            )
            
            embed.add_field(
                name=self.conf['messages']['ticket_created_time'],
                value=f"<t:{int(datetime.now().timestamp())}:F>",
                inline=True
            )
            
            # Instructions embed
            instructions_embed = discord.Embed(
                title=self.conf['messages']['ticket_instructions_title'],
                description=self.conf['messages']['ticket_instructions'],
                color=EmbedColors.DEFAULT
            )
            
            # Create view with buttons
            view = TicketThreadView(self, thread.id, type_name)
            
            # Register the view immediately for persistence
            self.bot.add_view(view)
            
            # Send the ticket information message in the thread
            ticket_message = await thread.send(
                embeds=[embed, instructions_embed], 
                view=view
            )
            
            # Update database with the actual ticket message ID
            await self.db_manager.update_ticket_message_id(thread.id, ticket_message.id)
            
            # Respond to interaction immediately
            await interaction.followup.send(
                self.conf['messages']['ticket_create_success'].format(thread=thread.mention),
                ephemeral=True
            )
            
            # Add admins to thread and send notifications (can be done after response)
            await self.add_admins_to_ticket(thread, type_name, interaction.user, ticket_number)
            
            # Log ticket creation
            await self.log_ticket_action('create', thread.id, interaction.user, type_name=type_name, ticket_number=ticket_number)
            
            # Send DM to creator with jump button
            try:
                dm_embed = discord.Embed(
                    title=self.conf['messages']['ticket_created_dm_title'],
                    description=self.conf['messages']['ticket_created_dm_content'].format(
                        number=ticket_number,
                        type_name=type_name
                    ),
                    color=EmbedColors.CREATE
                )
                
                # Create jump button view
                dm_view = discord.ui.View()
                jump_button = discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    label=self.conf['messages']['ticket_jump_button'],
                    url=f"https://discord.com/channels/{thread.guild.id}/{thread.id}"
                )
                dm_view.add_item(jump_button)
                
                await interaction.user.send(embed=dm_embed, view=dm_view)
            except:
                pass  # DM failed
                
        except Exception as e:
            logging.error(f"Error creating ticket thread: {e}")
            try:
                await interaction.followup.send(
                    self.conf['messages']['ticket_thread_create_error'], 
                    ephemeral=True
                )
            except:
                # If interaction has already been responded to, try response instead
                try:
                    await interaction.response.send_message(
                        self.conf['messages']['ticket_thread_create_error'], 
                        ephemeral=True
                    )
                except:
                    pass  # Give up if both fail

    async def log_ticket_action(self, action: str, thread_id: int, user: discord.Member, 
                               extra_user: discord.Member = None, type_name: str = None, 
                               ticket_number: int = None, reason: str = None):
        """Log ticket actions to info channel"""
        try:
            config_data = await self.db_manager.get_config()
            if not config_data or not config_data['info_channel_id']:
                return
            
            info_channel = self.bot.get_channel(config_data['info_channel_id'])
            if not info_channel:
                return
            
            thread = self.bot.get_channel(thread_id)
            
            if action == 'create':
                embed = discord.Embed(
                    title=self.conf['messages']['log_ticket_create_title'].format(number=ticket_number),
                    description=self.conf['messages']['log_ticket_create_description'].format(
                        type_name=type_name,
                        creator=user.mention
                    ),
                    color=EmbedColors.CREATE
                )
            elif action == 'accept':
                # Get ticket data for the ticket number
                ticket_data = await self.db_manager.fetch_ticket(thread_id)
                ticket_number = ticket_data['ticket_number'] if ticket_data else 'Unknown'
                
                embed = discord.Embed(
                    title=self.conf['messages']['log_ticket_accept_title'].format(number=ticket_number),
                    description=self.conf['messages']['log_ticket_accept_description'].format(
                        acceptor=user.mention
                    ),
                    color=EmbedColors.ACCEPT
                )
            elif action == 'close':
                ticket_data = await self.db_manager.get_ticket_history(thread_id)
                if ticket_data:
                    members_list = ", ".join([f"<@{m['user_id']}>" for m in ticket_data['members'][1:]]) or self.conf['messages']['unavailable_text']
                    acceptor_mention = f"<@{ticket_data['accepted_by']}>" if ticket_data['accepted_by'] else self.conf['messages']['unavailable_text']
                    creator_mention = f"<@{ticket_data['creator_id']}>"
                    
                    # Get ticket number, fallback to basic fetch if history doesn't have it
                    ticket_number = ticket_data.get('ticket_number')
                    if not ticket_number:
                        basic_ticket_data = await self.db_manager.fetch_ticket(thread_id)
                        ticket_number = basic_ticket_data['ticket_number'] if basic_ticket_data else None
                    
                    ticket_number = ticket_number or 'Unknown'
                    embed = discord.Embed(
                        title=self.conf['messages']['log_ticket_close_title'].format(number=ticket_number),
                        description=self.conf['messages']['log_ticket_close_description'].format(
                            type_name=ticket_data['type_name'],
                            creator=creator_mention,
                            acceptor=acceptor_mention,
                            members=members_list,
                            created_at=ticket_data['created_at'],
                            closer=user.mention,
                            reason=reason
                        ),
                        color=EmbedColors.CLOSE
                    )
            elif action == 'add_user':
                # Get ticket data for the ticket number
                ticket_data = await self.db_manager.fetch_ticket(thread_id)
                ticket_number = ticket_data['ticket_number'] if ticket_data else 'Unknown'
                
                embed = discord.Embed(
                    title=self.conf['messages']['log_user_add_title'].format(number=ticket_number),
                    description=self.conf['messages']['log_user_add_description'].format(
                        adder=user.mention,
                        user=extra_user.mention
                    ),
                    color=EmbedColors.ADD_USER
                )
            else:
                return
            
            embed.set_footer(text=self.conf['messages']['log_footer_text'])
            
            # Add view button if thread exists
            if thread:
                view = discord.ui.View()
                button = discord.ui.Button(
                    label=self.conf['messages']['log_button_view_ticket'],
                    url=f"https://discord.com/channels/{thread.guild.id}/{thread.id}",
                    style=discord.ButtonStyle.link
                )
                view.add_item(button)
                await info_channel.send(embed=embed, view=view)
            else:
                await info_channel.send(embed=embed)
                
        except Exception as e:
            logging.error(f"Error logging ticket action: {e}")

    @app_commands.command(name="tickets_init", description="初始化工单系统")
    @app_commands.describe(
        ticket_channel="工单频道（可选，留空则自动创建）",
        info_channel="工单信息频道（可选，留空则自动创建）"
    )
    async def init_ticket_system(self, interaction: discord.Interaction, 
                                ticket_channel: discord.TextChannel = None,
                                info_channel: discord.TextChannel = None):
        """Initialize the ticket system with optional channel parameters"""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                self.conf['messages']['admin_no_permission'], 
                ephemeral=True
            )
            return
        
        try:
            # Defer response since channel creation might take time
            await interaction.response.defer(ephemeral=True)
            
            # Check if system is already set up
            existing_config = await self.db_manager.get_config()
            if existing_config and existing_config.get('ticket_channel_id'):
                existing_ticket_channel = interaction.guild.get_channel(existing_config['ticket_channel_id'])
                existing_info_channel = interaction.guild.get_channel(existing_config['info_channel_id'])
                
                if existing_ticket_channel and existing_info_channel:
                    await interaction.followup.send(
                        self.conf['messages']['init_already_configured'].format(
                            ticket_channel=existing_ticket_channel.mention,
                            info_channel=existing_info_channel.mention
                        ),
                        ephemeral=True
                    )
                    return
            
            # Validate provided channels if any
            if ticket_channel:
                if not await self._validate_channel_permissions(ticket_channel):
                    await interaction.followup.send(
                        self.conf['messages']['init_channel_permission_error'],
                        ephemeral=True
                    )
                    return
            
            if info_channel:
                if not await self._validate_channel_permissions(info_channel):
                    await interaction.followup.send(
                        self.conf['messages']['init_channel_permission_error'],
                        ephemeral=True
                    )
                    return
            
            # Create or use existing channels
            if not ticket_channel:
                # Create ticket channel
                ticket_channel = await interaction.guild.create_text_channel(
                    name="🎫工单",
                    category=None,  # Will be placed at the top
                    topic="在此频道创建工单 - 点击下方按钮开始",
                    reason="初始化工单系统"
                )
                
                # Set appropriate permissions for ticket channel
                await ticket_channel.set_permissions(
                    interaction.guild.default_role,
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )
            
            if not info_channel:
                # Create info/log channel  
                info_channel = await interaction.guild.create_text_channel(
                    name="📋工单日志",
                    category=None,
                    topic="工单系统日志记录频道",
                    reason="初始化工单系统"
                )
                
                # Set permissions for info channel - read only for most users
                await info_channel.set_permissions(
                    interaction.guild.default_role,
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True
                )
            
            # Create main message in ticket channel
            embed = discord.Embed(
                title=self.conf['messages']['ticket_main_title'],
                description=self.conf['messages']['ticket_main_description'],
                color=EmbedColors.DEFAULT
            )
            
            # Add bot avatar as thumbnail if available
            if self.bot.user.avatar:
                embed.set_thumbnail(url=self.bot.user.avatar.url)
            
            # Add fields for each ticket type
            ticket_types = self.conf.get('ticket_types', {})
            for type_name, type_data in ticket_types.items():
                embed.add_field(
                    name=type_name,
                    value=type_data.get('description', '无描述'),
                    inline=False
                )
            
            embed.set_footer(text=self.conf['messages']['ticket_main_footer'])
            
            # Create view with ticket type buttons
            view = TicketCreateView(self, ticket_types)
            
            message = await ticket_channel.send(embed=embed, view=view)
            
            # Save configuration to database
            success = await self.db_manager.set_config(
                ticket_channel.id, 
                info_channel.id, 
                message.id
            )
            
            if success:
                # Determine if channels were auto-created or manually specified
                auto_created = not (interaction.data.get('options', [{}])[0].get('value') if interaction.data.get('options') else False)
                success_message = self.conf['messages']['init_success_auto' if auto_created else 'init_success_manual']
                
                # Send success message (visible to everyone)
                setup_embed = discord.Embed(
                    title=self.conf['messages']['init_success_title'],
                    description=success_message.format(
                        ticket_channel=ticket_channel.mention,
                        info_channel=info_channel.mention,
                        message_id=message.id,
                        setup_user=interaction.user.mention
                    ),
                    color=EmbedColors.CREATE
                )
                setup_embed.add_field(
                    name=self.conf['messages']['setup_types_field_name'],
                    value="\n".join([f"• {name}" for name in self.conf.get('ticket_types', {}).keys()]) or self.conf['messages']['setup_no_types'],
                    inline=False
                )
                
                await interaction.followup.send(embed=setup_embed, ephemeral=False)
                
                # Send a notification to the info channel
                log_embed = discord.Embed(
                    title=self.conf['messages']['init_log_title'],
                    description=self.conf['messages']['init_log_description'].format(
                        setup_user=interaction.user.mention,
                        ticket_channel=ticket_channel.mention
                    ),
                    color=EmbedColors.CREATE,
                    timestamp=discord.utils.utcnow()
                )
                await info_channel.send(embed=log_embed)
                
            else:
                # If database save failed and we created channels, clean them up
                if not interaction.data.get('options'):  # Auto-created channels
                    await ticket_channel.delete(reason=self.conf['messages']['cleanup_reason'])
                    await info_channel.delete(reason=self.conf['messages']['cleanup_reason'])
                
                await interaction.followup.send(
                    self.conf['messages']['init_db_error'],
                    ephemeral=True
                )
            
        except discord.Forbidden:
            await interaction.followup.send(
                self.conf['messages']['init_permission_error'],
                ephemeral=True
            )
        except Exception as e:
            logging.error(f"Error initializing ticket system: {e}")
            await interaction.followup.send(
                self.conf['messages']['init_error'].format(error=str(e)), 
                ephemeral=True
            )

    async def _validate_channel_permissions(self, channel: discord.TextChannel) -> bool:
        """Validate that the bot has required permissions in the channel"""
        try:
            bot_member = channel.guild.get_member(self.bot.user.id)
            if not bot_member:
                return False
            
            permissions = channel.permissions_for(bot_member)
            required_perms = [
                permissions.view_channel,
                permissions.send_messages,
                permissions.manage_messages,
                permissions.embed_links
            ]
            
            return all(required_perms)
        except:
            return False

    @app_commands.command(name="tickets_add_user", description="添加用户到工单")
    @app_commands.describe(user="要添加的用户")
    async def add_user_command(self, interaction: discord.Interaction, user: discord.Member):
        """Add user to ticket via command"""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                self.conf['messages']['command_thread_only'], 
                ephemeral=True
            )
            return
        
        thread_id = interaction.channel.id
        
        # Check if ticket exists
        ticket_exists, is_closed = await self.db_manager.check_ticket_status(thread_id)
        if not ticket_exists:
            await interaction.response.send_message(
                self.conf['messages']['ticket_thread_not_found'], 
                ephemeral=True
            )
            return
        
        if is_closed:
            await interaction.response.send_message(
                self.conf['messages']['ticket_closed_no_modify'], 
                ephemeral=True
            )
            return
        
        # Add user
        success = await self.db_manager.add_ticket_member(
            thread_id, user.id, interaction.user.id
        )
        
        if not success:
            await interaction.response.send_message(
                self.conf['messages']['add_user_already_added'], 
                ephemeral=True
            )
            return
        
        # Add to thread
        await interaction.channel.add_user(user)
        
        # Success response
        embed = discord.Embed(
            title=self.conf['messages']['add_user_success_title'],
            description=self.conf['messages']['add_user_success_content'].format(
                user=user.mention, 
                adder=interaction.user.mention
            ),
            color=EmbedColors.ADD_USER
        )
        
        await interaction.response.send_message(embed=embed)
        await self.log_ticket_action('add_user', thread_id, interaction.user, extra_user=user)

    @app_commands.command(name="tickets_stats", description="查看工单系统统计")
    async def stats_command(self, interaction: discord.Interaction):
        """Show ticket statistics"""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                self.conf['messages']['admin_no_permission'], 
                ephemeral=True
            )
            return
        
        try:
            stats = await self.db_manager.get_ticket_stats()
            
            embed = discord.Embed(
                title=self.conf['messages']['ticket_stats_title'],
                color=EmbedColors.DEFAULT
            )
            
            embed.add_field(
                name=self.conf['messages']['ticket_stats_total'],
                value=str(stats['total']),
                inline=True
            )
            
            embed.add_field(
                name=self.conf['messages']['ticket_stats_active'],
                value=str(stats['active']),
                inline=True
            )
            
            embed.add_field(
                name=self.conf['messages']['ticket_stats_closed'],
                value=str(stats['closed']),
                inline=True
            )
            
            embed.add_field(
                name=self.conf['messages']['ticket_stats_response_time'],
                value=self.conf['messages']['ticket_stats_response_time_format'].format(
                    time=stats['avg_response_time']
                ),
                inline=True
            )
            
            if stats['by_type']:
                type_stats = "\n".join([
                    f"• {type_name}: {count}" 
                    for type_name, count in stats['by_type']
                ])
                embed.add_field(
                    name=self.conf['messages']['ticket_stats_by_type'],
                    value=type_stats or self.conf['messages']['ticket_stats_no_data'],
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            logging.error(f"Error getting ticket stats: {e}")
            await interaction.response.send_message(
                self.conf['messages'].get('stats_error', '获取统计数据时发生错误'), 
                ephemeral=True
            )

    @app_commands.command(name="tickets_admin_list", description="显示当前的管理员配置")
    async def admin_list(self, interaction: discord.Interaction):
        """Display current admin configuration."""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                self.conf['messages']['admin_no_permission'],
                ephemeral=True
            )
            return

        embed = await self.format_admin_list()
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="tickets_admin_add_role", description="添加管理员身份组")
    @app_commands.describe(role="要添加的身份组")
    async def admin_add_role(self, interaction: discord.Interaction, role: discord.Role):
        """Add an admin role."""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                self.conf['messages']['admin_no_permission'],
                ephemeral=True
            )
            return

        view = AdminTypeSelectView(self, 'add', 'role', role.id)
        await interaction.response.send_message(
            self.conf['messages']['admin_type_select_add_role'],
            view=view,
            ephemeral=True
        )

    @app_commands.command(name="tickets_admin_remove_role", description="移除管理员身份组")
    @app_commands.describe(role="要移除的身份组")
    async def admin_remove_role(self, interaction: discord.Interaction, role: discord.Role):
        """Remove an admin role."""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                self.conf['messages']['admin_no_permission'],
                ephemeral=True
            )
            return

        view = AdminTypeSelectView(self, 'remove', 'role', role.id)
        await interaction.response.send_message(
            self.conf['messages']['admin_type_select_remove_role'],
            view=view,
            ephemeral=True
        )

    @app_commands.command(name="tickets_admin_add_user", description="添加管理员用户")
    @app_commands.describe(user="要添加的用户")
    async def admin_add_user(self, interaction: discord.Interaction, user: discord.User):
        """Add an admin user."""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                self.conf['messages']['admin_no_permission'],
                ephemeral=True
            )
            return

        view = AdminTypeSelectView(self, 'add', 'user', user.id)
        await interaction.response.send_message(
            self.conf['messages']['admin_type_select_add_user'],
            view=view,
            ephemeral=True
        )

    @app_commands.command(name="tickets_admin_remove_user", description="移除管理员用户")
    @app_commands.describe(user="要移除的用户")
    async def admin_remove_user(self, interaction: discord.Interaction, user: discord.User):
        """Remove an admin user."""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                self.conf['messages']['admin_no_permission'],
                ephemeral=True
            )
            return

        view = AdminTypeSelectView(self, 'remove', 'user', user.id)
        await interaction.response.send_message(
            self.conf['messages']['admin_type_select_remove_user'],
            view=view,
            ephemeral=True
        )

    @app_commands.command(name="tickets_accept", description="手动接受当前工单")
    async def accept_ticket_command(self, interaction: discord.Interaction):
        """Accept ticket via command"""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                self.conf['messages']['command_thread_only'], 
                ephemeral=True
            )
            return
        
        thread_id = interaction.channel.id
        thread = interaction.channel
        
        # Check if thread is already archived
        if thread.archived:
            await interaction.response.send_message(
                self.conf['messages']['ticket_already_closed'],
                ephemeral=True
            )
            return
        
        # Check if ticket exists and is not closed
        ticket_exists, is_closed = await self.db_manager.check_ticket_status(thread_id)
        if not ticket_exists:
            await interaction.response.send_message(
                self.conf['messages']['ticket_thread_not_found'], 
                ephemeral=True
            )
            return
        
        if is_closed:
            await interaction.response.send_message(
                self.conf['messages']['ticket_closed_no_modify'], 
                ephemeral=True
            )
            return
        
        # Get ticket data to check admin permissions
        ticket_data = await self.db_manager.fetch_ticket(thread_id)
        if not ticket_data:
            await interaction.response.send_message(
                self.conf['messages']['ticket_accept_get_info_error'], 
                ephemeral=True
            )
            return
        
        # Check admin permissions
        if not await self.is_admin_for_type(interaction.user, ticket_data['type_name']):
            await interaction.response.send_message(
                self.conf['messages']['ticket_admin_only'], 
                ephemeral=True
            )
            return
        
        # Accept the ticket
        success = await self.db_manager.accept_ticket(thread_id, interaction.user.id)
        if not success:
            await interaction.response.send_message(
                self.conf['messages']['ticket_already_accepted'], 
                ephemeral=True
            )
            return
        
        # Create success embed
        embed = discord.Embed(
            title=self.conf['messages']['ticket_accepted_title'],
            description=self.conf['messages']['ticket_accepted_content'].format(user=interaction.user.mention),
            color=EmbedColors.ACCEPT
        )
        
        await interaction.response.send_message(embed=embed)
        
        # Log action
        await self.log_ticket_action('accept', thread_id, interaction.user)
        
        # Send DM to creator
        if ticket_data:
            creator = interaction.guild.get_member(ticket_data['creator_id'])
            if creator:
                try:
                    dm_embed = discord.Embed(
                        title=self.conf['messages']['ticket_accepted_dm_title'],
                        description=self.conf['messages']['ticket_accepted_dm_content'].format(user=interaction.user.mention),
                        color=EmbedColors.ACCEPT
                    )
                    
                    # Create jump button view
                    dm_view = discord.ui.View()
                    jump_button = discord.ui.Button(
                        style=discord.ButtonStyle.link,
                        label=self.conf['messages']['ticket_jump_button'],
                        url=f"https://discord.com/channels/{interaction.guild.id}/{thread_id}"
                    )
                    dm_view.add_item(jump_button)
                    
                    await creator.send(embed=dm_embed, view=dm_view)
                except:
                    pass  # DM failed

    @app_commands.command(name="tickets_close", description="手动关闭当前工单")
    @app_commands.describe(reason="关闭工单的原因")
    async def close_ticket_command(self, interaction: discord.Interaction, reason: str):
        """Close ticket via command"""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                self.conf['messages']['command_thread_only'], 
                ephemeral=True
            )
            return
        
        thread_id = interaction.channel.id
        thread = interaction.channel
        
        # Check if thread is already archived
        if thread.archived:
            await interaction.response.send_message(
                self.conf['messages']['ticket_already_closed'],
                ephemeral=True
            )
            return
        
        # Check if ticket exists and is not closed
        ticket_exists, is_closed = await self.db_manager.check_ticket_status(thread_id)
        if not ticket_exists:
            await interaction.response.send_message(
                self.conf['messages']['ticket_thread_not_found'], 
                ephemeral=True
            )
            return
        
        if is_closed:
            await interaction.response.send_message(
                self.conf['messages']['ticket_already_closed'], 
                ephemeral=True
            )
            return
        
        # Get ticket data to check admin permissions
        ticket_data = await self.db_manager.fetch_ticket(thread_id)
        if not ticket_data:
            await interaction.response.send_message(
                self.conf['messages']['ticket_accept_get_info_error'], 
                ephemeral=True
            )
            return
        
        # Check admin permissions
        if not await self.is_admin_for_type(interaction.user, ticket_data['type_name']):
            await interaction.response.send_message(
                self.conf['messages']['ticket_admin_only'], 
                ephemeral=True
            )
            return
        
        # Close the ticket in database first
        success = await self.db_manager.close_ticket(thread_id, interaction.user.id, reason)
        if not success:
            await interaction.response.send_message(
                self.conf['messages']['ticket_close_stats_error'], 
                ephemeral=True
            )
            return
        
        # Create success embed
        embed = discord.Embed(
            title=self.conf['messages']['close_dm_title'],
            description=self.conf['messages']['close_dm_content'].format(
                closer=interaction.user.mention,
                reason=reason
            ),
            color=EmbedColors.CLOSE
        )
        
        # Respond to interaction first
        await interaction.response.send_message(embed=embed)
        
        # Update the original ticket message to disable all buttons
        try:
            if ticket_data and ticket_data.get('message_id'):
                try:
                    control_message = await thread.fetch_message(ticket_data['message_id'])
                    
                    # Create disabled view
                    disabled_view = TicketThreadView(self, thread_id, "")
                    for child in disabled_view.children:
                        child.disabled = True
                    
                    await control_message.edit(view=disabled_view)
                except discord.NotFound:
                    pass  # Message was deleted
        except Exception as e:
            logging.error(f"Error disabling buttons after close: {e}")
        
        # Log action
        await self.log_ticket_action('close', thread_id, interaction.user, reason=reason)
        
        # Lock and archive the thread after responding
        try:
            await thread.edit(locked=True, archived=True)
        except discord.HTTPException as e:
            logging.warning(f"Could not archive thread {thread_id}: {e}")
        
        # Send DM to creator
        if ticket_data:
            creator = interaction.guild.get_member(ticket_data['creator_id'])
            if creator:
                try:
                    dm_embed = discord.Embed(
                        title=self.conf['messages']['close_dm_title'],
                        description=self.conf['messages']['close_dm_content'].format(
                            closer=interaction.user.mention,
                            reason=reason
                        ),
                        color=EmbedColors.CLOSE
                    )
                    
                    # Create jump button view
                    dm_view = discord.ui.View()
                    jump_button = discord.ui.Button(
                        style=discord.ButtonStyle.link,
                        label=self.conf['messages']['ticket_jump_button'],
                        url=f"https://discord.com/channels/{interaction.guild.id}/{thread_id}"
                    )
                    dm_view.add_item(jump_button)
                    
                    await creator.send(embed=dm_embed, view=dm_view)
                except:
                    pass  # DM failed

    @app_commands.command(name="tickets_refresh_buttons", description="刷新所有工单的按钮状态")
    async def refresh_buttons_command(self, interaction: discord.Interaction):
        """Refresh button states for all tickets"""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                self.conf['messages']['admin_no_permission'], 
                ephemeral=True
            )
            return
        
        await interaction.response.defer(ephemeral=True)
        
        try:
            all_tickets = await self.db_manager.get_active_tickets()  # This gets ALL tickets now, not just active
            updated_count = 0
            error_count = 0
            skipped_count = 0
            
            # Process tickets in batches to avoid rate limits
            import asyncio
            batch_size = 4  # Conservative batch size
            delay_between_batches = 1.2  # seconds
            
            total_tickets = len(all_tickets)
            current_progress = 0
            
            # Send initial progress message
            if total_tickets > 5:
                try:
                    await interaction.edit_original_response(
                        content=self.conf['messages']['refresh_buttons_starting'].format(total=total_tickets)
                    )
                except:
                    pass
            
            for i in range(0, len(all_tickets), batch_size):
                batch = all_tickets[i:i + batch_size]
                
                for ticket_data in batch:
                    thread_id = ticket_data['thread_id']
                    type_name = ticket_data['type_name']
                    is_accepted = ticket_data.get('accepted_by') is not None
                    is_closed = ticket_data.get('is_closed', False)
                    
                    try:
                        thread = self.bot.get_channel(thread_id)
                        if thread:
                            # Skip archived threads (already closed)
                            if thread.archived:
                                skipped_count += 1
                                current_progress += 1
                                continue
                            
                            # Create view with correct state
                            ticket_view = TicketThreadView(self, thread_id, type_name)
                            
                            # Update button states based on ticket status
                            if is_accepted:
                                ticket_view.children[0].disabled = True  # Accept button
                                ticket_view.children[0].label = self.conf['messages']['ticket_accept_button_disabled']
                                ticket_view.children[0].style = discord.ButtonStyle.success
                            
                            if is_closed:
                                # Disable all buttons for closed tickets
                                for child in ticket_view.children:
                                    child.disabled = True
                            
                            # Register the updated view for persistence
                            self.bot.add_view(ticket_view)
                            
                            # Update the ticket message
                            await self.update_ticket_message_buttons(thread, ticket_data, ticket_view)
                            updated_count += 1
                        else:
                            # Thread not found, count as skipped
                            skipped_count += 1
                    except Exception as e:
                        logging.error(f"Error updating ticket {thread_id}: {e}")
                        error_count += 1
                    
                    current_progress += 1
                
                # Send progress update for large batches
                if total_tickets > 10 and i % (batch_size * 3) == 0 and current_progress < total_tickets:
                    try:
                        await interaction.edit_original_response(
                            content=self.conf['messages']['refresh_buttons_progress'].format(
                                current=current_progress,
                                total=total_tickets,
                                updated=updated_count,
                                skipped=skipped_count,
                                errors=error_count
                            )
                        )
                    except:
                        pass  # Ignore edit failures
                
                # Add delay between batches to avoid rate limits
                if i + batch_size < len(all_tickets):
                    await asyncio.sleep(delay_between_batches)
            
            # Final result message
            await interaction.followup.send(
                self.conf['messages']['refresh_buttons_complete'].format(
                    updated=updated_count,
                    skipped=skipped_count,
                    errors=error_count
                ), 
                ephemeral=True
            )
            
        except Exception as e:
            logging.error(f"Error in refresh_buttons_command: {e}")
            await interaction.followup.send(
                self.conf['messages']['refresh_buttons_error'], 
                ephemeral=True
            )

    @app_commands.command(name="tickets_refresh_main", description="刷新工单创建页面（更新头像和工单类型）")
    async def refresh_main_message_command(self, interaction: discord.Interaction):
        """Refresh the main ticket creation message"""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                self.conf['messages']['admin_no_permission'], 
                ephemeral=True
            )
            return
        
        try:
            # Get config data from database
            config_data = await self.db_manager.get_config()
            if not config_data:
                await interaction.response.send_message(
                    self.conf['messages']['refresh_main_no_config'], 
                    ephemeral=True
                )
                return

            ticket_channel_id = config_data.get('ticket_channel_id')
            main_message_id = config_data.get('main_message_id')
            
            if not ticket_channel_id or not main_message_id:
                await interaction.response.send_message(
                    self.conf['messages']['refresh_main_config_incomplete'], 
                    ephemeral=True
                )
                return

            # Get the ticket channel and message
            ticket_channel = self.bot.get_channel(ticket_channel_id)
            if not ticket_channel:
                await interaction.response.send_message(
                    self.conf['messages']['refresh_main_channel_not_found'], 
                    ephemeral=True
                )
                return

            try:
                main_message = await ticket_channel.fetch_message(main_message_id)
                
                # Update the main message with current ticket types and bot avatar
                ticket_types = self.conf.get('ticket_types', {})
                if ticket_types:
                    await self.update_main_message(ticket_channel, main_message, ticket_types)
                    
                    avatar_status = self.conf['messages']['refresh_main_avatar_updated'] if self.bot.user.avatar else self.conf['messages']['refresh_main_no_avatar']
                    await interaction.response.send_message(
                        self.conf['messages']['refresh_main_success'].format(
                            type_count=len(ticket_types),
                            avatar_status=avatar_status
                        ),
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        self.conf['messages']['refresh_main_no_types'], 
                        ephemeral=True
                    )
                
            except discord.NotFound:
                await interaction.response.send_message(
                    self.conf['messages']['refresh_main_message_not_found'], 
                    ephemeral=True
                )
            except Exception as e:
                logging.error(f"Error updating main message: {e}")
                await interaction.response.send_message(
                    self.conf['messages']['refresh_main_update_error'], 
                    ephemeral=True
                )
                
        except Exception as e:
            logging.error(f"Error in refresh_main_message_command: {e}")
            await interaction.response.send_message(
                self.conf['messages']['refresh_main_error'], 
                ephemeral=True
            )

    # ================== Ticket Type Management Commands ==================

    @app_commands.command(name="tickets_add_type", description="添加新的工单类型")
    async def add_ticket_type(self, interaction: discord.Interaction):
        """Add a new ticket type"""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                self.conf['messages']['admin_no_permission'], 
                ephemeral=True
            )
            return

        modal = TicketTypeModal(self)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="tickets_edit_type", description="编辑现有的工单类型")
    async def edit_ticket_type(self, interaction: discord.Interaction):
        """Edit an existing ticket type"""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                self.conf['messages']['admin_no_permission'], 
                ephemeral=True
            )
            return

        if not self.conf.get('ticket_types'):
            await interaction.response.send_message(
                "❌ 没有可编辑的工单类型",
                ephemeral=True
            )
            return

        view = TypeSelectView(self, 'edit')
        await interaction.response.send_message(
            self.conf['messages'].get('ticket_type_edit_title', '选择要修改的工单类型'),
            view=view,
            ephemeral=True
        )

    @app_commands.command(name="tickets_delete_type", description="删除工单类型")
    async def delete_ticket_type(self, interaction: discord.Interaction):
        """Delete a ticket type"""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                self.conf['messages']['admin_no_permission'], 
                ephemeral=True
            )
            return

        if not self.conf.get('ticket_types'):
            await interaction.response.send_message(
                "❌ 没有可删除的工单类型",
                ephemeral=True
            )
            return

        view = TypeSelectView(self, 'delete')
        await interaction.response.send_message(
            self.conf['messages'].get('ticket_type_delete_title', '选择要删除的工单类型'),
            view=view,
            ephemeral=True
        )

    # Helper methods for admin management
    async def format_admin_list(self) -> discord.Embed:
        """Format current admin configuration as an embed."""
        guild_id = self.main_conf['guild_id']
        guild = self.bot.get_guild(guild_id)
        if not guild:
            raise ValueError("Could not find configured guild")

        embed = discord.Embed(
            title=self.conf['messages']['admin_list_title'],
            color=EmbedColors.DEFAULT
        )

        embed.add_field(
            name="全局管理员",
            value=self._format_admin_entries(
                self.conf.get('admin_roles', []),
                self.conf.get('admin_users', []),
                guild
            ),
            inline=False
        )

        for type_name, type_data in self.conf.get('ticket_types', {}).items():
            embed.add_field(
                name=f"{type_name} 管理员",
                value=self._format_admin_entries(
                    type_data.get('admin_roles', []),
                    type_data.get('admin_users', []),
                    guild
                ),
                inline=False
            )

        return embed

    def _format_admin_entries(self, role_ids: list, user_ids: list, guild: discord.Guild) -> str:
        """Helper method to format admin entries for each section."""
        messages = self.conf['messages']
        lines = []

        if role_ids:
            lines.append(messages['admin_list_roles_header'])
            for role_id in role_ids:
                role = guild.get_role(role_id)
                if role:
                    lines.append(messages['admin_list_role_item'].format(role=role.mention))

        if user_ids:
            if lines:
                lines.append("")
            lines.append(messages['admin_list_users_header'])
            for user_id in user_ids:
                user = self.bot.get_user(user_id)
                if user:
                    lines.append(messages['admin_list_user_item'].format(user=user.mention))

        return "\n".join(lines) if lines else messages['admin_list_empty']

    async def save_config(self):
        """Save the current configuration back to the JSON file"""
        config_path = Path('./bot/config/config_tickets_new.json')

        try:
            async with aiofiles.open(config_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                config_data = json.loads(content)

            config_data.update(self.conf)

            async with aiofiles.open(config_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(config_data, indent=2, ensure_ascii=False))

            # Reload config to get updated values
            from bot.utils.config import Config
            config_instance = Config()
            self.conf = config_instance.get_config('tickets_new')
            
        except Exception as e:
            logging.error(f"Error saving config: {e}")

    async def add_global_admin(self, target_type: str, target_id: int, interaction: discord.Interaction) -> bool:
        """Add a global admin (role or user)."""
        # Remove from type-specific admins first
        for type_data in self.conf.get('ticket_types', {}).values():
            if target_type == 'role':
                if target_id in type_data.get('admin_roles', []):
                    type_data['admin_roles'].remove(target_id)
            else:
                if target_id in type_data.get('admin_users', []):
                    type_data['admin_users'].remove(target_id)

        target_list = 'admin_roles' if target_type == 'role' else 'admin_users'
        if target_id not in self.conf.get(target_list, []):
            if target_list not in self.conf:
                self.conf[target_list] = []
            self.conf[target_list].append(target_id)
            await self.save_config()
            return True
        return False

    async def add_type_admin(self, ticket_type: str, target_type: str, target_id: int, interaction: discord.Interaction) -> bool:
        """Add a type-specific admin (role or user)."""
        if target_type == 'role':
            if target_id in self.conf.get('admin_roles', []):
                await interaction.followup.send(
                    self.conf['messages']['admin_global_role_exists'],
                    ephemeral=True
                )
                return False
        else:
            if target_id in self.conf.get('admin_users', []):
                await interaction.followup.send(
                    self.conf['messages']['admin_global_user_exists'],
                    ephemeral=True
                )
                return False

        if 'ticket_types' not in self.conf:
            self.conf['ticket_types'] = {}
        
        if ticket_type not in self.conf['ticket_types']:
            return False

        type_data = self.conf['ticket_types'][ticket_type]
        target_list = 'admin_roles' if target_type == 'role' else 'admin_users'
        
        if target_list not in type_data:
            type_data[target_list] = []
            
        if target_id not in type_data[target_list]:
            type_data[target_list].append(target_id)
            await self.save_config()
            return True
        return False

    async def remove_global_admin(self, target_type: str, target_id: int, interaction: discord.Interaction) -> bool:
        """Remove a global admin (role or user)."""
        target_list = 'admin_roles' if target_type == 'role' else 'admin_users'
        if target_id in self.conf.get(target_list, []):
            self.conf[target_list].remove(target_id)
            await self.save_config()
            return True
        return False

    async def remove_type_admin(self, ticket_type: str, target_type: str, target_id: int, interaction: discord.Interaction) -> bool:
        """Remove a type-specific admin (role or user)."""
        type_data = self.conf.get('ticket_types', {}).get(ticket_type)
        if not type_data:
            return False

        target_list = 'admin_roles' if target_type == 'role' else 'admin_users'
        if target_id in type_data.get(target_list, []):
            type_data[target_list].remove(target_id)
            await self.save_config()
            return True
        return False

    async def handle_admin_change_response(self, success: bool, action: str, target_type: str, 
                                         target: discord.Object, ticket_type: str = "global", 
                                         interaction: discord.Interaction = None):
        """Handle response messages for admin changes."""
        if not interaction:
            return

        messages = self.conf['messages']
        if success:
            if action == 'add':
                if ticket_type == "global":
                    message = messages['admin_add_global'].format(mention=target.mention)
                else:
                    message = messages['admin_add_type'].format(mention=target.mention, type=ticket_type)
            else:
                if ticket_type == "global":
                    message = messages['admin_remove_global'].format(mention=target.mention)
                else:
                    message = messages['admin_remove_type'].format(mention=target.mention, type=ticket_type)
        else:
            if action == 'add':
                message = messages['admin_add_failed'].format(mention=target.mention)
            else:
                message = messages['admin_remove_failed'].format(mention=target.mention)

        await interaction.followup.send(message, ephemeral=True)
        
        embed = await self.format_admin_list()
        await interaction.followup.send(embed=embed)

    async def add_admins_to_ticket(self, thread, type_name: str, creator: discord.Member, ticket_number: int):
        """Add admins to ticket thread and send notifications"""
        try:
            all_admins_to_add = set()
            all_admins_for_notification = set()
            
            # Handle global admin roles - add all role members to thread
            for role_id in self.conf.get('admin_roles', []):
                role = thread.guild.get_role(role_id)
                if role:
                    # Add role members to both lists
                    for member in role.members:
                        if member != creator and not member.bot:
                            all_admins_to_add.add(member)
                            all_admins_for_notification.add(member)
            
            # Handle global admin users - add individually
            for user_id in self.conf.get('admin_users', []):
                member = thread.guild.get_member(user_id)
                if member and member != creator and not member.bot:
                    all_admins_to_add.add(member)
                    all_admins_for_notification.add(member)
            
            # Handle type-specific admin roles - add all role members to thread
            type_data = self.conf.get('ticket_types', {}).get(type_name, {})
            for role_id in type_data.get('admin_roles', []):
                role = thread.guild.get_role(role_id)
                if role:
                    # Add role members to both lists
                    for member in role.members:
                        if member != creator and not member.bot:
                            all_admins_to_add.add(member)
                            all_admins_for_notification.add(member)
            
            # Handle type-specific admin users - add individually
            for user_id in type_data.get('admin_users', []):
                member = thread.guild.get_member(user_id)
                if member and member != creator and not member.bot:
                    all_admins_to_add.add(member)
                    all_admins_for_notification.add(member)
            
            # Safety check: limit the number of admins to prevent issues
            max_admins = self.conf.get('max_admins_per_ticket', 50)  # Default limit of 50
            if len(all_admins_to_add) > max_admins:
                logging.warning(f"Too many admins ({len(all_admins_to_add)}) for ticket {thread.id}, limiting to {max_admins}")
                all_admins_to_add = set(list(all_admins_to_add)[:max_admins])
            
            # Add all admins to thread with rate limiting
            added_count = 0
            failed_count = 0
            for admin in all_admins_to_add:
                try:
                    # Add to thread
                    await thread.add_user(admin)
                    added_count += 1
                    
                    # Add to database
                    await self.db_manager.add_ticket_member(thread.id, admin.id, self.bot.user.id)
                    
                    # Rate limiting: small delay between additions to avoid API limits
                    if added_count % 5 == 0:  # Every 5 additions, pause briefly
                        await asyncio.sleep(0.5)
                        
                except discord.HTTPException as e:
                    if e.status == 429:  # Rate limited
                        logging.warning(f"Rate limited while adding admin {admin.id} to ticket {thread.id}, waiting...")
                        await asyncio.sleep(2)  # Wait longer for rate limit
                        try:
                            await thread.add_user(admin)
                            await self.db_manager.add_ticket_member(thread.id, admin.id, self.bot.user.id)
                            added_count += 1
                        except Exception as retry_e:
                            logging.error(f"Failed to add admin {admin.id} after rate limit retry: {retry_e}")
                            failed_count += 1
                    else:
                        logging.error(f"HTTP error adding admin {admin.id} to ticket {thread.id}: {e}")
                        failed_count += 1
                except Exception as e:
                    logging.error(f"Error adding admin {admin.id} to ticket {thread.id}: {e}")
                    failed_count += 1
            
            if added_count > 0:
                logging.info(f"Added {added_count} admins to ticket {thread.id}")
            if failed_count > 0:
                logging.warning(f"Failed to add {failed_count} admins to ticket {thread.id}")
            
            # Send DM notifications to all admins with rate limiting
            dm_count = 0
            dm_failed = 0
            for admin in all_admins_for_notification:
                try:
                    admin_embed = discord.Embed(
                        title=self.conf['messages']['admin_notification_title'],
                        description=self.conf['messages']['admin_notification_description'].format(
                            type_name=type_name,
                            ticket_number=ticket_number,
                            creator=creator.mention
                        ),
                        color=EmbedColors.CREATE
                    )
                    
                    # Create jump button
                    dm_view = discord.ui.View()
                    jump_button = discord.ui.Button(
                        style=discord.ButtonStyle.link,
                        label=self.conf['messages']['admin_notification_jump_button'],
                        url=f"https://discord.com/channels/{thread.guild.id}/{thread.id}"
                    )
                    dm_view.add_item(jump_button)
                    
                    await admin.send(embed=admin_embed, view=dm_view)
                    dm_count += 1
                    
                    # Rate limiting for DMs: pause every 10 DMs
                    if dm_count % 10 == 0:
                        await asyncio.sleep(1)
                        
                except discord.Forbidden:
                    logging.info(f"Could not send DM to admin {admin.display_name} (DMs disabled)")
                    dm_failed += 1
                except discord.HTTPException as e:
                    if e.status == 429:  # Rate limited
                        logging.warning(f"Rate limited while sending DM to admin {admin.id}, waiting...")
                        await asyncio.sleep(5)  # Wait longer for DM rate limits
                        try:
                            await admin.send(embed=admin_embed, view=dm_view)
                            dm_count += 1
                        except Exception as retry_e:
                            logging.error(f"Failed to send DM to admin {admin.id} after rate limit retry: {retry_e}")
                            dm_failed += 1
                    else:
                        logging.error(f"HTTP error sending DM to admin {admin.id}: {e}")
                        dm_failed += 1
                except Exception as e:
                    logging.error(f"Error sending DM to admin {admin.id}: {e}")
                    dm_failed += 1
            
            if dm_count > 0:
                logging.info(f"Sent DM notifications to {dm_count} admins for ticket {thread.id}")
            if dm_failed > 0:
                logging.warning(f"Failed to send DM notifications to {dm_failed} admins for ticket {thread.id}")
                    
        except Exception as e:
            logging.error(f"Error in add_admins_to_ticket: {e}")


class AdminTypeSelectView(discord.ui.View):
    def __init__(self, cog, action_type, target_type, target_id):
        super().__init__()
        self.cog = cog
        self.action_type = action_type
        self.target_type = target_type
        self.target_id = target_id
        self.messages = self.cog.conf['messages']

        options = [
            discord.SelectOption(
                label=self.messages['global_ticket_select_label'],
                description=self.messages['global_ticket_select_description'],
                value="global"
            )
        ]

        for type_name, type_data in cog.conf.get('ticket_types', {}).items():
            options.append(
                discord.SelectOption(
                    label=type_name,
                    description=type_data.get('description', '')[:100],
                    value=type_name
                )
            )

        select = discord.ui.Select(
            placeholder=self.messages['ticket_type_select_placeholder'],
            min_values=1,
            max_values=1,
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        selected_type = interaction.data['values'][0]
        await interaction.response.defer(ephemeral=True)

        if self.target_type == 'role':
            target = interaction.guild.get_role(self.target_id)
        else:
            target = await self.cog.bot.fetch_user(self.target_id)

        if not target:
            await interaction.followup.send(self.messages['target_not_found'], ephemeral=True)
            return

        if selected_type == "global":
            if self.action_type == 'add':
                success = await self.cog.add_global_admin(
                    self.target_type,
                    self.target_id,
                    interaction
                )
            else:
                success = await self.cog.remove_global_admin(
                    self.target_type,
                    self.target_id,
                    interaction
                )
        else:
            if self.action_type == 'add':
                success = await self.cog.add_type_admin(
                    selected_type,
                    self.target_type,
                    self.target_id,
                    interaction
                )
            else:
                success = await self.cog.remove_type_admin(
                    selected_type,
                    self.target_type,
                    self.target_id,
                    interaction
                )

        await self.cog.handle_admin_change_response(
            success,
            self.action_type,
            self.target_type,
            target,
            selected_type,
            interaction
        )


# ================== Ticket Type Management ==================

class TicketTypeModal(discord.ui.Modal):
    def __init__(self, cog, edit_type=None):
        title = cog.conf['messages'].get('ticket_type_modal_edit_title', '修改工单类型：{type_name}').format(type_name=edit_type) if edit_type else cog.conf['messages'].get('ticket_type_modal_title', '添加工单类型')
        super().__init__(title=title)
        self.cog = cog
        self.edit_type = edit_type
        self.messages = cog.conf['messages']

        # Pre-fill if editing
        existing_data = cog.conf['ticket_types'].get(edit_type, {}) if edit_type else {}

        self.type_name = discord.ui.TextInput(
            label=self.messages.get('ticket_type_name_label', '类型名称'),
            placeholder=self.messages.get('ticket_type_name_placeholder', '例如: 功能反馈'),
            default=edit_type or "",
            required=True,
            max_length=50
        )
        self.add_item(self.type_name)

        self.description = discord.ui.TextInput(
            label=self.messages.get('ticket_type_description_label', '类型说明'),
            placeholder=self.messages.get('ticket_type_description_placeholder', '在主页面显示的说明文字'),
            default=existing_data.get('description', ''),
            required=True,
            max_length=100
        )
        self.add_item(self.description)

        self.guide = discord.ui.TextInput(
            label=self.messages.get('ticket_type_guide_label', '用户指引'),
            placeholder=self.messages.get('ticket_type_guide_placeholder', '用户创建工单后看到的指引文字'),
            style=discord.TextStyle.paragraph,
            default=existing_data.get('guide', ''),
            required=True,
            max_length=1000
        )
        self.add_item(self.guide)

        self.button_color = discord.ui.TextInput(
            label=self.messages.get('ticket_type_color_label', '按钮颜色 (R, G, B)'),
            placeholder=self.messages.get('ticket_type_color_placeholder', '例如: R, G, B 或 red, green, blue'),
            default=existing_data.get('button_color', 'b'),
            required=False,
            max_length=10
        )
        self.add_item(self.button_color)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            type_name = self.type_name.value.strip()
            description = self.description.value.strip()
            guide = self.guide.value.strip()
            button_color = self.button_color.value.strip().lower() or 'b'

            # Validate button color
            valid_colors = {'r': 'r', 'g': 'g', 'b': 'b', 'grey': 'grey', 'gray': 'grey', 
                           'red': 'r', 'green': 'g', 'blue': 'b'}
            button_color = valid_colors.get(button_color, 'b')

            # Check if editing or creating new
            if self.edit_type and self.edit_type != type_name:
                # Renaming: remove old and add new
                if type_name in self.cog.conf['ticket_types']:
                    await interaction.response.send_message(
                        f"❌ 工单类型 '{type_name}' 已存在",
                        ephemeral=True
                    )
                    return
                
                # Save old data
                old_data = self.cog.conf['ticket_types'][self.edit_type].copy()
                # Remove old type
                del self.cog.conf['ticket_types'][self.edit_type]
                
                # Add new type with updated data
                self.cog.conf['ticket_types'][type_name] = {
                    'name': type_name,
                    'description': description,
                    'guide': guide,
                    'button_color': button_color,
                    'admin_roles': old_data.get('admin_roles', []),
                    'admin_users': old_data.get('admin_users', [])
                }
                
                action = "edit"
                old_name = self.edit_type
            else:
                # Creating new or editing without rename
                if not self.edit_type and type_name in self.cog.conf['ticket_types']:
                    await interaction.response.send_message(
                        f"❌ 工单类型 '{type_name}' 已存在",
                        ephemeral=True
                    )
                    return
                
                # Preserve existing admin settings if editing
                existing_admin_data = {}
                if self.edit_type:
                    existing_admin_data = {
                        'admin_roles': self.cog.conf['ticket_types'][self.edit_type].get('admin_roles', []),
                        'admin_users': self.cog.conf['ticket_types'][self.edit_type].get('admin_users', [])
                    }
                
                self.cog.conf['ticket_types'][type_name] = {
                    'name': type_name,
                    'description': description,
                    'guide': guide,
                    'button_color': button_color,
                    'admin_roles': existing_admin_data.get('admin_roles', []),
                    'admin_users': existing_admin_data.get('admin_users', [])
                }
                
                action = "edit" if self.edit_type else "add"
                old_name = self.edit_type if self.edit_type else None

            # Save to database
            await self.cog.db_manager.save_config('ticket_types', self.cog.conf['ticket_types'])
            
            # Reload config
            self.cog.conf = await self.cog.db_manager.get_config()

            # Send success message
            if action == "add":
                await interaction.response.send_message(
                    f"✅ 已添加工单类型: **{type_name}**",
                    ephemeral=True
                )
                
                # TODO: Add logging functionality if needed
            else:
                await interaction.response.send_message(
                    f"✅ 已更新工单类型: **{type_name}**",
                    ephemeral=True
                )
                
                # TODO: Add logging functionality if needed

        except Exception as e:
            logging.error(f"Error in TicketTypeModal: {e}")
            await interaction.response.send_message(
                "❌ 操作失败，请联系管理员",
                ephemeral=True
            )


class TypeSelectView(discord.ui.View):
    def __init__(self, cog, action):
        super().__init__()
        self.cog = cog
        self.action = action  # 'edit' or 'delete'

        if not cog.conf.get('ticket_types'):
            return

        options = []
        for type_name, type_data in cog.conf['ticket_types'].items():
            options.append(discord.SelectOption(
                label=type_name,
                description=type_data.get('description', '')[:100],
                emoji='✏️' if action == 'edit' else '🗑️'
            ))

        if options:
            select = discord.ui.Select(
                placeholder=cog.conf['messages'].get('ticket_type_select_placeholder', '选择工单类型'),
                options=options[:25]  # Discord limit
            )
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        selected_type = interaction.data['values'][0]
        
        if self.action == 'edit':
            modal = TicketTypeModal(self.cog, edit_type=selected_type)
            await interaction.response.send_modal(modal)
        elif self.action == 'delete':
            # Confirm deletion
            embed = discord.Embed(
                title="⚠️ 确认删除",
                description=f"确定要删除工单类型 **{selected_type}** 吗？\n\n这个操作无法撤销！",
                color=discord.Color.red()
            )
            
            view = DeleteConfirmView(self.cog, selected_type)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class DeleteConfirmView(discord.ui.View):
    def __init__(self, cog, type_name):
        super().__init__()
        self.cog = cog
        self.type_name = type_name

    @discord.ui.button(label="确认删除", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            # Remove from config
            if self.type_name in self.cog.conf['ticket_types']:
                del self.cog.conf['ticket_types'][self.type_name]
                
                # Save to database
                await self.cog.db_manager.save_config('ticket_types', self.cog.conf['ticket_types'])
                
                # Reload config
                self.cog.conf = await self.cog.db_manager.get_config()
                
                await interaction.response.send_message(
                    self.cog.conf['messages'].get('ticket_type_delete_success', '已删除工单类型: {type_name}').format(type_name=self.type_name),
                    ephemeral=True
                )
                
                # TODO: Add logging functionality if needed
            else:
                await interaction.response.send_message(
                    f"❌ 工单类型 '{self.type_name}' 不存在",
                    ephemeral=True
                )
        except Exception as e:
            logging.error(f"Error deleting ticket type: {e}")
            await interaction.response.send_message(
                "❌ 删除失败，请联系管理员",
                ephemeral=True
            )

    @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("已取消删除操作", ephemeral=True)

