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
        self.db_path = config.get_config('main')['db_path']

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
        self.original_message = original_message  # 保存原始消息引用

        # 创建表单输入框
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
            old_type_name = self.type_key
            if old_type_name != type_name:
                ticket_types.pop(old_type_name, None)

            # 记录编辑操作
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
            await self.cog.logger.log_type_add(
                admin=interaction.user,
                type_data={
                    'name': type_name,
                    'description': self.type_description.value.strip(),
                    'guide': self.user_guide.value.strip()
                }
            )

        # 更新或创建工单类型
        ticket_types[type_name] = {
            'name': type_name,
            'description': self.type_description.value.strip(),
            'guide': self.user_guide.value.strip(),
            'button_color': self.button_color.value.strip().lower()
        }

        # 保存配置并更新主消息
        await self.cog.save_ticket_types(ticket_types)
        if self.cog.ticket_system:
            await self.cog.ticket_system.update_main_message()

        # 发送确认消息
        await interaction.followup.send(
            f"Tickets type {'updated' if self.edit_mode else 'added'}: {type_name}",
            ephemeral=True
        )

        # 在所有操作完成后删除原始的选择菜单消息
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
        ticket_types = cog.conf.get('ticket_types', {})

        options = [
            discord.SelectOption(
                label=type_data['name'],
                description=type_data['description'][:100],
                value=type_name
            ) for type_name, type_data in ticket_types.items()
        ]

        super().__init__(
            placeholder="选择工单类型...",
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
                    f"Tickets type deleted: {selected_type}",
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

        # Channel/Category IDs
        self.create_channel_id = self.conf.get('create_channel_id')
        self.info_channel_id = self.conf.get('info_channel_id')
        self.open_category_id = self.conf.get('open_category_id')
        self.closed_category_id = self.conf.get('closed_category_id')

        # Main message ID
        self.main_message_id = self.conf.get('main_message_id')

        # Message content
        self.messages = self.conf['messages']

        # Status tracking
        self.is_ready = False

    async def check_and_clean_invalid_components(self):
        """检查所有组件并清理无效配置"""
        invalid_components = []
        config_changed = False

        # 从配置中获取组件名称
        messages = self.conf['messages']
        component_names = {
            'create_channel': messages.get('component_name_create_channel', 'Create Channel'),
            'info_channel': messages.get('component_name_info_channel', 'Info Channel'),
            'open_category': messages.get('component_name_open_category', 'Open Category'),
            'closed_category': messages.get('component_name_closed_category', 'Closed Category'),
            'main_message': messages.get('component_name_main_message', 'Main Message')
        }

        # 检查创建频道
        if self.create_channel_id:
            channel = self.guild.get_channel(self.create_channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                invalid_components.append((component_names['create_channel'], self.create_channel_id))
                self.create_channel_id = None
                config_changed = True

        # 检查日志频道
        if self.info_channel_id:
            channel = self.guild.get_channel(self.info_channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                invalid_components.append((component_names['info_channel'], self.info_channel_id))
                self.info_channel_id = None
                config_changed = True

        # 检查开放工单分类
        if self.open_category_id:
            category = self.guild.get_channel(self.open_category_id)
            if not category or not isinstance(category, discord.CategoryChannel):
                invalid_components.append((component_names['open_category'], self.open_category_id))
                self.open_category_id = None
                config_changed = True

        # 检查关闭工单分类
        if self.closed_category_id:
            category = self.guild.get_channel(self.closed_category_id)
            if not category or not isinstance(category, discord.CategoryChannel):
                invalid_components.append((component_names['closed_category'], self.closed_category_id))
                self.closed_category_id = None
                config_changed = True

        # 检查主消息
        if self.main_message_id:  # 直接检查主消息ID是否存在
            channel = self.guild.get_channel(self.create_channel_id)
            if channel:
                try:
                    await channel.fetch_message(self.main_message_id)
                except (discord.NotFound, discord.HTTPException):
                    invalid_components.append((component_names['main_message'], self.main_message_id))
                    self.main_message_id = None
                    config_changed = True
            else:
                # 如果创建频道不存在，主消息也标记为无效
                invalid_components.append((component_names['main_message'], self.main_message_id))
                self.main_message_id = None
                config_changed = True

        # 如果有无效组件，更新配置文件
        if config_changed:
            await self.save_config()

        return invalid_components, config_changed

    async def check_status(self):
        """检查系统状态并处理无效组件"""
        invalid_components, config_changed = await self.check_and_clean_invalid_components()

        # 如果发现无效组件，记录日志
        if invalid_components:
            invalid_report = "\n".join([f"- {name}: {id}" for name, id in invalid_components])
            logging.warning(f"Found invalid ticket system components:\n{invalid_report}")

        # 检查是否所有必需组件都存在且有效
        components_valid = all([
            self.create_channel_id is not None,
            self.info_channel_id is not None,
            self.open_category_id is not None,
            self.closed_category_id is not None
        ])

        return components_valid

    async def setup_system(self):
        """完整的系统设置流程"""
        # 首先清理无效组件
        invalid_components, config_changed = await self.check_and_clean_invalid_components()
        
        messages = self.conf['messages']
        component_names = {
            'create_channel': messages.get('component_name_create_channel', 'Create Channel'),
            'info_channel': messages.get('component_name_info_channel', 'Info Channel'),
            'open_category': messages.get('component_name_open_category', 'Open Category'),
            'closed_category': messages.get('component_name_closed_category', 'Closed Category'),
            'main_message': messages.get('component_name_main_message', 'Main Message')
        }

        new_components = {}

        # 创建缺失的组件，只在组件不存在时创建
        if not self.create_channel_id:
            channel, message_id = await self.create_ticket_channel()
            new_components[component_names['create_channel']] = channel.id
            if message_id:  # 如果成功创建了主消息，也添加到新组件列表中
                new_components[component_names['main_message']] = message_id

        if not self.info_channel_id:
            channel = await self.create_info_channel()
            new_components[component_names['info_channel']] = channel.id

        if not self.open_category_id or not self.closed_category_id:
            open_cat, closed_cat = await self.create_categories()
            if not self.open_category_id:
                new_components[component_names['open_category']] = open_cat.id
            if not self.closed_category_id:
                new_components[component_names['closed_category']] = closed_cat.id

        # 只有在没有通过create_ticket_channel创建主消息时才单独创建
        if not self.main_message_id and 'main_message' not in new_components:
            message = await self.create_initial_message()
            if message:
                new_components[component_names['main_message']] = message.id

        # 返回初始化报告
        report = {
            'invalid_components': invalid_components,
            'new_components': new_components,
            'config_changed': config_changed or bool(new_components)
        }

        return report

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
        await self.save_config()
        
        # 立即创建初始消息并获取消息对象
        message = await self.create_initial_message()
        
        # 返回创建的频道和消息ID，供setup_system使用
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
        await self.save_config()
        return channel

    async def create_categories(self):
        """Create both open and closed ticket categories"""
        # Create open category
        open_category = await self.guild.create_category(
            name="Open Tickets",
            overwrites={
                self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                self.guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    manage_channels=True,
                    manage_permissions=True
                )
            }
        )
        self.open_category_id = open_category.id

        # Create closed category
        closed_category = await self.guild.create_category(
            name="Closed Tickets",
            overwrites={
                self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                self.guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    manage_channels=True,
                    manage_permissions=True
                )
            }
        )
        self.closed_category_id = closed_category.id

        await self.save_config()
        return open_category, closed_category

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
        """Save the current configuration back to the JSON file"""
        config_path = Path('./bot/config/config_tickets.json')

        try:
            async with aiofiles.open(config_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                config_data = json.loads(content)

            config_data.update({
                'create_channel_id': self.create_channel_id,
                'info_channel_id': self.info_channel_id,
                'open_category_id': self.open_category_id,
                'closed_category_id': self.closed_category_id,
                'main_message_id': self.main_message_id
            })

            async with aiofiles.open(config_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(config_data, indent=2, ensure_ascii=False))
        except Exception as e:
            logging.error(f"Error saving config: {e}")

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

        # Add admin role permissions
        for role_id in self.ticket_system.conf.get('admin_roles', []):
            role = interaction.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )

        # Add admin user permissions
        for user_id in self.ticket_system.conf.get('admin_users', []):
            member = interaction.guild.get_member(user_id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )

        # Create the ticket channel
        open_category = interaction.guild.get_channel(self.ticket_system.open_category_id)
        channel = await interaction.guild.create_text_channel(
            name=channel_name,
            category=open_category,
            overwrites=overwrites
        )

        # Create initial message and control panel
        embed = discord.Embed(
            title=self.messages['ticket_created_title'].format(
                number=ticket_number,
                type_name=self.type_name
            ),
            description=self.type_data['guide'],
            color=discord.Color.blue()
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

        # 获取或创建已关闭分类
        closed_category = interaction.guild.get_channel(self.cog.ticket_system.closed_category_id)
        if not closed_category:
            closed_category = await self.cog.ticket_system.create_categories()

        # 关闭工单
        if await self.cog.db.close_ticket(self.ticket_channel.id, interaction.user.id, self.reason.value):
            # 获取工单成员
            members = await self.cog.db.get_ticket_members(self.ticket_channel.id)

            # 更新权限
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                self.creator: discord.PermissionOverwrite(view_channel=True, send_messages=False)
            }

            # 添加管���员角色权限
            for role_id in self.cog.conf.get('admin_roles', []):
                role = interaction.guild.get_role(role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

            # 添加工单成员权限
            for member_id, added_by, added_at in members:
                member = interaction.guild.get_member(member_id)
                if member:
                    overwrites[member] = discord.PermissionOverwrite(view_channel=True, send_messages=False)

            # 移动频道并更新权限
            await self.ticket_channel.edit(
                category=closed_category,
                overwrites=overwrites
            )

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

        if channel_id != allowed_channel_id:
            await interaction.response.send_message(
                "This command can only be used in the ticket management channel.",
                ephemeral=True
            )
            return False
        return True

    async def update_admin_permissions(self):
        """Update permissions for all admin users and roles in relevant channels."""
        if not self.ticket_system or not self.guild:
            return

        # Get info channel
        info_channel = self.guild.get_channel(self.ticket_system.info_channel_id)
        if not info_channel:
            return

        # Collect all admin overwrites
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            self.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True
            )
        }

        # Add role overwrites
        for role_id in self.conf.get('admin_roles', []):
            role = self.guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    manage_messages=True
                )

        # Add user overwrites
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

        # Get all active tickets
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('SELECT channel_id FROM tickets WHERE is_closed = 0')
            active_tickets = await cursor.fetchall()

        # Update permissions for all active ticket channels
        for (channel_id,) in active_tickets:
            channel = self.guild.get_channel(channel_id)
            if not channel:
                continue

            # Get existing overwrites and update them
            channel_overwrites = dict(channel.overwrites)

            # Add admin roles
            for role_id in self.conf.get('admin_roles', []):
                role = self.guild.get_role(role_id)
                if role:
                    channel_overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

            # Add admin users
            for user_id in self.conf.get('admin_users', []):
                member = self.guild.get_member(user_id)
                if member:
                    channel_overwrites[member] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        manage_messages=True
                    )

            await channel.edit(overwrites=channel_overwrites)

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

            # 发送完整报告
            await interaction.followup.send("\n".join(response_parts), ephemeral=True)

        except Exception as e:
            error_msg = messages['setup_error'].format(error=str(e))
            logging.error(error_msg)
            await interaction.followup.send(error_msg, ephemeral=True)

        except Exception as e:
            error_msg = messages['setup_error'].format(error=str(e))
            logging.error(error_msg)
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

    # 在 TicketsCog 类中添加

    async def is_admin(self, member: discord.Member) -> bool:
        """Enhanced admin check that considers roles, user list and Discord permissions."""
        # 检查是否在管理员用户列表中
        if member.id in self.conf.get('admin_users', []):
            return True

        # 检查是否有管理员角色
        admin_role_ids = self.conf.get('admin_roles', [])
        if any(role.id in admin_role_ids for role in member.roles):
            return True

        # 检查Discord权限
        if member.guild_permissions.administrator or \
                member.guild_permissions.manage_guild or \
                member.guild_permissions.manage_channels:
            return True

        return False

    async def format_admin_list(self) -> discord.Embed:
        """Format current admin configuration as an embed."""
        guild = self.bot.get_guild(self.guild_id)  # 直接获取 guild
        if not guild:
            raise ValueError("Could not find configured guild")

        embed = discord.Embed(
            title=self.conf['messages']['admin_list_title'],
            color=discord.Color.blue()
        )

        # 管理员角色列表
        role_list = []
        for role_id in self.conf.get('admin_roles', []):
            role = guild.get_role(role_id)
            if role:
                role_list.append(f"• {role.mention} (ID: {role.id})")
        embed.add_field(
            name=self.conf['messages']['admin_list_roles'],
            value="\n".join(role_list) if role_list else "无",
            inline=False
        )

        # 管理员用户列表
        user_list = []
        for user_id in self.conf.get('admin_users', []):
            user = self.bot.get_user(user_id)
            if user:
                user_list.append(f"• {user.mention} (ID: {user.id})")
        embed.add_field(
            name=self.conf['messages']['admin_list_users'],
            value="\n".join(user_list) if user_list else "无",
            inline=False
        )

        # Discord 权限说明
        embed.add_field(
            name=self.conf['messages']['admin_list_perms'],
            value="• Administrator\n• Manage Server\n• Manage Channels",
            inline=False
        )

        return embed

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

        admin_roles = self.conf.get('admin_roles', [])
        if role.id in admin_roles:
            await interaction.response.send_message(
                self.conf['messages']['admin_role_exists'],
                ephemeral=True
            )
            return

        admin_roles.append(role.id)
        self.conf['admin_roles'] = admin_roles
        await self.save_config()

        # Update permissions after adding role
        await self.update_admin_permissions()

        await interaction.response.send_message(
            self.conf['messages']['admin_add_role_success'].format(role=role.mention)
        )

        # Display updated admin list
        embed = await self.format_admin_list()
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="tickets_admin_remove_role",
        description="移除管理员身份组"
    )
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

        admin_roles = self.conf.get('admin_roles', [])
        if role.id not in admin_roles:
            await interaction.response.send_message(
                self.conf['messages']['admin_role_not_found'],
                ephemeral=True
            )
            return

        admin_roles.remove(role.id)
        self.conf['admin_roles'] = admin_roles
        await self.save_config()

        # Update permissions after removing role
        await self.update_admin_permissions()

        await interaction.response.send_message(
            self.conf['messages']['admin_remove_role_success'].format(role=role.mention)
        )

        # Display updated admin list
        embed = await self.format_admin_list()
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="tickets_admin_add_user",
        description="添加管理员用户"
    )
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

        admin_users = self.conf.get('admin_users', [])
        if user.id in admin_users:
            await interaction.response.send_message(
                self.conf['messages']['admin_user_exists'],
                ephemeral=True
            )
            return

        admin_users.append(user.id)
        self.conf['admin_users'] = admin_users
        await self.save_config()

        # Update permissions after adding user
        await self.update_admin_permissions()

        await interaction.response.send_message(
            self.conf['messages']['admin_add_user_success'].format(user=user.mention)
        )

        # Display updated admin list
        embed = await self.format_admin_list()
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="tickets_admin_remove_user",
        description="移除管理员用户"
    )
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

        admin_users = self.conf.get('admin_users', [])
        if user.id not in admin_users:
            await interaction.response.send_message(
                self.conf['messages']['admin_user_not_found'],
                ephemeral=True
            )
            return

        admin_users.remove(user.id)
        self.conf['admin_users'] = admin_users
        await self.save_config()

        # Update permissions after removing user
        await self.update_admin_permissions()

        await interaction.response.send_message(
            self.conf['messages']['admin_remove_user_success'].format(user=user.mention)
        )

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
