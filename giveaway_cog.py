# Author: MrZoyo
# Version: 0.7.7
# Date: 2024-07-03
# ========================================
import discord
from discord import app_commands, ui, components
from discord.ext import commands, tasks
from discord.utils import format_dt
from discord.ui import Button, View
import random
import string
import aiosqlite
import re
import datetime
import tempfile
import logging

from illegal_team_act_cog import IllegalTeamActCog


class GiveawayParticipationView(ui.View):
    def __init__(self, bot, giveaway_id, giveaway_channel_id):
        super().__init__(timeout=None)  # No interaction time limit
        self.bot = bot
        self.giveaway_id = giveaway_id
        self.giveaway_channel_id = int(giveaway_channel_id)
        self.message_id = None

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']
        self.giveaway_join_button_label = config['giveaway_join_button_label']
        self.giveaway_exit_button_label = config['giveaway_exit_button_label']
        self.giveaway_already_joined_message = config['giveaway_already_joined_message']
        self.giveaway_joined_message = config['giveaway_joined_message']
        self.giveaway_leave_message = config['giveaway_leave_message']
        self.giveaway_not_access_message = config['giveaway_not_access_message']
        self.giveaway_embed_participants_title = config['giveaway_embed_participants_title']
        self.giveaway_end_message = config['giveaway_end_message']

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

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']
        self.giveaway_embed_title_open = config['giveaway_embed_title_open']
        self.giveaway_embed_provider_title = config['giveaway_embed_provider_title']
        self.giveaway_embed_timeend_title = config['giveaway_embed_timeend_title']
        self.giveaway_embed_winner_number_title = config['giveaway_embed_winner_number_title']
        self.giveaway_embed_participants_title = config['giveaway_embed_participants_title']
        self.giveaway_embed_participants_text = config['giveaway_embed_participants_text']
        self.giveaway_embed_description_title = config['giveaway_embed_description_title']
        self.giveaway_embed_footer = config['giveaway_embed_footer']

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


class GiveawayForm(ui.Modal, title='Create Giveaway'):
    duration = ui.TextInput(label='Duration Time', placeholder='Enter the duration(Eg. 1d/24h/30m)', required=True,
                            min_length=2)
    winners = ui.TextInput(label='Number of Winners', placeholder='Enter the number of winners', required=True,
                           min_length=1, max_length=2, default="1")
    prizes = ui.TextInput(label='Prizes', placeholder='Enter the prizes', required=True, max_length=100)
    description = ui.TextInput(label='Description', placeholder='Enter the description', required=False,
                               default="No Limit", max_length=500)
    providers = ui.TextInput(label='Providers', placeholder='Leave blank as default', required=False)

    def __init__(self, bot, reaction_limit=0, message_limit=0, timespent_limit=0):
        super().__init__()
        self.bot = bot
        self.giveaways = {}

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']
        self.giveaway_channel_id = config['giveaway_channel_id']
        self.giveaway_default_provider = config['giveaway_default_provider']

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
        await self.insert_giveaway(
            giveaway_id,
            message.id,  # Add this line
            datetime.datetime.now().isoformat(),
            duration_in_minutes,
            int(self.winners.value),
            self.prizes.value,
            self.description.value,
            interaction.user.id,
            None,  # winner_ids will be None initially
            self.reaction_limit,
            self.message_limit,
            self.timespent_limit
        )

        # Store the message ID in the view
        giveaway_view.message_id = message.id

        # Store the GiveawayParticipationView instance in the giveaways dictionary
        self.bot.get_cog('GiveawayCog').giveaways[giveaway_id] = giveaway_view

        # Save the state of the GiveawayParticipationView instance
        await self.bot.get_cog('GiveawayCog').save_giveaways(giveaway_id, giveaway_view)

    async def generate_giveaway_id(self):
        # Fetch all existing giveaway IDs
        existing_ids = await self.fetch_all_giveaway_ids()

        # Generate a unique giveaway id
        while True:
            giveaway_id = ''.join(random.choices(string.digits, k=10))
            # Check if the giveaway_id already exists in the fetched list
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

    async def insert_giveaway(self, giveaway_id, message_id, starttime, duration, winner_number, prizes, description,
                              creator_id, winner_ids, reaction_req, message_req, timespent_req):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(
                'INSERT INTO giveaway (giveaway_id, message_id, starttime, duration, winner_number, prizes, description, creator_id, winner_ids, reaction_req, message_req, timespent_req) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (giveaway_id, message_id, starttime, duration, winner_number, prizes, description, creator_id,
                 winner_ids, reaction_req, message_req, timespent_req))
            await db.commit()
            await cursor.close()

    async def fetch_giveaway(self, giveaway_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(
                'SELECT * FROM giveaway WHERE giveaway_id = ?',
                (giveaway_id,))
            record = await cursor.fetchone()
            await cursor.close()
            return record

    async def fetch_all_giveaway_ids(self):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT giveaway_id FROM giveaway")
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


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


class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.giveaways = {}
        self.illegal_act_cog = IllegalTeamActCog(bot)

        config = self.bot.get_cog('ConfigCog').config
        self.db_path = config['db_path']
        self.giveaway_channel_id = config['giveaway_channel_id']
        self.giveaway_embed_title_open = config['giveaway_embed_title_open']
        self.giveaway_embed_title_closed = config['giveaway_embed_title_closed']
        self.giveaway_embed_title_closed_deleted = config['giveaway_embed_title_closed_deleted']
        self.giveaway_embed_description_closed_deleted = config['giveaway_embed_description_closed_deleted']
        self.giveaway_embed_description_title = config['giveaway_embed_description_title']
        self.giveaway_embed_end_label = config['giveaway_embed_end_label']
        self.giveaway_embed_winner_title = config['giveaway_embed_winner_title']
        self.giveaway_embed_no_winner = config['giveaway_embed_no_winner']
        self.giveaway_embed_cancel_label = config['giveaway_embed_cancel_label']
        self.giveaway_embed_earlyend_label = config['giveaway_embed_earlyend_label']
        self.giveaway_embed_time_extend_label = config['giveaway_embed_time_extend_label']
        self.giveaway_embed_timeend_title = config['giveaway_embed_timeend_title']
        self.giveaway_win_public_message = config['giveaway_win_public_message']
        self.giveaway_win_private_message = config['giveaway_win_private_message']
        self.giveaway_fail_message = config['giveaway_fail_message']

        # Start the background task
        self.check_giveaways.start()

    async def draw_winners(self, giveaway_id, winner_number):
        # Fetch the participant_ids from the database
        participant_ids = await self.fetch_participant_ids(giveaway_id)

        # Check if there are any participants
        if not participant_ids:
            return []

        # Draw the winners
        winners = random.sample(participant_ids, min(winner_number, len(participant_ids)))

        return winners

    @tasks.loop(seconds=30)
    async def check_giveaways(self):
        if not self.bot.is_closed():
            try:
                # logging.info("Checking giveaways...")
                # Fetch all giveaways from the database
                giveaways = await self.fetch_all_giveaways(is_end=False)

                for giveaway in giveaways:
                    # print(giveaway)
                    (giveaway_id, message_id, starttime, duration,
                     winner_number, prizes, description, creator_id,
                     reaction_req, message_req, timespent_req,
                     participant_ids, winner_ids, is_end) = giveaway

                    message_id = int(message_id)
                    # Check if the giveaway has ended
                    end_time = datetime.datetime.fromisoformat(starttime) + datetime.timedelta(minutes=duration)
                    if datetime.datetime.now() >= end_time and not is_end:
                        # print(end_time)
                        # The giveaway has ended
                        # Fetch the giveaway message
                        channel = self.bot.get_channel(self.giveaway_channel_id)
                        if channel is None:
                            logging.error(f"Couldn't find a channel with the ID {self.giveaway_channel_id}")
                        else:
                            try:
                                # Try to fetch the giveaway message
                                message = await channel.fetch_message(message_id)
                            except discord.NotFound:
                                logging.error(f"Couldn't find a message with the ID {message_id}")
                                # The message has been deleted
                                if datetime.datetime.now() >= end_time:
                                    # The giveaway has ended
                                    # Create a new end embed
                                    embed = discord.Embed(
                                        title=self.giveaway_embed_title_closed_deleted.format(giveaway_id),
                                        description=self.giveaway_embed_description_closed_deleted,
                                        color=discord.Color.red()
                                    )

                                    # Send the end embed
                                    await channel.send(embed=embed)

                                    # Mark the giveaway as ended in the database
                                    await self.mark_giveaway_as_ended(giveaway_id)
                            else:
                                # print(self.giveaways)
                                # The message exists
                                # Check if the giveaway_id exists in the giveaways dictionary
                                if giveaway_id not in self.giveaways:
                                    # The giveaway_id does not exist in the dictionary
                                    # Create a new GiveawayParticipationView instance
                                    giveaway_view = GiveawayParticipationView(self.bot, giveaway_id,
                                                                              self.giveaway_channel_id)
                                    giveaway_view.message_id = message_id
                                    self.giveaways[giveaway_id] = giveaway_view

                                    # Add the participants from the database
                                    if participant_ids is not None:
                                        participant_ids = str(participant_ids)
                                        participant_id_list = participant_ids.split(',')
                                        giveaway_view.participants = set(
                                            int(participant_id) for participant_id in participant_id_list)
                                    else:
                                        giveaway_view.participants = set()

                                # Fetch the GiveawayParticipationView instance associated with the giveaway
                                giveaway_view = self.giveaways[giveaway_id]

                                # Modify the embed
                                embed = message.embeds[0]
                                embed.title = self.giveaway_embed_end_label + embed.title
                                embed.color = discord.Color.red()

                                # Make all buttons non-interactive
                                for item in giveaway_view.children:
                                    item.disabled = True

                                # Draw the winners
                                winners = await self.draw_winners(giveaway_id, winner_number)

                                # Notify the winners
                                await self.notify_winners(winners, prizes, giveaway_id)

                                winners = [f"<@{winner_id}>" if winner_id is not None and winner_id != 0 else None for
                                           winner_id in winners]

                                embed.add_field(name=self.giveaway_embed_winner_title,
                                                value=", ".join(winners) if winners else self.giveaway_embed_no_winner,
                                                inline=False)

                                # Update the message
                                await message.edit(embed=embed, view=giveaway_view)

                                # Update the results to the database
                                await self.update_giveaway(giveaway_id, winners)

                                # Mark the giveaway as ended in the database
                                await self.mark_giveaway_as_ended(giveaway_id)

            except Exception as e:
                # print(f"An error occurred in check_giveaways: {e}")
                logging.error(f"An error occurred in check_giveaways: {e}")

    @check_giveaways.before_loop
    async def before_check_giveaways(self):
        await self.bot.wait_until_ready()

    async def fetch_all_giveaways(self, is_end=True):
        if not is_end:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.cursor()
                await cursor.execute('SELECT * FROM giveaway WHERE is_end = 0')
                records = await cursor.fetchall()
                await cursor.close()
                return records
        else:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.cursor()
                await cursor.execute('SELECT * FROM giveaway')
                records = await cursor.fetchall()
                await cursor.close()
                return records

    async def update_giveaway(self, giveaway_id, winners):
        logging.info(f"Updating giveaway {giveaway_id} with winners {winners}")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(
                'UPDATE giveaway SET winner_ids = ?, is_end = 1 WHERE giveaway_id = ?',
                (",".join(str(winner_id) for winner_id in winners), giveaway_id))
            await db.commit()
            await cursor.close()

        await self.cleanup_ended_giveaways()

    async def mark_giveaway_as_ended(self, giveaway_id):
        logging.info(f"Marking giveaway {giveaway_id} as ended")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(
                'UPDATE giveaway SET is_end = 1 WHERE giveaway_id = ?',
                (giveaway_id,))
            await db.commit()
            await cursor.close()

        await self.cleanup_ended_giveaways()

    @app_commands.command(name="ga_create",
                          description="Create a new giveaway"
                          )
    @app_commands.describe(reaction_req="Enter the reaction requirement",
                           message_req="Enter the message requirement",
                           timespent_req="Enter the time spent requirement(minute)"
                           )
    async def create_giveaway(self, interaction: discord.Interaction,
                              reaction_req: int = 0,
                              message_req: int = 0,
                              timespent_req: int = 0
                              ):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return

        form = GiveawayForm(self.bot, reaction_req, message_req, timespent_req)
        await interaction.response.send_modal(form)

    @app_commands.command(name="check_giveaway",
                          description="Check all current giveaways")
    async def check_giveaway(self, interaction: discord.Interaction):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return

        giveaways = await self.fetch_all_giveaways()

        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".txt") as temp:
            for giveaway in giveaways:
                temp.write(f"{giveaway}\n")
            temp.flush()  # Ensure data is written to disk
            temp.seek(0)  # Reset file pointer to the beginning for reading

            # Create a discord file object directly from the temporary file
            discord_file = discord.File(temp.name, filename="giveaways.txt")
            await interaction.response.send_message("Here are all the current giveaways:", file=discord_file)

        # File will be automatically deleted when exiting the with block

    async def add_participant_to_giveaway(self, giveaway_id, participant_id, interaction):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # Fetch the current participant_ids from the giveaway
            await cursor.execute('SELECT participant_ids FROM giveaway WHERE giveaway_id = ?',
                                 (giveaway_id,))
            record = await cursor.fetchone()
            current_participant_ids = record[0]

            # Add the new participant_id to the current participant_ids
            if current_participant_ids is None:
                new_participant_ids = str(participant_id)
            else:
                new_participant_ids = current_participant_ids + ',' + str(participant_id)

            # Update the participant_ids in the giveaway
            await cursor.execute('UPDATE giveaway SET participant_ids = ? WHERE giveaway_id = ?',
                                 (new_participant_ids, giveaway_id))
            await db.commit()
            await cursor.close()

    async def remove_participant_from_giveaway(self, giveaway_id, participant_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # Fetch the current participant_ids from the database
            await cursor.execute('SELECT participant_ids FROM giveaway WHERE giveaway_id = ?', (giveaway_id,))
            record = await cursor.fetchone()
            if record[0] is not None:
                current_participant_ids = record[0].split(',')

                # Remove the participant_id from the current participant_ids
                if str(participant_id) in current_participant_ids:
                    current_participant_ids.remove(str(participant_id))

                # Update the participant_ids in the database
                await cursor.execute('UPDATE giveaway SET participant_ids = ? WHERE giveaway_id = ?',
                                     (','.join(current_participant_ids), giveaway_id))
            else:
                logging.error(f"No participant_ids found for giveaway_id {giveaway_id}")
            await db.commit()
            await cursor.close()

    async def check_participant_eligibility(self, giveaway_id, participant_id, interaction):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # Fetch the giveaway's requirements from the giveaway table
            await cursor.execute("SELECT reaction_req, message_req, timespent_req FROM giveaway WHERE giveaway_id = ?",
                                 (giveaway_id,))
            giveaway_record = await cursor.fetchone()

            if giveaway_record is not None:
                # The giveaway exists in the giveaway table
                reaction_req, message_req, timespent_req = giveaway_record

                # Fetch the participant's record from the achievements table
                await cursor.execute("SELECT * FROM achievements WHERE user_id = ?", (participant_id,))
                record = await cursor.fetchone()

                if record is not None:
                    # The participant exists in the achievements table
                    _, message_count, reaction_count, time_spent, giveaway_count = record

                    # Check if the participant meets the requirements
                    if message_count >= message_req and reaction_count >= reaction_req and time_spent >= timespent_req:
                        # The participant meets the requirements
                        return True
                    else:
                        # The participant does not meet the requirements
                        return False
                else:
                    # The participant does not exist in the achievements table
                    await interaction.response.send_message(
                        f"User {participant_id} does not exist in the achievements table", ephemeral=True)
                    return False
            else:
                # The giveaway does not exist in the giveaway table
                await interaction.response.send_message(
                    f"Giveaway {giveaway_id} does not exist in the giveaway table", ephemeral=True)
                return False

    async def fetch_participant_ids(self, giveaway_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # Fetch the current participant_ids from the giveaway
            await cursor.execute('SELECT participant_ids FROM giveaway WHERE giveaway_id = ?',
                                 (giveaway_id,))
            record = await cursor.fetchone()
            current_participant_ids = record[0]

            if current_participant_ids is not None:
                # Split the string into a list and filter out any empty strings
                return [id for id in current_participant_ids.split(',') if id]
            else:
                return []

    async def fetch_winner_ids(self, giveaway_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # Fetch the winner_ids from the giveaway
            await cursor.execute('SELECT winner_ids FROM giveaway WHERE giveaway_id = ?', (giveaway_id,))
            record = await cursor.fetchone()
            await cursor.close()

            if record[0] is not None:
                # Extract the user IDs from the Discord mentions, convert them into integers, and ignore empty strings
                winner_ids = [int(mention.strip('<@>')) for mention in record[0].split(',') if mention]
            else:
                winner_ids = []

        return winner_ids

    async def is_participant(self, giveaway_id, participant_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # Fetch the current participant_ids from the giveaway
            await cursor.execute('SELECT participant_ids FROM giveaway WHERE giveaway_id = ?',
                                 (giveaway_id,))
            record = await cursor.fetchone()
            current_participant_ids = record[0]

            if current_participant_ids is not None:
                current_participant_ids = current_participant_ids.split(',')
                return str(participant_id) in current_participant_ids
            else:
                return False

    async def get_participant_count(self, giveaway_id):
        participant_ids = await self.fetch_participant_ids(giveaway_id)
        return len(participant_ids)

    async def fetch_giveaway(self, giveaway_id):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # Fetch the giveaway details from the database
            await cursor.execute('SELECT * FROM giveaway WHERE giveaway_id = ?',
                                 (giveaway_id,))
            record = await cursor.fetchone()
            await cursor.close()

            # Convert the record to a dictionary
            giveaway_details = {
                'giveaway_id': record[0],
                'message_id': record[1],
                'starttime': record[2],
                'duration': record[3],
                'winner_number': record[4],
                'prizes': record[5],
                'description': record[6],
                'creator_id': record[7],
                'reaction_req': record[8],
                'message_req': record[9],
                'timespent_req': record[10],
                'participant_ids': record[11],
                'winner_ids': record[12],
                'is_end': record[13],
            }

            return giveaway_details

    @app_commands.command(name="ga_cancel",
                          description="Cancel a giveaway without selecting winners")
    @app_commands.describe(giveaway_id="Enter the giveaway ID to cancel")
    async def cancel_giveaway(self, interaction: discord.Interaction, giveaway_id: str):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return

        # Fetch the giveaway details from the database
        giveaway_details = await self.fetch_giveaway(giveaway_id)

        if giveaway_details is None:
            # The giveaway does not exist
            await interaction.response.send_message(f"Giveaway {giveaway_id} does not exist.", ephemeral=True)
        elif giveaway_details['is_end']:
            # The giveaway has already ended
            await interaction.response.send_message(f"Giveaway {giveaway_id} has already ended.", ephemeral=True)
        else:
            # The giveaway is not ended, so cancel it
            # Mark the giveaway as ended in the database
            await self.mark_giveaway_as_ended(giveaway_id)

            # Fetch the giveaway message
            channel = self.bot.get_channel(self.giveaway_channel_id)
            message = await channel.fetch_message(giveaway_details['message_id'])

            # Update the embed to indicate that the giveaway is cancelled
            embed = message.embeds[0]
            embed.title = self.giveaway_embed_cancel_label + embed.title
            embed.color = discord.Color.orange()

            # Create a new instance of GiveawayParticipationView and set the message_id attribute
            view = GiveawayParticipationView(self.bot, giveaway_id, self.giveaway_channel_id)
            view.message_id = message.id
            view.disable_all_buttons()

            # Edit the message with the disabled view
            await message.edit(embed=embed, view=view)

            await interaction.response.send_message(f"Giveaway {giveaway_id} has been cancelled.", ephemeral=True)

    @app_commands.command(name="ga_end",
                          description="End a giveaway early and select the winner")
    @app_commands.describe(giveaway_id="Enter the giveaway ID to end")
    async def end_giveaway(self, interaction: discord.Interaction, giveaway_id: str):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return
        # Fetch the giveaway details from the database
        giveaway_details = await self.fetch_giveaway(giveaway_id)

        if giveaway_details is None:
            # The giveaway does not exist
            await interaction.response.send_message(f"Giveaway {giveaway_id} does not exist.", ephemeral=True)
        elif giveaway_details['is_end']:
            # The giveaway has already ended
            await interaction.response.send_message(f"Giveaway {giveaway_id} has already ended.", ephemeral=True)
        else:
            # The giveaway is not ended, so end it early
            # Draw the winners from the existing participants
            winners = await self.draw_winners(giveaway_id, giveaway_details['winner_number'])

            # Notify the winners
            await self.notify_winners(winners, giveaway_details['prizes'], giveaway_id)

            # Mark the giveaway as ended in the database and update the winners
            await self.update_giveaway(giveaway_id, winners)

            # Fetch the giveaway message
            channel = self.bot.get_channel(self.giveaway_channel_id)
            message = await channel.fetch_message(giveaway_details['message_id'])

            # Update the embed to indicate that the giveaway has ended early and display the winners
            embed = message.embeds[0]
            embed.title = self.giveaway_embed_earlyend_label + embed.title
            embed.color = discord.Color.red()

            winners = [f"<@{winner_id}>" if winner_id is not None and winner_id != 0 else None for
                       winner_id in winners]
            embed.add_field(name=self.giveaway_embed_winner_title,
                            value=", ".join(winners) if winners else self.giveaway_embed_no_winner, inline=False)

            # Create a new instance of GiveawayParticipationView and set the message_id attribute
            view = GiveawayParticipationView(self.bot, giveaway_id, self.giveaway_channel_id)
            view.message_id = message.id
            view.disable_all_buttons()

            # Edit the message with the disabled view
            await message.edit(embed=embed, view=view)

            await interaction.response.send_message(f"Giveaway {giveaway_id} has been ended early.", ephemeral=True)

    @app_commands.command(name="ga_time_extend",
                          description="Extend the time of a giveaway")
    @app_commands.describe(giveaway_id="Enter the giveaway ID to extend",
                           time="Enter the time to extend the giveaway by (in minutes)")
    async def extend_giveaway(self, interaction: discord.Interaction, giveaway_id: str, time: int):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return
        # Fetch the giveaway details from the database
        giveaway_details = await self.fetch_giveaway(giveaway_id)

        if giveaway_details is None:
            # The giveaway does not exist
            await interaction.response.send_message(f"Giveaway {giveaway_id} does not exist.", ephemeral=True)
        elif giveaway_details['is_end']:
            # The giveaway has already ended
            await interaction.response.send_message(f"Giveaway {giveaway_id} has already ended.", ephemeral=True)
        else:
            # The giveaway is not ended, so extend its time
            # Extend the duration of the giveaway by the specified time
            new_duration = giveaway_details['duration'] + time

            # Update the giveaway in the database with the new duration
            await self.update_giveaway_duration(giveaway_id, new_duration)

            # Fetch the giveaway message
            channel = self.bot.get_channel(self.giveaway_channel_id)
            message = await channel.fetch_message(giveaway_details['message_id'])

            # Update the embed to indicate that the giveaway time has been extended
            embed = message.embeds[0]
            embed.title = embed.title + self.giveaway_embed_time_extend_label
            embed.set_field_at(1, name=self.giveaway_embed_timeend_title,
                               value=format_dt(datetime.datetime.now() + datetime.timedelta(minutes=new_duration),
                                               style='R'), inline=True)

            # Update the message
            await message.edit(embed=embed)

            await interaction.response.send_message(f"Giveaway {giveaway_id} time has been extended by {time} minutes.",
                                                    ephemeral=True)

    @app_commands.command(name="ga_participant",
                          description="Fetch all participants for a giveaway")
    @app_commands.describe(giveaway_id="Enter the giveaway ID to fetch participants for")
    async def ga_participant(self, interaction: discord.Interaction, giveaway_id: str):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return

        # Fetch the giveaway details from the database
        giveaway_details = await self.fetch_giveaway(giveaway_id)

        if giveaway_details is None:
            # The giveaway does not exist
            await interaction.response.send_message(f"Giveaway {giveaway_id} does not exist.", ephemeral=True)

            return

        else:
            # Fetch all participant IDs for the giveaway
            participant_ids = await self.fetch_participant_ids(giveaway_id)

            if not participant_ids:
                await interaction.response.send_message(f"No participants found for giveaway {giveaway_id}.",
                                                        ephemeral=True)
                return

            # Create an instance of GiveawayCheckParticipantView
            participant_view = GiveawayCheckParticipantView(giveaway_id, participant_ids)

            # Send a message with the GiveawayCheckParticipantView instance as the view
            message = await interaction.response.send_message(content=f"Participants for giveaway {giveaway_id}:",
                                                              embed=participant_view.format_page(),
                                                              view=participant_view)
            participant_view.message = message

    @app_commands.command(name="ga_description",
                          description="Modify the description of a giveaway that is not yet finished")
    @app_commands.describe(giveaway_id="Enter the giveaway ID to modify",
                           description="Enter the new description for the giveaway")
    async def ga_description(self, interaction: discord.Interaction, giveaway_id: str, description: str):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return

        # Fetch the giveaway details from the database
        giveaway_details = await self.fetch_giveaway(giveaway_id)

        if giveaway_details is None:
            # The giveaway does not exist
            await interaction.response.send_message(f"Giveaway {giveaway_id} does not exist.", ephemeral=True)
        elif giveaway_details['is_end']:
            # The giveaway has already ended
            await interaction.response.send_message(f"Giveaway {giveaway_id} has already ended.", ephemeral=True)
        else:
            # The giveaway is not ended, so update its description
            await self.update_giveaway_description(giveaway_id, description)

            # Fetch the giveaway message
            channel = self.bot.get_channel(self.giveaway_channel_id)
            message = await channel.fetch_message(giveaway_details['message_id'])

            # Update the embed to reflect the new description
            embed = message.embeds[0]
            # Find the index of the "Description" field
            index = next((i for i, field in enumerate(message.embeds[0].fields) if
                          field.name == self.giveaway_embed_description_title), None)

            # Update the "Description" field if it exists
            if index is not None:
                embed.set_field_at(index, name=self.giveaway_embed_description_title, value=description,
                                   inline=False)

            # Edit the message with the updated embed
            await message.edit(embed=embed)

            await interaction.response.send_message(f"Giveaway {giveaway_id} description has been updated.",
                                                    ephemeral=True)

    @app_commands.command(name="ga_sendtowinner")
    @app_commands.describe(giveaway_id="Enter the giveaway ID to fetch winners for",
                           message="Enter the message to send to winners")
    async def ga_sendtowinner(self, interaction: discord.Interaction, giveaway_id: str, message: str):
        if not await self.illegal_act_cog.check_channel_validity(interaction):
            return
        # Fetch all winner IDs for the giveaway
        winner_ids = await self.fetch_winner_ids(giveaway_id)

        if not winner_ids:
            await interaction.response.send_message(f"No winners found for giveaway {giveaway_id}.", ephemeral=True)
            return
        else:
            failed_to_send = []
            # Iterate over the winners
            for winner_id in winner_ids:
                try:
                    winner = await self.bot.fetch_user(winner_id)
                    await winner.send(content=message)
                except discord.errors.Forbidden:
                    failed_to_send.append(winner_id)
                    continue

            if failed_to_send:
                # Handle the case where some messages could not be sent
                failed_mentions = ', '.join([f'<@{user_id}>' for user_id in failed_to_send])
                await interaction.response.send_message(f"Failed to send message to the following users: {failed_mentions} in giveaway {giveaway_id}. Message: {message}")
            else:
                await interaction.response.send_message(f"Message sent to all winners of giveaway {giveaway_id}. Message: {message}")

    async def update_giveaway_description(self, giveaway_id, new_description):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('UPDATE giveaway SET description = ? WHERE giveaway_id = ?',
                                 (new_description, giveaway_id))

    async def update_giveaway_duration(self, giveaway_id, new_duration):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(
                'UPDATE giveaway SET duration = ? WHERE giveaway_id = ?',
                (new_duration, giveaway_id)
            )
            await db.commit()
            await cursor.close()

    async def cleanup_ended_giveaways(self):
        logging.info("Cleaning up ended giveaways...")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('''
                DELETE FROM giveaway_views
                WHERE giveaway_id IN (
                    SELECT giveaway_id FROM giveaway WHERE is_end = 1
                )
            ''')
            await db.commit()
            await cursor.close()

    async def save_giveaways(self, giveaway_id, view):
        # print("Saving giveaways...")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute(
                'REPLACE INTO giveaway_views (giveaway_id, giveaway_channel_id, message_id) VALUES (?, ?, ?)',
                (giveaway_id, view.giveaway_channel_id, view.message_id))
            await db.commit()
            await cursor.close()

    async def load_giveaways(self):
        # print("Loading giveaways...")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()
            await cursor.execute('SELECT giveaway_id, giveaway_channel_id, message_id FROM giveaway_views')
            records = await cursor.fetchall()
            await cursor.close()
            for giveaway_id, giveaway_channel_id, message_id in records:
                view = GiveawayParticipationView(self.bot, giveaway_id, giveaway_channel_id)
                view.message_id = message_id
                self.giveaways[giveaway_id] = view

                # Fetch the giveaway message from Discord
                channel = self.bot.get_channel(int(giveaway_channel_id))
                if channel is None:
                    logging.error(f"Error: Channel {giveaway_channel_id} not found")
                    continue

                message = await channel.fetch_message(message_id)

                # Add the view to the message
                await message.edit(view=view)

    async def notify_winners(self, winners, prizes, giveaway_id):
        giveaway_channel = self.bot.get_channel(self.giveaway_channel_id)

        # Create a list of mentions for all winners
        winner_mentions = [f"<@{winner_id}>" if winner_id is not None and winner_id != 0 else None for
                           winner_id in winners]

        # Update the achievements for all participants
        await self.update_participant_achievements(giveaway_id)

        if winners:
            # Send a message in the giveaway channel congratulating all winners
            await giveaway_channel.send(
                self.giveaway_win_public_message.format(winner_mentions=', '.join(winner_mentions),
                                                        prizes=prizes))

            # Fetch the giveaway details from the database
            giveaway_details = await self.fetch_giveaway(giveaway_id)
            # Fetch the giveaway message
            channel = self.bot.get_channel(self.giveaway_channel_id)
            message = await channel.fetch_message(giveaway_details['message_id'])

            # Get the final version of the embed from the message
            embed = message.embeds[0]
            embed.color = discord.Color.green()

            # Send a private message to each winner
            for winner_id in winners:
                winner = await self.bot.fetch_user(winner_id)
                # print(winner_id, winner)
                if winner is None:
                    continue

                try:
                    await winner.send(self.giveaway_win_private_message.format(prizes=prizes), embed=embed)
                except discord.Forbidden:
                    print(
                        f"Could not send a private message to {winner.name}. They might have private messages disabled.")
        else:
            # No winners, send a message in the giveaway channel
            await giveaway_channel.send(self.giveaway_fail_message.format(prizes=prizes))

    async def update_participant_achievements(self, giveaway_id):
        # Fetch all participant IDs for the giveaway
        participant_ids = await self.fetch_participant_ids(giveaway_id)

        # Connect to the database
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.cursor()

            # For each participant ID
            for participant_id in participant_ids:
                # Fetch the current giveaway_count for the user from the achievement table
                await cursor.execute('SELECT giveaway_count FROM achievements WHERE user_id = ?', (participant_id,))
                record = await cursor.fetchone()

                if record is None:
                    # If the user doesn't have an entry in the achievement table, create a new entry with a giveaway_count of 1
                    await cursor.execute('INSERT INTO achievements (user_id, giveaway_count) VALUES (?, ?)',
                                         (participant_id, 1))
                else:
                    # If the user has an entry in the achievement table, increase the giveaway_count by 1
                    current_giveaway_count = record[0]
                    new_giveaway_count = current_giveaway_count + 1
                    await cursor.execute('UPDATE achievements SET giveaway_count = ? WHERE user_id = ?',
                                         (new_giveaway_count, participant_id))

            # Commit the changes and close the cursor
            await db.commit()
            await cursor.close()

    @commands.Cog.listener()
    async def on_ready(self):
        # Ensure the table exists
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS giveaway (
                    giveaway_id INTEGER NOT NULL,
                    message_id TEXT NOT NULL,
                    starttime TEXT NOT NULL,
                    duration INTEGER NOT NULL,
                    winner_number INTEGER NOT NULL,
                    prizes TEXT NOT NULL,
                    description TEXT,
                    creator_id TEXT NOT NULL,
                    reaction_req INTEGER DEFAULT 0,
                    message_req INTEGER DEFAULT 0,
                    timespent_req INTEGER DEFAULT 0,
                    participant_ids TEXT,
                    winner_ids TEXT,
                    is_end BOOLEAN DEFAULT 0
                )
            ''')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS giveaway_views (
                    giveaway_id TEXT PRIMARY KEY,
                    giveaway_channel_id TEXT,
                    message_id TEXT
                )
            ''')
            await db.commit()

            await self.load_giveaways()
