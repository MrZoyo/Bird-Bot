import datetime
import logging
import random
import tempfile

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands, tasks
from discord.utils import format_dt

from bot.utils import GiveawayDatabaseManager, check_channel_validity, config
from bot.utils.i18n import t

from .modals import GiveawayForm
from .views import GiveawayCheckParticipantView, GiveawayParticipationView


class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.giveaways = {}

        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']
        self.db = GiveawayDatabaseManager(self.db_path)

        self.conf = config.get_config('giveaway')
        self.giveaway_channel_id = self.conf['giveaway_channel_id']
        self.giveaway_embed_title_open = t('giveaway.giveaway_embed_title_open')
        self.giveaway_embed_title_closed = t('giveaway.giveaway_embed_title_closed')
        self.giveaway_embed_title_closed_deleted = t('giveaway.giveaway_embed_title_closed_deleted')
        self.giveaway_embed_description_closed_deleted = t('giveaway.giveaway_embed_description_closed_deleted')
        self.giveaway_embed_description_title = t('giveaway.giveaway_embed_description_title')
        self.giveaway_embed_end_label = t('giveaway.giveaway_embed_end_label')
        self.giveaway_embed_winner_title = t('giveaway.giveaway_embed_winner_title')
        self.giveaway_embed_no_winner = t('giveaway.giveaway_embed_no_winner')
        self.giveaway_embed_cancel_label = t('giveaway.giveaway_embed_cancel_label')
        self.giveaway_embed_earlyend_label = t('giveaway.giveaway_embed_earlyend_label')
        self.giveaway_embed_time_extend_label = t('giveaway.giveaway_embed_time_extend_label')
        self.giveaway_embed_timeend_title = t('giveaway.giveaway_embed_timeend_title')
        self.giveaway_win_public_message = t('giveaway.giveaway_win_public_message')
        self.giveaway_win_private_message = t('giveaway.giveaway_win_private_message')
        self.giveaway_fail_message = t('giveaway.giveaway_fail_message')

    async def cog_load(self):
        await self.db.initialize_database()
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
        return await self.db.fetch_all_giveaways(include_ended=is_end)

    async def update_giveaway(self, giveaway_id, winners):
        logging.info(f"Updating giveaway {giveaway_id} with winners {winners}")
        await self.db.update_giveaway_winners(giveaway_id, winners)
        await self.cleanup_ended_giveaways()

    async def mark_giveaway_as_ended(self, giveaway_id):
        logging.info(f"Marking giveaway {giveaway_id} as ended")
        await self.db.mark_giveaway_as_ended(giveaway_id)
        await self.cleanup_ended_giveaways()

    @app_commands.command(
        name="ga_create",
        description=locale_str(
            "Create a new giveaway",
            key="giveaway.ga_create.description",
        ),
    )
    @app_commands.describe(
        reaction_req=locale_str(
            "Enter the reaction requirement",
            key="giveaway.ga_create.params.reaction_req",
        ),
        message_req=locale_str(
            "Enter the message requirement",
            key="giveaway.ga_create.params.message_req",
        ),
        timespent_req=locale_str(
            "Enter the time spent requirement(minute)",
            key="giveaway.ga_create.params.timespent_req",
        ),
    )
    async def create_giveaway(self, interaction: discord.Interaction,
                              reaction_req: int = 0,
                              message_req: int = 0,
                              timespent_req: int = 0
                              ):
        if not await check_channel_validity(interaction):
            return

        form = GiveawayForm(self.bot, self.db, reaction_req, message_req, timespent_req)
        await interaction.response.send_modal(form)

    @app_commands.command(
        name="check_giveaway",
        description=locale_str(
            "Check all current giveaways",
            key="giveaway.check_giveaway.description",
        ),
    )
    async def check_giveaway(self, interaction: discord.Interaction):
        if not await check_channel_validity(interaction):
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
        await self.db.add_participant(giveaway_id, participant_id)

    async def remove_participant_from_giveaway(self, giveaway_id, participant_id):
        await self.db.remove_participant(giveaway_id, participant_id)

    async def check_participant_eligibility(self, giveaway_id, participant_id, interaction):
        giveaway_record = await self.db.fetch_giveaway_requirements(giveaway_id)
        if giveaway_record is None:
            await interaction.response.send_message(
                f"Giveaway {giveaway_id} does not exist in the giveaway table", ephemeral=True)
            return False

        reaction_req, message_req, timespent_req = giveaway_record

        record = await self.db.fetch_user_achievements(participant_id)
        if record is None:
            await interaction.response.send_message(
                f"User {participant_id} does not exist in the achievements table", ephemeral=True)
            return False

        _, message_count, reaction_count, time_spent, _giveaway_count = record
        return (message_count >= message_req
                and reaction_count >= reaction_req
                and time_spent >= timespent_req)

    async def fetch_participant_ids(self, giveaway_id):
        return await self.db.fetch_participant_ids(giveaway_id)

    async def fetch_winner_ids(self, giveaway_id):
        return await self.db.fetch_winner_ids(giveaway_id)

    async def is_participant(self, giveaway_id, participant_id):
        return await self.db.is_participant(giveaway_id, participant_id)

    async def get_participant_count(self, giveaway_id):
        participant_ids = await self.fetch_participant_ids(giveaway_id)
        return len(participant_ids)

    async def fetch_giveaway(self, giveaway_id):
        return await self.db.fetch_giveaway(giveaway_id)

    @app_commands.command(
        name="ga_cancel",
        description=locale_str(
            "Cancel a giveaway without selecting winners",
            key="giveaway.ga_cancel.description",
        ),
    )
    @app_commands.describe(
        giveaway_id=locale_str(
            "Enter the giveaway ID to cancel",
            key="giveaway.ga_cancel.params.giveaway_id",
        ),
    )
    async def cancel_giveaway(self, interaction: discord.Interaction, giveaway_id: str):
        if not await check_channel_validity(interaction):
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

    @app_commands.command(
        name="ga_end",
        description=locale_str(
            "End a giveaway early and select the winner",
            key="giveaway.ga_end.description",
        ),
    )
    @app_commands.describe(
        giveaway_id=locale_str(
            "Enter the giveaway ID to end",
            key="giveaway.ga_end.params.giveaway_id",
        ),
    )
    async def end_giveaway(self, interaction: discord.Interaction, giveaway_id: str):
        if not await check_channel_validity(interaction):
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

    @app_commands.command(
        name="ga_time_extend",
        description=locale_str(
            "Extend the time of a giveaway",
            key="giveaway.ga_time_extend.description",
        ),
    )
    @app_commands.describe(
        giveaway_id=locale_str(
            "Enter the giveaway ID to extend",
            key="giveaway.ga_time_extend.params.giveaway_id",
        ),
        time=locale_str(
            "Enter the time to extend the giveaway by (in minutes)",
            key="giveaway.ga_time_extend.params.time",
        ),
    )
    async def extend_giveaway(self, interaction: discord.Interaction, giveaway_id: str, time: int):
        if not await check_channel_validity(interaction):
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

    @app_commands.command(
        name="ga_participant",
        description=locale_str(
            "Fetch all participants for a giveaway",
            key="giveaway.ga_participant.description",
        ),
    )
    @app_commands.describe(
        giveaway_id=locale_str(
            "Enter the giveaway ID to fetch participants for",
            key="giveaway.ga_participant.params.giveaway_id",
        ),
    )
    async def ga_participant(self, interaction: discord.Interaction, giveaway_id: str):
        if not await check_channel_validity(interaction):
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

    @app_commands.command(
        name="ga_description",
        description=locale_str(
            "Modify the description of a giveaway that is not yet finished",
            key="giveaway.ga_description.description",
        ),
    )
    @app_commands.describe(
        giveaway_id=locale_str(
            "Enter the giveaway ID to modify",
            key="giveaway.ga_description.params.giveaway_id",
        ),
        description=locale_str(
            "Enter the new description for the giveaway",
            key="giveaway.ga_description.params.description",
        ),
    )
    async def ga_description(self, interaction: discord.Interaction, giveaway_id: str, description: str):
        if not await check_channel_validity(interaction):
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

    @app_commands.command(
        name="ga_sendtowinner",
        description=locale_str(
            "Send a message to all winners of a giveaway",
            key="giveaway.ga_sendtowinner.description",
        ),
    )
    @app_commands.describe(
        giveaway_id=locale_str(
            "Enter the giveaway ID to fetch winners for",
            key="giveaway.ga_sendtowinner.params.giveaway_id",
        ),
        message=locale_str(
            "Enter the message to send to winners",
            key="giveaway.ga_sendtowinner.params.message",
        ),
    )
    async def ga_sendtowinner(self, interaction: discord.Interaction, giveaway_id: str, message: str):
        """ Send a message to all winners of a giveaway"""
        if not await check_channel_validity(interaction):
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
        await self.db.update_giveaway_description(giveaway_id, new_description)

    async def update_giveaway_duration(self, giveaway_id, new_duration):
        await self.db.update_giveaway_duration(giveaway_id, new_duration)

    async def cleanup_ended_giveaways(self):
        logging.info("Cleaning up ended giveaways...")
        await self.db.cleanup_ended_giveaway_views()

    async def save_giveaways(self, giveaway_id, view):
        await self.db.save_giveaway_view(giveaway_id, view.giveaway_channel_id, view.message_id)

    async def load_giveaways(self):
        records = await self.db.load_giveaway_views()
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
        participant_ids = await self.fetch_participant_ids(giveaway_id)
        await self.db.increment_giveaway_achievements(participant_ids)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.load_giveaways()
