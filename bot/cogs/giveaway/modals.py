import datetime
import random
import re
import string

import discord
from discord import ui

from bot.utils import config
from bot.utils.i18n import t

from .views import GiveawayConfirmationView, GiveawayParticipationView


class GiveawayForm(ui.Modal, title='Create Giveaway'):
    duration = ui.TextInput(label='Duration Time', placeholder='Enter the duration(Eg. 1d/24h/30m)', required=True,
                            min_length=2)
    winners = ui.TextInput(label='Number of Winners', placeholder='Enter the number of winners', required=True,
                           min_length=1, max_length=2, default="1")
    prizes = ui.TextInput(label='Prizes', placeholder='Enter the prizes', required=True, max_length=100)
    description = ui.TextInput(label='Description', placeholder='Enter the description', required=False,
                               default="No Limit", max_length=500)
    providers = ui.TextInput(label='Providers', placeholder='Leave blank as default', required=False)

    def __init__(self, bot, db, reaction_limit=0, message_limit=0, timespent_limit=0):
        super().__init__()
        self.bot = bot
        self.db = db
        self.giveaways = {}

        self.conf = config.get_config('giveaway')
        self.giveaway_channel_id = self.conf['giveaway_channel_id']
        self.giveaway_default_provider = t('giveaway.giveaway_default_provider')

        self.reaction_limit = reaction_limit
        self.message_limit = message_limit
        # Convert the timespent_limit to seconds
        self.timespent_limit = timespent_limit * 60

    async def on_submit(self, interaction: discord.Interaction):
        # Validate the input
        if not self.validate():
            return

        # Convert the duration to minutes
        matches = re.findall(r'(\d+)(w|week|weeks|d|day|days|h|hour|hours|m|min|mins|minute|minutes)',
                             self.duration.value)
        duration_in_minutes = 0

        for match in matches:
            duration_value, duration_unit = match
            duration_value = int(duration_value)

            if duration_unit.startswith('w'):
                duration_in_minutes += duration_value * 7 * 24 * 60
            elif duration_unit.startswith('d'):
                duration_in_minutes += duration_value * 24 * 60
            elif duration_unit.startswith('h'):
                duration_in_minutes += duration_value * 60
            else:
                duration_in_minutes += duration_value

        # Generate a unique giveaway id
        giveaway_id = await self.generate_giveaway_id()

        # Store the giveaway details
        self.giveaways[giveaway_id] = {
            'duration': duration_in_minutes,
            'winners': int(self.winners.value),
            'prizes': self.prizes.value,
            'description': self.description.value,
            'providers': self.providers.value if self.providers.value else self.giveaway_default_provider,
            'initiator': interaction.user.id
        }

        # Create an instance of GiveawayConfirmationView
        giveaway_confirmation_view = GiveawayConfirmationView(self.bot)

        # Create the embed
        embed = giveaway_confirmation_view.create_embed(
            giveaway_id=giveaway_id,
            prizes=self.prizes.value,
            description=self.description.value,
            winners=self.winners.value,
            duration=duration_in_minutes,
            providers=self.providers.value if self.providers.value else self.giveaway_default_provider,
            interaction=interaction
        )

        message = f"Limitations:\n" \
                  f"Reaction: {self.reaction_limit}\n" \
                  f"Message: {self.message_limit}\n" \
                  f"Time Spent(min): {self.timespent_limit / 60}"

        await interaction.response.send_message(content=message, embed=embed, ephemeral=False)

        # Create an instance of GiveawayParticipationView
        giveaway_view = GiveawayParticipationView(self.bot, giveaway_id, self.giveaway_channel_id)

        # Send the embed in the giveaway channel
        giveaway_channel = self.bot.get_channel(self.giveaway_channel_id)
        message = await giveaway_channel.send(embed=embed, view=giveaway_view)

        # Insert the giveaway into the database
        await self.db.insert_giveaway(
            giveaway_id,
            message.id,
            datetime.datetime.now().isoformat(),
            duration_in_minutes,
            int(self.winners.value),
            self.prizes.value,
            self.description.value,
            interaction.user.id,
            None,  # winner_ids will be None initially
            self.reaction_limit,
            self.message_limit,
            self.timespent_limit,
        )

        # Store the message ID in the view
        giveaway_view.message_id = message.id

        # Store the GiveawayParticipationView instance in the giveaways dictionary
        self.bot.get_cog('GiveawayCog').giveaways[giveaway_id] = giveaway_view

        # Save the state of the GiveawayParticipationView instance
        await self.bot.get_cog('GiveawayCog').save_giveaways(giveaway_id, giveaway_view)

    async def generate_giveaway_id(self):
        existing_ids = await self.db.fetch_all_giveaway_ids()
        while True:
            giveaway_id = ''.join(random.choices(string.digits, k=10))
            if giveaway_id not in existing_ids:
                return giveaway_id

    def validate(self):
        # Validate winners
        if not self.winners.value.isdigit() or int(self.winners.value) < 1:
            self.winners.error = "The number of winners must be an integer greater than or equal to one."
            return False

        # Validate duration
        matches = re.findall(r'(\d+)(w|week|weeks|d|day|days|h|hour|hours|m|min|mins|minute|minutes)',
                             self.duration.value)
        if not matches:
            self.duration.error = ("Invalid duration format. Please enter a duration in the format "
                                   "(w/week/weeks/d/day/days/h/hour/hours/m/min/mins/minute/minutes).")
            return False

        return True

