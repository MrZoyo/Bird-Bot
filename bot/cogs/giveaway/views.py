import datetime
import logging

import discord
from discord import components, ui
from discord.ui import Button, View
from discord.utils import format_dt

from bot.utils import config
from bot.utils.i18n import t


class GiveawayParticipationView(ui.View):
    def __init__(self, bot, giveaway_id, giveaway_channel_id):
        super().__init__(timeout=None)  # No interaction time limit
        self.bot = bot
        self.giveaway_id = giveaway_id
        self.giveaway_channel_id = int(giveaway_channel_id)
        self.message_id = None

        self.conf = config.get_config('giveaway')
        self.giveaway_join_button_label = t('giveaway.giveaway_join_button_label')
        self.giveaway_exit_button_label = t('giveaway.giveaway_exit_button_label')
        self.giveaway_already_joined_message = t('giveaway.giveaway_already_joined_message')
        self.giveaway_joined_message = t('giveaway.giveaway_joined_message')
        self.giveaway_leave_message = t('giveaway.giveaway_leave_message')
        self.giveaway_not_access_message = t('giveaway.giveaway_not_access_message')
        self.giveaway_embed_participants_title = t('giveaway.giveaway_embed_participants_title')
        self.giveaway_end_message = t('giveaway.giveaway_end_message')

        # buttons definition
        self.participate_button = Button(label=self.giveaway_join_button_label,
                                         style=components.ButtonStyle.primary,
                                         custom_id=f"participate_{str(self.giveaway_id)}")
        self.exit_button = Button(label=self.giveaway_exit_button_label,
                                  style=components.ButtonStyle.danger,
                                  custom_id=f"exit_{str(self.giveaway_id)}")

        self.participate_button.callback = self.participate
        self.exit_button.callback = self.exit

        self.add_item(self.participate_button)

    def disable_all_buttons(self):
        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True

    def to_dict(self):
        return {
            'giveaway_id': self.giveaway_id,
            'giveaway_channel_id': self.giveaway_channel_id,
            'message_id': self.message_id,
        }

    async def participate(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            # The interaction has already been responded to
            return

        giveaway_cog = self.bot.get_cog('GiveawayCog')

        if await giveaway_cog.is_participant(self.giveaway_id, interaction.user.id):
            # The user has already participated

            # Create an exit button
            exit_button = ui.Button(label=self.giveaway_exit_button_label, style=discord.ButtonStyle.danger)
            exit_button.callback = self.exit

            # Create a view for the exit button
            exit_view = ui.View()
            exit_view.add_item(exit_button)

            await interaction.response.send_message(self.giveaway_already_joined_message,
                                                    view=exit_view,
                                                    ephemeral=True)
        else:
            # The user is participating for the first time
            # Check if the user meets the requirements to participate in the giveaway
            if await giveaway_cog.check_participant_eligibility(self.giveaway_id, interaction.user.id, interaction):
                # Add the user's ID to the participant_ids column in the database
                await giveaway_cog.add_participant_to_giveaway(self.giveaway_id, interaction.user.id, interaction)

                # Create an exit button
                exit_button = ui.Button(label=self.giveaway_exit_button_label, style=discord.ButtonStyle.danger)
                exit_button.callback = self.exit

                # Create a view for the exit button
                exit_view = ui.View()
                exit_view.add_item(exit_button)

                # Send a message with the exit button
                await interaction.response.send_message(self.giveaway_joined_message,
                                                        view=exit_view,
                                                        ephemeral=True)
            else:
                # The user does not meet the requirements to participate in the giveaway
                await interaction.response.send_message(self.giveaway_not_access_message, ephemeral=True)

        # Update the number of participants in the giveaway embed
        await self.update_giveaway_embed()

    async def exit(self, interaction: discord.Interaction):
        giveaway_cog = self.bot.get_cog('GiveawayCog')
        giveaway_details = await giveaway_cog.fetch_giveaway(self.giveaway_id)

        if giveaway_details['is_end']:
            # The giveaway has already ended
            await interaction.response.send_message(self.giveaway_end_message, ephemeral=True)
            return
        if await giveaway_cog.is_participant(self.giveaway_id, interaction.user.id):
            # The user is currently participating and wants to exit

            # Remove the user's ID from the participant_ids column in the database
            await giveaway_cog.remove_participant_from_giveaway(self.giveaway_id, interaction.user.id)

            await interaction.response.send_message(self.giveaway_leave_message, ephemeral=True)

            # Update the number of participants in the giveaway embed
            await self.update_giveaway_embed()

    async def update_giveaway_embed(self):
        # Fetch the giveaway message
        channel = self.bot.get_channel(self.giveaway_channel_id)
        if channel is None:
            logging.error(f"Error: Channel {self.giveaway_channel_id} not found")
            return
        message = await channel.fetch_message(self.message_id)

        # Find the index of the "Number of Participants" field
        index = next((i for i, field in enumerate(message.embeds[0].fields) if
                      field.name == self.giveaway_embed_participants_title),
                     None)

        # Update the "Number of Participants" field with the new number of participants
        giveaway_cog = self.bot.get_cog('GiveawayCog')
        participant_count = await giveaway_cog.get_participant_count(self.giveaway_id)

        if index is not None:
            # Update the "Number of Participants" field if it exists
            message.embeds[0].set_field_at(index, name=self.giveaway_embed_participants_title,
                                           value=str(participant_count),
                                           inline=True)

        await message.edit(embed=message.embeds[0])

class GiveawayConfirmationView(View):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

        self.conf = config.get_config('giveaway')
        self.giveaway_embed_title_open = t('giveaway.giveaway_embed_title_open')
        self.giveaway_embed_provider_title = t('giveaway.giveaway_embed_provider_title')
        self.giveaway_embed_timeend_title = t('giveaway.giveaway_embed_timeend_title')
        self.giveaway_embed_winner_number_title = t('giveaway.giveaway_embed_winner_number_title')
        self.giveaway_embed_participants_title = t('giveaway.giveaway_embed_participants_title')
        self.giveaway_embed_participants_text = t('giveaway.giveaway_embed_participants_text')
        self.giveaway_embed_description_title = t('giveaway.giveaway_embed_description_title')
        self.giveaway_embed_footer = t('giveaway.giveaway_embed_footer')

    def create_embed(self, giveaway_id, prizes, description, winners, duration, providers, interaction):
        # Create an embed to show all the giveaway information
        embed = discord.Embed(
            title=self.giveaway_embed_title_open.format(prizes=prizes),
            color=discord.Color.blue()
        )

        # Calculate the end time and express it as elapsed_time
        end_time = datetime.datetime.now() + datetime.timedelta(minutes=duration)
        elapsed_time = format_dt(end_time, style='R')

        # Set the start time in the timestamp
        embed.timestamp = datetime.datetime.now()

        # Add the fields to the embed
        embed.add_field(name=self.giveaway_embed_provider_title, value=providers, inline=False)
        embed.add_field(name=self.giveaway_embed_timeend_title, value=elapsed_time, inline=True)
        embed.add_field(name=self.giveaway_embed_winner_number_title, value=str(winners), inline=True)
        embed.add_field(name=self.giveaway_embed_participants_title, value=self.giveaway_embed_participants_text,
                        inline=True)
        embed.add_field(name=self.giveaway_embed_description_title, value=description, inline=False)

        embed.set_footer(text=self.giveaway_embed_footer.format(giveaway_id=giveaway_id))

        # Set the thumbnail to the bot's avatar
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        return embed

class GiveawayCheckParticipantView(ui.View):
    def __init__(self, giveaway_id, participant_ids):
        super().__init__()
        self.giveaway_id = giveaway_id
        self.participant_ids = participant_ids
        self.current_page = 0
        self.items_per_page = 50
        self.message = None

        self.previous_button = ui.Button(style=discord.ButtonStyle.blurple, label="Previous", disabled=True)
        self.next_button = ui.Button(style=discord.ButtonStyle.green,
                                     label="Next",
                                     disabled=len(participant_ids) <= self.items_per_page)

        self.previous_button.callback = self.previous_page
        self.next_button.callback = self.next_page

        self.add_item(self.previous_button)
        self.add_item(self.next_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    async def previous_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_page -= 1
        await self.update_buttons()
        await interaction.edit_original_response(embed=self.format_page(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_page += 1
        await self.update_buttons()
        await interaction.edit_original_response(embed=self.format_page(), view=self)

    async def update_buttons(self):
        max_pages = self.get_max_pages()  # Ensure you calculate it fresh
        self.previous_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page >= max_pages - 1
        if self.message:
            await self.message.edit(view=self)

    def get_max_pages(self):
        return (len(self.participant_ids) - 1) // self.items_per_page + 1

    def format_page(self):
        # Create an Embed object
        embed_title = f"Participants for Giveaway ID: {self.giveaway_id}"
        embed = discord.Embed(title=embed_title, color=discord.Color.blue())

        # Calculate the range of participants for the current page
        start_index = self.current_page * self.items_per_page
        end_index = start_index + self.items_per_page

        # Get the participants for the current page
        current_page_participants = self.participant_ids[start_index:end_index]

        message = ""

        # Add the participants to the Embed object
        for i, participant_id in enumerate(current_page_participants, start=start_index + 1):
            message += f"{i}. <@{participant_id}>\n"

        embed.description = message

        # Add the page number to the footer
        embed.set_footer(
            text=f"Page {self.current_page + 1}/{self.get_max_pages()} | Total Participants: {len(self.participant_ids)}")

        return embed

