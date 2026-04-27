import asyncio
import logging
from datetime import datetime

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from bot.utils import TicketsDatabaseManager, fmt_channel, fmt_user
from bot.utils.config import Config
from bot.utils.i18n import t

from .embeds import EmbedColors
from .modals import TicketTypeModal
from .views import (
    AdminTypeSelectView,
    TicketCreateView,
    TicketThreadView,
    TypeSelectView,
)


class TicketsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config()
        self.conf = self.config.get_config('tickets')
        # ticket_types now lives in the DB (P2-5). Drop it from the
        # snapshot so a later `await config.save_config('tickets',
        # self.conf)` can't accidentally mirror the DB-backed map back
        # into YAML and create a double source of truth.
        self.conf.pop('ticket_types', None)
        self.main_conf = self.config.get_config('main')
        self.db_manager = TicketsDatabaseManager(self.main_conf['db_path'])
        # DB-backed cache refreshed on cog_load / after every CRUD.
        self.ticket_types: dict = {}

    async def cog_load(self):
        """Initialize the cog"""
        await self.db_manager.initialize_database()
        self.ticket_types = await self.db_manager.list_ticket_types()

        # Fix any tickets with NULL ticket_number
        fixed_count = await self.db_manager.fix_null_ticket_numbers()
        if fixed_count > 0:
            logging.info(f"Fixed {fixed_count} tickets with NULL ticket_number")

        # Check and close tickets for missing channels
        await self.check_and_close_missing_tickets()

        logging.info(
            f"TicketsCog loaded successfully ({len(self.ticket_types)} ticket types)"
        )

    async def _refresh_ticket_types(self) -> None:
        """Reload the ticket_types cache from DB; call after any CRUD."""
        self.ticket_types = await self.db_manager.list_ticket_types()

    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize views on bot ready"""
        try:
            # Get config data from database
            config_data = await self.db_manager.get_config()
            if not config_data:
                logging.warning("TicketsCog: No config data found in database")
                return

            ticket_channel_id = config_data.get('ticket_channel_id')
            main_message_id = config_data.get('main_message_id')

            if not ticket_channel_id or not main_message_id:
                logging.warning("TicketsCog: Missing channel or message ID in config")
                return

            # Get the ticket channel and message
            ticket_channel = self.bot.get_channel(ticket_channel_id)
            if not ticket_channel:
                logging.error("TicketsCog: Could not find ticket channel %s", fmt_channel(ticket_channel_id))
                return

            try:
                main_message = await ticket_channel.fetch_message(main_message_id)

                # Create and register persistent view for main message
                ticket_types = self.ticket_types
                if ticket_types:
                    main_view = TicketCreateView(self, ticket_types)
                    self.bot.add_view(main_view)

                    # Update the main message with current ticket types
                    await self.update_main_message(ticket_channel, main_message, ticket_types)

                    logging.info(f"TicketsCog: Restored main ticket message with {len(ticket_types)} ticket types")

            except discord.NotFound:
                logging.warning(f"TicketsCog: Main message {main_message_id} not found")
            except Exception as e:
                logging.error(f"TicketsCog: Error updating main message: {e}")

            # Restore active ticket thread views and update button states
            active_tickets = await self.db_manager.get_active_tickets()
            restored_count = 0
            updated_count = 0

            # Process tickets in batches to avoid rate limits
            batch_size = 3  # Smaller batch size for startup
            delay_between_batches = 1.5  # seconds

            logging.info(f"TicketsCog: Starting to restore {len(active_tickets)} ticket views with button updates...")

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
                            ticket_view = TicketThreadView(self, thread_id, type_name, is_accepted)

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
                                logging.warning(
                                    "TicketsCog: Could not update buttons for ticket thread %s: %s",
                                    fmt_channel(thread or thread_id),
                                    e,
                                )

                    except Exception as e:
                        logging.error(
                            "TicketsCog: Error restoring ticket thread %s: %s",
                            fmt_channel(thread_id),
                            e,
                        )

                # Add delay between batches to avoid rate limits
                if i + batch_size < len(active_tickets):
                    await asyncio.sleep(delay_between_batches)

            if restored_count > 0:
                logging.info(f"TicketsCog: Restored {restored_count} active ticket thread views")
                logging.info(f"TicketsCog: Updated {updated_count} ticket message buttons")
                if updated_count < restored_count:
                    logging.info("TicketsCog: Some button updates failed - use /tickets_refresh_buttons if needed")

        except Exception as e:
            logging.error(f"TicketsCog on_ready error: {e}")

    async def update_main_message(self, channel, message, ticket_types):
        """Update the main ticket message with current types"""
        try:
            embed = discord.Embed(
                title=t('tickets.messages.ticket_main_title'),
                description=t('tickets.messages.ticket_main_description'),
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

            embed.set_footer(text=t('tickets.messages.ticket_main_footer'))

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
                logging.warning("Ticket message %s not found in thread %s", message_id, fmt_channel(thread))
            except discord.HTTPException as e:
                logging.warning(
                    "Could not update ticket message %s in thread %s: %s",
                    message_id,
                    fmt_channel(thread),
                    e,
                )

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
        if ticket_type and ticket_type in self.ticket_types:
            type_data = self.ticket_types[ticket_type]

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
                    t('tickets.messages.old_system_no_new_channel'),
                    ephemeral=True
                )
                return

            ticket_channel = interaction.guild.get_channel(config_data['ticket_channel_id'])
            if not ticket_channel:
                await interaction.followup.send(
                    t('tickets.messages.ticket_thread_not_found'),
                    ephemeral=True
                )
                return

            # Generate ticket number
            ticket_number = await self.db_manager.get_ticket_number()
            thread_name = f"ticket-{ticket_number}"

            # Create private thread directly
            thread = await ticket_channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.private_thread,
                invitable=False,
                auto_archive_duration=4320  # 3 days
            )

            # Add creator to thread
            await thread.add_user(interaction.user)

            # Add admin users to thread
            for user_id in type_data.get('admin_users', []):
                try:
                    user = interaction.guild.get_member(user_id)
                    if user:
                        await thread.add_user(user)
                except discord.HTTPException:
                    pass  # Ignore if user can't be added

            # Add admin role members to thread
            for role_id in type_data.get('admin_roles', []):
                try:
                    role = interaction.guild.get_role(role_id)
                    if role:
                        for member in role.members:
                            try:
                                await thread.add_user(member)
                            except discord.HTTPException:
                                pass  # Ignore if member can't be added
                except discord.HTTPException:
                    pass  # Ignore if role doesn't exist

            # Create ticket in database (will update message ID later)
            success = await self.db_manager.create_ticket(
                thread.id, 0, interaction.user.id,  # Use 0 as temporary message ID
                type_name, ticket_channel.id, ticket_number
            )

            if not success:
                await thread.delete()
                await interaction.followup.send(
                    t('tickets.messages.ticket_create_db_error'),
                    ephemeral=True
                )
                return

            # Create ticket embed
            embed = discord.Embed(
                title=t('tickets.messages.ticket_created_title').format(
                    number=ticket_number,
                    type_name=type_name
                ),
                description=type_data['guide'],
                color=EmbedColors.CREATE
            )

            embed.add_field(
                name=t('tickets.messages.ticket_created_creator'),
                value=interaction.user.mention,
                inline=True
            )

            embed.add_field(
                name=t('tickets.messages.ticket_created_time'),
                value=f"<t:{int(datetime.now().timestamp())}:F>",
                inline=True
            )

            # Instructions embed
            instructions_embed = discord.Embed(
                title=t('tickets.messages.ticket_instructions_title'),
                description=t('tickets.messages.ticket_instructions'),
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
                t('tickets.messages.ticket_create_success').format(thread=thread.mention),
                ephemeral=True
            )

            # Add admins to thread and send notifications (can be done after response)
            await self.add_admins_to_ticket(thread, type_name, interaction.user, ticket_number)

            # Log ticket creation
            await self.log_ticket_action('create', thread.id, interaction.user, type_name=type_name, ticket_number=ticket_number)

            # Send DM to creator with jump button
            try:
                dm_embed = discord.Embed(
                    title=t('tickets.messages.ticket_created_dm_title'),
                    description=t('tickets.messages.ticket_created_dm_content').format(
                        number=ticket_number,
                        type_name=type_name
                    ),
                    color=EmbedColors.CREATE
                )

                # Create jump button view
                dm_view = discord.ui.View()
                jump_button = discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    label=t('tickets.messages.ticket_jump_button'),
                    url=f"https://discord.com/channels/{thread.guild.id}/{thread.id}"
                )
                dm_view.add_item(jump_button)

                await interaction.user.send(embed=dm_embed, view=dm_view)
            except (discord.Forbidden, discord.HTTPException):
                pass  # DM failed

        except Exception as e:
            logging.error(
                "Error creating ticket thread for user %s type %s: %s",
                fmt_user(interaction.user),
                type_name,
                e,
            )
            try:
                await interaction.followup.send(
                    t('tickets.messages.ticket_thread_create_error'),
                    ephemeral=True
                )
            except discord.HTTPException:
                # If interaction has already been responded to, try response instead
                try:
                    await interaction.response.send_message(
                        t('tickets.messages.ticket_thread_create_error'),
                        ephemeral=True
                    )
                except discord.HTTPException:
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
                    title=t('tickets.messages.log_ticket_create_title').format(number=ticket_number),
                    description=t('tickets.messages.log_ticket_create_description').format(
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
                    title=t('tickets.messages.log_ticket_accept_title').format(number=ticket_number),
                    description=t('tickets.messages.log_ticket_accept_description').format(
                        acceptor=user.mention
                    ),
                    color=EmbedColors.ACCEPT
                )
            elif action == 'close':
                ticket_data = await self.db_manager.get_ticket_history(thread_id)
                if ticket_data:
                    members_list = ", ".join([f"<@{m['user_id']}>" for m in ticket_data['members'][1:]]) or t('tickets.messages.unavailable_text')
                    acceptor_mention = f"<@{ticket_data['accepted_by']}>" if ticket_data['accepted_by'] else t('tickets.messages.unavailable_text')
                    creator_mention = f"<@{ticket_data['creator_id']}>"

                    # Get ticket number, fallback to basic fetch if history doesn't have it
                    ticket_number = ticket_data.get('ticket_number')
                    if not ticket_number:
                        basic_ticket_data = await self.db_manager.fetch_ticket(thread_id)
                        ticket_number = basic_ticket_data['ticket_number'] if basic_ticket_data else None

                    ticket_number = ticket_number or 'Unknown'
                    embed = discord.Embed(
                        title=t('tickets.messages.log_ticket_close_title').format(number=ticket_number),
                        description=t('tickets.messages.log_ticket_close_description').format(
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
                    title=t('tickets.messages.log_user_add_title').format(number=ticket_number),
                    description=t('tickets.messages.log_user_add_description').format(
                        adder=user.mention,
                        user=extra_user.mention
                    ),
                    color=EmbedColors.ADD_USER
                )
            else:
                return

            embed.set_footer(text=t('tickets.messages.log_footer_text'))

            # Add view button if thread exists
            if thread:
                view = discord.ui.View()
                button = discord.ui.Button(
                    label=t('tickets.messages.log_button_view_ticket'),
                    url=f"https://discord.com/channels/{thread.guild.id}/{thread.id}",
                    style=discord.ButtonStyle.link
                )
                view.add_item(button)
                await info_channel.send(embed=embed, view=view)
            else:
                await info_channel.send(embed=embed)

        except Exception as e:
            logging.error(
                "Error logging ticket action %s for thread %s by user %s: %s",
                action,
                fmt_channel(thread_id),
                fmt_user(user),
                e,
            )

    @app_commands.command(
        name="tickets_init",
        description=locale_str(
            "Initialize the ticket system",
            key="tickets.tickets_init.description",
        ),
    )
    @app_commands.describe(
        ticket_channel=locale_str(
            "Ticket channel (optional — auto-created if empty)",
            key="tickets.tickets_init.params.ticket_channel",
        ),
        info_channel=locale_str(
            "Ticket info channel (optional — auto-created if empty)",
            key="tickets.tickets_init.params.info_channel",
        ),
    )
    async def init_ticket_system(self, interaction: discord.Interaction,
                                ticket_channel: discord.TextChannel = None,
                                info_channel: discord.TextChannel = None):
        """Initialize the ticket system with optional channel parameters"""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                t('tickets.messages.admin_no_permission')
            )
            return

        try:
            # Defer response since channel creation might take time
            await interaction.response.defer()

            # Check if system is already set up
            existing_config = await self.db_manager.get_config()
            if existing_config and existing_config.get('ticket_channel_id'):
                existing_ticket_channel = interaction.guild.get_channel(existing_config['ticket_channel_id'])
                existing_info_channel = interaction.guild.get_channel(existing_config['info_channel_id'])

                if existing_ticket_channel and existing_info_channel:
                    await interaction.followup.send(
                        t('tickets.messages.init_already_configured').format(
                            ticket_channel=existing_ticket_channel.mention,
                            info_channel=existing_info_channel.mention
                        )
                    )
                    return

            # Validate provided channels if any
            if ticket_channel:
                if not await self._validate_channel_permissions(ticket_channel):
                    await interaction.followup.send(
                        t('tickets.messages.init_channel_permission_error')
                    )
                    return

            if info_channel:
                if not await self._validate_channel_permissions(info_channel):
                    await interaction.followup.send(
                        t('tickets.messages.init_channel_permission_error')
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
                title=t('tickets.messages.ticket_main_title'),
                description=t('tickets.messages.ticket_main_description'),
                color=EmbedColors.DEFAULT
            )

            # Add bot avatar as thumbnail if available
            if self.bot.user.avatar:
                embed.set_thumbnail(url=self.bot.user.avatar.url)

            # Add fields for each ticket type
            ticket_types = self.ticket_types
            for type_name, type_data in ticket_types.items():
                embed.add_field(
                    name=type_name,
                    value=type_data.get('description', '无描述'),
                    inline=False
                )

            embed.set_footer(text=t('tickets.messages.ticket_main_footer'))

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
                success_message = t(
                    'tickets.messages.init_success_auto'
                    if auto_created
                    else 'tickets.messages.init_success_manual'
                )

                # Send success message (visible to everyone)
                setup_embed = discord.Embed(
                    title=t('tickets.messages.init_success_title'),
                    description=success_message.format(
                        ticket_channel=ticket_channel.mention,
                        info_channel=info_channel.mention,
                        message_id=message.id,
                        setup_user=interaction.user.mention
                    ),
                    color=EmbedColors.CREATE
                )
                setup_embed.add_field(
                    name=t('tickets.messages.setup_types_field_name'),
                    value="\n".join([f"• {name}" for name in self.ticket_types.keys()]) or t('tickets.messages.setup_no_types'),
                    inline=False
                )

                await interaction.followup.send(embed=setup_embed, ephemeral=False)

                # Send a notification to the info channel
                log_embed = discord.Embed(
                    title=t('tickets.messages.init_log_title'),
                    description=t('tickets.messages.init_log_description').format(
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
                    await ticket_channel.delete(reason=t('tickets.messages.cleanup_reason'))
                    await info_channel.delete(reason=t('tickets.messages.cleanup_reason'))

                await interaction.followup.send(
                    t('tickets.messages.init_db_error')
                )

        except discord.Forbidden:
            await interaction.followup.send(
                t('tickets.messages.init_permission_error')
            )
        except Exception as e:
            logging.error("Error initializing ticket system by user %s: %s", fmt_user(interaction.user), e)
            await interaction.followup.send(
                t('tickets.messages.init_error').format(error=str(e))
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
        except Exception:
            logging.exception("_validate_channel_permissions failed")
            return False

    @app_commands.command(
        name="tickets_add_user",
        description=locale_str(
            "Add a user to the current ticket",
            key="tickets.tickets_add_user.description",
        ),
    )
    @app_commands.describe(
        user=locale_str(
            "User to add",
            key="tickets.tickets_add_user.params.user",
        ),
    )
    async def add_user_command(self, interaction: discord.Interaction, user: discord.Member):
        """Add user to ticket via command"""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                t('tickets.messages.command_thread_only'),
                ephemeral=True
            )
            return

        thread_id = interaction.channel.id

        # Check if ticket exists
        ticket_exists, is_closed = await self.db_manager.check_ticket_status(thread_id)
        if not ticket_exists:
            await interaction.response.send_message(
                t('tickets.messages.ticket_thread_not_found'),
                ephemeral=True
            )
            return

        if is_closed:
            await interaction.response.send_message(
                t('tickets.messages.ticket_closed_no_modify'),
                ephemeral=True
            )
            return

        # Add user
        success = await self.db_manager.add_ticket_member(
            thread_id, user.id, interaction.user.id
        )

        if not success:
            await interaction.response.send_message(
                t('tickets.messages.add_user_already_added'),
                ephemeral=True
            )
            return

        # Add to thread
        await interaction.channel.add_user(user)

        # Success response
        embed = discord.Embed(
            title=t('tickets.messages.add_user_success_title'),
            description=t('tickets.messages.add_user_success_content').format(
                user=user.mention,
                adder=interaction.user.mention
            ),
            color=EmbedColors.ADD_USER
        )

        await interaction.response.send_message(embed=embed)
        await self.log_ticket_action('add_user', thread_id, interaction.user, extra_user=user)

    @app_commands.command(
        name="tickets_stats",
        description=locale_str(
            "View ticket system statistics",
            key="tickets.tickets_stats.description",
        ),
    )
    async def stats_command(self, interaction: discord.Interaction):
        """Show ticket statistics"""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                t('tickets.messages.admin_no_permission'),
                ephemeral=True
            )
            return

        try:
            stats = await self.db_manager.get_ticket_stats()

            embed = discord.Embed(
                title=t('tickets.messages.ticket_stats_title'),
                color=EmbedColors.DEFAULT
            )

            embed.add_field(
                name=t('tickets.messages.ticket_stats_total'),
                value=str(stats['total']),
                inline=True
            )

            embed.add_field(
                name=t('tickets.messages.ticket_stats_active'),
                value=str(stats['active']),
                inline=True
            )

            embed.add_field(
                name=t('tickets.messages.ticket_stats_closed'),
                value=str(stats['closed']),
                inline=True
            )

            embed.add_field(
                name=t('tickets.messages.ticket_stats_response_time'),
                value=t('tickets.messages.ticket_stats_response_time_format').format(
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
                    name=t('tickets.messages.ticket_stats_by_type'),
                    value=type_stats or t('tickets.messages.ticket_stats_no_data'),
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logging.error(f"Error getting ticket stats: {e}")
            await interaction.response.send_message(
                t('tickets.messages.stats_error'),
                ephemeral=True
            )

    @app_commands.command(
        name="tickets_admin_list",
        description=locale_str(
            "Show current admin configuration",
            key="tickets.tickets_admin_list.description",
        ),
    )
    async def admin_list(self, interaction: discord.Interaction):
        """Display current admin configuration."""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                t('tickets.messages.admin_no_permission'),
                ephemeral=True
            )
            return

        embed = await self.format_admin_list()
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="tickets_admin_add_role",
        description=locale_str(
            "Add an admin role",
            key="tickets.tickets_admin_add_role.description",
        ),
    )
    @app_commands.describe(
        role=locale_str(
            "Role to add",
            key="tickets.tickets_admin_add_role.params.role",
        ),
    )
    async def admin_add_role(self, interaction: discord.Interaction, role: discord.Role):
        """Add an admin role."""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                t('tickets.messages.admin_no_permission'),
                ephemeral=True
            )
            return

        view = AdminTypeSelectView(self, 'add', 'role', role.id)
        await interaction.response.send_message(
            t('tickets.messages.admin_type_select_add_role'),
            view=view,
            ephemeral=True
        )

    @app_commands.command(
        name="tickets_admin_remove_role",
        description=locale_str(
            "Remove an admin role",
            key="tickets.tickets_admin_remove_role.description",
        ),
    )
    @app_commands.describe(
        role=locale_str(
            "Role to remove",
            key="tickets.tickets_admin_remove_role.params.role",
        ),
    )
    async def admin_remove_role(self, interaction: discord.Interaction, role: discord.Role):
        """Remove an admin role."""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                t('tickets.messages.admin_no_permission'),
                ephemeral=True
            )
            return

        view = AdminTypeSelectView(self, 'remove', 'role', role.id)
        await interaction.response.send_message(
            t('tickets.messages.admin_type_select_remove_role'),
            view=view,
            ephemeral=True
        )

    @app_commands.command(
        name="tickets_admin_add_user",
        description=locale_str(
            "Add an admin user",
            key="tickets.tickets_admin_add_user.description",
        ),
    )
    @app_commands.describe(
        user=locale_str(
            "User to add",
            key="tickets.tickets_admin_add_user.params.user",
        ),
    )
    async def admin_add_user(self, interaction: discord.Interaction, user: discord.User):
        """Add an admin user."""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                t('tickets.messages.admin_no_permission'),
                ephemeral=True
            )
            return

        view = AdminTypeSelectView(self, 'add', 'user', user.id)
        await interaction.response.send_message(
            t('tickets.messages.admin_type_select_add_user'),
            view=view,
            ephemeral=True
        )

    @app_commands.command(
        name="tickets_admin_remove_user",
        description=locale_str(
            "Remove an admin user",
            key="tickets.tickets_admin_remove_user.description",
        ),
    )
    @app_commands.describe(
        user=locale_str(
            "User to remove",
            key="tickets.tickets_admin_remove_user.params.user",
        ),
    )
    async def admin_remove_user(self, interaction: discord.Interaction, user: discord.User):
        """Remove an admin user."""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                t('tickets.messages.admin_no_permission'),
                ephemeral=True
            )
            return

        view = AdminTypeSelectView(self, 'remove', 'user', user.id)
        await interaction.response.send_message(
            t('tickets.messages.admin_type_select_remove_user'),
            view=view,
            ephemeral=True
        )

    @app_commands.command(
        name="tickets_accept",
        description=locale_str(
            "Manually accept the current ticket",
            key="tickets.tickets_accept.description",
        ),
    )
    async def accept_ticket_command(self, interaction: discord.Interaction):
        """Accept ticket via command"""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                t('tickets.messages.command_thread_only'),
                ephemeral=True
            )
            return

        thread_id = interaction.channel.id
        thread = interaction.channel

        # Check if thread is already archived
        if thread.archived:
            await interaction.response.send_message(
                t('tickets.messages.ticket_already_closed'),
                ephemeral=True
            )
            return

        # Check if ticket exists and is not closed
        ticket_exists, is_closed = await self.db_manager.check_ticket_status(thread_id)
        if not ticket_exists:
            await interaction.response.send_message(
                t('tickets.messages.ticket_thread_not_found'),
                ephemeral=True
            )
            return

        if is_closed:
            await interaction.response.send_message(
                t('tickets.messages.ticket_closed_no_modify'),
                ephemeral=True
            )
            return

        # Get ticket data to check admin permissions
        ticket_data = await self.db_manager.fetch_ticket(thread_id)
        if not ticket_data:
            await interaction.response.send_message(
                t('tickets.messages.ticket_accept_get_info_error'),
                ephemeral=True
            )
            return

        # Check admin permissions
        if not await self.is_admin_for_type(interaction.user, ticket_data['type_name']):
            await interaction.response.send_message(
                t('tickets.messages.ticket_admin_only'),
                ephemeral=True
            )
            return

        # Accept the ticket
        success = await self.db_manager.accept_ticket(thread_id, interaction.user.id)
        if not success:
            await interaction.response.send_message(
                t('tickets.messages.ticket_already_accepted'),
                ephemeral=True
            )
            return

        # Create success embed
        embed = discord.Embed(
            title=t('tickets.messages.ticket_accepted_title'),
            description=t('tickets.messages.ticket_accepted_content').format(user=interaction.user.mention),
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
                        title=t('tickets.messages.ticket_accepted_dm_title'),
                        description=t('tickets.messages.ticket_accepted_dm_content').format(user=interaction.user.mention),
                        color=EmbedColors.ACCEPT
                    )

                    # Create jump button view
                    dm_view = discord.ui.View()
                    jump_button = discord.ui.Button(
                        style=discord.ButtonStyle.link,
                        label=t('tickets.messages.ticket_jump_button'),
                        url=f"https://discord.com/channels/{interaction.guild.id}/{thread_id}"
                    )
                    dm_view.add_item(jump_button)

                    await creator.send(embed=dm_embed, view=dm_view)
                except (discord.Forbidden, discord.HTTPException):
                    pass  # DM failed

    @app_commands.command(
        name="tickets_close",
        description=locale_str(
            "Manually close the current ticket",
            key="tickets.tickets_close.description",
        ),
    )
    @app_commands.describe(
        reason=locale_str(
            "Reason for closing the ticket",
            key="tickets.tickets_close.params.reason",
        ),
    )
    async def close_ticket_command(self, interaction: discord.Interaction, reason: str):
        """Close ticket via command"""
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message(
                t('tickets.messages.command_thread_only'),
                ephemeral=True
            )
            return

        thread_id = interaction.channel.id
        thread = interaction.channel

        # Check if thread is already archived
        if thread.archived:
            await interaction.response.send_message(
                t('tickets.messages.ticket_already_closed'),
                ephemeral=True
            )
            return

        # Check if ticket exists and is not closed
        ticket_exists, is_closed = await self.db_manager.check_ticket_status(thread_id)
        if not ticket_exists:
            await interaction.response.send_message(
                t('tickets.messages.ticket_thread_not_found'),
                ephemeral=True
            )
            return

        if is_closed:
            await interaction.response.send_message(
                t('tickets.messages.ticket_already_closed'),
                ephemeral=True
            )
            return

        # Get ticket data to check admin permissions
        ticket_data = await self.db_manager.fetch_ticket(thread_id)
        if not ticket_data:
            await interaction.response.send_message(
                t('tickets.messages.ticket_accept_get_info_error'),
                ephemeral=True
            )
            return

        # Check admin permissions
        if not await self.is_admin_for_type(interaction.user, ticket_data['type_name']):
            await interaction.response.send_message(
                t('tickets.messages.ticket_admin_only'),
                ephemeral=True
            )
            return

        # Close the ticket in database first
        success = await self.db_manager.close_ticket(thread_id, interaction.user.id, reason)
        if not success:
            await interaction.response.send_message(
                t('tickets.messages.ticket_close_stats_error'),
                ephemeral=True
            )
            return

        # Create success embed
        embed = discord.Embed(
            title=t('tickets.messages.close_dm_title'),
            description=t('tickets.messages.close_dm_content').format(
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

                    # Create disabled view with proper ticket status
                    disabled_view = await TicketThreadView.create_with_status(self, thread_id, "")
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
            logging.warning("Could not archive ticket thread %s: %s", fmt_channel(thread_id), e)

        # Send DM to creator
        if ticket_data:
            creator = interaction.guild.get_member(ticket_data['creator_id'])
            if creator:
                try:
                    dm_embed = discord.Embed(
                        title=t('tickets.messages.close_dm_title'),
                        description=t('tickets.messages.close_dm_content').format(
                            closer=interaction.user.mention,
                            reason=reason
                        ),
                        color=EmbedColors.CLOSE
                    )

                    # Create jump button view
                    dm_view = discord.ui.View()
                    jump_button = discord.ui.Button(
                        style=discord.ButtonStyle.link,
                        label=t('tickets.messages.ticket_jump_button'),
                        url=f"https://discord.com/channels/{interaction.guild.id}/{thread_id}"
                    )
                    dm_view.add_item(jump_button)

                    await creator.send(embed=dm_embed, view=dm_view)
                except (discord.Forbidden, discord.HTTPException):
                    pass  # DM failed

    @app_commands.command(
        name="tickets_refresh_buttons",
        description=locale_str(
            "Refresh button states for all tickets",
            key="tickets.tickets_refresh_buttons.description",
        ),
    )
    async def refresh_buttons_command(self, interaction: discord.Interaction):
        """Refresh button states for all tickets"""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                t('tickets.messages.admin_no_permission'),
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
            batch_size = 4  # Conservative batch size
            delay_between_batches = 1.2  # seconds

            total_tickets = len(all_tickets)
            current_progress = 0

            # Send initial progress message
            if total_tickets > 5:
                try:
                    await interaction.edit_original_response(
                        content=t('tickets.messages.refresh_buttons_starting').format(total=total_tickets)
                    )
                except discord.HTTPException:
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
                            ticket_view = TicketThreadView(self, thread_id, type_name, is_accepted)

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
                        logging.error("Error updating ticket thread %s: %s", fmt_channel(thread_id), e)
                        error_count += 1

                    current_progress += 1

                # Send progress update for large batches
                if total_tickets > 10 and i % (batch_size * 3) == 0 and current_progress < total_tickets:
                    try:
                        await interaction.edit_original_response(
                            content=t('tickets.messages.refresh_buttons_progress').format(
                                current=current_progress,
                                total=total_tickets,
                                updated=updated_count,
                                skipped=skipped_count,
                                errors=error_count
                            )
                        )
                    except discord.HTTPException:
                        pass  # Ignore edit failures

                # Add delay between batches to avoid rate limits
                if i + batch_size < len(all_tickets):
                    await asyncio.sleep(delay_between_batches)

            # Final result message
            await interaction.followup.send(
                t('tickets.messages.refresh_buttons_complete').format(
                    updated=updated_count,
                    skipped=skipped_count,
                    errors=error_count
                ),
                ephemeral=True
            )

        except Exception as e:
            logging.error(f"Error in refresh_buttons_command: {e}")
            await interaction.followup.send(
                t('tickets.messages.refresh_buttons_error'),
                ephemeral=True
            )

    @app_commands.command(
        name="tickets_refresh_main",
        description=locale_str(
            "Refresh the main ticket creation page (bot avatar + ticket types)",
            key="tickets.tickets_refresh_main.description",
        ),
    )
    async def refresh_main_message_command(self, interaction: discord.Interaction):
        """Refresh the main ticket creation message"""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                t('tickets.messages.admin_no_permission'),
                ephemeral=True
            )
            return

        try:
            # Get config data from database
            config_data = await self.db_manager.get_config()
            if not config_data:
                await interaction.response.send_message(
                    t('tickets.messages.refresh_main_no_config'),
                    ephemeral=True
                )
                return

            ticket_channel_id = config_data.get('ticket_channel_id')
            main_message_id = config_data.get('main_message_id')

            if not ticket_channel_id or not main_message_id:
                await interaction.response.send_message(
                    t('tickets.messages.refresh_main_config_incomplete'),
                    ephemeral=True
                )
                return

            # Get the ticket channel and message
            ticket_channel = self.bot.get_channel(ticket_channel_id)
            if not ticket_channel:
                await interaction.response.send_message(
                    t('tickets.messages.refresh_main_channel_not_found'),
                    ephemeral=True
                )
                return

            try:
                main_message = await ticket_channel.fetch_message(main_message_id)

                # Update the main message with current ticket types and bot avatar
                ticket_types = self.ticket_types
                if ticket_types:
                    await self.update_main_message(ticket_channel, main_message, ticket_types)

                    avatar_status = t('tickets.messages.refresh_main_avatar_updated') if self.bot.user.avatar else t('tickets.messages.refresh_main_no_avatar')
                    await interaction.response.send_message(
                        t('tickets.messages.refresh_main_success').format(
                            type_count=len(ticket_types),
                            avatar_status=avatar_status
                        ),
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        t('tickets.messages.refresh_main_no_types'),
                        ephemeral=True
                    )

            except discord.NotFound:
                await interaction.response.send_message(
                    t('tickets.messages.refresh_main_message_not_found'),
                    ephemeral=True
                )
            except Exception as e:
                logging.error(f"Error updating main message: {e}")
                await interaction.response.send_message(
                    t('tickets.messages.refresh_main_update_error'),
                    ephemeral=True
                )

        except Exception as e:
            logging.error(f"Error in refresh_main_message_command: {e}")
            await interaction.response.send_message(
                t('tickets.messages.refresh_main_error'),
                ephemeral=True
            )

    # ================== Ticket Type Management Commands ==================

    @app_commands.command(
        name="tickets_add_type",
        description=locale_str(
            "Add a new ticket type",
            key="tickets.tickets_add_type.description",
        ),
    )
    async def add_ticket_type(self, interaction: discord.Interaction):
        """Add a new ticket type"""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                t('tickets.messages.admin_no_permission'),
                ephemeral=True
            )
            return

        modal = TicketTypeModal(self)
        await interaction.response.send_modal(modal)

    @app_commands.command(
        name="tickets_edit_type",
        description=locale_str(
            "Edit an existing ticket type",
            key="tickets.tickets_edit_type.description",
        ),
    )
    async def edit_ticket_type(self, interaction: discord.Interaction):
        """Edit an existing ticket type"""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                t('tickets.messages.admin_no_permission'),
                ephemeral=True
            )
            return

        if not self.ticket_types:
            await interaction.response.send_message(
                "❌ 没有可编辑的工单类型",
                ephemeral=True
            )
            return

        view = TypeSelectView(self, 'edit')
        await interaction.response.send_message(
            t('tickets.messages.ticket_type_edit_title'),
            view=view,
            ephemeral=True
        )

    @app_commands.command(
        name="tickets_delete_type",
        description=locale_str(
            "Delete a ticket type",
            key="tickets.tickets_delete_type.description",
        ),
    )
    async def delete_ticket_type(self, interaction: discord.Interaction):
        """Delete a ticket type"""
        if not await self.is_admin_for_type(interaction.user):
            await interaction.response.send_message(
                t('tickets.messages.admin_no_permission'),
                ephemeral=True
            )
            return

        if not self.ticket_types:
            await interaction.response.send_message(
                "❌ 没有可删除的工单类型",
                ephemeral=True
            )
            return

        view = TypeSelectView(self, 'delete')
        await interaction.response.send_message(
            t('tickets.messages.ticket_type_delete_title'),
            view=view,
            ephemeral=True
        )

    async def check_and_close_missing_tickets(self):
        """检查并关闭频道已消失的工单"""
        try:
            # 获取所有活跃工单
            active_tickets = await self.db_manager.get_active_tickets()
            if not active_tickets:
                return

            guild_id = self.main_conf['guild_id']
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logging.error("Could not find guild %s for ticket cleanup", guild_id)
                return

            closed_count = 0
            for ticket in active_tickets:
                if ticket['is_closed']:
                    continue

                thread_id = ticket['thread_id']
                thread_found = False

                # 检查线程是否存在于任何频道中
                for channel in guild.text_channels:
                    try:
                        # 检查活跃线程
                        for thread in channel.threads:
                            if thread.id == thread_id:
                                thread_found = True
                                break

                        if thread_found:
                            break

                        # 检查归档线程
                        async for thread in channel.archived_threads(limit=None):
                            if thread.id == thread_id:
                                thread_found = True
                                break

                        if thread_found:
                            break
                    except Exception:
                        # 如果一个频道失败，继续检查其他频道
                        continue

                # 如果找不到线程，在数据库中关闭工单
                if not thread_found:
                    success = await self.db_manager.close_ticket(
                        thread_id,
                        self.bot.user.id,
                        "工单频道已被删除或不存在"
                    )
                    if success:
                        closed_count += 1
                        logging.info("Closed missing ticket thread %s", fmt_channel(thread_id))

            if closed_count > 0:
                logging.info(f"Automatically closed {closed_count} tickets with missing channels")

        except Exception as e:
            logging.error(f"Error checking and closing missing tickets: {e}")


    # Helper methods for admin management
    async def format_admin_list(self) -> discord.Embed:
        """Format current admin configuration as an embed."""
        guild_id = self.main_conf['guild_id']
        guild = self.bot.get_guild(guild_id)
        if not guild:
            raise ValueError("Could not find configured guild")

        embed = discord.Embed(
            title=t('tickets.messages.admin_list_title'),
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

        for type_name, type_data in self.ticket_types.items():
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
        lines = []

        if role_ids:
            lines.append(t('tickets.messages.admin_list_roles_header'))
            for role_id in role_ids:
                role = guild.get_role(role_id)
                if role:
                    lines.append(t('tickets.messages.admin_list_role_item').format(role=role.mention))

        if user_ids:
            if lines:
                lines.append("")
            lines.append(t('tickets.messages.admin_list_users_header'))
            for user_id in user_ids:
                user = self.bot.get_user(user_id)
                if user:
                    lines.append(t('tickets.messages.admin_list_user_item').format(user=user.mention))

        return "\n".join(lines) if lines else t('tickets.messages.admin_list_empty')

    async def save_config(self):
        """Persist tickets YAML config via the unified writer (P2-3).

        self.conf carries the admin_roles / admin_users / channel ids /
        messages fields only — ticket_types was popped at cog init
        because it lives in the DB now (P2-5). Writing the current
        snapshot through config.save_config round-trips ruamel.yaml
        (comments preserved) and refreshes the in-memory cache so
        subsequent reads observe the canonical parsed form.
        """
        try:
            from bot.utils import config as _config
            reloaded = await _config.save_config('tickets', self.conf)
            # `ticket_types` is never in YAML anymore; keep the snapshot
            # aligned so an accidental re-read of self.conf doesn't
            # resurface a stale key.
            reloaded.pop('ticket_types', None)
            self.conf = reloaded
        except Exception as e:
            logging.error(f"Error saving config: {e}")

    async def add_global_admin(self, target_type: str, target_id: int, interaction: discord.Interaction) -> bool:
        """Add a global admin (role or user).

        Promoting an id to the global list also removes any per-type
        override that already carried it. With ticket_types now in DB,
        those per-type mutations need to round-trip through
        upsert_ticket_type — mutating the cache alone would not persist.
        """
        type_list_key = 'admin_roles' if target_type == 'role' else 'admin_users'
        for type_name, type_data in list(self.ticket_types.items()):
            if target_id in type_data.get(type_list_key, []):
                updated = dict(type_data)
                updated[type_list_key] = [x for x in type_data.get(type_list_key, []) if x != target_id]
                await self.db_manager.upsert_ticket_type(type_name, updated)
        await self._refresh_ticket_types()

        target_list = type_list_key
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
                    t('tickets.messages.admin_global_role_exists'),
                    ephemeral=True
                )
                return False
        else:
            if target_id in self.conf.get('admin_users', []):
                await interaction.followup.send(
                    t('tickets.messages.admin_global_user_exists'),
                    ephemeral=True
                )
                return False

        if ticket_type not in self.ticket_types:
            return False

        type_data = dict(self.ticket_types[ticket_type])  # shallow copy; we persist via upsert
        target_list = 'admin_roles' if target_type == 'role' else 'admin_users'

        type_data.setdefault(target_list, list(type_data.get(target_list, [])))

        if target_id not in type_data[target_list]:
            type_data[target_list].append(target_id)
            # Persist the mutated type_data row (DB is authoritative for
            # ticket_types; save_config only writes the YAML conf).
            await self.db_manager.upsert_ticket_type(ticket_type, type_data)
            await self._refresh_ticket_types()
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
        source = self.ticket_types.get(ticket_type)
        if not source:
            return False

        target_list = 'admin_roles' if target_type == 'role' else 'admin_users'
        if target_id in source.get(target_list, []):
            type_data = dict(source)
            type_data[target_list] = [x for x in source.get(target_list, []) if x != target_id]
            await self.db_manager.upsert_ticket_type(ticket_type, type_data)
            await self._refresh_ticket_types()
            return True
        return False

    async def handle_admin_change_response(self, success: bool, action: str, target_type: str,
                                         target: discord.Object, ticket_type: str = "global",
                                         interaction: discord.Interaction = None):
        """Handle response messages for admin changes."""
        if not interaction:
            return

        if success:
            if action == 'add':
                if ticket_type == "global":
                    message = t('tickets.messages.admin_add_global', mention=target.mention)
                else:
                    message = t('tickets.messages.admin_add_type', mention=target.mention, type=ticket_type)
            else:
                if ticket_type == "global":
                    message = t('tickets.messages.admin_remove_global', mention=target.mention)
                else:
                    message = t('tickets.messages.admin_remove_type', mention=target.mention, type=ticket_type)
        else:
            if action == 'add':
                message = t('tickets.messages.admin_add_failed', mention=target.mention)
            else:
                message = t('tickets.messages.admin_remove_failed', mention=target.mention)

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
            type_data = self.ticket_types.get(type_name, {})
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
                logging.warning(
                    "Too many admins (%s) for ticket thread %s, limiting to %s",
                    len(all_admins_to_add),
                    fmt_channel(thread),
                    max_admins,
                )
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
                        logging.warning(
                            "Rate limited while adding admin %s to ticket thread %s, waiting...",
                            fmt_user(admin),
                            fmt_channel(thread),
                        )
                        await asyncio.sleep(2)  # Wait longer for rate limit
                        try:
                            await thread.add_user(admin)
                            await self.db_manager.add_ticket_member(thread.id, admin.id, self.bot.user.id)
                            added_count += 1
                        except Exception as retry_e:
                            logging.error(
                                "Failed to add admin %s to ticket thread %s after rate limit retry: %s",
                                fmt_user(admin),
                                fmt_channel(thread),
                                retry_e,
                            )
                            failed_count += 1
                    else:
                        logging.error(
                            "HTTP error adding admin %s to ticket thread %s: %s",
                            fmt_user(admin),
                            fmt_channel(thread),
                            e,
                        )
                        failed_count += 1
                except Exception as e:
                    logging.error(
                        "Error adding admin %s to ticket thread %s: %s",
                        fmt_user(admin),
                        fmt_channel(thread),
                        e,
                    )
                    failed_count += 1

            if added_count > 0:
                logging.info("Added %s admins to ticket thread %s", added_count, fmt_channel(thread))
            if failed_count > 0:
                logging.warning("Failed to add %s admins to ticket thread %s", failed_count, fmt_channel(thread))

            # Send DM notifications to all admins with rate limiting
            dm_count = 0
            dm_failed = 0
            for admin in all_admins_for_notification:
                try:
                    admin_embed = discord.Embed(
                        title=t('tickets.messages.admin_notification_title'),
                        description=t('tickets.messages.admin_notification_description').format(
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
                        label=t('tickets.messages.admin_notification_jump_button'),
                        url=f"https://discord.com/channels/{thread.guild.id}/{thread.id}"
                    )
                    dm_view.add_item(jump_button)

                    await admin.send(embed=admin_embed, view=dm_view)
                    dm_count += 1

                    # Rate limiting for DMs: pause every 10 DMs
                    if dm_count % 10 == 0:
                        await asyncio.sleep(1)

                except discord.Forbidden:
                    logging.info("Could not send DM to admin %s (DMs disabled)", fmt_user(admin))
                    dm_failed += 1
                except discord.HTTPException as e:
                    if e.status == 429:  # Rate limited
                        logging.warning("Rate limited while sending DM to admin %s, waiting...", fmt_user(admin))
                        await asyncio.sleep(5)  # Wait longer for DM rate limits
                        try:
                            await admin.send(embed=admin_embed, view=dm_view)
                            dm_count += 1
                        except Exception as retry_e:
                            logging.error(
                                "Failed to send DM to admin %s after rate limit retry: %s",
                                fmt_user(admin),
                                retry_e,
                            )
                            dm_failed += 1
                    else:
                        logging.error("HTTP error sending DM to admin %s: %s", fmt_user(admin), e)
                        dm_failed += 1
                except Exception as e:
                    logging.error("Error sending DM to admin %s: %s", fmt_user(admin), e)
                    dm_failed += 1

            if dm_count > 0:
                logging.info("Sent DM notifications to %s admins for ticket thread %s", dm_count, fmt_channel(thread))
            if dm_failed > 0:
                logging.warning(
                    "Failed to send DM notifications to %s admins for ticket thread %s",
                    dm_failed,
                    fmt_channel(thread),
                )

        except Exception as e:
            logging.error(
                "Error in add_admins_to_ticket for thread %s creator %s: %s",
                fmt_channel(thread),
                fmt_user(creator),
                e,
            )
