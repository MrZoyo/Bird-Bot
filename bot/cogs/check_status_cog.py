# bot/cogs/check_status_cog.py
import asyncio
import io
import logging
import os
import re
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import discord
import matplotlib.pyplot as plt
from discord.app_commands import locale_str
from discord.ext import commands, tasks

from bot.utils import CheckStatusDatabaseManager, check_channel_validity, config
from bot.utils.i18n import t


class MemberPositionView(discord.ui.View):
    def __init__(self, bot, url):
        super().__init__()
        self.bot = bot
        self.add_item(
            discord.ui.Button(
                label=t('checkstatus.where_is_join_button_label'),
                url=url,
            )
        )


class CheckStatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.where_is_menu = discord.app_commands.ContextMenu(
            name='Where Is',
            callback=self.where_is_context_menu,
        )

        main_config = config.get_config('main')
        self.db_path = main_config['db_path']
        self.db = CheckStatusDatabaseManager(self.db_path)
        self.logging_file = main_config['logging_file']
        self.keyword_log_file = main_config.get('keyword_log_file', './data/keyword_detection.log')
        self.room_log_file = main_config.get('room_log_file', './data/room_activity.log')

        self.bot.tree.add_command(self.where_is_menu)
        self.check_voice_status_task.start()

    async def cog_load(self):
        # Table must be built before the 10-minute task fires; see P0-3a notes.
        await self.db.initialize_database()

    def cog_unload(self):
        self.check_voice_status_task.cancel()
        self.bot.tree.remove_command(self.where_is_menu.name, type=self.where_is_menu.type)

    @tasks.loop(minutes=10)
    async def check_voice_status_task(self):
        """Record voice-channel occupancy every 10 minutes."""
        try:
            category_counts = {}
            total_people = 0
            total_channels = 0
            for guild in self.bot.guilds:
                for channel in guild.voice_channels:
                    if channel.category is not None:
                        if channel.category.name not in category_counts:
                            category_counts[channel.category.name] = {'people': 0, 'channels': 0}
                        category_counts[channel.category.name]['people'] += len(channel.members)
                        if len(channel.members) > 0:
                            category_counts[channel.category.name]['channels'] += 1
                            total_channels += 1
                        total_people += len(channel.members)
            category_counts = {k: v for k, v in category_counts.items() if v['people'] > 0 or v['channels'] > 0}

            await self.db.record_status(
                datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'),
                total_people,
                total_channels,
            )

            logging.info(f"Voice status checked at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            logging.error(f"An error occurred while checking voice status: {str(e)}")

    @check_voice_status_task.before_loop
    async def before_check_voice_status_task(self):
        now = datetime.now()
        next_run = (now + timedelta(minutes=10 - now.minute % 10)).replace(second=0, microsecond=0)
        await asyncio.sleep((next_run - now).total_seconds())
        await self.bot.wait_until_ready()

    @discord.app_commands.command(
        name="print_voice_status",
        description=locale_str(
            "Plot long-term voice activity charts for a given date / month / year",
            key="checkstatus.print_voice_status.description",
        ),
    )
    @discord.app_commands.describe(
        date=locale_str(
            "The date in format YYYY-MM-DD, YYYY-MM, or YYYY.",
            key="checkstatus.print_voice_status.params.date",
        ),
    )
    async def print_voice_status(self, interaction: discord.Interaction, date: str):
        """Generates line graphs for the number of people and channels on a specific date, month, or year."""
        await interaction.response.defer()
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
                mode = "day"
            elif re.fullmatch(r"\d{4}-\d{2}", date):
                mode = "month"
            elif re.fullmatch(r"\d{4}", date):
                mode = "year"
            else:
                await interaction.followup.send(t('checkstatus.date_format_error'), ephemeral=True)
                return

            rows = await self.db.fetch_status_by_date_prefix(date)

            if not rows:
                await interaction.followup.send(
                    t('checkstatus.no_data_for_date', date=date), ephemeral=True,
                )
                return

            timestamps = [datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S') for row in rows]
            people_counts = [row[1] for row in rows]
            channel_counts = [row[2] for row in rows]

            def save_fig():
                buf = io.BytesIO()
                plt.savefig(buf, format='png', bbox_inches='tight')
                buf.seek(0)
                plt.close()
                return buf

            def offset_y(y: float) -> float:
                return y + max(0.02, y * 0.001)

            # matplotlib titles / axis labels remain in English; extracting them
            # is a separate follow-up (P1-6 step 1 flagged; not pulling into
            # locale this pass to keep the per-cog refactor focused).
            if mode == "day":
                max_people = max(people_counts)
                max_channels = max(channel_counts)
                max_people_time = timestamps[people_counts.index(max_people)]
                max_channels_time = timestamps[channel_counts.index(max_channels)]

                plt.figure(figsize=(10, 5))
                plt.plot(timestamps, people_counts, color='#4c78a8', alpha=0.75, linewidth=2, marker='o',
                         markersize=4, label='People')
                plt.scatter([max_people_time], [max_people], color='red', zorder=5, label=f'Peak {max_people}')
                plt.text(max_people_time, offset_y(max_people), str(max_people), ha='center', va='bottom', color='red',
                         fontsize=9)
                plt.title(f'Voice participants (max {max_people} at {max_people_time.strftime("%H:%M")})')
                plt.xlabel('Time')
                plt.ylabel('People')
                plt.grid(True, alpha=0.3)
                plt.legend()
                plt.xticks(rotation=45)
                people_buf = save_fig()

                plt.figure(figsize=(10, 5))
                plt.plot(timestamps, channel_counts, color='#72b7b2', alpha=0.75, linewidth=2, marker='o',
                         markersize=4, label='Rooms')
                plt.scatter([max_channels_time], [max_channels], color='red', zorder=5,
                            label=f'Peak {max_channels}')
                plt.text(max_channels_time, offset_y(max_channels), str(max_channels), ha='center', va='bottom', color='red',
                         fontsize=9)
                plt.title(f'Voice rooms (max {max_channels} at {max_channels_time.strftime("%H:%M")})')
                plt.xlabel('Time')
                plt.ylabel('Rooms')
                plt.grid(True, alpha=0.3)
                plt.legend()
                plt.xticks(rotation=45)
                channels_buf = save_fig()

            elif mode == "month":
                daily_people = defaultdict(int)
                daily_channels = defaultdict(int)
                for ts, p, c in zip(timestamps, people_counts, channel_counts):
                    day_key = ts.date().isoformat()
                    daily_people[day_key] = max(daily_people[day_key], p)
                    daily_channels[day_key] = max(daily_channels[day_key], c)

                days_sorted = sorted(daily_people.keys())
                x_idx = list(range(len(days_sorted)))
                day_labels = [d for d in days_sorted]

                people_series = [daily_people[d] for d in days_sorted]
                channels_series = [daily_channels[d] for d in days_sorted]

                plt.figure(figsize=(10, 5))
                plt.plot(x_idx, people_series, color='#4c78a8', alpha=0.6, linewidth=2, marker='o',
                         markersize=4, label='Daily peak people')
                plt.scatter(x_idx, people_series, color='red', zorder=5)
                for x, y in zip(x_idx, people_series):
                    plt.text(x, offset_y(y), str(y), ha='center', va='bottom', color='red', fontsize=8)
                plt.title(f'{date} daily voice peaks (people)')
                plt.xlabel('Day')
                plt.ylabel('People')
                plt.grid(True, alpha=0.3)
                plt.legend()
                plt.xticks(x_idx, day_labels, rotation=45)
                people_buf = save_fig()

                plt.figure(figsize=(10, 5))
                plt.plot(x_idx, channels_series, color='#72b7b2', alpha=0.6, linewidth=2, marker='o',
                         markersize=4, label='Daily peak rooms')
                plt.scatter(x_idx, channels_series, color='red', zorder=5)
                for x, y in zip(x_idx, channels_series):
                    plt.text(x, offset_y(y), str(y), ha='center', va='bottom', color='red', fontsize=8)
                plt.title(f'{date} daily voice peaks (rooms)')
                plt.xlabel('Day')
                plt.ylabel('Rooms')
                plt.grid(True, alpha=0.3)
                plt.legend()
                plt.xticks(x_idx, day_labels, rotation=45)
                channels_buf = save_fig()

            else:  # mode == "year"
                monthly_people = defaultdict(int)
                monthly_channels = defaultdict(int)
                for ts, p, c in zip(timestamps, people_counts, channel_counts):
                    month_key = ts.strftime('%Y-%m')
                    monthly_people[month_key] = max(monthly_people[month_key], p)
                    monthly_channels[month_key] = max(monthly_channels[month_key], c)

                months_sorted = sorted(monthly_people.keys())
                x_idx = list(range(len(months_sorted)))
                month_labels = [m.split('-')[-1] for m in months_sorted]

                people_series = [monthly_people[m] for m in months_sorted]
                channels_series = [monthly_channels[m] for m in months_sorted]

                plt.figure(figsize=(10, 5))
                plt.bar(x_idx, people_series, color='#4c78a8', alpha=0.75, label='Monthly peak people')
                for x, y in zip(x_idx, people_series):
                    plt.text(x, y, str(y), ha='center', va='bottom', color='#333', fontsize=8)
                plt.title(f'{date} monthly voice peaks (people)')
                plt.xlabel('Month')
                plt.ylabel('People')
                plt.grid(axis='y', alpha=0.3)
                plt.xticks(x_idx, month_labels, rotation=0)
                plt.legend()
                people_buf = save_fig()

                plt.figure(figsize=(10, 5))
                plt.bar(x_idx, channels_series, color='#72b7b2', alpha=0.75, label='Monthly peak rooms')
                for x, y in zip(x_idx, channels_series):
                    plt.text(x, y, str(y), ha='center', va='bottom', color='#333', fontsize=8)
                plt.title(f'{date} monthly voice peaks (rooms)')
                plt.xlabel('Month')
                plt.ylabel('Rooms')
                plt.grid(axis='y', alpha=0.3)
                plt.xticks(x_idx, month_labels, rotation=0)
                plt.legend()
                channels_buf = save_fig()

            await interaction.followup.send(files=[
                discord.File(people_buf, filename='people_stats.png'),
                discord.File(channels_buf, filename='channels_stats.png'),
            ])
        except Exception as e:
            await interaction.followup.send(
                t('checkstatus.error_generic', error=str(e)), ephemeral=True,
            )

    @discord.app_commands.command(
        name="check_log",
        description=locale_str(
            "Return the last N lines of a server log",
            key="checkstatus.check_log.description",
        ),
    )
    @discord.app_commands.describe(
        x=locale_str(
            "Number of lines from the end of the log file to return.",
            key="checkstatus.check_log.params.x",
        ),
        log_type=locale_str(
            "Log type: 1/main, 2/keyword, 3/room. Defaults to main.",
            key="checkstatus.check_log.params.log_type",
        ),
    )
    async def check_log(self, interaction: discord.Interaction, x: int, log_type: str = "main"):
        if not await check_channel_validity(interaction):
            return

        log_type_map = {
            "1": "main",
            "2": "keyword",
            "3": "room",
            "main": "main",
            "keyword": "keyword",
            "room": "room",
        }
        normalized_type = log_type_map.get(log_type.lower() if log_type else "main", "main")

        log_config = {
            "main":    {"file": self.logging_file,     "name": t('checkstatus.log_type_main')},
            "keyword": {"file": self.keyword_log_file, "name": t('checkstatus.log_type_keyword')},
            "room":    {"file": self.room_log_file,    "name": t('checkstatus.log_type_room')},
        }

        log_file = log_config[normalized_type]["file"]
        log_type_name = log_config[normalized_type]["name"]

        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except FileNotFoundError:
            await interaction.response.send_message(
                t('checkstatus.log_file_not_found', log_type_name=log_type_name)
            )
            return

        if not lines:
            await interaction.response.send_message(
                t('checkstatus.log_file_empty', log_type_name=log_type_name)
            )
            return

        last_x_lines = ''.join(lines[-x:])
        if len(last_x_lines) > 1900:
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as temp:
                temp.write(last_x_lines.encode())
                temp_file_name = temp.name
            await interaction.response.send_message(
                t('checkstatus.log_too_long', log_type_name=log_type_name),
                file=discord.File(temp_file_name, filename=f"{log_type_name}_log.txt"),
            )
            os.remove(temp_file_name)
        else:
            await interaction.response.send_message(
                t(
                    'checkstatus.log_last_lines',
                    log_type_name=log_type_name,
                    x=x,
                    lines=last_x_lines,
                )
            )

    @discord.app_commands.command(
        name="check_voice_status",
        description=locale_str(
            "Return voice channel / member counts by category",
            key="checkstatus.check_voice_status.description",
        ),
    )
    async def check_voice_status(self, interaction: discord.Interaction):
        """Returns the number of people and active channels in each category and the total numbers."""
        await interaction.response.defer()
        try:
            category_counts = {}
            total_people = 0
            total_channels = 0
            for guild in self.bot.guilds:
                for channel in guild.voice_channels:
                    if channel.category is not None:
                        if channel.category.name not in category_counts:
                            category_counts[channel.category.name] = {'people': 0, 'channels': 0}
                        category_counts[channel.category.name]['people'] += len(channel.members)
                        if len(channel.members) > 0:
                            category_counts[channel.category.name]['channels'] += 1
                            total_channels += 1
                        total_people += len(channel.members)
            category_counts = {k: v for k, v in category_counts.items() if v['people'] > 0 or v['channels'] > 0}

            embed = discord.Embed(title=t('checkstatus.voice_stats_title'), color=discord.Color.blue())
            for category, counts in category_counts.items():
                embed.add_field(
                    name=category,
                    value=t(
                        'checkstatus.voice_stats_category_value',
                        people=counts['people'],
                        channels=counts['channels'],
                    ),
                    inline=False,
                )
            embed.add_field(
                name=t('checkstatus.voice_stats_total_people_title'),
                value=t('checkstatus.voice_stats_total_people_value', count=total_people),
                inline=False,
            )
            embed.add_field(
                name=t('checkstatus.voice_stats_total_channels_title'),
                value=t('checkstatus.voice_stats_total_channels_value', count=total_channels),
                inline=False,
            )
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(
                t('checkstatus.error_generic', error=str(e)), ephemeral=True,
            )

    async def _send_where_is(self, interaction: discord.Interaction, member: discord.Member):
        """Shared body for /where_is slash command and the Where Is context menu."""
        if member.voice is None or member.voice.channel is None:
            await interaction.followup.send(
                t('checkstatus.where_is_not_found_message', name=member.display_name),
                ephemeral=True,
            )
            return

        logging.info(f"Checking position for {member.display_name} by {interaction.user.display_name}")

        channel = member.voice.channel
        members_in_channel = [m.display_name for m in channel.members]
        vc_url_direct = f"https://discord.com/channels/{member.guild.id}/{channel.id}"

        embed = discord.Embed(
            title=t('checkstatus.where_is_title_message', name=member.display_name),
            color=discord.Color.blue(),
        )
        embed.add_field(
            name=t('checkstatus.current_channel_name_message'),
            value=vc_url_direct,
            inline=False,
        )
        embed.add_field(
            name=t('checkstatus.current_channel_members_message'),
            value="\n".join(members_in_channel),
            inline=False,
        )

        view = MemberPositionView(self.bot, vc_url_direct)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @discord.app_commands.command(
        name="where_is",
        description=locale_str(
            "Show the voice channel a member is currently in",
            key="checkstatus.where_is.description",
        ),
    )
    @discord.app_commands.describe(
        member=locale_str(
            "The member to check the position for",
            key="checkstatus.where_is.params.member",
        ),
    )
    async def check_member_position(self, interaction: discord.Interaction, member: discord.Member):
        """Returns the current channel of the member and a list of members within the channel."""
        await interaction.response.defer(ephemeral=True)
        try:
            await self._send_where_is(interaction, member)
        except Exception as e:
            await interaction.followup.send(
                t('checkstatus.error_generic', error=str(e)), ephemeral=True,
            )

    async def where_is_context_menu(self, interaction: discord.Interaction, member: discord.Member):
        """Find out where the member is in voice channels."""
        await interaction.response.defer(ephemeral=True)
        try:
            await self._send_where_is(interaction, member)
        except Exception as e:
            await interaction.followup.send(
                t('checkstatus.error_generic', error=str(e)), ephemeral=True,
            )
