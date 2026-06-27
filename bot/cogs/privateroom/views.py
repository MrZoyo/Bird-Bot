import asyncio
from datetime import datetime

import discord

from bot.utils.components_v2 import build_panel_container
from bot.utils.i18n import t

from .modals import PurchaseModal


class ConfirmPurchaseView(discord.ui.View):
    def __init__(self, cog, user, hours, percentage, cost, balance, is_restore=False, old_room=None, is_renewal=False):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self.hours = hours
        self.percentage = percentage
        self.cost = cost
        self.balance = balance
        self.is_restore = is_restore
        self.old_room = old_room
        self.is_renewal = is_renewal

        # 加载消息文本

        # 添加确认按钮
        if is_renewal:
            confirm_label = t('privateroom.messages.renewal_confirm_button')
            cancel_label = t('privateroom.messages.renewal_cancel_button')
        else:
            confirm_label = t('privateroom.messages.confirm_button')
            cancel_label = t('privateroom.messages.cancel_button')

        confirm_button = discord.ui.Button(
            style=discord.ButtonStyle.green,
            label=confirm_label,
            custom_id='confirm_purchase'
        )
        confirm_button.callback = self.confirm_callback

        # 添加取消按钮
        cancel_button = discord.ui.Button(
            style=discord.ButtonStyle.red,
            label=cancel_label,
            custom_id='cancel_purchase'
        )
        cancel_button.callback = self.cancel_callback

        self.add_item(confirm_button)
        self.add_item(cancel_button)

    async def confirm_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return

        # 显示购买确认modal
        modal = PurchaseModal(
            self.cog,
            self.cost,
            self.balance,
            self.is_restore,
            self.old_room,
            is_renewal=self.is_renewal
        )
        await interaction.response.send_modal(modal)

        # Schedule message deletion after 15 seconds
        await asyncio.sleep(15)
        try:
            await interaction.message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass  # Message might already be deleted or not accessible

    async def cancel_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return

        cancel_message = t('privateroom.messages.renewal_cancelled') if self.is_renewal else t('privateroom.messages.purchase_cancelled')
        await interaction.response.edit_message(
            content=cancel_message,
            embed=None,
            view=None
        )


class PrivateRoomShopView(discord.ui.LayoutView):
    def __init__(self, cog, *, available_rooms: int | None = None):
        super().__init__(timeout=None)  # 永久有效
        self.cog = cog
        self.available_rooms = available_rooms

        # 加载消息文本

        # 添加购买按钮
        purchase_button = discord.ui.Button(
            style=discord.ButtonStyle.primary,
            label=t('privateroom.messages.shop_button_label'),
            custom_id='purchase_privateroom'
        )
        purchase_button.callback = self.purchase_callback

        # 添加提前续费按钮
        renewal_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=t('privateroom.messages.shop_renewal_button_label'),
            custom_id='advance_renewal_privateroom'
        )
        renewal_button.callback = self.renewal_callback

        # 添加恢复按钮
        restore_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            label=t('privateroom.messages.shop_restore_button_label'),
            custom_id='restore_privateroom'
        )
        restore_button.callback = self.restore_callback

        thumbnail_url = None
        if self.cog.bot.user.avatar:
            thumbnail_url = self.cog.bot.user.avatar.url

        max_rooms = self.cog.conf['max_rooms']
        shown_available_rooms = (
            available_rooms
            if available_rooms is not None
            else max_rooms
        )

        self.add_item(build_panel_container(
            title=t('privateroom.messages.shop_title'),
            description=t('privateroom.messages.shop_description').format(
                points_cost=self.cog.conf['points_cost'],
                duration=self.cog.conf['room_duration_days'],
                hours_threshold=self.cog.conf['voice_hours_threshold'],
                booster_hours=self.cog.conf.get('booster_discount_hours', 0),
                available_rooms=shown_available_rooms,
                max_rooms=max_rooms,
            ),
            footer=t('privateroom.messages.shop_footer'),
            accent_color=discord.Color.purple(),
            thumbnail_url=thumbnail_url,
            buttons=[purchase_button, renewal_button, restore_button],
        ))

    async def purchase_callback(self, interaction: discord.Interaction):
        await self.cog.handle_purchase_request(interaction)

    async def renewal_callback(self, interaction: discord.Interaction):
        await self.cog.handle_advance_renewal_request(interaction)

    async def restore_callback(self, interaction: discord.Interaction):
        await self.cog.handle_restore_request(interaction)


class ResetConfirmView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=60)
        self.cog = cog

        # 添加确认按钮
        confirm_button = discord.ui.Button(
            style=discord.ButtonStyle.danger,
            label=t('privateroom.messages.reset_confirm_button'),
            custom_id='confirm_reset'
        )
        confirm_button.callback = self.confirm_callback

        # 添加取消按钮
        cancel_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=t('privateroom.messages.reset_cancel_button'),
            custom_id='cancel_reset'
        )
        cancel_button.callback = self.cancel_callback

        self.add_item(confirm_button)
        self.add_item(cancel_button)

    async def confirm_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        await self.cog.reset_system(interaction)

    async def cancel_callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=t('privateroom.messages.reset_cancelled'),
            view=None
        )


class RoomListView(discord.ui.View):
    def __init__(self, cog, rooms, total_rooms, page=1, items_per_page=10):
        super().__init__(timeout=180)  # 3 minute timeout
        self.cog = cog
        self.page = page
        self.items_per_page = items_per_page
        self.total_rooms = total_rooms
        self.total_pages = (total_rooms - 1) // items_per_page + 1 if total_rooms > 0 else 1

        # Messages

        # Add navigation buttons
        self.prev_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=t('privateroom.messages.list_prev_button'),
            disabled=page <= 1,
            row=0
        )
        self.prev_button.callback = self.previous_page

        self.next_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label=t('privateroom.messages.list_next_button'),
            disabled=page >= self.total_pages,
            row=0
        )
        self.next_button.callback = self.next_page

        self.add_item(self.prev_button)
        self.add_item(self.next_button)

    async def format_page(self):
        """Format the embed for the current page"""
        rooms, _ = await self.cog.db.get_paginated_active_rooms(self.page, self.items_per_page)

        embed = discord.Embed(
            title=t('privateroom.messages.list_title'),
            color=discord.Color.blue()
        )

        # Add room information
        for room_id, user_id, start_date, end_date in rooms:
            # Get user and channel objects
            user = self.cog.bot.get_user(user_id)
            channel = self.cog.bot.get_channel(room_id)

            user_mention = user.mention if user else f"用户 ID: {user_id}"
            channel_name = channel.name if channel else f"未找到 (ID: {room_id})"

            # Format dates
            start = datetime.fromisoformat(start_date).strftime("%Y-%m-%d")
            end = datetime.fromisoformat(end_date).strftime("%Y-%m-%d")

            # Add field
            embed.add_field(
                name=channel_name,
                value=t('privateroom.messages.list_room_info').format(
                    owner_mention=user_mention,
                    start=start,
                    end=end
                ),
                inline=False
            )

        # Add pagination info to footer
        embed.set_footer(text=t('privateroom.messages.list_footer').format(
            current_page=self.page,
            total_pages=self.total_pages,
            total_rooms=self.total_rooms
        ))

        return embed

    async def previous_page(self, interaction: discord.Interaction):
        """Handle previous page button click"""
        self.page -= 1

        # Update button states
        self.prev_button.disabled = self.page <= 1
        self.next_button.disabled = False

        # Update message
        embed = await self.format_page()
        await interaction.response.edit_message(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        """Handle next page button click"""
        self.page += 1

        # Update button states
        self.prev_button.disabled = False
        self.next_button.disabled = self.page >= self.total_pages

        # Update message
        embed = await self.format_page()
        await interaction.response.edit_message(embed=embed, view=self)
