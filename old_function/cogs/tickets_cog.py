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

from bot.utils import config, check_channel_validity, TicketsDatabaseManager, TicketsNewDatabaseManager, MediaHandler
from bot.utils.file_utils import generate_file_tree


class TicketLogger:
    def __init__(self, bot, info_channel_id, messages):
        self.bot = bot
        self.info_channel_id = info_channel_id
        self.messages = messages

    async def log_ticket_create(self, ticket_number, type_name, creator, channel):
        """Log ticket creation to info channel"""
        info_channel = self.bot.get_channel(self.info_channel_id)
        if not info_channel:
            return

        embed = discord.Embed(
            title=self.messages['log_ticket_create_title'],
            description=self.messages['log_ticket_create_description'].format(
                number=ticket_number,
                type_name=type_name,
                creator=creator.mention
            ),
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )

        view = JumpToChannelView(channel)
        await info_channel.send(embed=embed, view=view)

    async def log_ticket_accept(self, channel, acceptor):
        """Log ticket acceptance to info channel"""
        info_channel = self.bot.get_channel(self.info_channel_id)
        if not info_channel:
            return

        embed = discord.Embed(
            title=self.messages['log_ticket_accept_title'],
            description=self.messages['log_ticket_accept_description'].format(
                acceptor=acceptor.mention
            ),
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )

        view = JumpToChannelView(channel)
        await info_channel.send(embed=embed, view=view)

    async def log_ticket_close(self, channel, closer, reason, ticket_type=None):
        """Log ticket closure to info channel"""
        info_channel = self.bot.get_channel(self.info_channel_id)
        if not info_channel:
            return

        embed = discord.Embed(
            title=self.messages['log_ticket_close_title'],
            description=self.messages['log_ticket_close_description'].format(
                closer=closer.mention,
                reason=reason
            ),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )

        view = JumpToChannelView(channel)
        await info_channel.send(embed=embed, view=view)

    async def log_user_add(self, channel, adder, user):
        """Log user addition to info channel"""
        info_channel = self.bot.get_channel(self.info_channel_id)
        if not info_channel:
            return

        embed = discord.Embed(
            title=self.messages['log_user_add_title'],
            description=self.messages['log_user_add_description'].format(
                adder=adder.mention,
                user=user.mention
            ),
            color=discord.Color.teal(),
            timestamp=discord.utils.utcnow()
        )

        view = JumpToChannelView(channel)
        await info_channel.send(embed=embed, view=view)


class TicketSystem:
    def __init__(self, cog, guild):
        self.cog = cog
        self.guild = guild
        self.conf = cog.conf
        self.info_channel_id = self.conf.get('info_channel_id')
        self.main_channel_id = self.conf.get('create_channel_id')  # Use create_channel_id as main channel
        self.main_message_id = self.conf.get('main_message_id')
        
    async def get_next_ticket_number(self):
        """Get the next ticket number"""
        # Simple implementation: count all tickets and add 1
        total_tickets = len(await self.cog.db.get_active_tickets()) + 1
        return total_tickets

    async def get_available_category(self, is_closed=False):
        """Get an available category for ticket placement"""
        # Simple implementation: return None to indicate no category management
        return None

    async def check_status(self):
        """Check if the ticket system is properly set up"""
        if not self.info_channel_id or not self.main_channel_id:
            return False
        
        info_channel = self.guild.get_channel(self.info_channel_id)
        main_channel = self.guild.get_channel(self.main_channel_id)
        
        return bool(info_channel and main_channel)

    async def setup_system(self):
        """Set up the ticket system"""
        setup_report = {
            'invalid_components': [],
            'new_components': {}
        }
        
        # Check if channels exist
        info_channel = self.guild.get_channel(self.info_channel_id) if self.info_channel_id else None
        main_channel = self.guild.get_channel(self.main_channel_id) if self.main_channel_id else None
        
        if not info_channel:
            setup_report['invalid_components'].append(('Info Channel', self.info_channel_id))
        
        if not main_channel:
            setup_report['invalid_components'].append(('Main Channel', self.main_channel_id))
            
        # Create main message if it doesn't exist
        if main_channel and not self.main_message_id:
            embed = discord.Embed(
                title=self.conf['messages']['ticket_main_title'],
                description=self.conf['messages']['ticket_main_description'],
                color=discord.Color.blue()
            )
            
            # Add fields for each ticket type
            for type_name, type_data in self.conf.get('ticket_types', {}).items():
                embed.add_field(
                    name=type_name,
                    value=type_data.get('description', '无描述'),
                    inline=False
                )
            
            embed.set_footer(text=self.conf['messages']['ticket_main_footer'])
            
            view = TicketMainView(self)
            message = await main_channel.send(embed=embed, view=view)
            
            # Update config with new message ID
            self.main_message_id = message.id
            self.conf['main_message_id'] = message.id
            await self.cog.save_config()
            
            setup_report['new_components']['Main Message'] = message.id
        
        return setup_report

    async def update_main_message(self):
        """Update the main ticket message"""
        if not self.main_message_id or not self.main_channel_id:
            return
            
        main_channel = self.guild.get_channel(self.main_channel_id)
        if not main_channel:
            return
            
        try:
            message = await main_channel.fetch_message(self.main_message_id)
            
            # Create updated embed with ticket types
            embed = discord.Embed(
                title=self.conf['messages']['ticket_main_title'],
                description=self.conf['messages']['ticket_main_description'],
                color=discord.Color.blue()
            )
            
            # Add fields for each ticket type
            for type_name, type_data in self.conf.get('ticket_types', {}).items():
                embed.add_field(
                    name=type_name,
                    value=type_data.get('description', '无描述'),
                    inline=False
                )
            
            embed.set_footer(text=self.conf['messages']['ticket_main_footer'])
            
            view = TicketMainView(self)
            await message.edit(embed=embed, view=view)
        except discord.NotFound:
            # Message was deleted, create new one
            await self.setup_system()


class TicketMainView(discord.ui.View):
    def __init__(self, ticket_system):
        super().__init__(timeout=None)
        self.ticket_system = ticket_system
        self.messages = ticket_system.conf['messages']
        
        # Add buttons for each ticket type
        for type_name, type_data in ticket_system.conf.get('ticket_types', {}).items():
            button = TicketButton(ticket_system, type_name, type_data)
            self.add_item(button)


class TicketButton(discord.ui.Button):
    def __init__(self, ticket_system, type_name, type_data):
        color = type_data.get('button_color', 'b').lower()
        button_style = TicketButton.get_button_style(color)

        super().__init__(
            style=button_style,
            label=f"{type_name}",
            custom_id=f"ticket_{type_name}"
        )
        self.ticket_system = ticket_system
        self.type_name = type_name
        self.type_data = type_data

        self.messages = config.get_config('tickets')['messages']

    @staticmethod
    def get_button_style(color_value):
        if color_value in ['r', 'red', 'R', 'RED', 'Red']:
            return discord.ButtonStyle.danger
        elif color_value in ['g', 'green', 'G', 'GREEN', 'Green']:
            return discord.ButtonStyle.success
        elif color_value in ['b', 'blue', 'B', 'BLUE', 'Blue']:
            return discord.ButtonStyle.primary
        else:
            return discord.ButtonStyle.secondary

    async def callback(self, interaction: discord.Interaction):
        # Check if new ticket system is available
        try:
            new_cog = interaction.client.get_cog('TicketsNewCog')
            if new_cog:
                db_manager = new_cog.db_manager
                config_data = await db_manager.get_config()
                
                if config_data and config_data.get('ticket_channel_id'):
                    # New system is available, redirect user
                    new_channel = interaction.guild.get_channel(config_data['ticket_channel_id'])
                    if new_channel:
                        await interaction.response.send_message(
                            self.messages['old_system_redirect'].format(channel=new_channel.mention),
                            ephemeral=True
                        )
                        return
        except Exception as e:
            logging.error(f"Error checking new ticket system: {e}")
        
        # New system not available, show error message
        await interaction.response.send_message(
            self.messages['old_system_no_new_channel'],
            ephemeral=True
        )


class TicketConfirmModal(discord.ui.Modal):
    def __init__(self, ticket_system, type_name, type_data):
        super().__init__(title=ticket_system.conf['messages']['ticket_modal_confirm_title'].format(type_name=type_name))
        self.ticket_system = ticket_system
        self.type_name = type_name
        self.type_data = type_data
        self.messages = ticket_system.conf['messages']

        self.confirmation = discord.ui.TextInput(
            label=self.messages['ticket_modal_confirm_label'].format(type_name=type_name),
            placeholder=self.messages['ticket_modal_confirm_placeholder'],
            required=True,
            max_length=10
        )
        self.add_item(self.confirmation)

    async def on_submit(self, interaction: discord.Interaction):
        # This modal is now disabled - redirect to new system
        await interaction.response.send_message(
            self.messages['old_system_disabled'],
            ephemeral=True
        )


class JumpToChannelView(discord.ui.View):
    def __init__(self, channel):
        super().__init__(timeout=None)

        self.messages = config.get_config('tickets')['messages']

        self.add_item(discord.ui.Button(
            style=discord.ButtonStyle.link,
            label=self.messages['ticket_jump_button'],
            url=channel.jump_url
        ))


class TicketControlView(discord.ui.View):
    def __init__(self, cog, channel, creator, type_name, is_accepted=False):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel = channel
        self.creator = creator
        self.type_name = type_name
        self.messages = self.cog.conf['messages']

        self.accept_button = discord.ui.Button(
            style=discord.ButtonStyle.primary if not is_accepted else discord.ButtonStyle.success,
            label=self.messages['ticket_accept_button'] if not is_accepted else self.messages[
                'ticket_accept_button_disabled'],
            custom_id=f"accept_{channel.id}",
            disabled=is_accepted
        )
        self.accept_button.callback = self.accept_callback

        self.add_user_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label=self.messages['ticket_add_user_button'],
            custom_id=f"add_user_{channel.id}"
        )
        self.add_user_button.callback = self.add_user_callback

        self.close_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label=self.messages['ticket_close_button'],
            custom_id=f"close_{channel.id}"
        )
        self.close_button.callback = self.close_callback

        self.add_item(self.accept_button)
        self.add_item(self.add_user_button)
        self.add_item(self.close_button)

    async def accept_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        ticket_details = await self.cog.db.fetch_ticket(self.channel.id)
        if not ticket_details:
            await interaction.followup.send(self.messages['ticket_accept_get_info_error'], ephemeral=True)
            return

        if not await self.cog.is_admin(interaction.user, ticket_details['type_name']):
            await interaction.followup.send(self.messages['ticket_admin_only'], ephemeral=True)
            return

        if await self.cog.db.accept_ticket(self.channel.id, interaction.user.id):
            self.accept_button.style = discord.ButtonStyle.success
            self.accept_button.label = self.messages['ticket_accept_button_disabled']
            self.accept_button.disabled = True

            embed = discord.Embed(
                title=self.messages['ticket_accepted_title'],
                description=self.messages['ticket_accepted_content'].format(user=interaction.user.mention),
                color=discord.Color.green()
            )
            await self.channel.send(embed=embed)

            try:
                creator_embed = discord.Embed(
                    title=self.messages['ticket_accepted_dm_title'],
                    description=self.messages['ticket_accepted_dm_content'].format(
                        user=interaction.user.display_name
                    ),
                    color=discord.Color.green()
                )
                view = JumpToChannelView(self.channel)
                await self.creator.send(embed=creator_embed, view=view)
            except discord.Forbidden:
                pass

            await self.cog.logger.log_ticket_accept(
                channel=self.channel,
                acceptor=interaction.user
            )

            await interaction.message.edit(
                view=TicketControlView(
                    self.cog,
                    self.channel,
                    self.creator,
                    ticket_details['type_name'],
                    is_accepted=True
                )
            )
        else:
            await interaction.followup.send(self.messages['ticket_already_accepted'], ephemeral=True)

    async def add_user_callback(self, interaction: discord.Interaction):
        modal = AddUserModal(self.cog, self.channel)
        await interaction.response.send_modal(modal)

    async def close_callback(self, interaction: discord.Interaction):
        modal = CloseTicketModal(self.cog, self.channel, self.creator, self.type_name)
        await interaction.response.send_modal(modal)


class AddUserModal(discord.ui.Modal):
    def __init__(self, cog, ticket_channel):
        messages = cog.conf['messages']
        super().__init__(title=messages['add_user_modal_title'])
        self.cog = cog
        self.ticket_channel = ticket_channel
        self.messages = messages

        self.user_id = discord.ui.TextInput(
            label=self.messages['add_user_modal_label'],
            placeholder=self.messages['add_user_modal_placeholder'],
            required=True,
            min_length=17,
            max_length=20
        )
        self.add_item(self.user_id)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            user_id = int(self.user_id.value)
            user = await self.cog.bot.fetch_user(user_id)
            if not user:
                await interaction.followup.send(self.messages['add_user_not_found'], ephemeral=True)
                return

            member = interaction.guild.get_member(user.id)
            if not member:
                await interaction.followup.send(self.messages['add_user_not_found'], ephemeral=True)
                return

            await self.cog.handle_add_user(interaction, member, self.ticket_channel.id)

        except ValueError:
            await interaction.followup.send(self.messages['add_user_invalid_id'], ephemeral=True)


class CloseTicketModal(discord.ui.Modal):
    def __init__(self, cog, ticket_channel, creator, type_name):
        super().__init__(title=cog.conf['messages']['close_modal_title'])
        self.cog = cog
        self.ticket_channel = ticket_channel
        self.creator = creator
        self.type_name = type_name
        self.messages = cog.conf['messages']

        self.reason = discord.ui.TextInput(
            label=self.messages['close_modal_label'],
            placeholder=self.messages['close_modal_placeholder'],
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if await self.cog.db.close_ticket(self.ticket_channel.id, interaction.user.id, self.reason.value):
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_messages=True
                ),
                self.creator: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True
                )
            }

            # Add admin permissions
            for role_id in self.cog.conf.get('admin_roles', []):
                role = interaction.guild.get_role(role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

            for user_id in self.cog.conf.get('admin_users', []):
                member = interaction.guild.get_member(user_id)
                if member:
                    overwrites[member] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

            # Add type-specific admin permissions
            type_data = self.cog.conf['ticket_types'].get(self.type_name, {})
            for role_id in type_data.get('admin_roles', []):
                role = interaction.guild.get_role(role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

            for user_id in type_data.get('admin_users', []):
                member = interaction.guild.get_member(user_id)
                if member:
                    overwrites[member] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

            # Add ticket members (read-only)
            members = await self.cog.db.get_ticket_members(self.ticket_channel.id)
            for member_id, added_by, added_at in members:
                member = interaction.guild.get_member(member_id)
                if member and member != self.creator:
                    overwrites[member] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=False,
                        read_message_history=True
                    )

            try:
                await self.ticket_channel.edit(overwrites=overwrites)
            except Exception as e:
                logging.error(f"Failed to update ticket permissions: {e}")

            embed = discord.Embed(
                title=self.cog.conf['messages']['log_ticket_close_title'],
                description=self.cog.conf['messages']['log_ticket_close_description'].format(
                    closer=interaction.user.mention,
                    reason=self.reason.value
                ),
                color=discord.Color.red()
            )

            await self.ticket_channel.send(embed=embed)

            # Update control panel buttons
            view = TicketControlView(self.cog, self.ticket_channel, self.creator, self.type_name,
                                     is_accepted=True)
            for item in view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

            try:
                message = await self.ticket_channel.fetch_message(interaction.message.id)
                await message.edit(view=view)
            except discord.NotFound:
                pass

            # Send DM to creator
            try:
                creator_embed = discord.Embed(
                    title=self.cog.conf['messages']['close_dm_title'],
                    description=self.cog.conf['messages']['close_dm_content'].format(
                        closer=interaction.user.display_name,
                        reason=self.reason.value
                    ),
                    color=discord.Color.red()
                )
                view = JumpToChannelView(self.ticket_channel)
                await self.creator.send(embed=creator_embed, view=view)
            except discord.Forbidden:
                pass

            await self.cog.logger.log_ticket_close(
                channel=self.ticket_channel,
                closer=interaction.user,
                reason=self.reason.value,
                ticket_type=self.type_name
            )

            await interaction.followup.send(self.cog.conf['messages']['ticket_stats_closed'], ephemeral=True)


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

        for type_name, type_data in cog.conf['ticket_types'].items():
            options.append(
                discord.SelectOption(
                    label=type_name,
                    description=type_data['description'][:100],
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


class TicketTypeModal(discord.ui.Modal):
    def __init__(self, cog, edit_type=None):
        title = "编辑工单类型" if edit_type else "添加工单类型"
        super().__init__(title=title)
        self.cog = cog
        self.edit_type = edit_type
        self.messages = cog.conf['messages']

        # Pre-fill if editing
        existing_data = cog.conf['ticket_types'].get(edit_type, {}) if edit_type else {}

        self.type_name = discord.ui.TextInput(
            label="类型名称",
            placeholder="输入工单类型名称",
            default=edit_type or "",
            required=True,
            max_length=50
        )
        self.add_item(self.type_name)

        self.description = discord.ui.TextInput(
            label="描述",
            placeholder="输入工单类型描述",
            default=existing_data.get('description', ''),
            required=True,
            max_length=100
        )
        self.add_item(self.description)

        self.guide = discord.ui.TextInput(
            label="指导信息",
            placeholder="用户创建工单时显示的指导信息",
            style=discord.TextStyle.paragraph,
            default=existing_data.get('guide', ''),
            required=True,
            max_length=1000
        )
        self.add_item(self.guide)

        self.button_color = discord.ui.TextInput(
            label="按钮颜色",
            placeholder="r/g/b/grey (红/绿/蓝/灰)",
            default=existing_data.get('button_color', 'b'),
            required=False,
            max_length=10
        )
        self.add_item(self.button_color)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            type_name = self.type_name.value.strip()
            
            # Validation
            if not type_name:
                await interaction.response.send_message("类型名称不能为空", ephemeral=True)
                return

            if not self.edit_type and type_name in self.cog.conf['ticket_types']:
                await interaction.response.send_message("该类型名称已存在", ephemeral=True)
                return

            # Create type data
            type_data = {
                'description': self.description.value.strip(),
                'guide': self.guide.value.strip(),
                'button_color': self.button_color.value.strip() or 'b',
                'admin_roles': [],
                'admin_users': []
            }

            # If editing and name changed, remove old entry
            if self.edit_type and self.edit_type != type_name:
                del self.cog.conf['ticket_types'][self.edit_type]

            # Add/update type
            self.cog.conf['ticket_types'][type_name] = type_data

            # Save config
            await self.cog.save_config()

            # Update main message
            if self.cog.ticket_system:
                await self.cog.ticket_system.update_main_message()

            if self.edit_type:
                message = self.messages['ticket_type_update_success'].format(type_name=type_name)
            else:
                message = self.messages['ticket_type_add_success'].format(type_name=type_name)
            await interaction.response.send_message(message, ephemeral=False)

        except Exception as e:
            logging.error(f"Error in TicketTypeModal: {e}")
            await interaction.response.send_message(self.messages['ticket_type_operation_failed'], ephemeral=True)


class TypeSelectView(discord.ui.View):
    def __init__(self, cog, action):
        super().__init__()
        self.cog = cog
        self.action = action  # 'edit' or 'delete'

        if not cog.conf.get('ticket_types'):
            return

        options = []
        for type_name, type_data in cog.conf['ticket_types'].items():
            options.append(
                discord.SelectOption(
                    label=type_name,
                    description=type_data['description'][:100],
                    value=type_name
                )
            )

        if options:
            select = discord.ui.Select(
                placeholder=f"选择要{action}的工单类型",
                options=options
            )
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        selected_type = interaction.data['values'][0]

        if self.action == 'edit':
            modal = TicketTypeModal(self.cog, selected_type)
            await interaction.response.send_modal(modal)
        elif self.action == 'delete':
            # Create confirmation view
            view = ConfirmDeleteView(self.cog, selected_type)
            await interaction.response.send_message(
                f"确定要删除工单类型 `{selected_type}` 吗？",
                view=view,
                ephemeral=True
            )


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, cog, type_name):
        super().__init__()
        self.cog = cog
        self.type_name = type_name

    @discord.ui.button(label="确认删除", style=discord.ButtonStyle.danger)
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if self.type_name in self.cog.conf['ticket_types']:
                del self.cog.conf['ticket_types'][self.type_name]
                await self.cog.save_config()

                # Update main message
                if self.cog.ticket_system:
                    await self.cog.ticket_system.update_main_message()

                await interaction.response.send_message(self.messages['ticket_type_delete_success'].format(type_name=self.type_name), ephemeral=False)
            else:
                await interaction.response.send_message(self.messages['ticket_type_not_found'], ephemeral=True)
        except Exception as e:
            logging.error(f"Error deleting ticket type: {e}")
            await interaction.response.send_message(self.messages['ticket_type_delete_failed'], ephemeral=True)

    @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary)
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(self.messages['ticket_type_delete_cancelled'], ephemeral=True)


class TicketsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.main_config = config.get_config('main')
        self.conf = config.get_config('tickets')
        self.db_path = self.main_config['db_path']
        self.guild_id = self.main_config['guild_id']
        self.guild = None
        self.ticket_system = None
        self.db = TicketsDatabaseManager(self.db_path)
        self.logger = TicketLogger(bot, self.conf['info_channel_id'], self.conf['messages'])

    async def cog_load(self):
        """Initialize the cog and database."""
        await self.db.initialize_database()

    async def check_ticket_channel(self, interaction):
        """Check if command is used in the ticket creation channel"""
        if not self.ticket_system or not self.ticket_system.info_channel_id:
            return await check_channel_validity(interaction)

        channel_id = interaction.channel_id
        allowed_channel_id = self.ticket_system.info_channel_id

        messages = self.conf['messages']

        if channel_id != allowed_channel_id:
            await interaction.response.send_message(
                messages['command_channel_only'],
                ephemeral=True
            )
            return False
        return True

    async def update_admin_permissions(self):
        """Update permissions for all admin users and roles in relevant channels."""
        if not self.ticket_system or not self.guild:
            logging.warning("Cannot update admin permissions: ticket system or guild not initialized")
            return

        info_channel = self.guild.get_channel(self.ticket_system.info_channel_id)
        if not info_channel:
            return

        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            self.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True
            )
        }

        for role_id in self.conf.get('admin_roles', []):
            role = self.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_messages=True
                )

        for user_id in self.conf.get('admin_users', []):
            member = self.guild.get_member(user_id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_messages=True
                )

        for type_data in self.conf['ticket_types'].values():
            for role_id in type_data.get('admin_roles', []):
                role = self.guild.get_role(role_id)
                if role and role not in overwrites:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

            for user_id in type_data.get('admin_users', []):
                member = self.guild.get_member(user_id)
                if member and member not in overwrites:
                    overwrites[member] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

        await info_channel.edit(overwrites=overwrites)

        active_tickets = await self.db.get_active_tickets()

        for channel_id, message_id, creator_id, type_name, is_accepted in active_tickets:
            channel = self.guild.get_channel(channel_id)
            if not channel:
                continue

            fresh_overwrites = {
                self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                self.guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_messages=True
                )
            }

            creator = self.guild.get_member(creator_id)
            if creator:
                fresh_overwrites[creator] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )

            ticket_info = await self.db.fetch_ticket(channel_id)
            if ticket_info and ticket_info.get('is_closed'):
                members = await self.db.get_ticket_members(channel_id)
                for member_id, _, _ in members:
                    member = self.guild.get_member(member_id)
                    if member and member != creator:
                        fresh_overwrites[member] = discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=False,
                            read_message_history=True
                        )
            else:
                members = await self.db.get_ticket_members(channel_id)
                for member_id, _, _ in members:
                    member = self.guild.get_member(member_id)
                    if member and member != creator:
                        fresh_overwrites[member] = discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=True,
                            read_message_history=True
                        )

            for role_id in self.conf.get('admin_roles', []):
                role = self.guild.get_role(role_id)
                if role:
                    fresh_overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

            for user_id in self.conf.get('admin_users', []):
                member = self.guild.get_member(user_id)
                if member:
                    fresh_overwrites[member] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

            type_data = self.conf['ticket_types'].get(type_name, {})
            for role_id in type_data.get('admin_roles', []):
                role = self.guild.get_role(role_id)
                if role:
                    fresh_overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

            for user_id in type_data.get('admin_users', []):
                member = self.guild.get_member(user_id)
                if member:
                    fresh_overwrites[member] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

            try:
                await channel.edit(overwrites=fresh_overwrites)
            except discord.HTTPException as e:
                logging.error(f"Failed to update permissions for channel {channel.id}: {e}")

        logging.info(f"Updated permissions for {len(active_tickets)} active tickets")

    # @app_commands.command(
    #     name="tickets_setup",
    #     description="Initialize the ticket system"
    # )
    async def ticket_setup(self, interaction: discord.Interaction):
        """Initialize the ticket system."""
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            setup_report = await self.ticket_system.setup_system()

            response_parts = []
            messages = self.conf['messages']

            if setup_report['invalid_components']:
                response_parts.append(messages['setup_invalid_components'])
                for name, id in setup_report['invalid_components']:
                    response_parts.append(messages['setup_invalid_component_item'].format(
                        name=name, id=id
                    ))

            if setup_report['new_components']:
                response_parts.append(messages['setup_new_components'])
                for name, id in setup_report['new_components'].items():
                    response_parts.append(messages['setup_new_component_item'].format(
                        name=name, id=id
                    ))

            if not setup_report['invalid_components'] and not setup_report['new_components']:
                response_parts.append(messages['setup_no_changes'])

            await interaction.followup.send("\n".join(response_parts), ephemeral=True)

        except Exception as e:
            error_msg = messages['setup_error'].format(error=str(e))
            logging.error(f"Setup error: {e}")
            await interaction.followup.send(error_msg, ephemeral=True)

    # @app_commands.command(
    #     name="tickets_old_stats",
    #     description="显示工单统计信息（旧系统）"
    # )
    async def ticket_stats(self, interaction: discord.Interaction):
        """Display ticket statistics."""
        if not await self.check_ticket_channel(interaction):
            return

        await interaction.response.defer()

        try:
            stats = await self.db.get_ticket_stats()
            messages = self.conf['messages']

            embed = discord.Embed(
                title=messages['ticket_stats_title'],
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )

            embed.add_field(name=messages['ticket_stats_total'], value=str(stats['total']), inline=True)
            embed.add_field(name=messages['ticket_stats_active'], value=str(stats['active']), inline=True)
            embed.add_field(name=messages['ticket_stats_closed'], value=str(stats['closed']), inline=True)
            embed.add_field(
                name=messages['ticket_stats_response_time'],
                value=messages['ticket_stats_response_time_format'].format(time=stats['avg_response_time']),
                inline=True
            )

            type_breakdown = "\n".join(f"{type_name}: {count}" for type_name, count in stats['by_type'])
            embed.add_field(
                name=messages['ticket_stats_by_type'],
                value=type_breakdown or messages['ticket_stats_no_data'],
                inline=False
            )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logging.error(f"Error getting ticket stats: {e}")
            await interaction.followup.send(
                "An error occurred while fetching ticket statistics.",
                ephemeral=True
            )

    # @app_commands.command(
    #     name="tickets_cleanup",
    #     description="清理无效的工单数据"
    # )
    async def cleanup_tickets(self, interaction: discord.Interaction):
        """Clean up invalid ticket data."""
        if not await self.check_ticket_channel(interaction):
            return

        await interaction.response.defer()

        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('SELECT channel_id FROM tickets')
                all_channel_ids = [row[0] for row in await cursor.fetchall()]

            valid_channels = []
            invalid_channels = []
            for channel_id in all_channel_ids:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    valid_channels.append(channel_id)
                else:
                    invalid_channels.append(channel_id)

            if invalid_channels:
                await self.db.clean_invalid_tickets(valid_channels)

                await interaction.followup.send(
                    self.conf['messages']['cleanup_success'].format(count=len(invalid_channels)),
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    self.conf['messages']['cleanup_no_invalid'],
                    ephemeral=True
                )

        except Exception as e:
            logging.error(f"Error cleaning up tickets: {e}")
            await interaction.followup.send(
                self.conf['messages']['cleanup_error'].format(error=str(e)),
                ephemeral=True
            )

    async def is_admin(self, member: discord.Member, ticket_type: str = None) -> bool:
        """Check if a member is an admin for the specified ticket type or globally."""
        current_config = config.get_config('tickets')

        if member.id in current_config.get('admin_users', []):
            return True

        if any(role.id in current_config.get('admin_roles', []) for role in member.roles):
            return True

        if member.guild_permissions.administrator:
            return True

        if ticket_type is None:
            return False

        type_data = current_config['ticket_types'].get(ticket_type)
        if not type_data:
            return False

        if member.id in type_data.get('admin_users', []):
            return True

        if any(role.id in type_data.get('admin_roles', []) for role in member.roles):
            return True

        return False

    async def format_admin_list(self) -> discord.Embed:
        """Format current admin configuration as an embed."""
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            raise ValueError("Could not find configured guild")

        embed = discord.Embed(
            title=self.conf['messages']['admin_list_title'],
            color=discord.Color.blue()
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

        for type_name, type_data in self.conf['ticket_types'].items():
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

    def _format_admin_entries(self, role_ids: list, user_ids: list,
                              guild: discord.Guild) -> str:
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

    async def add_global_admin(self, target_type: str, target_id: int,
                               interaction: discord.Interaction) -> bool:
        """Add a global admin (role or user)."""
        for type_data in self.conf['ticket_types'].values():
            if target_type == 'role':
                if target_id in type_data.get('admin_roles', []):
                    type_data['admin_roles'].remove(target_id)
            else:
                if target_id in type_data.get('admin_users', []):
                    type_data['admin_users'].remove(target_id)

        target_list = 'admin_roles' if target_type == 'role' else 'admin_users'
        if target_id not in self.conf[target_list]:
            self.conf[target_list].append(target_id)
            await self.save_config()
            await self.update_admin_permissions()
            return True
        return False

    async def add_type_admin(self, ticket_type: str, target_type: str,
                             target_id: int, interaction: discord.Interaction) -> bool:
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

        type_data = self.conf['ticket_types'].get(ticket_type)
        if not type_data:
            return False

        target_list = 'admin_roles' if target_type == 'role' else 'admin_users'
        if target_id not in type_data.get(target_list, []):
            if target_list not in type_data:
                type_data[target_list] = []
            type_data[target_list].append(target_id)
            await self.save_config()
            await self.update_admin_permissions()
            return True
        return False

    # Old admin commands commented out to avoid conflicts with new ticket system
    # The new ticket system (TicketsNewCog) now handles all admin commands

    async def remove_global_admin(self, target_type: str, target_id: int,
                                  interaction: discord.Interaction) -> bool:
        """Remove a global admin (role or user)."""
        target_list = 'admin_roles' if target_type == 'role' else 'admin_users'
        if target_id in self.conf[target_list]:
            self.conf[target_list].remove(target_id)
            await self.save_config()
            await self.update_admin_permissions()
            return True
        return False

    async def remove_type_admin(self, ticket_type: str, target_type: str,
                                target_id: int, interaction: discord.Interaction) -> bool:
        """Remove a type-specific admin (role or user)."""
        type_data = self.conf['ticket_types'].get(ticket_type)
        if not type_data:
            return False

        target_list = 'admin_roles' if target_type == 'role' else 'admin_users'
        if target_id in type_data.get(target_list, []):
            type_data[target_list].remove(target_id)
            await self.save_config()
            await self.update_admin_permissions()
            return True
        return False

    # Conflicting admin commands removed - now handled by TicketsNewCog

    async def handle_admin_change_response(self, success: bool, action: str,
                                           target_type: str, target: discord.Object,
                                           ticket_type: str = "global",
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
                    message = messages['admin_add_type'].format(
                        mention=target.mention,
                        type=ticket_type
                    )
            else:
                if ticket_type == "global":
                    message = messages['admin_remove_global'].format(mention=target.mention)
                else:
                    message = messages['admin_remove_type'].format(
                        mention=target.mention,
                        type=ticket_type
                    )
        else:
            if action == 'add':
                message = messages['admin_add_failed'].format(mention=target.mention)
            else:
                message = messages['admin_remove_failed'].format(mention=target.mention)

        await interaction.followup.send(message, ephemeral=True)

        embed = await self.format_admin_list()
        await interaction.followup.send(embed=embed)

    async def save_config(self):
        """Save the current configuration back to the JSON file"""
        config_path = Path('./bot/config/config_tickets.json')

        try:
            async with aiofiles.open(config_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                config_data = json.loads(content)

            config_data.update(self.conf)

            async with aiofiles.open(config_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(config_data, indent=2, ensure_ascii=False))

            self.conf = config.reload_config('tickets')
        except Exception as e:
            logging.error(f"Error saving config: {e}")

    # @app_commands.command(name="tickets_add_type")
    async def add_ticket_type(self, interaction: discord.Interaction):
        """Add a new ticket type"""
        if not await self.check_ticket_channel(interaction):
            return

        modal = TicketTypeModal(self)
        await interaction.response.send_modal(modal)

    # @app_commands.command(name="tickets_edit_type")
    async def edit_ticket_type(self, interaction: discord.Interaction):
        """Edit an existing ticket type"""
        if not await self.check_ticket_channel(interaction):
            return

        view = TypeSelectView(self, 'edit')
        await interaction.response.send_message(
            self.conf['messages']['ticket_type_edit_title'],
            view=view,
            ephemeral=True
        )

    # @app_commands.command(name="tickets_delete_type")
    async def delete_ticket_type(self, interaction: discord.Interaction):
        """Delete a ticket type"""
        if not await self.check_ticket_channel(interaction):
            return

        view = TypeSelectView(self, 'delete')
        await interaction.response.send_message(
            self.conf['messages']['ticket_type_delete_title'],
            view=view,
            ephemeral=True
        )

    async def save_ticket_types(self, ticket_types):
        """Save ticket types to config file"""
        self.conf['ticket_types'] = ticket_types
        config_path = Path('./bot/config/config_tickets.json')

        async with aiofiles.open(config_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(self.conf, indent=2, ensure_ascii=False))

    async def log_action(self, title, description):
        """Log an action to the info channel"""
        channel = self.bot.get_channel(self.ticket_system.info_channel_id)
        if not channel:
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )

        await channel.send(embed=embed)

    async def handle_add_user(self, interaction: discord.Interaction,
                              user: discord.Member, channel_id: Optional[int] = None) -> bool:
        """Handles adding a user to a ticket channel."""
        messages = self.conf['messages']
        channel_id = channel_id or interaction.channel_id

        if await self.db.add_ticket_member(channel_id, user.id, interaction.user.id):
            channel = self.bot.get_channel(channel_id)
            await channel.set_permissions(
                user,
                read_messages=True,
                send_messages=True
            )

            embed = discord.Embed(
                title=messages['add_user_success_title'],
                description=messages['add_user_success_content'].format(
                    user=user.mention,
                    adder=interaction.user.mention
                ),
                color=discord.Color.green()
            )
            await channel.send(embed=embed)

            try:
                user_embed = discord.Embed(
                    title=messages['add_user_dm_title'],
                    description=messages['add_user_dm_content'].format(
                        channel=channel.name
                    ),
                    color=discord.Color.blue()
                )
                view = JumpToChannelView(channel)
                await user.send(embed=user_embed, view=view)
            except discord.Forbidden:
                pass

            await self.logger.log_user_add(
                channel=channel,
                adder=interaction.user,
                user=user
            )

            await interaction.followup.send(
                messages['add_user_success_content'].format(
                    user=user.mention,
                    adder=interaction.user.mention
                ),
                ephemeral=True
            )
            return True
        else:
            error_message = messages['ticket_closed_no_modify']
            if await self.db.check_member_exists(channel_id, user.id):
                error_message = messages['add_user_already_added']

            await interaction.followup.send(error_message, ephemeral=True)
            return False

    # @app_commands.command(
    #     name="tickets_old_add_user",
    #     description="添加用户到当前工单（旧系统）"
    # )
    # @app_commands.describe(
    #     user="要添加的用户"
    # )
    async def ticket_add_user(self, interaction: discord.Interaction, user: discord.Member):
        await interaction.response.defer(ephemeral=True, thinking=False)
        await self.handle_add_user(interaction, user)

    # @app_commands.command(
    #     name="tickets_old_accept",
    #     description="手动接受当前工单（旧系统）"
    # )
    async def accept_ticket(self, interaction: discord.Interaction):
        """Manually accept the current ticket."""
        await interaction.response.defer()

        channel_id = interaction.channel_id
        ticket_status = await self.db.check_ticket_status(channel_id)
        if not ticket_status[0]:
            await interaction.followup.send(
                self.conf['messages']['command_channel_only'],
                ephemeral=True
            )
            return

        ticket_details = await self.db.fetch_ticket(channel_id)
        if not ticket_details:
            await interaction.followup.send(
                self.conf['messages']['ticket_accept_get_info_error'],
                ephemeral=True
            )
            return

        if not await self.is_admin(interaction.user, ticket_details['type_name']):
            await interaction.followup.send(
                self.conf['messages']['ticket_admin_only'],
                ephemeral=True
            )
            return

        if await self.db.accept_ticket(channel_id, interaction.user.id):
            try:
                ticket_details = await self.db.fetch_ticket(channel_id)
                if ticket_details and ticket_details['message_id']:
                    message = await interaction.channel.fetch_message(ticket_details['message_id'])
                    if message:
                        creator = await self.bot.fetch_user(ticket_details['creator_id'])
                        view = TicketControlView(
                            self,
                            interaction.channel,
                            creator,
                            ticket_details['type_name'],
                            is_accepted=True
                        )
                        await message.edit(view=view)
            except discord.NotFound:
                logging.error(f"Could not find control message for ticket {channel_id}")
            except Exception as e:
                logging.error(f"Error updating ticket control panel: {e}")

            embed = discord.Embed(
                title=self.conf['messages']['ticket_accepted_title'],
                description=self.conf['messages']['ticket_accepted_content'].format(
                    user=interaction.user.mention
                ),
                color=discord.Color.green()
            )
            await interaction.channel.send(embed=embed)

            await self.logger.log_ticket_accept(
                channel=interaction.channel,
                acceptor=interaction.user
            )

            await interaction.followup.send(self.conf['messages']['ticket_accepted_title'], ephemeral=True)
        else:
            await interaction.followup.send(
                self.conf['messages']['ticket_already_accepted'],
                ephemeral=True
            )

    # @app_commands.command(
    #     name="tickets_old_close",
    #     description="手动关闭当前工单（旧系统）"
    # )
    # @app_commands.describe(reason="关闭工单的原因")
    async def close_ticket(self, interaction: discord.Interaction, reason: str):
        """Manually close the current ticket."""
        await interaction.response.defer()

        channel_id = interaction.channel_id
        exists, is_closed = await self.db.check_ticket_status(channel_id)
        if not exists:
            await interaction.followup.send(
                self.conf['messages']['command_channel_only'],
                ephemeral=True
            )
            return

        if is_closed:
            await interaction.followup.send(
                self.conf['messages']['ticket_close_stats_error'],
                ephemeral=True
            )
            return

        ticket_info = await self.db.fetch_ticket(channel_id)
        if not ticket_info:
            await interaction.followup.send(
                self.conf['messages']['ticket_close_get_info_error'],
                ephemeral=True
            )
            return

        if await self.db.close_ticket(channel_id, interaction.user.id, reason):
            try:
                creator = await self.bot.fetch_user(ticket_info['creator_id']) if ticket_info['creator_id'] else None

                overwrites = {
                    interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    interaction.guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_channels=True,
                        manage_messages=True
                    ),
                }

                if creator:
                    overwrites[creator] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=False,
                        read_message_history=True
                    )

                members = await self.db.get_ticket_members(channel_id)
                for member_id, _, _ in members:
                    member = interaction.guild.get_member(member_id)
                    if member and member != creator:
                        overwrites[member] = discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=False,
                            read_message_history=True
                        )

                await interaction.channel.edit(overwrites=overwrites)

                try:
                    if ticket_info['message_id']:
                        message = await interaction.channel.fetch_message(ticket_info['message_id'])
                        if message:
                            view = TicketControlView(
                                self,
                                interaction.channel,
                                creator,
                                ticket_info['type_name'],
                                is_accepted=ticket_info['is_accepted']
                            )
                            for item in view.children:
                                if isinstance(item, discord.ui.Button):
                                    item.disabled = True
                            await message.edit(view=view)
                except discord.NotFound:
                    logging.error(f"Could not find control message for ticket {channel_id}")
                except Exception as e:
                    logging.error(f"Error updating ticket control panel: {e}")

                embed = discord.Embed(
                    title=self.conf['messages']['log_ticket_close_title'],
                    description=self.conf['messages']['log_ticket_close_description'].format(
                        closer=interaction.user.mention,
                        reason=reason
                    ),
                    color=discord.Color.red()
                )
                await interaction.channel.send(embed=embed)

                await self.logger.log_ticket_close(
                    channel=interaction.channel,
                    closer=interaction.user,
                    reason=reason
                )

                if creator:
                    try:
                        creator_embed = discord.Embed(
                            title=self.conf['messages']['close_dm_title'],
                            description=self.conf['messages']['close_dm_content'].format(
                                closer=interaction.user.display_name,
                                reason=reason
                            ),
                            color=discord.Color.red()
                        )
                        view = JumpToChannelView(interaction.channel)
                        await creator.send(embed=creator_embed, view=view)
                    except discord.Forbidden:
                        pass

                await interaction.followup.send(self.conf['messages']['ticket_stats_closed'], ephemeral=True)

            except Exception as e:
                logging.error(f"Error closing ticket: {e}")
                await interaction.followup.send(
                    self.conf['messages']['ticket_close_error'],
                    ephemeral=True
                )

    # @app_commands.command(
    #     name="tickets_archive",
    #     description="归档当前分类中所有已关闭的工单"
    # )
    async def archive_tickets(self, interaction: discord.Interaction):
        """Archive closed tickets to files."""
        if not await self.check_ticket_channel(interaction):
            return

        await interaction.response.defer()

        try:
            # Get current channel's category
            current_channel = interaction.channel
            if not current_channel.category:
                await interaction.followup.send(
                    "当前频道不在任何分类中，无法确定要归档的工单范围。",
                    ephemeral=True
                )
                return
            
            category = current_channel.category
            
            # Get all channels in the current category
            category_channel_ids = [channel.id for channel in category.channels if isinstance(channel, discord.TextChannel)]
            
            # Get closed tickets that are in this category
            closed_tickets = await self.db.get_closed_tickets_in_category(category_channel_ids)
            
            if not closed_tickets:
                await interaction.followup.send(
                    f"在分类 `{category.name}` 中没有找到已关闭的工单需要归档。",
                    ephemeral=True
                )
                return

            # Create archive directory if it doesn't exist
            archive_dir = Path("./archive")
            archive_dir.mkdir(exist_ok=True)
            
            archived_count = 0
            total_files_downloaded = 0
            total_files_skipped = 0
            errors = []

            for ticket_data in closed_tickets:
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

                    # Create archive filename
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"ticket_{ticket_number}_{type_name}_{timestamp}.txt"
                    archive_path = archive_dir / filename

                    # Collect ticket information
                    archive_content = []
                    archive_content.append(f"=== 工单归档 #{ticket_number} ===")
                    archive_content.append(f"工单类型: {type_name}")
                    archive_content.append(f"创建者ID: {creator_id}")
                    archive_content.append(f"频道ID: {channel_id}")
                    archive_content.append(f"归档时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    archive_content.append("=" * 50)
                    archive_content.append("")

                    # Create ticket-specific archive subdirectory for files
                    ticket_archive_dir = archive_dir / f"ticket_{ticket_number}_{type_name}_{timestamp}"
                    ticket_archive_dir.mkdir(exist_ok=True)
                    
                    # Get ticket messages and download attachments
                    try:
                        messages = []
                        downloaded_files = []
                        skipped_files = []
                        
                        async for message in channel.history(limit=None, oldest_first=True):
                            timestamp_str = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                            author_info = f"{message.author.display_name} ({message.author.id})"
                            
                            msg_content = f"[{timestamp_str}] {author_info}: {message.content}"
                            
                            # Handle attachments with file download
                            if message.attachments:
                                for attachment in message.attachments:
                                    # Check file size (50MB limit)
                                    max_file_size = 50 * 1024 * 1024  # 50MB in bytes
                                    
                                    if attachment.size <= max_file_size:
                                        try:
                                            # Create safe filename
                                            safe_filename = f"{timestamp_str.replace(':', '-').replace(' ', '_')}_{attachment.filename}"
                                            file_path = ticket_archive_dir / safe_filename
                                            
                                            # Download file
                                            await attachment.save(file_path)
                                            downloaded_files.append(safe_filename)
                                            
                                            msg_content += f"\n    📎 附件: {attachment.filename} (已下载为: {safe_filename})"
                                            msg_content += f"\n        原始URL: {attachment.url}"
                                            msg_content += f"\n        文件大小: {attachment.size / 1024:.1f} KB"
                                            
                                        except Exception as download_error:
                                            msg_content += f"\n    📎 附件: {attachment.filename} (下载失败: {str(download_error)})"
                                            msg_content += f"\n        原始URL: {attachment.url}"
                                            logging.error(f"Failed to download attachment {attachment.filename}: {download_error}")
                                    else:
                                        # File too large, just record URL
                                        skipped_files.append(attachment.filename)
                                        msg_content += f"\n    📎 附件: {attachment.filename} (文件过大: {attachment.size / 1024 / 1024:.1f} MB > 50MB)"
                                        msg_content += f"\n        原始URL: {attachment.url}"
                            
                            # Handle embeds
                            if message.embeds:
                                for embed in message.embeds:
                                    if embed.title:
                                        msg_content += f"\n    📋 嵌入标题: {embed.title}"
                                    if embed.description:
                                        msg_content += f"\n    📋 嵌入描述: {embed.description}"
                                    # Handle embed images
                                    if embed.image:
                                        msg_content += f"\n    📋 嵌入图片: {embed.image.url}"
                                    if embed.thumbnail:
                                        msg_content += f"\n    📋 嵌入缩略图: {embed.thumbnail.url}"
                            
                            messages.append(msg_content)
                        
                        archive_content.extend(messages)
                        
                        # Add file summary
                        if downloaded_files or skipped_files:
                            archive_content.append("")
                            archive_content.append("=== 文件统计 ===")
                            if downloaded_files:
                                archive_content.append("已下载的文件:")
                                for filename in downloaded_files:
                                    archive_content.append(f"  - {filename}")
                            if skipped_files:
                                archive_content.append("跳过的文件 (超过50MB限制):")
                                for filename in skipped_files:
                                    archive_content.append(f"  - {filename}")
                            archive_content.append(f"总计: {len(downloaded_files)} 个文件已下载, {len(skipped_files)} 个文件被跳过")
                        
                        # Update global counters
                        total_files_downloaded += len(downloaded_files)
                        total_files_skipped += len(skipped_files)
                        
                    except Exception as e:
                        archive_content.append(f"错误: 无法获取消息历史 - {str(e)}")

                    # Get ticket members
                    try:
                        members = await self.db.get_ticket_members(channel_id)
                        if members:
                            archive_content.append("")
                            archive_content.append("=== 工单成员 ===")
                            for member_id, added_by, added_at in members:
                                member = self.guild.get_member(member_id)
                                member_name = member.display_name if member else f"用户ID: {member_id}"
                                archive_content.append(f"- {member_name} (由 {added_by} 添加于 {added_at})")
                    except Exception as e:
                        archive_content.append(f"错误: 无法获取工单成员 - {str(e)}")

                    # Write archive file
                    async with aiofiles.open(archive_path, 'w', encoding='utf-8') as f:
                        await f.write('\n'.join(archive_content))

                    archived_count += 1
                    logging.info(f"Archived ticket #{ticket_number} to {archive_path}")

                except Exception as e:
                    errors.append(f"工单 #{ticket_data.get('ticket_number', 'unknown')}: {str(e)}")
                    logging.error(f"Error archiving ticket {ticket_data.get('channel_id')}: {e}")

            # Send result
            result_message = f"✅ 成功归档了分类 `{category.name}` 中的 {archived_count} 个已关闭工单到 `./archive/` 目录。"
            
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
        """Initialize ticket system and guild on bot ready."""
        self.guild = self.bot.get_guild(self.guild_id)
        if not self.guild:
            logging.error("Could not find configured guild")
            return

        self.ticket_system = TicketSystem(self, self.guild)

        is_ready = await self.ticket_system.check_status()
        if not is_ready:
            logging.warning("Ticket system not fully initialized. Use /tickets_setup to initialize.")

        await self.update_admin_permissions()

        active_tickets = await self.db.get_active_tickets()

        for channel_id, message_id, creator_id, type_name, is_accepted in active_tickets:
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    creator = await self.bot.fetch_user(creator_id)
                    type_data = self.conf.get('ticket_types', {}).get(type_name)

                    if type_data and message and creator:
                        view = TicketControlView(
                            self, channel, creator, type_name,
                            is_accepted=is_accepted
                        )
                        await message.edit(view=view)
                        # Add persistent view for ticket control buttons
                        self.bot.add_view(view)
                except discord.NotFound:
                    logging.warning(f"Could not find message {message_id} for ticket {channel_id}")
                except Exception as e:
                    logging.error(f"Error restoring ticket {channel_id}: {e}")

        # Register persistent views for main ticket message
        if self.ticket_system.main_message_id:
            try:
                await self.ticket_system.update_main_message()
                
                # Add persistent view to bot so buttons work after restart
                main_view = TicketMainView(self.ticket_system)
                self.bot.add_view(main_view)
                
            except Exception as e:
                logging.error(f"Failed to update main message: {e}")

        logging.info("Ticket system initialized successfully")

