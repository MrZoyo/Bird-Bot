import discord

from bot.utils.i18n import t


class CheckinMakeupModal(discord.ui.Modal):
    def __init__(self, db, user_id, conf, remaining_count, balance, cost, missed_date):
        super().__init__(title=t('shop.makeup_modal_title'))
        self.db = db
        self.user_id = user_id
        self.conf = conf
        self.remaining_count = remaining_count
        self.balance = balance
        self.cost = cost
        self.missed_date = missed_date
        
        self.info_field = discord.ui.TextInput(
            label=t('shop.makeup_modal_info_label'),
            default=t('shop.makeup_modal_info_format').format(
                remaining=remaining_count,
                total=conf['makeup_checkin_limit_per_month'],
                cost=cost,
                balance=balance
            ),
            style=discord.TextStyle.paragraph,
            required=False
        )
        
        self.confirm_field = discord.ui.TextInput(
            label=t('shop.makeup_modal_confirm_label'),
            placeholder=t('shop.makeup_modal_confirm_placeholder'),
            required=True,
            max_length=10,
            style=discord.TextStyle.short
        )
        
        self.add_item(self.info_field)
        self.add_item(self.confirm_field)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        confirm_text = self.confirm_field.value.strip().lower()
        if confirm_text not in ['yes', 'y']:
            await interaction.followup.send(
                t('shop.makeup_modal_invalid_confirm'), 
                ephemeral=True
            )
            return
        
        # Check balance again
        current_balance = await self.db.get_user_balance(self.user_id)
        if current_balance < self.cost:
            await interaction.followup.send(
                t('shop.makeup_checkin_insufficient_balance_description').format(
                    cost=self.cost, 
                    balance=current_balance
                ),
                ephemeral=True
            )
            return
        
        # Perform makeup checkin
        success = await self.db.add_makeup_record(self.user_id, self.missed_date)
        if not success:
            await interaction.followup.send(
                t('shop.makeup_checkin_no_quota_description').format(
                    limit=self.conf['makeup_checkin_limit_per_month']
                ),
                ephemeral=True
            )
            return
        
        # Deduct balance
        new_balance = await self.db.update_user_balance_with_record(
            self.user_id,
            -self.cost,
            "makeup_checkin",
            self.user_id,
            f"Makeup check-in for {self.missed_date}"
        )
        
        await interaction.followup.send(
            t('shop.makeup_modal_success_private').format(
                date=self.missed_date,
                cost=self.cost
            ),
            ephemeral=True
        )




class BalanceModifyModal(discord.ui.Modal):
    def __init__(self, db, target_user, conf, current_balance):
        super().__init__(
            title=t('shop.modify_balance_modal_title').format(
                user_name=target_user.display_name
            )
        )
        self.db = db
        self.target_user = target_user
        self.conf = conf

        amount_label = (
            f"{t('shop.modify_balance_amount_label')} (💰:{current_balance})"
        )
        self.amount = discord.ui.TextInput(
            label=amount_label,
            placeholder=t('shop.modify_balance_amount_placeholder'),
            required=True
        )

        self.operation_type = discord.ui.TextInput(
            label=t('shop.modify_balance_type_label'),
            placeholder=t('shop.modify_balance_type_placeholder'),
            required=False
        )

        self.reason = discord.ui.TextInput(
            label=t('shop.modify_balance_reason_label'),
            placeholder=t('shop.modify_balance_reason_placeholder'),
            style=discord.TextStyle.paragraph,
            required=True
        )

        self.add_item(self.amount)
        self.add_item(self.operation_type)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            # Parse and validate amount
            amount = int(self.amount.value)

            # Validate operation type
            op_type = self.operation_type.value.strip().lower()
            if not op_type or op_type not in ["shop", "admin"]:
                op_type = "admin"

            # Get reason
            reason = self.reason.value.strip()

            # Update balance with record
            new_balance = await self.db.update_user_balance_with_record(
                self.target_user.id,
                amount,
                op_type,
                interaction.user.id,
                reason
            )

            # Send success message
            await interaction.followup.send(
                t('shop.modify_balance_success').format(
                    user_name=self.target_user.display_name,
                    amount=('+' if amount > 0 else '') + str(amount),
                    balance=new_balance
                ),
            )

        except ValueError:
            await interaction.followup.send(
                t('shop.modify_balance_invalid_amount'),
                ephemeral=True
            )

