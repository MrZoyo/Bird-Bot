import logging

import discord

from bot.utils.components_v2 import build_panel_container
from bot.utils.i18n import t

from .embeds import EmbedColors
from .modals import (
    AddUserModal,
    CloseTicketModal,
    TicketConfirmModal,
    TicketTypeModal,
)


class TicketCreateView(discord.ui.LayoutView):
    def __init__(self, cog, ticket_types):
        super().__init__(timeout=None)
        self.cog = cog
        self.ticket_types = ticket_types

        # Create buttons for each ticket type
        buttons = []
        type_lines = []
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
            buttons.append(button)
            type_lines.append(f"**{type_name}**\n{type_data.get('description', '无描述')}")

        description_parts = [t('tickets.messages.ticket_main_description')]
        if type_lines:
            description_parts.append("\n\n".join(type_lines))

        self.add_item(build_panel_container(
            title=t('tickets.messages.ticket_main_title'),
            description="\n\n".join(part for part in description_parts if part),
            footer=t('tickets.messages.ticket_main_footer'),
            accent_color=EmbedColors.DEFAULT,
            buttons=buttons,
        ))

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
                t('tickets.messages.ticket_thread_create_error'),
                ephemeral=True
            )


class TicketThreadView(discord.ui.View):
    def __init__(self, cog, thread_id: int, type_name: str, is_accepted: bool = False):
        super().__init__(timeout=None)
        self.cog = cog
        self.thread_id = thread_id
        self.type_name = type_name

        # Accept button
        accept_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label=t('tickets.messages.ticket_accept_button_disabled') if is_accepted else t('tickets.messages.ticket_accept_button'),
            custom_id=f'accept_ticket_{thread_id}',
            disabled=is_accepted
        )
        accept_button.callback = self.accept_callback
        self.add_item(accept_button)

        # Add user button
        add_user_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=t('tickets.messages.ticket_add_user_button'),
            custom_id=f'add_user_{thread_id}'
        )
        add_user_button.callback = self.add_user_callback
        self.add_item(add_user_button)

        # Close button
        close_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label=t('tickets.messages.ticket_close_button'),
            custom_id=f'close_ticket_{thread_id}'
        )
        close_button.callback = self.close_callback
        self.add_item(close_button)

    @classmethod
    async def create_with_status(cls, cog, thread_id: int, type_name: str):
        """Create a TicketThreadView with proper ticket status from database"""
        ticket_data = await cog.db_manager.fetch_ticket(thread_id)
        is_accepted = ticket_data.get('is_accepted', False) if ticket_data else False
        return cls(cog, thread_id, type_name, is_accepted)

    async def accept_callback(self, interaction: discord.Interaction):
        """Handle ticket acceptance"""
        try:
            if not await self.cog.is_admin_for_type(interaction.user, self.type_name):
                await interaction.response.send_message(
                    t('tickets.messages.ticket_admin_only'),
                    ephemeral=True
                )
                return

            success = await self.cog.db_manager.accept_ticket(self.thread_id, interaction.user.id)
            if not success:
                await interaction.response.send_message(
                    t('tickets.messages.ticket_already_accepted'),
                    ephemeral=True
                )
                return

            # Create accepted embed
            embed = discord.Embed(
                title=t('tickets.messages.ticket_accepted_title'),
                description=t('tickets.messages.ticket_accepted_content').format(user=interaction.user.mention),
                color=EmbedColors.ACCEPT
            )

            # Update view to disable accept button
            new_view = TicketThreadView(self.cog, self.thread_id, self.type_name, is_accepted=True)

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
                            title=t('tickets.messages.ticket_accepted_dm_title'),
                            description=t('tickets.messages.ticket_accepted_dm_content').format(user=interaction.user.mention),
                            color=EmbedColors.ACCEPT
                        )

                        # Create jump button view
                        dm_view = discord.ui.View()
                        jump_button = discord.ui.Button(
                            style=discord.ButtonStyle.link,
                            label=t('tickets.messages.ticket_jump_button'),
                            url=f"https://discord.com/channels/{interaction.guild.id}/{self.thread_id}"
                        )
                        dm_view.add_item(jump_button)

                        await creator.send(embed=dm_embed, view=dm_view)
                    except (discord.Forbidden, discord.HTTPException):
                        pass  # DM failed, continue

        except Exception as e:
            logging.error(f"Error in accept_callback: {e}")
            await interaction.response.send_message(
                t('tickets.messages.ticket_accept_get_info_error'),
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


class AdminTypeSelectView(discord.ui.View):
    def __init__(self, cog, action_type, target_type, target_id):
        super().__init__()
        self.cog = cog
        self.action_type = action_type
        self.target_type = target_type
        self.target_id = target_id

        options = [
            discord.SelectOption(
                label=t('tickets.messages.global_ticket_select_label'),
                description=t('tickets.messages.global_ticket_select_description'),
                value="global"
            )
        ]

        for type_name, type_data in cog.ticket_types.items():
            options.append(
                discord.SelectOption(
                    label=type_name,
                    description=type_data.get('description', '')[:100],
                    value=type_name
                )
            )

        select = discord.ui.Select(
            placeholder=t('tickets.messages.ticket_type_select_placeholder'),
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
            await interaction.followup.send(t('tickets.messages.target_not_found'), ephemeral=True)
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


class TypeSelectView(discord.ui.View):
    def __init__(self, cog, action):
        super().__init__()
        self.cog = cog
        self.action = action  # 'edit' or 'delete'

        if not cog.ticket_types:
            return

        options = []
        for type_name, type_data in cog.ticket_types.items():
            options.append(discord.SelectOption(
                label=type_name,
                description=type_data.get('description', '')[:100],
                emoji='✏️' if action == 'edit' else '🗑️'
            ))

        if options:
            select = discord.ui.Select(
                placeholder=t('tickets.messages.ticket_type_select_placeholder'),
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
            # Remove from the ticket_types table (DB is authoritative
            # now, P2-5). Same pattern as the add/edit path — no more
            # broken save_config('ticket_types', ...) / self.conf
            # clobber from get_config().
            if self.type_name in self.cog.ticket_types:
                ok = await self.cog.db_manager.remove_ticket_type(self.type_name)
                if not ok:
                    await interaction.response.send_message(
                        t('tickets.messages.ticket_type_delete_failure'),
                        ephemeral=True,
                    )
                    return
                await self.cog._refresh_ticket_types()

                await interaction.response.send_message(
                    t('tickets.messages.ticket_type_delete_success').format(type_name=self.type_name),
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
