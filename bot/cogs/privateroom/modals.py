import discord

from bot.utils.i18n import t


class PurchaseModal(discord.ui.Modal):
    def __init__(self, cog, cost, balance, is_restore=False, old_room=None, is_restore_settings=False, is_renewal=False):
        if is_renewal:
            title = cog.conf['messages']['renewal_modal_title']
            label = cog.conf['messages']['renewal_modal_label']
            placeholder = cog.conf['messages']['renewal_modal_placeholder']
        else:
            title = cog.conf['messages']['modal_title']
            label = cog.conf['messages']['modal_label']
            placeholder = cog.conf['messages']['modal_placeholder']

        super().__init__(title=title)
        self.cog = cog
        self.cost = cost
        self.balance = balance
        self.is_restore = is_restore
        self.old_room = old_room
        self.is_restore_settings = is_restore_settings
        self.is_renewal = is_renewal

        # 加载消息文本

        # 添加确认输入
        self.confirmation = discord.ui.TextInput(
            label=label,
            placeholder=placeholder,
            required=True,
            max_length=5
        )
        self.add_item(self.confirmation)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)

        # 确认输入验证
        if self.confirmation.value.lower() != 'yes':
            await interaction.followup.send(
                t('privateroom.messages.error_confirmation_failed'),
                ephemeral=True
            )
            return

        # 处理续费逻辑
        if self.is_renewal:
            await self.cog.process_advance_renewal(interaction, self.cost)
            return

        # 最终检查用户是否已有活跃的私人房间
        active_room = await self.cog.db.get_active_room_by_user(interaction.user.id)
        if active_room:
            channel = self.cog.bot.get_channel(active_room['room_id'])
            if channel:
                await interaction.followup.send(
                    t('privateroom.messages.error_already_owns'),
                    ephemeral=True
                )
                return

        # 再次检查余额，确保在交互过程中余额没有变化
        if self.cost > 0:
            current_balance = await self.cog.shop_db.get_user_balance(interaction.user.id)
            if current_balance < self.cost:
                await interaction.followup.send(
                    t('privateroom.messages.error_insufficient_balance'),
                    ephemeral=True
                )
                return

        # 创建或恢复房间
        if self.is_restore and self.old_room:
            success = await self.cog.restore_private_room(interaction, self.old_room, self.cost)
        else:
            success = await self.cog.create_private_room(interaction, self.cost)

        if not success:
            await interaction.followup.send(
                t('privateroom.messages.error_create_failed'),
                ephemeral=True
            )
