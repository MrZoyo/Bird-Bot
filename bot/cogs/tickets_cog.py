import sqlite3
import discord
from discord.ext import commands
from discord import app_commands
import logging
import json
from pathlib import Path
import aiofiles
import aiosqlite
from typing import Optional
from datetime import datetime

from bot.utils import config, check_channel_validity, TicketsDatabaseManager

import discord
from typing import Optional, List


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


class TicketEmbed(discord.Embed):
    """Enhanced embed for ticket system messages"""

    def __init__(self, title: str, description: str, color: discord.Color,
                 bot_avatar_url: str, channel_links: Optional[List[tuple]] = None):
        super().__init__(
            title=title,
            description=description,
            color=color,
            timestamp=discord.utils.utcnow()
        )

        self.messages = config.get_config('tickets')['messages']

        # Set footer with bot avatar
        self.set_footer(
            text=self.messages['log_footer_text'],
            icon_url=bot_avatar_url
        )

        # Add channel links as buttons in a view if provided
        self.view = None
        if channel_links:
            self.view = discord.ui.View()
            for label, url in channel_links:
                self.view.add_item(
                    discord.ui.Button(
                        style=discord.ButtonStyle.link,
                        label=label,
                        url=url
                    )
                )


class TicketLogger:
    """Handles ticket system logging with enhanced embeds"""

    def __init__(self, bot, info_channel_id: int, messages: dict):
        self.bot = bot
        self.info_channel_id = info_channel_id
        self.messages = messages
        self.colors = EmbedColors
        self.db = TicketsDatabaseManager(config.get_config('main')['db_path'])

    async def get_ticket_number(self, channel_id: int) -> int:
        """Get ticket number using database manager."""
        return await self.db.get_ticket_number(channel_id)

    async def format_title(self, base_title: str, ticket_number: int = None) -> str:
        """Format log title with ticket number if provided."""
        if ticket_number is not None:
            return f"[Ticket #{ticket_number}] {base_title}"
        return base_title

    async def log_ticket_create(self, ticket_number: int, type_name: str,
                                creator: discord.Member, channel: discord.TextChannel):
        """Log ticket creation"""
        title = await self.format_title(self.messages['log_ticket_create_title'], ticket_number)
        embed = await self._create_base_embed(
            title=title,
            description=self.messages['log_ticket_create_description'].format(
                number=ticket_number,
                type_name=type_name,
                creator=creator.mention
            ),
            color=self.colors.CREATE,
            channel_mentions=[(self.messages['log_ticket_view_button'], channel)]
        )
        await self._send_log(embed)

    async def log_ticket_accept(self, channel: discord.TextChannel,
                                acceptor: discord.Member):
        """Log ticket acceptance"""
        ticket_number = await self.get_ticket_number(channel.id)
        title = await self.format_title(self.messages['log_ticket_accept_title'], ticket_number)
        embed = await self._create_base_embed(
            title=title,
            description=self.messages['log_ticket_accept_description'].format(
                acceptor=acceptor.mention
            ),
            color=self.colors.ACCEPT,
            channel_mentions=[(self.messages['log_ticket_view_button'], channel)]
        )
        await self._send_log(embed)

    async def log_ticket_close(self, channel: discord.TextChannel,
                               closer: discord.Member, reason: str):
        """Log ticket closure"""
        ticket_number = await self.get_ticket_number(channel.id)
        title = await self.format_title(self.messages['log_ticket_close_title'], ticket_number)
        embed = await self._create_base_embed(
            title=title,
            description=self.messages['log_ticket_close_description'].format(
                closer=closer.mention,
                reason=reason
            ),
            color=self.colors.CLOSE,
            channel_mentions=[(self.messages['log_ticket_view_button'], channel)]
        )
        await self._send_log(embed)

    async def log_user_add(self, channel: discord.TextChannel,
                           adder: discord.Member, user: discord.Member):
        """Log user addition to ticket"""
        ticket_number = await self.get_ticket_number(channel.id)
        title = await self.format_title(self.messages['log_user_add_title'], ticket_number)
        embed = await self._create_base_embed(
            title=title,
            description=self.messages['log_user_add_description'].format(
                adder=adder.mention,
                user=user.mention
            ),
            color=self.colors.ADD_USER,
            channel_mentions=[(self.messages['log_ticket_view_button'], channel)]
        )
        await self._send_log(embed)

    async def log_type_add(self, admin: discord.Member, type_data: dict):
        """Log ticket type addition"""
        title = await self.format_title(self.messages['log_type_add_title'])
        embed = await self._create_base_embed(
            title=title,
            description=self.messages['log_type_add_description'].format(
                admin=admin.mention,
                name=type_data['name'],
                description=type_data['description'],
                guide=type_data['guide']
            ),
            color=self.colors.ADD_TYPE
        )
        await self._send_log(embed)

    async def log_type_edit(self, admin: discord.Member,
                            old_type: str, new_type_data: dict):
        """Log ticket type edit"""
        title = await self.format_title(self.messages['log_type_edit_title'])
        embed = await self._create_base_embed(
            title=title,
            description=self.messages['log_type_edit_description'].format(
                admin=admin.mention,
                old_name=old_type,
                new_name=new_type_data['name'],
                description=new_type_data['description'],
                guide=new_type_data['guide']
            ),
            color=self.colors.EDIT_TYPE
        )
        await self._send_log(embed)

    async def log_type_delete(self, admin: discord.Member, type_name: str):
        """Log ticket type deletion"""
        title = await self.format_title(self.messages['log_type_delete_title'])
        embed = await self._create_base_embed(
            title=title,
            description=self.messages['log_type_delete_description'].format(
                admin=admin.mention,
                name=type_name
            ),
            color=self.colors.DELETE_TYPE
        )
        await self._send_log(embed)

    async def _create_base_embed(self, title: str, description: str,
                                 color: discord.Color,
                                 channel_mentions: Optional[List[tuple]] = None) -> TicketEmbed:
        """Create a base embed with consistent styling"""
        bot_avatar_url = str(self.bot.user.avatar.url) if self.bot.user.avatar else str(
            self.bot.user.default_avatar.url)

        # Convert channel mentions to link tuples
        channel_links = None
        if channel_mentions:
            channel_links = [
                (label, f"https://discord.com/channels/{channel.guild.id}/{channel.id}")
                for label, channel in channel_mentions
            ]

        return TicketEmbed(
            title=title,
            description=description,
            color=color,
            bot_avatar_url=bot_avatar_url,
            channel_links=channel_links
        )

    async def _send_log(self, embed: TicketEmbed):
        channel = self.bot.get_channel(self.info_channel_id)
        if not channel:
            logging.error(f"Logging channel with ID {self.info_channel_id} not found.")
            return
        if embed.view:
            await channel.send(embed=embed, view=embed.view)
        else:
            await channel.send(embed=embed)


class TicketTypeModal(discord.ui.Modal):
    def __init__(self, cog, title=None, default_values=None, edit_mode=False, type_key=None, original_message=None):
        messages = cog.conf['messages']
        if edit_mode:
            title = messages['ticket_type_modal_edit_title'].format(type_name=type_key)
        else:
            title = messages['ticket_type_modal_title']

        super().__init__(title=title)
        self.cog = cog
        self.edit_mode = edit_mode
        self.type_key = type_key
        self.original_message = original_message

        # Create form inputs
        self.type_name = discord.ui.TextInput(
            label=messages['ticket_type_name_label'],
            placeholder=messages['ticket_type_name_placeholder'],
            required=True,
            max_length=50,
            default=default_values['name'] if default_values else None
        )

        self.type_description = discord.ui.TextInput(
            label=messages['ticket_type_description_label'],
            placeholder=messages['ticket_type_description_placeholder'],
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1024,
            default=default_values['description'] if default_values else None
        )

        self.user_guide = discord.ui.TextInput(
            label=messages['ticket_type_guide_label'],
            placeholder=messages['ticket_type_guide_placeholder'],
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=1024,
            default=default_values['guide'] if default_values else None
        )

        self.button_color = discord.ui.TextInput(
            label=messages['ticket_type_color_label'],
            placeholder=messages['ticket_type_color_placeholder'],
            required=True,
            max_length=5,
            default=default_values.get('button_color') if default_values else "B"
        )

        self.add_item(self.type_name)
        self.add_item(self.type_description)
        self.add_item(self.user_guide)
        self.add_item(self.button_color)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Get ticket types from config
        ticket_types = self.cog.conf.get('ticket_types', {})
        type_name = self.type_name.value.strip()

        if self.edit_mode and self.type_key:
            # Keep existing admin settings when editing
            old_type_name = self.type_key
            old_admin_roles = ticket_types[old_type_name].get('admin_roles', [])
            old_admin_users = ticket_types[old_type_name].get('admin_users', [])

            if old_type_name != type_name:
                ticket_types.pop(old_type_name, None)

            # Record edit operation
            await self.cog.logger.log_type_edit(
                admin=interaction.user,
                old_type=old_type_name,
                new_type_data={
                    'name': type_name,
                    'description': self.type_description.value.strip(),
                    'guide': self.user_guide.value.strip()
                }
            )
        else:
            # Initialize empty admin lists for new types
            old_admin_roles = []
            old_admin_users = []

            # Record add operation
            await self.cog.logger.log_type_add(
                admin=interaction.user,
                type_data={
                    'name': type_name,
                    'description': self.type_description.value.strip(),
                    'guide': self.user_guide.value.strip()
                }
            )

        # Update or create ticket type with admin settings
        ticket_types[type_name] = {
            'name': type_name,
            'description': self.type_description.value.strip(),
            'guide': self.user_guide.value.strip(),
            'button_color': self.button_color.value.strip().lower(),
            'admin_roles': old_admin_roles,  # Preserve or initialize admin settings
            'admin_users': old_admin_users
        }

        # Save config and update main message
        await self.cog.save_ticket_types(ticket_types)
        if self.cog.ticket_system:
            await self.cog.ticket_system.update_main_message()

        # Send confirmation message
        await interaction.followup.send(
            f"Tickets type {'updated' if self.edit_mode else 'added'}: {type_name}",
            ephemeral=True
        )

        # Clean up original message if editing
        if self.original_message:
            try:
                await self.original_message.delete()
            except discord.NotFound:
                pass
            except Exception as e:
                logging.error(f"Error deleting selection message after edit: {e}")


class TypeSelectMenu(discord.ui.Select):
    def __init__(self, cog, action):
        self.cog = cog
        self.action = action
        self.messages = cog.conf['messages']
        ticket_types = cog.conf.get('ticket_types', {})

        options = [
            discord.SelectOption(
                label=type_data['name'],
                description=type_data['description'][:100],
                value=type_name
            ) for type_name, type_data in ticket_types.items()
        ]

        super().__init__(
            placeholder=self.messages['ticket_type_select_placeholder'],
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_type = self.values[0]
        original_message = interaction.message

        if self.action == 'delete':
            ticket_types = self.cog.conf.get('ticket_types', {})

            if selected_type in ticket_types:
                # 为删除操作延迟响应
                await interaction.response.defer(ephemeral=True)

                # 删除工单类型
                ticket_types.pop(selected_type)
                await self.cog.save_ticket_types(ticket_types)
                await self.cog.ticket_system.update_main_message()

                # 记录删除操作
                await self.cog.logger.log_type_delete(
                    admin=interaction.user,
                    type_name=selected_type
                )

                # 发送确认消息
                await interaction.followup.send(
                    self.messages['ticket_type_delete_success'].format(type_name=selected_type),
                    ephemeral=True
                )

                # 在所有操作完成后删除选择菜单消息
                try:
                    await original_message.delete()
                except discord.NotFound:
                    pass
                except Exception as e:
                    logging.error(f"Error deleting selection message: {e}")

        elif self.action == 'edit':
            ticket_types = self.cog.conf.get('ticket_types', {})
            type_data = ticket_types.get(selected_type)

            if type_data:
                # 创建模态框并添加原始消息引用
                modal = TicketTypeModal(
                    self.cog,
                    default_values=type_data,
                    edit_mode=True,
                    type_key=selected_type,
                    original_message=original_message  # 传递原始消息引用
                )
                await interaction.response.send_modal(modal)


class TypeSelectView(discord.ui.View):
    def __init__(self, cog, action):
        super().__init__()
        self.add_item(TypeSelectMenu(cog, action))


class TicketView(discord.ui.View):
    def __init__(self, ticket_system, ticket_types):
        super().__init__(timeout=None)
        self.ticket_system = ticket_system

        # Add button for each ticket type, using custom colors
        for type_name, type_data in ticket_types.items():
            self.add_item(TicketButton(ticket_system, type_name, type_data))


class TicketSystem:
    """Manages the core ticket system infrastructure"""

    def __init__(self, cog, guild):
        self.guild = guild
        self.cog = cog
        self.main_config = config.get_config('main')
        self.db_path = self.main_config.get('db_path')

        self.conf = config.get_config('tickets')

        # Message content
        self.messages = self.conf['messages']

        # Status tracking
        self.is_ready = False

        # 基础频道和消息ID
        self.create_channel_id = self.conf.get('create_channel_id')
        self.info_channel_id = self.conf.get('info_channel_id')
        self.main_message_id = self.conf.get('main_message_id')

        # 使用列表存储多个分类ID
        self.open_categories = self.conf.get('open_categories', [])
        self.closed_categories = self.conf.get('closed_categories', [])
        self.category_channel_limit = self.conf.get('category_channel_limit', 50)  # 每个分类的频道上限

    async def create_new_category(self, is_closed: bool) -> discord.CategoryChannel:
        """创建新的工单分类"""
        categories = self.closed_categories if is_closed else self.open_categories
        base_name = "Closed Tickets" if is_closed else "Open Tickets"

        # 确定新分类的序号
        suffix = len(categories) + 1 if categories else ""
        category_name = f"{base_name} {suffix}".strip()

        # 获取position
        reference_category = None
        if categories:
            reference_category = self.guild.get_channel(categories[0])

        try:
            # 创建新分类
            category = await self.guild.create_category(
                name=category_name,
                overwrites={
                    self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    self.guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        manage_channels=True,
                        manage_permissions=True
                    )
                }
            )

            # 设置position
            if reference_category:
                try:
                    await category.move(after=reference_category)
                except discord.HTTPException as e:
                    logging.error(f"Failed to move category {category.name}: {e}")

            # 添加到配置
            await self.add_category(category, is_closed)

            return category

        except discord.HTTPException as e:
            logging.error(f"Failed to create category {category_name}: {e}")
            raise

    async def get_available_category(self, is_closed: bool) -> discord.CategoryChannel:
        """获取可用的工单分类（未满的最小序号分类）"""
        # 先运行清理检查
        await self.check_and_clean_invalid_components()

        categories = self.closed_categories if is_closed else self.open_categories

        # 检查现有分类
        for category_id in categories:
            category = self.guild.get_channel(category_id)
            if category and len(category.channels) < self.category_channel_limit:
                return category

        # 如果没有可用分类或所有分类都满了，创建新分类
        try:
            return await self.create_new_category(is_closed)
        except Exception as e:
            logging.error(f"Failed to create new category: {e}")
            raise

    async def setup_system(self):
        """完整的系统设置流程"""
        # 首先清理无效组件
        invalid_components, config_changed = await self.check_and_clean_invalid_components()

        messages = self.conf['messages']
        component_names = {
            'create_channel': messages.get('component_name_create_channel', '工单创建频道'),
            'info_channel': messages.get('component_name_info_channel', '工单日志频道'),
            'open_category': messages.get('component_name_open_category', '开放工单分类'),
            'closed_category': messages.get('component_name_closed_category', '已关闭工单分类'),
            'main_message': messages.get('component_name_main_message', '工单主消息')
        }

        new_components = {}

        # 检查创建频道
        if self.create_channel_id:
            channel = self.guild.get_channel(self.create_channel_id)
            if not channel:
                self.create_channel_id = None
                config_changed = True

        # 检查信息频道
        if self.info_channel_id:
            channel = self.guild.get_channel(self.info_channel_id)
            if not channel:
                self.info_channel_id = None
                config_changed = True

        # 检查主消息
        if self.main_message_id:
            try:
                channel = self.guild.get_channel(self.create_channel_id)
                if channel:
                    await channel.fetch_message(self.main_message_id)
                else:
                    self.main_message_id = None
                    config_changed = True
            except discord.NotFound:
                self.main_message_id = None
                config_changed = True

        # 创建缺失的组件
        if not self.create_channel_id:
            channel, message_id = await self.create_ticket_channel()
            if channel:
                self.create_channel_id = channel.id
                config_changed = True
                new_components[component_names['create_channel']] = channel.id
                if message_id:
                    self.main_message_id = message_id
                    new_components[component_names['main_message']] = message_id

        if not self.info_channel_id:
            channel = await self.create_info_channel()
            if channel:
                self.info_channel_id = channel.id
                config_changed = True
                new_components[component_names['info_channel']] = channel.id

        # 检查分类是否存在且有效
        if not self.open_categories or not any(self.guild.get_channel(cat_id) for cat_id in self.open_categories):
            category = await self.create_new_category(is_closed=False)
            if category:
                config_changed = True
                new_components[f"{component_names['open_category']} 1"] = category.id

        if not self.closed_categories or not any(self.guild.get_channel(cat_id) for cat_id in self.closed_categories):
            category = await self.create_new_category(is_closed=True)
            if category:
                config_changed = True
                new_components[f"{component_names['closed_category']} 1"] = category.id

        # 确保主消息存在
        if not self.main_message_id and 'main_message' not in new_components:
            message = await self.create_initial_message()
            if message:
                self.main_message_id = message.id
                config_changed = True
                new_components[component_names['main_message']] = message.id

        # 如果配置有变化，保存更新
        if config_changed:
            await self.save_config()

        # 返回初始化报告
        report = {
            'invalid_components': invalid_components,
            'new_components': new_components,
            'config_changed': config_changed
        }

        return report

    async def check_and_clean_invalid_components(self):
        """更新的组件检查方法，包含分类管理功能"""
        invalid_components = []
        config_changed = False

        # 检查并清理无效的开放工单分类
        valid_open_categories = []
        for category_id in self.open_categories:
            category = self.guild.get_channel(category_id)
            if category and isinstance(category, discord.CategoryChannel):
                valid_open_categories.append(category_id)
            else:
                invalid_components.append((f"开放工单分类 {len(valid_open_categories) + 1}", category_id))
                config_changed = True

        # 检查并清理无效的关闭工单分类
        valid_closed_categories = []
        for category_id in self.closed_categories:
            category = self.guild.get_channel(category_id)
            if category and isinstance(category, discord.CategoryChannel):
                valid_closed_categories.append(category_id)
            else:
                invalid_components.append((f"已关闭工单分类 {len(valid_closed_categories) + 1}", category_id))
                config_changed = True

        # 更新配置
        if len(valid_open_categories) != len(self.open_categories):
            self.open_categories = valid_open_categories
            self.conf['open_categories'] = valid_open_categories
            config_changed = True

        if len(valid_closed_categories) != len(self.closed_categories):
            self.closed_categories = valid_closed_categories
            self.conf['closed_categories'] = valid_closed_categories
            config_changed = True

        return invalid_components, config_changed

    async def add_category(self, category: discord.CategoryChannel, is_closed: bool):
        """将新的分类添加到配置中"""
        # 先运行清理检查
        await self.check_and_clean_invalid_components()

        # 添加新分类ID到相应的列表
        if is_closed:
            if category.id not in self.closed_categories:
                self.closed_categories.append(category.id)
                self.conf['closed_categories'] = self.closed_categories
                await self.save_config()
        else:
            if category.id not in self.open_categories:
                self.open_categories.append(category.id)
                self.conf['open_categories'] = self.open_categories
                await self.save_config()

        return True

    async def create_ticket_channel(self):
        """Create the ticket creation channel with proper permissions"""
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=False,
                add_reactions=False
            ),
            self.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_messages=True,
                manage_channels=True,
                add_reactions=True
            )
        }

        channel = await self.guild.create_text_channel(
            name="create-ticket",
            overwrites=overwrites
        )
        self.create_channel_id = channel.id
        self.conf['create_channel_id'] = channel.id  # 更新配置

        # 立即创建初始消息并获取消息对象
        message = await self.create_initial_message()
        if message:
            self.main_message_id = message.id
            self.conf['main_message_id'] = message.id  # 更新配置

        # 保存配置
        await self.save_config()

        # 返回创建的频道和消息ID
        return channel, message.id if message else None

    async def create_info_channel(self):
        """Create the ticket information channel with proper permissions"""
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            self.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_messages=True,
                manage_channels=True
            )
        }

        channel = await self.guild.create_text_channel(
            name="ticket-logs",
            overwrites=overwrites
        )
        self.info_channel_id = channel.id
        self.conf['info_channel_id'] = channel.id  # 更新配置
        await self.save_config()
        return channel

    async def create_initial_message(self):
        """Create the initial ticket system message"""
        if not self.create_channel_id:
            return None

        channel = self.guild.get_channel(self.create_channel_id)
        if not channel:
            return None

        # Use values from the configuration
        messages = self.conf.get('messages', {})
        ticket_types = self.conf.get('ticket_types', {})

        title = messages.get('ticket_main_title', "工单系统")
        description = messages.get('ticket_main_description', "有问题或者建议？在这里你可以：")
        footer = messages.get('ticket_main_footer', "-----------点击下方按钮开始创建对应工单-----------")

        # Get the bot's avatar URL
        bot_avatar_url = self.guild.me.avatar.url if self.guild.me.avatar else self.bot.user.default_avatar.url

        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )

        # 添加所有工单类型的描述
        for type_name, type_data in ticket_types.items():
            embed.add_field(
                name=type_name,
                value=type_data['description'],
                inline=False
            )

        embed.set_footer(text=footer)
        embed.set_thumbnail(url=bot_avatar_url)  # Add bot avatar as thumbnail

        # Create the TicketView with ticket_system and ticket_types
        view = TicketView(self, ticket_types)

        message = await channel.send(embed=embed, view=view)
        self.main_message_id = message.id
        self.conf['main_message_id'] = message.id  # 更新配置
        await self.save_config()
        return message

    async def update_main_message(self):
        """Update the main ticket message"""
        channel = self.guild.get_channel(self.create_channel_id)
        if not channel:
            logging.error(f"Could not find channel with ID {self.create_channel_id}")
            return None

        try:
            message = await channel.fetch_message(self.main_message_id)
        except discord.NotFound:
            # If the message doesn't exist, create a new one
            logging.info("Main message not found, creating new one")
            return await self.create_initial_message()
        except Exception as e:
            logging.error(f"Error fetching main message: {e}")
            return None

        # Use updated configuration values for the message
        messages = self.conf.get('messages', {})
        ticket_types = self.conf.get('ticket_types', {})

        title = messages.get('ticket_main_title', "联系我们")
        description = messages.get('ticket_main_description', "有问题或者建议？在这里你可以：")
        footer = messages.get('ticket_main_footer', "-----------点击下方按钮开始创建对应工单-----------")

        # Get the bot's avatar URL
        bot_avatar_url = self.guild.me.avatar.url if self.guild.me.avatar else self.guild.me.default_avatar.url

        # Update the embed
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blue()
        )

        # Add fields for each ticket type
        embed.clear_fields()

        for type_name, type_data in ticket_types.items():
            embed.add_field(
                name=type_name,
                value=type_data['description'],
                inline=False
            )

        embed.set_footer(text=footer)
        embed.set_thumbnail(url=bot_avatar_url)

        # Create view with ticket buttons
        view = TicketView(self, ticket_types)

        try:
            await message.edit(embed=embed, view=view)
        except Exception as e:
            logging.error(f"Failed to edit main message: {e}")
            return None

        return message

    async def save_config(self):
        """Save the current configuration back to the JSON file and reload it"""
        config_path = Path('./bot/config/config_tickets.json')

        try:
            async with aiofiles.open(config_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                config_data = json.loads(content)

            # 更新所有ID相关的配置
            config_data.update({
                'create_channel_id': self.create_channel_id,
                'info_channel_id': self.info_channel_id,
                'open_categories': self.open_categories,
                'closed_categories': self.closed_categories,
                'category_channel_limit': self.category_channel_limit,
                'main_message_id': self.main_message_id
            })

            async with aiofiles.open(config_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(config_data, indent=2, ensure_ascii=False))

            # 重新加载配置
            self.conf = config.reload_config('tickets')

            # 更新logger的channel ID
            if hasattr(self.cog, 'logger'):
                self.cog.logger = TicketLogger(
                    self.cog.bot,
                    self.conf['info_channel_id'],
                    self.conf['messages']
                )

        except Exception as e:
            logging.error(f"Error saving ticket system config: {e}")
            raise

    async def get_next_ticket_number(self):
        """Generate the next ticket number."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('SELECT COUNT(*) FROM tickets')
                count = await cursor.fetchone()
                return (count[0] if count else 0) + 1
        except Exception as e:
            logging.error(f"Error getting next ticket number: {e}")
            return 1

    async def check_status(self) -> bool:
        """检查工单系统状态"""
        # 检查必要的频道
        if not self.create_channel_id or not self.info_channel_id:
            logging.warning("Ticket system not fully initialized. Use /tickets_setup to initialize.")
            return False

        # 检查分类
        if not self.open_categories or not self.closed_categories:
            logging.warning("Ticket categories not initialized. Use /tickets_setup to initialize.")
            return False

        # 检查主消息
        if not self.main_message_id:
            logging.warning("Ticket main message not initialized. Use /tickets_setup to initialize.")
            return False

        # 检查组件有效性
        invalid_components, _ = await self.check_and_clean_invalid_components()
        if invalid_components:
            logging.warning("Found invalid ticket system components:")
            for name, id in invalid_components:
                logging.warning(f"- {name}: {id}")
            logging.warning("Ticket system not fully initialized. Use /tickets_setup to initialize.")
            return False

        logging.info("Ticket system initialized successfully")
        return True


class TicketConfirmView(discord.ui.View):
    def __init__(self, ticket_system, type_name, type_data):
        super().__init__(timeout=60)
        self.ticket_system = ticket_system
        self.type_name = type_name
        self.type_data = type_data
        self.messages = self.ticket_system.conf['messages']

        # 添加确认和取消按钮
        confirm_button = discord.ui.Button(
            style=discord.ButtonStyle.green,
            label=self.messages['ticket_create_confirm_button']
        )
        confirm_button.callback = self.confirm

        cancel_button = discord.ui.Button(
            style=discord.ButtonStyle.grey,
            label=self.messages['ticket_create_cancel_button']
        )
        cancel_button.callback = self.cancel

        self.add_item(confirm_button)
        self.add_item(cancel_button)

    async def cancel(self, interaction: discord.Interaction):
        """Handle cancellation of ticket creation"""
        await interaction.response.edit_message(
            content=self.messages['ticket_create_cancelled'],
            view=None
        )

    async def confirm(self, interaction: discord.Interaction):
        """Handle the confirmation of ticket creation"""
        await interaction.response.defer()

        # Get the next available ticket number
        ticket_number = await self.ticket_system.get_next_ticket_number()
        channel_name = f"ticket-{ticket_number}"

        # Set up base permissions for the new ticket channel
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True
            ),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )
        }

        # Add global admin role permissions
        for role_id in self.ticket_system.conf.get('admin_roles', []):
            role = interaction.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )

        # Add global admin user permissions
        for user_id in self.ticket_system.conf.get('admin_users', []):
            member = interaction.guild.get_member(user_id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )

        # Add type-specific admin role permissions
        type_data = self.ticket_system.conf['ticket_types'].get(self.type_name, {})
        for role_id in type_data.get('admin_roles', []):
            role = interaction.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )

        # Add type-specific admin user permissions
        for user_id in type_data.get('admin_users', []):
            member = interaction.guild.get_member(user_id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )

        # 获取可用分类
        try:
            category = await self.ticket_system.get_available_category(is_closed=False)
        except Exception as e:
            await interaction.followup.send(
                "Failed to get or create category for the ticket. Please contact administrators.",
                ephemeral=True
            )
            logging.error(f"Failed to get category for ticket: {e}")
            return

        # 创建频道
        try:
            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites  # 使用更新后的权限设置
            )
        except discord.HTTPException as e:
            await interaction.followup.send(
                "Failed to create ticket channel. Please try again later.",
                ephemeral=True
            )
            logging.error(f"Failed to create ticket channel: {e}")
            return

        # Create initial message and control panel
        embed = discord.Embed(
            title=self.messages['ticket_created_title'].format(
                number=ticket_number,
                type_name=self.type_name
            ),
            description=self.type_data['guide'],
            color=discord.Color.blue()
        )

        # 添加创建者和时间信息
        embed.add_field(
            name="创建者",
            value=f"{interaction.user.mention}",
            inline=True
        )
        embed.add_field(
            name="创建时间",
            value=f"<t:{int(datetime.now().timestamp())}:F>",
            inline=True
        )

        embed.add_field(
            name=self.messages['ticket_instructions_title'],
            value=self.messages['ticket_instructions'],
            inline=False
        )

        # Create control panel view and send message
        view = TicketControlView(
            self.ticket_system.cog,
            channel,
            interaction.user,
            self.type_name
        )
        message = await channel.send(embed=embed, view=view)

        # Create ticket in database
        db = self.ticket_system.cog.db
        if await db.create_ticket(
                channel_id=channel.id,
                message_id=message.id,
                creator_id=interaction.user.id,
                type_name=self.type_name
        ):
            # Send notifications
            await interaction.edit_original_response(
                content=self.messages['ticket_create_success'].format(channel=channel.mention),
                view=None
            )

            # Log notification
            await self.ticket_system.cog.logger.log_ticket_create(
                ticket_number=ticket_number,
                type_name=self.type_name,
                creator=interaction.user,
                channel=channel
            )
            admins_to_notify = set()  # 使用集合避免重复

            # 添加全局管理员
            for user_id in self.ticket_system.conf.get('admin_users', []):
                admins_to_notify.add(user_id)

            # 添加拥有全局管理员角色的用户
            for role_id in self.ticket_system.conf.get('admin_roles', []):
                role = interaction.guild.get_role(role_id)
                if role:
                    for member in role.members:
                        admins_to_notify.add(member.id)

            # 添加类型特定管理员
            type_data = self.ticket_system.conf['ticket_types'].get(self.type_name, {})
            for user_id in type_data.get('admin_users', []):
                admins_to_notify.add(user_id)

            # 添加拥有类型特定管理员角色的用户
            for role_id in type_data.get('admin_roles', []):
                role = interaction.guild.get_role(role_id)
                if role:
                    for member in role.members:
                        admins_to_notify.add(member.id)

            # 创建管理员通知嵌入消息
            admin_embed = discord.Embed(
                title=self.messages['log_ticket_create_title'],
                description=self.messages['log_ticket_create_description'].format(
                    number=ticket_number,
                    type_name=self.type_name,
                    creator=interaction.user.mention
                ),
                color=discord.Color.blue()
            )

            # 创建跳转按钮视图
            view = JumpToChannelView(channel)

            # 发送通知给所有管理员
            for admin_id in admins_to_notify:
                try:
                    admin_user = await self.ticket_system.cog.bot.fetch_user(admin_id)
                    if admin_user:
                        try:
                            await admin_user.send(embed=admin_embed, view=view)
                        except discord.Forbidden:
                            # 用户可能关闭了私信
                            continue
                        except Exception as e:
                            logging.error(f"Failed to send notification to admin {admin_id}: {e}")
                except discord.NotFound:
                    logging.warning(f"Could not find admin user with ID {admin_id}")
                    continue

            # DM notification
            try:
                creator_embed = discord.Embed(
                    title=self.messages['ticket_created_dm_title'],
                    description=self.messages['ticket_created_dm_content'].format(
                        number=ticket_number,
                        type_name=self.type_name
                    ),
                    color=discord.Color.blue()
                )
                view = JumpToChannelView(channel)
                await interaction.user.send(embed=creator_embed, view=view)
            except discord.Forbidden:
                pass  # User has DMs disabled
        else:
            # Handle creation failure
            await channel.delete()
            await interaction.edit_original_response(
                content="Failed to create ticket. Please try again.",
                view=None
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


class TicketButton(discord.ui.Button):
    def __init__(self, ticket_system, type_name, type_data):
        color = type_data.get('button_color', 'b').lower()  # Default to blue if not provided
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
        # Determine the button style based on the color value
        if color_value in ['r', 'red', 'R', 'RED', 'Red']:
            return discord.ButtonStyle.danger
        elif color_value in ['g', 'green', 'G', 'GREEN', 'Green']:
            return discord.ButtonStyle.success
        elif color_value in ['b', 'blue', 'B', 'BLUE', 'Blue']:
            return discord.ButtonStyle.primary
        else:
            return discord.ButtonStyle.secondary

    async def callback(self, interaction: discord.Interaction):
        # Use the correct initialization for TicketConfirmView with the expected arguments
        await interaction.response.send_message(
            self.messages['ticket_create_confirm'].format(type_name=self.type_name),
            view=TicketConfirmView(self.ticket_system, self.type_name, self.type_data),
            ephemeral=True,
            delete_after=10,
        )


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

        # Check if user is admin
        if not await self.cog.is_admin(interaction.user):
            await interaction.followup.send(self.messages['ticket_admin_only'], ephemeral=True)
            return

        # Try to accept the ticket using database manager
        if await self.cog.db.accept_ticket(self.channel.id, interaction.user.id):
            # Update button state
            self.accept_button.style = discord.ButtonStyle.success
            self.accept_button.label = self.messages['ticket_accept_button_disabled']
            self.accept_button.disabled = True

            # Channel notification
            embed = discord.Embed(
                title=self.messages['ticket_accepted_title'],
                description=self.messages['ticket_accepted_content'].format(user=interaction.user.mention),
                color=discord.Color.green()
            )
            await self.channel.send(embed=embed)

            # DM notification
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

            # Log action
            await self.cog.logger.log_ticket_accept(
                channel=self.channel,
                acceptor=interaction.user
            )

            # Update the message view
            await interaction.message.edit(
                view=TicketControlView(
                    self.cog,
                    self.channel,
                    self.creator,
                    self.type_name,
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

            # Convert user to member
            member = interaction.guild.get_member(user.id)
            if not member:
                await interaction.followup.send(self.messages['add_user_not_found'], ephemeral=True)
                return

            # Use the shared add user logic
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

        # 获取工单接受状态
        async with aiosqlite.connect(self.cog.db_path) as db:
            cursor = await db.execute(
                'SELECT is_accepted FROM tickets WHERE channel_id = ?',
                (self.ticket_channel.id,)
            )
            result = await cursor.fetchone()
            is_accepted = result[0] if result else False

        try:
            # 获取可用的已关闭工单分类
            closed_category = await self.cog.ticket_system.get_available_category(is_closed=True)
        except Exception as e:
            await interaction.followup.send(
                self.messages['ticket_category_get_closed_error'],
                ephemeral=True
            )
            logging.error(f"Failed to get closed category for ticket: {e}")
            return

        # 关闭工单
        if await self.cog.db.close_ticket(self.ticket_channel.id, interaction.user.id, self.reason.value):
            # 获取工单成员
            members = await self.cog.db.get_ticket_members(self.ticket_channel.id)

            # 更新权限
            overwrites = {
                # 基础权限
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_channels=True,
                    manage_messages=True
                ),
                # 创建者可以查看但不能发消息
                self.creator: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    read_message_history=True
                )
            }

            # 添加全局管理员权限
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

            # 添加类型特定管理员权限
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

            # 添加工单成员权限（只能查看，不能发消息）
            for member_id, added_by, added_at in members:
                member = interaction.guild.get_member(member_id)
                if member and member != self.creator:  # 创建者的权限已经设置过
                    overwrites[member] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=False,
                        read_message_history=True
                    )

            try:
                # 更新频道设置
                await self.ticket_channel.edit(
                    category=closed_category,
                    overwrites=overwrites
                )
            except discord.HTTPException as e:
                await interaction.followup.send(
                    self.messages['ticket_category_move_to_closed_error'],
                    ephemeral=True
                )
                logging.error(f"Failed to move ticket to closed category: {e}")
                return

            # 发送频道通知
            embed = discord.Embed(
                title=self.messages['log_ticket_close_title'],
                description=self.messages['log_ticket_close_description'].format(
                    closer=interaction.user.mention,
                    reason=self.reason.value
                ),
                color=discord.Color.red()
            )
            await self.ticket_channel.send(embed=embed)

            # 更新控制面板按钮
            view = TicketControlView(self.cog, self.ticket_channel, self.creator, self.type_name,
                                     is_accepted=is_accepted)
            for item in view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
                    # 如果是接受按钮，根据工单状态设置样式
                    if item.custom_id and item.custom_id.startswith('accept_'):
                        if is_accepted:
                            item.style = discord.ButtonStyle.success
                            item.label = self.messages['ticket_accept_button_disabled']
                        else:
                            item.style = discord.ButtonStyle.primary
                            item.label = self.messages['ticket_accept_button']

            try:
                message = await self.ticket_channel.fetch_message(interaction.message.id)
                await message.edit(view=view)
            except discord.NotFound:
                pass

            # 发送DM通知
            try:
                creator_embed = discord.Embed(
                    title=self.messages['close_dm_title'],
                    description=self.messages['close_dm_content'].format(
                        closer=interaction.user.display_name,
                        reason=self.reason.value
                    ),
                    color=discord.Color.red()
                )
                view = JumpToChannelView(self.ticket_channel)
                await self.creator.send(embed=creator_embed, view=view)
            except discord.Forbidden:
                pass

            # 记录操作
            await self.cog.logger.log_ticket_close(
                channel=self.ticket_channel,
                closer=interaction.user,
                reason=self.reason.value
            )


class AdminTypeSelectView(discord.ui.View):
    def __init__(self, cog, action_type, target_type, target_id):
        super().__init__()
        self.cog = cog
        self.action_type = action_type  # 'add' or 'remove'
        self.target_type = target_type  # 'role' or 'user'
        self.target_id = target_id
        self.messages = self.cog.conf['messages']

        # Create select menu for ticket types
        options = [
            discord.SelectOption(
                label=self.messages['global_ticket_select_label'],
                description=self.messages['global_ticket_select_description'],
                value="global"
            )
        ]

        # Add options for each ticket type
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

        # Get the target object (role or user)
        if self.target_type == 'role':
            target = interaction.guild.get_role(self.target_id)
        else:
            target = await self.cog.bot.fetch_user(self.target_id)

        if not target:
            await interaction.followup.send(self.messages['target_not_found'], ephemeral=True)
            return

        if selected_type == "global":
            # Handle global admin changes
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
            # Handle type-specific admin changes
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

        # Handle response
        await self.cog.handle_admin_change_response(
            success,
            self.action_type,
            self.target_type,
            target,
            selected_type,
            interaction
        )


class TicketsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.main_config = config.get_config('main')
        self.conf = config.get_config('tickets')
        self.db_path = self.main_config['db_path']
        self.guild_id = self.main_config['guild_id']  # 从配置中获取 guild_id
        self.guild = None  # 初始化为 None，在 on_ready 中设置
        self.ticket_system = None
        self.db = TicketsDatabaseManager(self.db_path)
        self.logger = TicketLogger(bot, self.conf['info_channel_id'], self.conf['messages'])

    async def cog_load(self):
        """Initialize the cog and database."""
        await self.db.initialize_database()

    async def check_ticket_channel(self, interaction):
        """Check if command is used in the ticket creation channel"""
        # If no channel is set up yet, allow command in admin channel for initial setup
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

        # Get info channel
        info_channel = self.guild.get_channel(self.ticket_system.info_channel_id)
        if not info_channel:
            return

        # Collect all admin overwrites for info channel
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            self.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True
            )
        }

        # Add role overwrites for info channel
        for role_id in self.conf.get('admin_roles', []):
            role = self.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_messages=True
                )

        # Add user overwrites for info channel
        for user_id in self.conf.get('admin_users', []):
            member = self.guild.get_member(user_id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_messages=True
                )

        # Update info channel permissions
        await info_channel.edit(overwrites=overwrites)

        # Get all active tickets using existing database method
        active_tickets = await self.db.get_active_tickets()

        # Update permissions for all active ticket channels
        for channel_id, _, _, type_name, _ in active_tickets:
            channel = self.guild.get_channel(channel_id)
            if not channel:
                continue

            # Get existing overwrites and update them
            channel_overwrites = dict(channel.overwrites)

            # Ensure default role and bot permissions
            channel_overwrites[self.guild.default_role] = discord.PermissionOverwrite(view_channel=False)
            channel_overwrites[self.guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True
            )

            # Add global admin roles
            for role_id in self.conf.get('admin_roles', []):
                role = self.guild.get_role(role_id)
                if role:
                    channel_overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

            # Add global admin users
            for user_id in self.conf.get('admin_users', []):
                member = self.guild.get_member(user_id)
                if member:
                    channel_overwrites[member] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

            # Add type-specific admin roles
            type_data = self.conf['ticket_types'].get(type_name, {})
            for role_id in type_data.get('admin_roles', []):
                role = self.guild.get_role(role_id)
                if role:
                    channel_overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

            # Add type-specific admin users
            for user_id in type_data.get('admin_users', []):
                member = self.guild.get_member(user_id)
                if member:
                    channel_overwrites[member] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

            try:
                await channel.edit(overwrites=channel_overwrites)
            except discord.HTTPException as e:
                logging.error(f"Failed to update permissions for channel {channel.id}: {e}")

        logging.info(f"Updated permissions for {len(active_tickets)} active tickets")

    @app_commands.command(
        name="tickets_setup",
        description="Initialize the ticket system"
    )
    async def ticket_setup(self, interaction: discord.Interaction):
        """Initialize the ticket system."""
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # 运行完整的设置流程
            setup_report = await self.ticket_system.setup_system()

            # 准备响应消息
            response_parts = []
            messages = self.conf['messages']

            # 报告无效组件
            if setup_report['invalid_components']:
                response_parts.append(messages['setup_invalid_components'])
                for name, id in setup_report['invalid_components']:
                    response_parts.append(messages['setup_invalid_component_item'].format(
                        name=name, id=id
                    ))

            # 报告新建的组件
            if setup_report['new_components']:
                response_parts.append(messages['setup_new_components'])
                for name, id in setup_report['new_components'].items():
                    response_parts.append(messages['setup_new_component_item'].format(
                        name=name, id=id
                    ))

            # 如果没有任何变化，显示系统已设置完成的消息
            if not setup_report['invalid_components'] and not setup_report['new_components']:
                response_parts.append(messages['setup_no_changes'])

            # 打印调试信息
            # print("Setup Report:", setup_report)  # 添加调试输出
            # print("Response Parts:", response_parts)  # 添加调试输出

            # 发送完整报告
            await interaction.followup.send("\n".join(response_parts), ephemeral=True)

        except Exception as e:
            error_msg = messages['setup_error'].format(error=str(e))
            logging.error(f"Setup error: {e}")  # 添加错误日志
            await interaction.followup.send(error_msg, ephemeral=True)

    @app_commands.command(
        name="tickets_stats",
        description="显示工单统计信息"
    )
    async def ticket_stats(self, interaction: discord.Interaction):
        """Display ticket statistics."""
        if not await self.check_ticket_channel(interaction):
            return

        await interaction.response.defer()

        try:
            # Get stats using the database manager
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

            # Add type breakdown
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

    @app_commands.command(
        name="tickets_cleanup",
        description="清理无效的工单数据"
    )
    async def cleanup_tickets(self, interaction: discord.Interaction):
        """Clean up invalid ticket data."""
        if not await self.check_ticket_channel(interaction):
            return

        await interaction.response.defer()

        try:
            # Get all ticket channels
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('SELECT channel_id FROM tickets')
                all_channel_ids = [row[0] for row in await cursor.fetchall()]

            # Check which channels still exist
            valid_channels = []
            invalid_channels = []
            for channel_id in all_channel_ids:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    valid_channels.append(channel_id)
                else:
                    invalid_channels.append(channel_id)

            if invalid_channels:
                # Clean up invalid channels
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
        """
        Check if a member is an admin for the specified ticket type or globally.
        If ticket_type is None, only checks global admin status.
        """
        # Check global admin status
        if member.id in self.conf.get('admin_users', []):
            return True

        if any(role.id in self.conf.get('admin_roles', []) for role in member.roles):
            return True

        if member.guild_permissions.administrator:
            return True

        # If only checking global status or no ticket type specified, return here
        if ticket_type is None:
            return False

        # Check type-specific admin status
        type_data = self.conf['ticket_types'].get(ticket_type)
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

        # Global admins section
        embed.add_field(
            name="全局管理员",
            value=self._format_admin_entries(
                self.conf.get('admin_roles', []),
                self.conf.get('admin_users', []),
                guild
            ),
            inline=False
        )

        # Type-specific admins sections
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

        # Format roles
        if role_ids:
            lines.append(messages['admin_list_roles_header'])
            for role_id in role_ids:
                role = guild.get_role(role_id)
                if role:
                    lines.append(messages['admin_list_role_item'].format(role=role.mention))

        # Format users
        if user_ids:
            if lines:  # Add a blank line if there were roles
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
        # Remove from all type-specific admin lists first
        for type_data in self.conf['ticket_types'].values():
            if target_type == 'role':
                if target_id in type_data.get('admin_roles', []):
                    type_data['admin_roles'].remove(target_id)
            else:
                if target_id in type_data.get('admin_users', []):
                    type_data['admin_users'].remove(target_id)

        # Add to global admin list
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
        # Check if target is already a global admin
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

    @app_commands.command(
        name="tickets_admin_list",
        description="显示当前的管理员配置"
    )
    async def admin_list(self, interaction: discord.Interaction):
        """Display current admin configuration."""
        if not await self.check_ticket_channel(interaction):
            return

        if not await self.is_admin(interaction.user):
            await interaction.response.send_message(
                self.conf['messages']['admin_no_permission'],
                ephemeral=True
            )
            return

        embed = await self.format_admin_list()
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tickets_admin_add_role",
        description="添加管理员身份组"
    )
    @app_commands.describe(role="要添加的身份组")
    async def admin_add_role(self, interaction: discord.Interaction, role: discord.Role):
        """Add an admin role."""
        if not await self.check_ticket_channel(interaction):
            return

        if not await self.is_admin(interaction.user):
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

    # Remove role from either global or type-specific admin list
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

    # Update existing admin commands
    @app_commands.command(name="tickets_admin_remove_role")
    @app_commands.describe(role="要移除的身份组")
    async def admin_remove_role(self, interaction: discord.Interaction, role: discord.Role):
        """Remove an admin role."""
        if not await self.check_ticket_channel(interaction):
            return

        if not await self.is_admin(interaction.user):
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

    @app_commands.command(name="tickets_admin_add_user")
    @app_commands.describe(user="要添加的用户")
    async def admin_add_user(self, interaction: discord.Interaction, user: discord.User):
        """Add an admin user."""
        if not await self.check_ticket_channel(interaction):
            return

        if not await self.is_admin(interaction.user):
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

    @app_commands.command(name="tickets_admin_remove_user")
    @app_commands.describe(user="要移除的用户")
    async def admin_remove_user(self, interaction: discord.Interaction, user: discord.User):
        """Remove an admin user."""
        if not await self.check_ticket_channel(interaction):
            return

        if not await self.is_admin(interaction.user):
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

    # Update messages in response to changes
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
            else:  # remove
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

        # Display updated admin list
        embed = await self.format_admin_list()
        await interaction.followup.send(embed=embed)

    async def save_config(self):
        """Save the current configuration back to the JSON file"""
        config_path = Path('./bot/config/config_tickets.json')

        try:
            async with aiofiles.open(config_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                config_data = json.loads(content)

            # 更新配置
            config_data.update(self.conf)

            async with aiofiles.open(config_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(config_data, indent=2, ensure_ascii=False))
        except Exception as e:
            logging.error(f"Error saving config: {e}")

    @app_commands.command(name="tickets_add_type")
    async def add_ticket_type(self, interaction: discord.Interaction):
        """Add a new ticket type"""
        if not await self.check_ticket_channel(interaction):
            return

        modal = TicketTypeModal(self)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="tickets_edit_type")
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

    @app_commands.command(name="tickets_delete_type")
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
        """
        Handles adding a user to a ticket channel.
        Returns True if user was successfully added, False otherwise.
        """
        messages = self.conf['messages']
        channel_id = channel_id or interaction.channel_id

        # Add user to database
        if await self.db.add_ticket_member(channel_id, user.id, interaction.user.id):
            # Get channel and update permissions
            channel = self.bot.get_channel(channel_id)
            await channel.set_permissions(
                user,
                read_messages=True,
                send_messages=True
            )

            # Send channel notification
            embed = discord.Embed(
                title=messages['add_user_success_title'],
                description=messages['add_user_success_content'].format(
                    user=user.mention,
                    adder=interaction.user.mention
                ),
                color=discord.Color.green()
            )
            await channel.send(embed=embed)

            # Send DM notification
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
                pass  # User has DMs disabled

            # Log action
            await self.logger.log_user_add(
                channel=channel,
                adder=interaction.user,
                user=user
            )

            # Send ephemeral success message
            await interaction.followup.send(
                messages['add_user_success_content'].format(
                    user=user.mention,
                    adder=interaction.user.mention
                ),
                ephemeral=True
            )
            return True
        else:
            # Database operation failed - send appropriate error message
            error_message = messages['ticket_closed_no_modify']
            if await self.db.check_member_exists(channel_id, user.id):
                error_message = messages['add_user_already_added']

            await interaction.followup.send(error_message, ephemeral=True)
            return False

    @app_commands.command(
        name="tickets_add_user",
        description="添加用户到当前工单"
    )
    @app_commands.describe(
        user="要添加的用户"
    )
    async def ticket_add_user(self, interaction: discord.Interaction, user: discord.Member):
        # Immediately acknowledge the interaction without sending a response
        await interaction.response.defer(ephemeral=True, thinking=False)
        await self.handle_add_user(interaction, user)

    @app_commands.command(
        name="tickets_accept",
        description="手动接受当前工单"
    )
    async def accept_ticket(self, interaction: discord.Interaction):
        """Manually accept the current ticket."""
        await interaction.response.defer()

        # 确保在工单频道中使用
        channel_id = interaction.channel_id
        ticket_status = await self.db.check_ticket_status(channel_id)
        if not ticket_status[0]:
            await interaction.followup.send(
                self.conf['messages']['command_channel_only'],
                ephemeral=True
            )
            return

        # 检查用户是否是管理员
        if not await self.is_admin(interaction.user):
            await interaction.followup.send(
                self.conf['messages']['ticket_admin_only'],
                ephemeral=True
            )
            return

        # 尝试接受工单
        if await self.db.accept_ticket(channel_id, interaction.user.id):
            # 获取工单初始消息并更新控制面板
            try:
                # 获取工单信息
                ticket_details = await self.db.fetch_ticket(channel_id)
                if ticket_details and ticket_details['message_id']:
                    message = await interaction.channel.fetch_message(ticket_details['message_id'])
                    if message:
                        # 创建新的控制面板视图
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

            # 创建通知 embed
            embed = discord.Embed(
                title=self.conf['messages']['ticket_accepted_title'],
                description=self.conf['messages']['ticket_accepted_content'].format(
                    user=interaction.user.mention
                ),
                color=discord.Color.green()
            )
            await interaction.channel.send(embed=embed)

            # 记录操作
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

    @app_commands.command(
        name="tickets_close",
        description="手动关闭当前工单"
    )
    @app_commands.describe(reason="关闭工单的原因")
    async def close_ticket(self, interaction: discord.Interaction, reason: str):
        """Manually close the current ticket."""
        await interaction.response.defer()

        # 确保在工单频道中使用
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

        # 获取工单信息
        ticket_info = await self.db.fetch_ticket(channel_id)
        if not ticket_info:
            await interaction.followup.send(
                self.conf['messages']['ticket_close_get_info_error'],
                ephemeral=True
            )
            return

        # 关闭工单
        if await self.db.close_ticket(channel_id, interaction.user.id, reason):
            try:
                # 获取创建者信息
                creator = await self.bot.fetch_user(ticket_info['creator_id']) if ticket_info['creator_id'] else None

                # 获取可用的已关闭工单分类
                closed_category = await self.ticket_system.get_available_category(is_closed=True)

                # 更新频道权限
                overwrites = {
                    interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    interaction.guild.me: discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_channels=True,
                        manage_messages=True
                    ),
                }

                # 如果存在创建者，添加他们的权限
                if creator:
                    overwrites[creator] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=False,
                        read_message_history=True
                    )

                # 为工单成员设置权限
                members = await self.db.get_ticket_members(channel_id)
                for member_id, _, _ in members:
                    member = interaction.guild.get_member(member_id)
                    if member and member != creator:  # 避免重复设置创建者的权限
                        overwrites[member] = discord.PermissionOverwrite(
                            view_channel=True,
                            send_messages=False,
                            read_message_history=True
                        )

                # 更新频道设置
                await interaction.channel.edit(
                    category=closed_category,
                    overwrites=overwrites
                )

                # 更新控制面板
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
                            # 禁用所有按钮
                            for item in view.children:
                                if isinstance(item, discord.ui.Button):
                                    item.disabled = True
                            await message.edit(view=view)
                except discord.NotFound:
                    logging.error(f"Could not find control message for ticket {channel_id}")
                except Exception as e:
                    logging.error(f"Error updating ticket control panel: {e}")

                # 发送关闭通知
                embed = discord.Embed(
                    title=self.conf['messages']['log_ticket_close_title'],
                    description=self.conf['messages']['log_ticket_close_description'].format(
                        closer=interaction.user.mention,
                        reason=reason
                    ),
                    color=discord.Color.red()
                )
                await interaction.channel.send(embed=embed)

                # 记录操作
                await self.logger.log_ticket_close(
                    channel=interaction.channel,
                    closer=interaction.user,
                    reason=reason
                )

                # 如果找到创建者，发送DM通知
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
                        pass  # Creator has DMs disabled

                await interaction.followup.send(self.conf['messages']['ticket_stats_closed'], ephemeral=True)

            except Exception as e:
                logging.error(f"Error closing ticket: {e}")
                await interaction.followup.send(
                    self.conf['messages']['ticket_close_error'],
                    ephemeral=True
                )

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize ticket system and guild on bot ready."""
        # 设置 guild
        self.guild = self.bot.get_guild(self.guild_id)
        if not self.guild:
            logging.error("Could not find configured guild")
            return

        # Initialize ticket system
        self.ticket_system = TicketSystem(self, self.guild)

        # Check if system needs setup
        is_ready = await self.ticket_system.check_status()
        if not is_ready:
            logging.warning("Ticket system not fully initialized. Use /tickets_setup to initialize.")

        # Update permissions for all channels
        await self.update_admin_permissions()

        # Restore active tickets
        active_tickets = await self.db.get_active_tickets()

        for channel_id, message_id, creator_id, type_name, is_accepted in active_tickets:
            channel = self.bot.get_channel(channel_id)
            if channel:
                try:
                    # Restore ticket view
                    message = await channel.fetch_message(message_id)
                    creator = await self.bot.fetch_user(creator_id)
                    type_data = self.conf.get('ticket_types', {}).get(type_name)

                    if type_data and message and creator:
                        view = TicketControlView(
                            self, channel, creator, type_name,
                            is_accepted=is_accepted
                        )
                        await message.edit(view=view)
                except discord.NotFound:
                    logging.warning(f"Could not find message {message_id} for ticket {channel_id}")
                except Exception as e:
                    logging.error(f"Error restoring ticket {channel_id}: {e}")

        # Update main message if it exists
        if self.ticket_system.main_message_id:
            try:
                await self.ticket_system.update_main_message()
            except Exception as e:
                logging.error(f"Failed to update main message: {e}")

        logging.info("Ticket system initialized successfully")
