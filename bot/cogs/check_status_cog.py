# bot/cogs/check_status_cog.py
import asyncio
import discord
from discord.ext import commands, tasks
import os
import tempfile
import logging
import aiosqlite
from datetime import datetime, timezone, timedelta
import matplotlib.pyplot as plt
import io
import re
from collections import defaultdict
from bot.utils import config, check_channel_validity


class MemberPositionView(discord.ui.View):
    def __init__(self, bot, url):
        super().__init__()
        self.bot = bot

        self.main_config = config.get_config('main')
        self.logging_file = self.main_config['logging_file']

        self.conf = config.get_config('checkstatus')
        self.where_is_join_button_label = self.conf['where_is_join_button_label']

        # Create a link button that directs to the user's channel
        self.add_item(discord.ui.Button(label=self.where_is_join_button_label, url=url))


class CheckStatusCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.where_is_menu = discord.app_commands.ContextMenu(
            name='Where Is',
            callback=self.where_is_context_menu,
        )
        self.bot.tree.add_command(self.where_is_menu)

        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']
        self.logging_file = self.main_config['logging_file']

        self.conf = config.get_config('checkstatus')
        # Add main config to self.conf so check_log can access keyword_log_file
        self.conf.update(self.main_config)

        self.where_is_not_found_message = self.conf['where_is_not_found_message']
        self.where_is_title_message = self.conf['where_is_title_message']
        self.current_channel_name_message = self.conf['current_channel_name_message']
        self.current_channel_members_message = self.conf['current_channel_members_message']

        self.check_voice_status_task.start()

    @tasks.loop(minutes=10)
    async def check_voice_status_task(self):
        """Checks the number of people and active channels in voice channels and records it in the database."""
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
            # Remove categories with no active players or channels
            category_counts = {k: v for k, v in category_counts.items() if v['people'] > 0 or v['channels'] > 0}

            # Record the data in the database
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT INTO status (timestamp, people, channels)
                    VALUES (?, ?, ?)
                ''', (datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'), total_people, total_channels))
                await db.commit()

            logging.info(f"Voice status checked at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        except Exception as e:
            logging.error(f"An error occurred while checking voice status: {str(e)}")

    @check_voice_status_task.before_loop
    async def before_check_voice_status_task(self):
        now = datetime.now()
        next_run = (now + timedelta(minutes=10 - now.minute % 10)).replace(second=0, microsecond=0)
        await asyncio.sleep((next_run - now).total_seconds())
        await self.bot.wait_until_ready()

    @discord.app_commands.command(name="print_voice_status")
    @discord.app_commands.describe(date="The date in format YYYY-MM-DD, YYYY-MM, or YYYY.")
    async def print_voice_status(self, interaction: discord.Interaction, date: str):
        """Generates line graphs for the number of people and channels on a specific date, month, or year."""
        await interaction.response.defer()
        try:
            # 判断日期模式
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
                mode = "day"
            elif re.fullmatch(r"\d{4}-\d{2}", date):
                mode = "month"
            elif re.fullmatch(r"\d{4}", date):
                mode = "year"
            else:
                await interaction.followup.send("日期格式不支持，请使用 YYYY-MM-DD / YYYY-MM / YYYY。", ephemeral=True)
                return

            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute('''
                        SELECT timestamp, people, channels FROM status
                        WHERE timestamp LIKE ?
                        ORDER BY timestamp
                    ''', (f'{date}%',))
                rows = await cursor.fetchall()

            if not rows:
                await interaction.followup.send(f"No data found for the specified date: {date}", ephemeral=True)
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
                # Slight nudge upward to avoid overlap with markers
                return y + max(0.02, y * 0.001)

            if mode == "day":
                # 按时间序列画线，突出当日峰值
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
                # 按天取峰值，红点标注每日最高
                daily_people = defaultdict(int)
                daily_channels = defaultdict(int)
                for ts, p, c in zip(timestamps, people_counts, channel_counts):
                    day_key = ts.date().isoformat()
                    daily_people[day_key] = max(daily_people[day_key], p)
                    daily_channels[day_key] = max(daily_channels[day_key], c)

                days_sorted = sorted(daily_people.keys())
                x_idx = list(range(len(days_sorted)))
                day_labels = [d for d in days_sorted]  # 显示完整日期

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
                discord.File(channels_buf, filename='channels_stats.png')
            ])
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="check_log")
    @discord.app_commands.describe(
        x="Number of lines from the end of the log file to return.",
        log_type="日志类型：1/main(主日志)、2/keyword(关键词检测)、3/room(房间活动)，默认为main"
    )
    async def check_log(self, interaction: discord.Interaction, x: int, log_type: str = "main"):
        if not await check_channel_validity(interaction):
            return

        # Normalize log_type: support both numbers and text
        log_type_map = {
            "1": "main",
            "2": "keyword",
            "3": "room",
            "main": "main",
            "keyword": "keyword",
            "room": "room"
        }

        # Default to "main" if not provided
        normalized_type = log_type_map.get(log_type.lower() if log_type else "main", "main")

        # Log type configuration mapping
        log_config = {
            "main": {
                "file": self.logging_file,
                "name": "主要"
            },
            "keyword": {
                "file": self.conf.get('keyword_log_file', './data/keyword_detection.log'),
                "name": "关键词检测"
            },
            "room": {
                "file": self.conf.get('room_log_file', './data/room_activity.log'),
                "name": "房间活动"
            }
        }

        config = log_config[normalized_type]
        log_file = config["file"]
        log_type_name = config["name"]

        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except FileNotFoundError:
            await interaction.response.send_message(f"{log_type_name}日志文件不存在。")
            return

        if not lines:
            await interaction.response.send_message(f"{log_type_name}日志文件为空。")
            return

        last_x_lines = ''.join(lines[-x:])
        if len(last_x_lines) > 1900:
            # If the message is too long, write it to a temporary file and send the file
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as temp:
                temp.write(last_x_lines.encode())
                temp_file_name = temp.name
            await interaction.response.send_message(
                f"{log_type_name}日志过长，以文件形式发送。",
                file=discord.File(temp_file_name, filename=f"{log_type_name}_log.txt")
            )
            os.remove(temp_file_name)  # Delete the temporary file
        else:
            await interaction.response.send_message(f"**{log_type_name}日志最后 {x} 行**:\n```{last_x_lines}```")

    @discord.app_commands.command(name="check_voice_status")
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
            # Remove categories with no active players or channels
            category_counts = {k: v for k, v in category_counts.items() if v['people'] > 0 or v['channels'] > 0}
            embed = discord.Embed(title="Voice Channel Statistics", color=discord.Color.blue())
            for category, counts in category_counts.items():
                embed.add_field(name=category, value=f"{counts['people']} people, {counts['channels']} active channels",
                                inline=False)
            embed.add_field(name="Total People in Voice Channels", value=f"{total_people} people", inline=False)
            embed.add_field(name="Total Active Channels", value=f"{total_channels} channels", inline=False)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    @discord.app_commands.command(name="where_is")
    @discord.app_commands.describe(member="The member to check the position for")
    async def check_member_position(self, interaction: discord.Interaction, member: discord.Member):
        """Returns the current channel of the member and a list of members within the channel."""
        await interaction.response.defer(ephemeral=True)
        try:
            if member.voice is None or member.voice.channel is None:
                await interaction.followup.send(self.where_is_not_found_message.format(name=member.display_name),
                                                ephemeral=True)
                return

            logging.info(f"Checking position for {member.display_name} by {interaction.user.display_name}")

            channel = member.voice.channel
            members_in_channel = [m.display_name for m in channel.members]

            guild_id = member.guild.id
            channel_id = member.voice.channel.id
            vc_url_direct = f"https://discord.com/channels/{guild_id}/{channel_id}"

            embed = discord.Embed(title=self.where_is_title_message.format(name=member.display_name),
                                  color=discord.Color.blue())
            embed.add_field(name=self.current_channel_name_message, value="".join(vc_url_direct), inline=False)
            embed.add_field(name=self.current_channel_members_message, value="\n".join(members_in_channel),
                            inline=False)

            view = MemberPositionView(self.bot, vc_url_direct)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    async def where_is_context_menu(self, interaction: discord.Interaction, member: discord.Member):
        """Find out where the member is in voice channels."""
        await interaction.response.defer(ephemeral=True)
        try:
            if member.voice is None or member.voice.channel is None:
                await interaction.followup.send(self.where_is_not_found_message.format(name=member.display_name),
                                                ephemeral=True)
                return

            logging.info(f"Checking position for {member.display_name} by {interaction.user.display_name}")

            channel = member.voice.channel
            members_in_channel = [m.display_name for m in channel.members]

            guild_id = member.guild.id
            channel_id = member.voice.channel.id
            vc_url_direct = f"https://discord.com/channels/{guild_id}/{channel_id}"

            embed = discord.Embed(title=self.where_is_title_message.format(name=member.display_name),
                                  color=discord.Color.blue())
            embed.add_field(name=self.current_channel_name_message, value="".join(vc_url_direct), inline=False)
            embed.add_field(name=self.current_channel_members_message, value="\n".join(members_in_channel),
                            inline=False)

            view = MemberPositionView(self.bot, vc_url_direct)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS status (
                    timestamp TEXT NOT NULL,
                    people INTEGER DEFAULT 0,
                    channels INTEGER DEFAULT 0
                )
            ''')
