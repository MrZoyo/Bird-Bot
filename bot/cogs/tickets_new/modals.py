import logging

import discord

from bot.utils.i18n import t

from .embeds import EmbedColors


class TicketConfirmModal(discord.ui.Modal):
    def __init__(self, cog, type_name: str, type_data: dict):
        super().__init__(title=t('tickets_new.messages.ticket_modal_confirm_title').format(type_name=type_name))
        self.cog = cog
        self.type_name = type_name
        self.type_data = type_data

        self.confirm_input = discord.ui.TextInput(
            label=t('tickets_new.messages.ticket_modal_confirm_label').format(type_name=type_name),
            placeholder=t('tickets_new.messages.ticket_modal_confirm_placeholder'),
            max_length=10,
            required=True
        )
        self.add_item(self.confirm_input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirm_input.value.lower() != "yes":
            await interaction.response.send_message(
                t('tickets_new.messages.ticket_confirmation_failed'),
                ephemeral=True
            )
            return

        # Acknowledge the interaction immediately to prevent timeout
        await interaction.response.defer(ephemeral=True)

        # Create the ticket thread
        await self.cog.create_ticket_thread(interaction, self.type_name, self.type_data)


class AddUserModal(discord.ui.Modal):
    def __init__(self, cog, thread_id: int):
        super().__init__(title=t('tickets_new.messages.add_user_modal_title'))
        self.cog = cog
        self.thread_id = thread_id

        self.user_input = discord.ui.TextInput(
            label=t('tickets_new.messages.add_user_modal_label'),
            placeholder=t('tickets_new.messages.add_user_modal_placeholder'),
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
                    t('tickets_new.messages.add_user_not_found'),
                    ephemeral=True
                )
                return

            # Check if ticket is closed
            _, is_closed = await self.cog.db_manager.check_ticket_status(self.thread_id)
            if is_closed:
                await interaction.response.send_message(
                    t('tickets_new.messages.ticket_closed_no_modify'),
                    ephemeral=True
                )
                return

            # Add user to database
            success = await self.cog.db_manager.add_ticket_member(
                self.thread_id, user_id, interaction.user.id
            )

            if not success:
                await interaction.response.send_message(
                    t('tickets_new.messages.add_user_already_added'),
                    ephemeral=True
                )
                return

            # Add user to thread
            thread = interaction.guild.get_thread(self.thread_id)
            if thread:
                await thread.add_user(user)

            # Create success embed
            embed = discord.Embed(
                title=t('tickets_new.messages.add_user_success_title'),
                description=t('tickets_new.messages.add_user_success_content').format(
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
                    title=t('tickets_new.messages.add_user_dm_title'),
                    description=t('tickets_new.messages.add_user_dm_content').format(thread=thread.mention if thread else f"<#{self.thread_id}>"),
                    color=EmbedColors.ADD_USER
                )

                # Create jump button view
                dm_view = discord.ui.View()
                jump_button = discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    label=t('tickets_new.messages.ticket_jump_button'),
                    url=f"https://discord.com/channels/{thread.guild.id}/{thread.id}" if thread else f"https://discord.com/channels/{interaction.guild.id}/{self.thread_id}"
                )
                dm_view.add_item(jump_button)

                await user.send(embed=dm_embed, view=dm_view)
            except (discord.Forbidden, discord.HTTPException):
                pass  # DM failed

        except ValueError:
            await interaction.response.send_message(
                t('tickets_new.messages.add_user_invalid_id'),
                ephemeral=True
            )
        except Exception as e:
            logging.error(f"Error in AddUserModal: {e}")
            await interaction.response.send_message(
                t('tickets_new.messages.add_user_error').format(error=str(e)),
                ephemeral=True
            )


class CloseTicketModal(discord.ui.Modal):
    def __init__(self, cog, thread_id: int):
        super().__init__(title=t('tickets_new.messages.close_modal_title'))
        self.cog = cog
        self.thread_id = thread_id

        self.reason_input = discord.ui.TextInput(
            label=t('tickets_new.messages.close_modal_label'),
            placeholder=t('tickets_new.messages.close_modal_placeholder'),
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=True
        )
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Lazy import to break the modals ↔ views cycle: TicketThreadView
        # lives in .views, which itself imports CloseTicketModal at the
        # top level. Importing here resolves at first call, after both
        # modules finish loading.
        from .views import TicketThreadView

        try:
            reason = self.reason_input.value

            # Check if thread is already archived
            thread = interaction.guild.get_thread(self.thread_id)
            if thread and thread.archived:
                await interaction.response.send_message(
                    t('tickets_new.messages.ticket_already_closed'),
                    ephemeral=True
                )
                return

            # Close in database first
            success = await self.cog.db_manager.close_ticket(
                self.thread_id, interaction.user.id, reason
            )

            if not success:
                await interaction.response.send_message(
                    t('tickets_new.messages.ticket_close_stats_error'),
                    ephemeral=True
                )
                return

            # Create close embed (for in-thread display)
            embed = discord.Embed(
                title=t('tickets_new.messages.close_dm_title'),
                description=t('tickets_new.messages.close_dm_content').format(
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

                        # Create disabled view with proper ticket status
                        disabled_view = await TicketThreadView.create_with_status(self.cog, self.thread_id, "")
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
                            title=t('tickets_new.messages.close_dm_title'),
                            description=t('tickets_new.messages.close_dm_content').format(
                                closer=interaction.user.mention,
                                reason=reason
                            ),
                            color=EmbedColors.CLOSE
                        )

                        # Create jump button view
                        dm_view = discord.ui.View()
                        jump_button = discord.ui.Button(
                            style=discord.ButtonStyle.link,
                            label=t('tickets_new.messages.ticket_jump_button'),
                            url=f"https://discord.com/channels/{interaction.guild.id}/{self.thread_id}"
                        )
                        dm_view.add_item(jump_button)

                        await creator.send(embed=dm_embed, view=dm_view)
                    except (discord.Forbidden, discord.HTTPException):
                        pass  # DM failed

        except Exception as e:
            logging.error(f"Error in CloseTicketModal: {e}")
            # Try to respond if we haven't already
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        t('tickets_new.messages.ticket_close_error'),
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        t('tickets_new.messages.ticket_close_error'),
                        ephemeral=True
                    )
            except discord.HTTPException:
                pass  # Give up if both fail


class TicketTypeModal(discord.ui.Modal):
    def __init__(self, cog, edit_type=None):
        title = t('tickets_new.messages.ticket_type_modal_edit_title').format(type_name=edit_type) if edit_type else t('tickets_new.messages.ticket_type_modal_title')
        super().__init__(title=title)
        self.cog = cog
        self.edit_type = edit_type

        # Pre-fill if editing
        existing_data = cog.ticket_types.get(edit_type, {}) if edit_type else {}

        self.type_name = discord.ui.TextInput(
            label=t('tickets_new.messages.ticket_type_name_label'),
            placeholder=t('tickets_new.messages.ticket_type_name_placeholder'),
            default=(edit_type or "")[:50],  # Ensure default doesn't exceed max_length
            required=True,
            max_length=50
        )
        self.add_item(self.type_name)

        self.description = discord.ui.TextInput(
            label=t('tickets_new.messages.ticket_type_description_label'),
            placeholder=t('tickets_new.messages.ticket_type_description_placeholder'),
            default=existing_data.get('description', '')[:100],  # Ensure default doesn't exceed max_length
            required=True,
            max_length=100
        )
        self.add_item(self.description)

        self.guide = discord.ui.TextInput(
            label=t('tickets_new.messages.ticket_type_guide_label'),
            placeholder=t('tickets_new.messages.ticket_type_guide_placeholder'),
            style=discord.TextStyle.paragraph,
            default=existing_data.get('guide', '')[:1000],  # Ensure default doesn't exceed max_length
            required=True,
            max_length=1000
        )
        self.add_item(self.guide)

        self.button_color = discord.ui.TextInput(
            label=t('tickets_new.messages.ticket_type_color_label'),
            placeholder=t('tickets_new.messages.ticket_type_color_placeholder'),
            default=existing_data.get('button_color', 'b')[:10],  # Ensure default doesn't exceed max_length
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

            # Check if editing or creating new.
            # Pre-refactor this block mutated self.cog.ticket_types in place
            # then called db_manager.save_config('ticket_types', ...) — a
            # method that never existed on TicketsNewDatabaseManager — and
            # overwrote self.cog.conf with db_manager.get_config()'s 3-field
            # result, wiping messages / admin_* / channel ids from memory.
            # The whole command silently failed through discord.py's error
            # handler. Now: mutate a local type_data dict, persist via the
            # ticket_types CRUD (single row in DB), then refresh the cache.
            if self.edit_type and self.edit_type != type_name:
                # Renaming path
                if type_name in self.cog.ticket_types:
                    await interaction.response.send_message(
                        f"❌ 工单类型 '{type_name}' 已存在",
                        ephemeral=True
                    )
                    return

                old_data = self.cog.ticket_types[self.edit_type]
                type_data = {
                    'name': type_name,
                    'description': description,
                    'guide': guide,
                    'button_color': button_color,
                    'admin_roles': list(old_data.get('admin_roles', [])),
                    'admin_users': list(old_data.get('admin_users', [])),
                }
                await self.cog.db_manager.rename_ticket_type(
                    self.edit_type, type_name, type_data,
                )

                action = "edit"
                old_name = self.edit_type
            else:
                # Add or in-place edit (no rename)
                if not self.edit_type and type_name in self.cog.ticket_types:
                    await interaction.response.send_message(
                        f"❌ 工单类型 '{type_name}' 已存在",
                        ephemeral=True
                    )
                    return

                existing_admin_data = {}
                if self.edit_type:
                    prior = self.cog.ticket_types.get(self.edit_type, {})
                    existing_admin_data = {
                        'admin_roles': list(prior.get('admin_roles', [])),
                        'admin_users': list(prior.get('admin_users', [])),
                    }

                type_data = {
                    'name': type_name,
                    'description': description,
                    'guide': guide,
                    'button_color': button_color,
                    'admin_roles': existing_admin_data.get('admin_roles', []),
                    'admin_users': existing_admin_data.get('admin_users', []),
                }
                await self.cog.db_manager.upsert_ticket_type(type_name, type_data)

                action = "edit" if self.edit_type else "add"
                old_name = self.edit_type if self.edit_type else None

            await self.cog._refresh_ticket_types()

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
