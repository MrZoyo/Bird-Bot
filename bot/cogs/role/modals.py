import discord

from bot.utils.i18n import t
from bot.utils.modal_helpers import add_labeled_text_input
from bot.utils.role_db import RoleDatabaseManager
from bot.utils.signature_cooldown import (
    DEFAULT_SIGNATURE_MAX_CHANGES,
    resolve_signature_cooldown_days,
)


class SignatureModal(discord.ui.Modal):
    def __init__(self, bot, max_length):
        super().__init__(title=t('role.signature.modal_title'))
        self.bot = bot
        self.signature = add_labeled_text_input(
            self,
            t('role.signature.modal_label'),
            placeholder=t('role.signature.modal_placeholder'),
            max_length=max_length,
            style=discord.TextStyle.paragraph
        )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        role_cog = self.bot.get_cog('RoleCog')
        signature_config = role_cog.role_config['signature']
        cooldown_days = resolve_signature_cooldown_days(signature_config)
        role_db = RoleDatabaseManager(role_cog.main_config['db_path'])

        # Check if user is disabled
        signature_data = await role_db.get_user_signature(interaction.user.id)
        if signature_data and signature_data['is_disabled']:
            await interaction.followup.send(t('role.signature.disabled_message'), ephemeral=True)
            return

        # Find available time slot
        available_slot = await role_db.find_available_time_slot(
            interaction.user.id,
            cooldown_days=cooldown_days,
        )
        if available_slot is None:
            # Cannot change signature yet
            current_sig = signature_data['signature'] if signature_data else "无"
            await interaction.followup.send(
                t('role.signature.cooldown_message',
                  signature=current_sig,
                  max_changes=DEFAULT_SIGNATURE_MAX_CHANGES,
                  cooldown_days=cooldown_days),
                ephemeral=True
            )
            return

        # Update signature
        if await role_db.update_user_signature(interaction.user.id, str(self.signature), available_slot):
            # Calculate remaining changes
            remaining_times = await role_db.get_signature_remaining_changes(
                interaction.user.id,
                cooldown_days=cooldown_days,
            )

            await interaction.followup.send(
                t('role.signature.success_message',
                  signature=str(self.signature),
                  remaining_times=remaining_times,
                  max_changes=DEFAULT_SIGNATURE_MAX_CHANGES,
                  cooldown_days=cooldown_days),
                ephemeral=True
            )
        else:
            await interaction.followup.send(t('role.signature.update_failed_message'), ephemeral=True)
