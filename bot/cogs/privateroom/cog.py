import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Any, Dict, Optional, Tuple

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands, tasks

from bot.utils import ShopDatabaseManager, check_channel_validity, config
from bot.utils.i18n import t
from bot.utils.privateroom_db import PrivateRoomDatabaseManager

from .views import (
    ConfirmPurchaseView,
    PrivateRoomShopView,
    ResetConfirmView,
    RoomListView,
)


class PrivateRoomCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # 加载配置
        self.main_config = config.get_config('main')
        self.db_path = self.main_config['db_path']
        self.conf = config.get_config('privateroom')
        self.role_config = config.get_config('role')  # 加载role配置以获取助力用户身份组ID

        # 初始化数据库管理器
        self.db = PrivateRoomDatabaseManager(self.db_path)
        self.shop_db = ShopDatabaseManager(self.db_path)

        # 启动过期房间检查任务
        self.check_expired_rooms.start()

    def cog_unload(self):
        # 停止任务
        self.check_expired_rooms.cancel()

    @tasks.loop(time=time(hour=8, minute=10))  # 每天8:10检查
    async def check_expired_rooms(self):
        """检查并删除过期的私人房间，并发送续费提醒"""
        logging.info("Checking for expired private rooms...")

        # 获取过期房间
        expired_rooms = await self.db.get_expired_rooms()

        # 处理每个过期房间
        for room_data in expired_rooms:
            room_id = room_data['room_id']
            user_id = room_data['user_id']

            # 获取房间对象
            channel = self.bot.get_channel(room_id)
            if channel:
                try:
                    # 获取房间名称（用于通知）
                    room_name = channel.name

                    # 删除房间
                    await channel.delete(reason="Private room expired")
                    logging.info(f"Deleted expired private room {room_id} for user {user_id}")

                    # 发送通知给用户
                    await self.send_expiration_notification(user_id, room_name, room_data)

                except discord.HTTPException as e:
                    logging.error(f"Failed to delete expired room {room_id}: {e}")
            else:
                logging.info(f"Expired room {room_id} not found, already deleted")

            # 无论房间是否存在，都标记为非活跃
            await self.db.deactivate_room(room_id)

        # 检查并发送续费提醒
        logging.info("Checking for rooms eligible for renewal reminder...")
        await self.check_and_send_renewal_reminders()

    @check_expired_rooms.before_loop
    async def before_check_expired_rooms(self):
        await self.bot.wait_until_ready()

        # 计算下次运行时间（在8:10）
        now = datetime.now()
        target_time = time(hour=self.conf['check_time_hour'], minute=self.conf['check_time_minute'])

        # 如果今天的目标时间已经过了，等到明天
        tomorrow = now.date() + timedelta(days=1)
        next_run = datetime.combine(
            tomorrow if now.time() >= target_time else now.date(),
            target_time
        )

        # 计算等待时间
        wait_seconds = (next_run - now).total_seconds()
        logging.info(f"Scheduled first check_expired_rooms in {wait_seconds:.2f} seconds")
        await asyncio.sleep(wait_seconds)

    async def send_expiration_notification(self, user_id, room_name, room_data):
        """发送房间过期通知给用户"""
        try:
            user = await self.bot.fetch_user(user_id)
            if not user:
                return

            # 创建嵌入消息
            embed = discord.Embed(
                title=t('privateroom.messages.room_expired_title'),
                description=t('privateroom.messages.room_expired_description').format(
                    room_name=room_name
                ),
                color=discord.Color.red()
            )

            embed.set_footer(text=t('privateroom.messages.room_expired_footer'))

            # 创建带有按钮的视图
            view = discord.ui.View()

            # 获取商店消息
            shop_messages = await self.db.get_shop_messages()
            if shop_messages:
                # 使用第一个商店消息
                channel_id, message_id = shop_messages[0]

                # 创建跳转按钮
                button = discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    label=t('privateroom.messages.room_expired_button'),
                    url=f"https://discord.com/channels/{self.bot.get_guild(self.main_config['guild_id']).id}/{channel_id}/{message_id}"
                )
                view.add_item(button)

            # 发送私信
            await user.send(embed=embed, view=view)

        except discord.HTTPException as e:
            logging.error(f"Failed to send expiration notification to user {user_id}: {e}")

    async def check_and_send_renewal_reminders(self):
        """检查并发送续费提醒"""
        try:
            # 获取续费阈值
            renewal_threshold = self.conf.get('renewal_days_threshold', 7)

            # 获取符合续费条件的房间
            eligible_rooms = await self.db.get_rooms_eligible_for_renewal(renewal_threshold)

            if not eligible_rooms:
                logging.info("No rooms eligible for renewal reminder")
                return

            logging.info(f"Found {len(eligible_rooms)} rooms eligible for renewal reminder")

            # 为每个符合条件的房间发送提醒
            for room_data in eligible_rooms:
                room_id = room_data['room_id']
                user_id = room_data['user_id']

                # 获取房间对象
                channel = self.bot.get_channel(room_id)
                if not channel:
                    logging.warning(f"Room {room_id} not found for renewal reminder")
                    # 房间不存在，也标记为已发送，避免重复检查
                    await self.db.update_renewal_reminder_flag(room_id, True)
                    continue

                # 发送续费提醒
                success = await self.send_renewal_reminder(user_id, channel, room_data)

                # 无论成功与否，都标记为已发送，避免重复发送
                if success:
                    await self.db.update_renewal_reminder_flag(room_id, True)
                    logging.info(f"Sent renewal reminder for room {room_id} to user {user_id}")
                else:
                    # 即使发送失败（如用户关闭私信），也标记为已发送
                    await self.db.update_renewal_reminder_flag(room_id, True)
                    logging.warning(f"Failed to send renewal reminder for room {room_id} to user {user_id}, but marked as sent")

        except Exception as e:
            logging.error(f"Error in check_and_send_renewal_reminders: {e}", exc_info=True)

    async def send_renewal_reminder(self, user_id: int, channel: discord.VoiceChannel,
                                    room_data: Dict[str, Any]) -> bool:
        """发送续费提醒私信

        Args:
            user_id: 用户ID
            channel: 房间频道对象
            room_data: 房间数据，包含 end_date, days_remaining

        Returns:
            bool: 是否成功发送
        """
        try:
            # 获取用户对象
            user = await self.bot.fetch_user(user_id)
            if not user:
                logging.error(f"User {user_id} not found for renewal reminder")
                return False

            # 提取房间信息
            end_date = room_data['end_date']
            days_remaining = room_data['days_remaining']
            room_name = channel.name

            # 创建嵌入消息
            embed = discord.Embed(
                title=t('privateroom.messages.renewal_reminder_title'),
                description=t('privateroom.messages.renewal_reminder_description').format(
                    room_name=room_name,
                    days_remaining=days_remaining
                ),
                color=discord.Color.orange()
            )

            # 添加房间信息字段
            embed.add_field(
                name="",
                value=t('privateroom.messages.renewal_reminder_room_info').format(
                    room_name=room_name,
                    end_date=end_date.strftime("%Y-%m-%d %H:%M"),
                    days_remaining=days_remaining
                ),
                inline=False
            )

            embed.set_footer(text=t('privateroom.messages.renewal_reminder_footer'))

            # 创建视图（可能包含按钮）
            view = discord.ui.View()

            # 获取商店消息，构建跳转链接
            shop_messages = await self.db.get_shop_messages()
            if shop_messages:
                # 使用第一个商店消息的频道
                channel_id, _ = shop_messages[0]

                # 验证商店频道是否存在
                shop_channel = self.bot.get_channel(channel_id)
                if shop_channel:
                    # 构建频道链接（不使用 message_id）
                    guild = self.bot.get_guild(self.main_config['guild_id'])
                    if guild:
                        shop_url = f"https://discord.com/channels/{guild.id}/{channel_id}"

                        # 创建跳转按钮
                        button = discord.ui.Button(
                            style=discord.ButtonStyle.link,
                            label=t('privateroom.messages.renewal_reminder_button_label'),
                            url=shop_url
                        )
                        view.add_item(button)
                else:
                    # 商店频道不存在，添加警告信息
                    embed.add_field(
                        name="",
                        value=t('privateroom.messages.renewal_reminder_no_shop'),
                        inline=False
                    )
            else:
                # 没有商店消息，添加警告信息
                embed.add_field(
                    name="",
                    value=t('privateroom.messages.renewal_reminder_no_shop'),
                    inline=False
                )

            # 发送私信
            try:
                if view.children:
                    await user.send(embed=embed, view=view)
                else:
                    await user.send(embed=embed)
                return True
            except discord.Forbidden:
                # 用户关闭了私信，改为在私房内提醒
                logging.warning(
                    f"Cannot send renewal reminder to user {user_id}: DMs are disabled, sending to room"
                )
                if not channel:
                    return False
                try:
                    if view.children:
                        await channel.send(content=user.mention, embed=embed, view=view)
                    else:
                        await channel.send(content=user.mention, embed=embed)
                    return True
                except (discord.Forbidden, discord.HTTPException) as e:
                    logging.error(
                        f"Failed to send renewal reminder in room {channel.id} for user {user_id}: {e}",
                        exc_info=True
                    )
                    return False
        except discord.HTTPException as e:
            # 其他 Discord API 错误
            logging.error(f"Failed to send renewal reminder to user {user_id}: {e}", exc_info=True)
            return False
        except Exception as e:
            # 其他未预期的错误
            logging.error(f"Unexpected error sending renewal reminder to user {user_id}: {e}", exc_info=True)
            return False

    @app_commands.command(
        name="privateroom_init",
        description=locale_str(
            "Initialize the private room system (admin only)",
            key="privateroom.privateroom_init.description",
        ),
    )
    async def initialize_system(self, interaction: discord.Interaction):
        """初始化私人房间系统"""
        # 验证管理员权限
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        # 检查是否已初始化
        category_id = await self.db.get_category_id()
        if category_id:
            await interaction.followup.send(t('privateroom.messages.init_already'), ephemeral=True)
            return

        # 创建分类
        try:
            guild = interaction.guild
            category = await guild.create_category(
                name="私人房间",
                reason="初始化私人房间系统"
            )

            # 设置分类权限
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=False,
                    connect=False
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    manage_channels=True,
                    manage_permissions=True
                )
            }
            await category.edit(overwrites=overwrites)

            # 保存分类ID
            await self.db.set_category_id(category.id)

            # 初始化数据库
            await self.db.initialize_database()

            await interaction.followup.send(
                t('privateroom.messages.init_success').format(
                    category_id=category.id
                ),
                ephemeral=True
            )

        except discord.HTTPException as e:
            logging.error(f"Failed to initialize private room system: {e}")
            await interaction.followup.send(t('privateroom.messages.init_fail'), ephemeral=True)

    @app_commands.command(
        name="privateroom_reset",
        description=locale_str(
            "Reset the private room system (admin only)",
            key="privateroom.privateroom_reset.description",
        ),
    )
    async def reset_system_command(self, interaction: discord.Interaction):
        """重置私人房间系统命令"""
        # 验证管理员权限
        if not await check_channel_validity(interaction):
            return

        # 显示确认对话框
        view = ResetConfirmView(self)
        await interaction.response.send_message(
            t('privateroom.messages.reset_confirm'),
            view=view,
            ephemeral=True
        )

    async def reset_system(self, interaction: discord.Interaction):
        """执行系统重置逻辑"""
        try:
            # 获取所有活跃房间
            category_id = await self.db.get_category_id()
            if category_id:
                category = interaction.guild.get_channel(category_id)
                if category:
                    # 删除分类下的所有频道
                    for channel in category.channels:
                        await channel.delete(reason="Resetting private room system")

                    # 删除分类
                    await category.delete(reason="Resetting private room system")

            # 删除所有商店消息
            shop_messages = await self.db.get_shop_messages()
            for channel_id, message_id in shop_messages:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        message = await channel.fetch_message(message_id)
                        await message.delete()
                    except (discord.NotFound, discord.Forbidden):
                        pass

            # 重置数据库
            await self.db.reset_privateroom_system()

            await interaction.followup.send(t('privateroom.messages.reset_success'), ephemeral=True)

        except Exception as e:
            logging.error(f"Failed to reset private room system: {e}")
            await interaction.followup.send(f"重置系统时出错: {e}", ephemeral=True)

    @app_commands.command(
        name="privateroom_setup",
        description=locale_str(
            "Set up the private room shop (admin only)",
            key="privateroom.privateroom_setup.description",
        ),
    )
    @app_commands.describe(
        channel=locale_str(
            "Channel to host the shop",
            key="privateroom.privateroom_setup.params.channel",
        ),
    )
    async def setup_shop(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """设置私人房间商店"""
        # 验证管理员权限
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        # 检查是否已初始化
        category_id = await self.db.get_category_id()
        if not category_id:
            await interaction.followup.send(t('privateroom.messages.error_no_category'), ephemeral=True)
            return

        try:
            # 首先验证并清理不存在的旧商店消息
            cleaned_count = await self.verify_shop_messages()

            # 直接使用传入的频道
            target_channel = channel

            # 检查频道类型
            if not isinstance(target_channel, discord.TextChannel):
                await interaction.followup.send("指定的频道必须是文字频道。", ephemeral=True)
                return

            # 创建商店嵌入消息
            embed = discord.Embed(
                title=t('privateroom.messages.shop_title'),
                description=t('privateroom.messages.shop_description').format(
                    points_cost=self.conf['points_cost'],
                    duration=self.conf['room_duration_days'],
                    hours_threshold=self.conf['voice_hours_threshold'],
                    booster_hours=self.conf.get('booster_discount_hours', 0),
                    available_rooms=self.conf['max_rooms'] - await self.db.get_active_rooms_count(),
                    max_rooms=self.conf['max_rooms']
                ),
                color=discord.Color.purple()
            )

            # 设置页脚
            embed.set_footer(text=t('privateroom.messages.shop_footer'))

            # 如果机器人有头像，添加为嵌入消息的缩略图
            if self.bot.user.avatar:
                embed.set_thumbnail(url=self.bot.user.avatar.url)

            # 创建商店视图
            view = PrivateRoomShopView(self)

            # 发送消息到指定频道
            message = await target_channel.send(embed=embed, view=view)

            # 保存消息ID到数据库
            await self.db.save_shop_message(target_channel.id, message.id)

            # 构建响应消息
            response_message = t('privateroom.messages.setup_success').format(channel=target_channel.mention)
            if cleaned_count > 0:
                response_message += "\n" + t('privateroom.messages.shop_cleaned_old').format(count=cleaned_count)

            await interaction.followup.send(response_message, ephemeral=True)

        except Exception as e:
            logging.error(f"Failed to setup private room shop: {e}")
            await interaction.followup.send(
                t('privateroom.messages.setup_fail').format(error=str(e)),
                ephemeral=True
            )

    async def get_last_month_voice_hours(self, user_id: int) -> float:
        """计算用户上个月的语音时长（小时）"""
        try:
            now = datetime.now()
            if now.month == 1:
                last_month = 12
                last_year = now.year - 1
            else:
                last_month = now.month - 1
                last_year = now.year

            seconds = await self.db.get_user_monthly_voice_seconds(user_id, last_year, last_month)
            return seconds / 3600
        except Exception as e:
            logging.error(f"Error getting last month voice hours: {e}")
            return 0

    async def is_booster(self, user_id: int) -> bool:
        """检查用户是否为助力用户（通过身份组判断）

        Args:
            user_id: 用户ID

        Returns:
            bool: 是否拥有助力用户身份组
        """
        try:
            # 从role配置中获取助力用户身份组ID
            helper_role_id = self.role_config.get('signature', {}).get('helper_role_id')
            if not helper_role_id:
                logging.warning("helper_role_id not configured in role config")
                return False

            # 获取guild和member
            guild = self.bot.get_guild(self.main_config['guild_id'])
            if not guild:
                return False

            member = guild.get_member(user_id)
            if not member:
                return False

            # 检查用户是否拥有助力身份组（与role_cog保持一致的检测方式）
            return any(role.id == helper_role_id for role in member.roles)

        except Exception as e:
            logging.error(f"Error checking booster status for user {user_id}: {e}")
            return False

    async def get_booster_bonus_hours(self) -> float:
        """获取助力用户优惠时长（小时）

        Returns:
            float: 优惠小时数
        """
        return float(self.conf.get('booster_discount_hours', 0))

    async def calculate_discount(self, user_id: int) -> tuple:
        """计算用户的折扣率和需要支付的积分

        Returns:
            tuple: (actual_hours, percentage, discount, final_cost, is_booster, bonus_hours)
        """
        # 获取语音时长要求和积分成本
        voice_threshold = self.conf['voice_hours_threshold']
        points_cost = self.conf['points_cost']

        # 获取用户上个月语音时长
        actual_hours = await self.get_last_month_voice_hours(user_id)

        # 检查是否为助力用户并获取加成时长
        is_booster = await self.is_booster(user_id)
        bonus_hours = await self.get_booster_bonus_hours() if is_booster else 0

        # 计算等效时长（实际时长 + 助力加成）
        effective_hours = actual_hours + bonus_hours

        # 计算百分比（基于等效时长）
        percentage = min(100, (effective_hours / voice_threshold) * 100)

        # 计算折扣和最终成本
        discount = min(100, percentage)
        final_cost = int(points_cost * (1 - discount / 100))

        return actual_hours, percentage, discount, final_cost, is_booster, bonus_hours

    async def handle_purchase_request(self, interaction: discord.Interaction):
        """处理购买私人房间的请求"""
        await interaction.response.defer(ephemeral=True)

        user = interaction.user
        user_id = user.id

        # Check if we've reached the room limit
        active_rooms_count = await self.db.get_active_rooms_count()
        max_rooms = self.conf.get('max_rooms', 40)  # Default to 40 if not set
        if active_rooms_count >= max_rooms:
            await interaction.followup.send(
                t('privateroom.messages.error_room_limit_reached'),
                ephemeral=True
            )
            return

        # 检查用户是否已有活跃的私人房间
        active_room = await self.db.get_active_room_by_user(user_id)
        if active_room:
            # 检查房间是否实际存在
            channel = self.bot.get_channel(active_room['room_id'])
            if channel:
                # 房间确实存在且活跃
                await interaction.followup.send(t('privateroom.messages.error_already_owns'), ephemeral=True)
                return
            else:
                # 房间在数据库中标记为活跃，但实际不存在，需要恢复
                # 继续处理，但使用恢复流程
                return await self._process_room_restoration(interaction, active_room)

        # 获取用户余额
        balance = await self.shop_db.get_user_balance(user_id)

        # 常规购买流程
        # 计算折扣和最终成本
        actual_hours, percentage, discount, cost, is_booster, bonus_hours = await self.calculate_discount(user_id)

        # 检查余额是否足够支付购买成本
        if cost > 0 and balance < cost:
            # Create an informative embed instead of simple error message
            embed = discord.Embed(
                title=t('privateroom.messages.error_insufficient_balance_title'),
                description=t('privateroom.messages.error_insufficient_balance_description'),
                color=discord.Color.red()
            )

            # Calculate the points needed
            points_needed = cost - balance
            original_cost = self.conf['points_cost']
            discount_amount = original_cost - cost

            # Add details to the embed
            embed.add_field(
                name=t('privateroom.messages.error_insufficient_balance_original_price'),
                value=f"**{original_cost}** {t('privateroom.messages.points_label')}",
                inline=False
            )

            embed.add_field(
                name=t('privateroom.messages.error_insufficient_balance_voice_time'),
                value=t('privateroom.messages.error_insufficient_balance_voice_format').format(
                    hours=round(actual_hours, 1),
                    minutes=int(actual_hours * 60),
                    discount=discount_amount
                ),
                inline=False
            )

            # 如果是助力用户，显示加成信息
            if is_booster and bonus_hours > 0:
                embed.add_field(
                    name="🚀 助力用户加成",
                    value=f"**+{round(bonus_hours, 1)}** 小时",
                    inline=False
                )

            embed.add_field(
                name=t('privateroom.messages.error_insufficient_balance_after_discount'),
                value=f"**{cost}** {t('privateroom.messages.points_label')}",
                inline=False
            )

            embed.add_field(
                name=t('privateroom.messages.error_insufficient_balance_current'),
                value=t('privateroom.messages.error_insufficient_balance_current_format').format(
                    balance=balance,
                    needed=points_needed
                ),
                inline=False
            )

            # Set footer with suggestion (添加助力用户提示)
            footer_text = t('privateroom.messages.error_insufficient_balance_footer')
            if not is_booster:
                booster_hours_config = await self.get_booster_bonus_hours()
                if booster_hours_config > 0:
                    footer_text += "\n" + t('privateroom.messages.error_insufficient_balance_booster_info').format(booster_hours=round(booster_hours_config, 1))
            embed.set_footer(text=footer_text)

            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # 创建确认嵌入消息
        embed = discord.Embed(
            title=t('privateroom.messages.confirm_title'),
            color=discord.Color.gold()
        )

        embed.add_field(
            name="",
            value=t('privateroom.messages.confirm_last_month').format(
                hours=round(actual_hours, 1)
            ),
            inline=False
        )

        # 如果是助力用户，显示加成信息
        if is_booster and bonus_hours > 0:
            embed.add_field(
                name="",
                value=t('privateroom.messages.confirm_booster_bonus').format(
                    bonus_hours=round(bonus_hours, 1)
                ),
                inline=False
            )

        embed.add_field(
            name="",
            value=t('privateroom.messages.confirm_discount').format(
                discount=round(discount, 1)
            ),
            inline=False
        )

        embed.add_field(
            name="",
            value=t('privateroom.messages.confirm_cost').format(cost=cost),
            inline=False
        )

        embed.add_field(
            name="",
            value=t('privateroom.messages.confirm_balance').format(balance=balance),
            inline=False
        )

        # 创建确认视图
        view = ConfirmPurchaseView(self, user, actual_hours, percentage, cost, balance)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def handle_advance_renewal_request(self, interaction: discord.Interaction):
        """处理提前续费私人房间的请求"""
        await interaction.response.defer(ephemeral=True)

        user = interaction.user
        user_id = user.id

        # 检查用户是否有活跃的私人房间
        active_room = await self.db.get_active_room_by_user(user_id)
        if not active_room:
            await interaction.followup.send(
                t('privateroom.messages.error_no_room_for_renewal'),
                ephemeral=True
            )
            return

        # 检查房间是否确实存在
        channel = self.bot.get_channel(active_room['room_id'])
        if not channel:
            await interaction.followup.send(
                t('privateroom.messages.error_room_not_found'),
                ephemeral=True
            )
            return

        # 检查房间剩余时间是否符合续费条件
        end_date = active_room['end_date']
        now = datetime.now()
        days_remaining = (end_date - now).days

        renewal_threshold = self.conf.get('renewal_days_threshold', 7)
        if days_remaining > renewal_threshold:
            await interaction.followup.send(
                t('privateroom.messages.error_renewal_too_early').format(
                    days_remaining=days_remaining,
                    threshold=renewal_threshold
                ),
                ephemeral=True
            )
            return

        # 获取用户余额
        balance = await self.shop_db.get_user_balance(user_id)

        # 计算续费折扣和最终成本
        actual_hours, percentage, discount, cost, is_booster, bonus_hours = await self.calculate_discount(user_id)

        # 检查余额是否足够支付续费成本
        if cost > 0 and balance < cost:
            # 创建详细的余额不足消息
            embed = discord.Embed(
                title=t('privateroom.messages.error_insufficient_balance_title'),
                description=t('privateroom.messages.error_renewal_insufficient_balance_description'),
                color=discord.Color.red()
            )

            # 计算所需积分
            points_needed = cost - balance
            original_cost = self.conf['points_cost']
            discount_amount = original_cost - cost

            # 添加详细信息到embed
            embed.add_field(
                name=t('privateroom.messages.error_insufficient_balance_original_price'),
                value=f"**{original_cost}** {t('privateroom.messages.points_label')}",
                inline=False
            )

            embed.add_field(
                name=t('privateroom.messages.error_insufficient_balance_voice_time'),
                value=t('privateroom.messages.error_insufficient_balance_voice_format').format(
                    hours=round(actual_hours, 1),
                    minutes=int(actual_hours * 60),
                    discount=discount_amount
                ),
                inline=False
            )

            # 如果是助力用户，显示加成信息
            if is_booster and bonus_hours > 0:
                embed.add_field(
                    name="🚀 助力用户加成",
                    value=f"**+{round(bonus_hours, 1)}** 小时",
                    inline=False
                )

            embed.add_field(
                name=t('privateroom.messages.error_insufficient_balance_after_discount'),
                value=f"**{cost}** {t('privateroom.messages.points_label')}",
                inline=False
            )

            embed.add_field(
                name=t('privateroom.messages.error_insufficient_balance_current'),
                value=t('privateroom.messages.error_insufficient_balance_current_format').format(
                    balance=balance,
                    needed=points_needed
                ),
                inline=False
            )

            # 设置页脚（添加助力用户提示）
            footer_text = t('privateroom.messages.error_insufficient_balance_footer')
            if not is_booster:
                booster_hours_config = await self.get_booster_bonus_hours()
                if booster_hours_config > 0:
                    footer_text += "\n" + t('privateroom.messages.error_insufficient_balance_booster_info').format(booster_hours=round(booster_hours_config, 1))
            embed.set_footer(text=footer_text)

            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        # 创建续费确认嵌入消息
        embed = discord.Embed(
            title=t('privateroom.messages.renewal_confirm_title'),
            color=discord.Color.gold()
        )

        # 显示当前房间信息
        embed.add_field(
            name="",
            value=t('privateroom.messages.renewal_current_room').format(
                room_name=channel.name,
                days_remaining=days_remaining
            ),
            inline=False
        )

        embed.add_field(
            name="",
            value=t('privateroom.messages.renewal_extend_days').format(
                extend_days=self.conf.get('renewal_extend_days', 31)
            ),
            inline=False
        )

        embed.add_field(
            name="",
            value=t('privateroom.messages.confirm_last_month').format(
                hours=round(actual_hours, 1)
            ),
            inline=False
        )

        # 如果是助力用户，显示加成信息
        if is_booster and bonus_hours > 0:
            embed.add_field(
                name="",
                value=t('privateroom.messages.confirm_booster_bonus').format(
                    bonus_hours=round(bonus_hours, 1)
                ),
                inline=False
            )

        embed.add_field(
            name="",
            value=t('privateroom.messages.confirm_discount').format(
                discount=round(discount, 1)
            ),
            inline=False
        )

        embed.add_field(
            name="",
            value=t('privateroom.messages.renewal_cost').format(cost=cost),
            inline=False
        )

        embed.add_field(
            name="",
            value=t('privateroom.messages.confirm_balance').format(balance=balance),
            inline=False
        )

        # 创建确认视图
        view = ConfirmPurchaseView(self, user, actual_hours, percentage, cost, balance, is_renewal=True)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def handle_restore_request(self, interaction: discord.Interaction):
        """Handle the request to restore a private room"""
        await interaction.response.defer(ephemeral=True)

        user = interaction.user
        user_id = user.id

        # Check if user has an active room first
        active_room = await self.db.get_active_room_by_user(user_id)
        if active_room:
            # Check if the room actually exists in Discord
            channel = self.bot.get_channel(active_room['room_id'])
            if channel:
                # Room exists and is active - no need to restore
                await interaction.followup.send(
                    t('privateroom.messages.error_already_owns'),
                    ephemeral=True
                )
                return
            # If we get here, room is in DB as active but doesn't exist in Discord
            # We'll fall through to room restoration process
        else:
            # No active room, check for inactive but valid rooms
            inactive_room = await self.db.get_inactive_valid_room(user_id)
            if not inactive_room:
                # No room to restore
                await interaction.followup.send(
                    t('privateroom.messages.error_no_room_to_restore'),
                    ephemeral=True
                )
                return
            active_room = inactive_room  # Use the inactive room for restoration

        # Create restoration confirmation embed
        start_date = active_room['start_date']
        end_date = active_room['end_date']

        embed = discord.Embed(
            title=t('privateroom.messages.room_restore_title'),
            description=t('privateroom.messages.room_restore_description').format(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            ),
            color=discord.Color.gold()
        )

        # Create confirmation view (no cost for restoration)
        view = ConfirmPurchaseView(
            self, user, 0, 0, 0, 0,  # Cost is 0 for restoration
            is_restore=True, old_room=active_room
        )

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def _process_room_restoration(self, interaction: discord.Interaction, room_data):
        """Process room restoration without deferring the interaction again"""
        # Create restoration confirmation embed
        start_date = room_data['start_date']
        end_date = room_data['end_date']

        embed = discord.Embed(
            title=t('privateroom.messages.room_restore_title'),
            description=t('privateroom.messages.room_restore_description').format(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            ),
            color=discord.Color.gold()
        )

        # Create confirmation view (no cost for restoration)
        view = ConfirmPurchaseView(
            self, interaction.user, 0, 0, 0, 0,  # Cost is 0 for restoration
            is_restore=True, old_room=room_data
        )

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    async def process_advance_renewal(self, interaction: discord.Interaction, cost: int) -> bool:
        """处理提前续费操作"""
        user = interaction.user
        user_id = user.id

        try:
            # 再次检查用户余额
            if cost > 0:
                current_balance = await self.shop_db.get_user_balance(user_id)
                if current_balance < cost:
                    await interaction.followup.send(
                        t('privateroom.messages.error_insufficient_balance'),
                        ephemeral=True
                    )
                    return False

            # 获取当前活跃房间
            active_room = await self.db.get_active_room_by_user(user_id)
            if not active_room:
                await interaction.followup.send(
                    t('privateroom.messages.error_no_room_for_renewal'),
                    ephemeral=True
                )
                return False

            # 检查房间是否存在
            channel = self.bot.get_channel(active_room['room_id'])
            if not channel:
                await interaction.followup.send(
                    t('privateroom.messages.error_room_not_found'),
                    ephemeral=True
                )
                return False

            # 再次校验续费窗口，避免重复续费叠加
            now = datetime.now()
            days_remaining = (active_room['end_date'] - now).days
            renewal_threshold = self.conf.get('renewal_days_threshold', 7)
            if days_remaining > renewal_threshold:
                await interaction.followup.send(
                    t('privateroom.messages.error_renewal_too_early').format(
                        days_remaining=days_remaining,
                        threshold=renewal_threshold
                    ),
                    ephemeral=True
                )
                return False

            # 计算新的结束时间
            current_end_date = active_room['end_date']
            extend_days = self.conf.get('renewal_extend_days', 31)
            new_end_date = current_end_date + timedelta(days=extend_days)

            # 设置结束时间为8:00
            new_end_date = new_end_date.replace(
                hour=self.conf['check_time_hour'],
                minute=0,
                second=0,
                microsecond=0
            )

            # 更新数据库中的房间到期时间
            await self.db.extend_room_validity(active_room['room_id'], new_end_date)

            # 扣除积分
            if cost > 0:
                await self.shop_db.update_user_balance_with_record(
                    user_id, -cost, "shop", user_id,
                    f"提前续费私人房间 ({extend_days}天)"
                )

            # 发送成功确认
            await interaction.followup.send(
                t('privateroom.messages.renewal_success_title'),
                ephemeral=True
            )

            # 在房间中发送续费成功的embed
            await self.send_renewal_success_embed(channel, user, new_end_date, extend_days)

            # 发送私信通知
            await self.send_renewal_confirmation(user, channel, new_end_date, extend_days)

            return True

        except Exception as e:
            logging.error(f"Error processing advance renewal: {e}", exc_info=True)
            await interaction.followup.send(
                t('privateroom.messages.error_renewal_failed'),
                ephemeral=True
            )
            return False

    @app_commands.command(
        name="privateroom_fix",
        description=locale_str(
            "Adjust a user's private room validity period (admin only)",
            key="privateroom.privateroom_fix.description",
        ),
    )
    @app_commands.describe(
        user=locale_str(
            "User whose room to adjust",
            key="privateroom.privateroom_fix.params.user",
        ),
        days=locale_str(
            "Remaining validity in days",
            key="privateroom.privateroom_fix.params.days",
        ),
    )
    async def fix_private_room(self, interaction: discord.Interaction, user: discord.User, days: int):
        """调整指定用户的私人房间有效期"""
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer(ephemeral=False)

        if days <= 0:
            await interaction.followup.send(
                t('privateroom.messages.fix_invalid_days'),
                ephemeral=False
            )
            return

        active_room = await self.db.get_active_room_by_user(user.id)
        if not active_room:
            await interaction.followup.send(
                t('privateroom.messages.fix_no_active_room').format(user_mention=user.mention),
                ephemeral=False
            )
            return

        now = datetime.now()
        if active_room['end_date'] <= now:
            await interaction.followup.send(
                t('privateroom.messages.fix_no_active_room').format(user_mention=user.mention),
                ephemeral=False
            )
            return

        channel = self.bot.get_channel(active_room['room_id'])
        if not channel:
            await interaction.followup.send(
                t('privateroom.messages.fix_room_not_found').format(user_mention=user.mention),
                ephemeral=False
            )
            return

        new_end_date = now + timedelta(days=days)
        new_end_date = new_end_date.replace(
            hour=self.conf['check_time_hour'],
            minute=0,
            second=0,
            microsecond=0
        )

        await self.db.extend_room_validity(active_room['room_id'], new_end_date)

        await interaction.followup.send(
            t('privateroom.messages.fix_success').format(
                user_mention=user.mention,
                days=days,
                end_date=new_end_date.strftime("%Y-%m-%d %H:%M")
            ),
            ephemeral=False
        )

    async def create_private_room(self, interaction: discord.Interaction, cost: int) -> bool:
        """创建新的私人房间"""
        user = interaction.user

        # 计算结束日期
        now = datetime.now()
        duration_days = self.conf['room_duration_days']
        end_date = now + timedelta(days=duration_days)

        # 设置结束时间为8:00
        end_date = end_date.replace(hour=self.conf['check_time_hour'], minute=0, second=0, microsecond=0)

        # 创建房间
        success, channel = await self._create_room_channel(
            interaction, user, now, end_date, cost, is_restore=False
        )

        if success:
            # 确认购买成功
            await interaction.followup.send(
                t('privateroom.messages.purchase_success_title'),
                ephemeral=True
            )

            # Update shop messages to reflect new available count
            await self.update_shop_messages()

        return success

    async def restore_private_room(self, interaction: discord.Interaction, old_room: Dict, cost: int = 0) -> bool:
        """Restore a private room that exists in database but not in Discord"""
        user = interaction.user

        # Start and end dates come from the old room
        start_date = old_room['start_date']
        end_date = old_room['end_date']
        old_room_id = old_room['room_id']

        # Restore the room
        success, _ = await self._create_room_channel(
            interaction, user, start_date, end_date, cost, old_room_id, is_restore=True
        )

        if success:
            # Confirm restoration success
            await interaction.followup.send(
                t('privateroom.messages.room_restored_success'),
                ephemeral=True
            )

            # Update shop messages
            await self.update_shop_messages()

        return success

    async def _create_room_channel(
            self,
            interaction: discord.Interaction,
            user: discord.User,
            start_date: datetime,
            end_date: datetime,
            cost: int = 0,
            old_room_id: int = None,
            is_restore: bool = False
    ) -> Tuple[bool, Optional[discord.VoiceChannel]]:
        """
        Common helper method to create or restore a private room channel.

        Returns:
            Tuple of (success: bool, channel: Optional[discord.VoiceChannel])
        """
        try:
            guild = interaction.guild

            # 最后一次检查用户余额是否足够
            if cost > 0:
                current_balance = await self.shop_db.get_user_balance(user.id)
                if current_balance < cost:
                    await interaction.followup.send(
                        t('privateroom.messages.error_insufficient_balance'),
                        ephemeral=True
                    )
                    return False, None

            # 最后一次检查用户是否已有房间
            active_room = await self.db.get_active_room_by_user(user.id)
            if active_room:
                channel = self.bot.get_channel(active_room['room_id'])
                if channel:
                    await interaction.followup.send(
                        t('privateroom.messages.error_already_owns'),
                        ephemeral=True
                    )
                    return False, None

            # 获取分类
            category_id = await self.db.get_category_id()
            category = guild.get_channel(category_id)

            if not category:
                logging.error(f"Private room category {category_id} not found")
                await interaction.followup.send(
                    t('privateroom.messages.error_no_category'),
                    ephemeral=True
                )
                return False, None

            # 创建房间名称
            room_name = t('privateroom.messages.room_name').format(user_name=user.display_name)

            # 设置房间权限
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=False,
                    connect=False
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    manage_channels=True,
                    manage_permissions=True
                ),
                user: discord.PermissionOverwrite(
                    view_channel=True,
                    connect=True,
                    speak=True,
                    move_members=True,
                    mute_members=True,
                    deafen_members=True,
                    use_voice_activation=True,
                    manage_channels=True,
                    create_instant_invite=True,
                    manage_permissions=True
                )
            }

            # 创建房间
            reason = f"Private room {'restored' if is_restore else 'created'} for {user.display_name}"
            channel = await guild.create_voice_channel(
                name=room_name,
                category=category,
                overwrites=overwrites,
                reason=reason
            )

            # 处理数据库操作
            if is_restore and old_room_id:
                # 恢复现有房间
                await self.db.restore_room(old_room_id, channel.id)
            else:
                # 创建新房间
                await self.db.create_room(channel.id, user.id, start_date, end_date)

            # 扣除积分（如果需要）
            if cost > 0:
                duration_days = self.conf['room_duration_days']
                await self.shop_db.update_user_balance_with_record(
                    user.id, -cost, "shop", user.id,
                    f"{'恢复' if is_restore else '购买'}私人房间 ({duration_days}天)"
                )

            # 发送房间信息
            await self.send_room_info(channel, user, start_date, end_date)

            # 发送私信通知
            await self.send_purchase_confirmation(user, channel, end_date, is_restore)

            return True, channel

        except Exception as e:
            logging.error(f"Error {'restoring' if is_restore else 'creating'} private room: {e}", exc_info=True)
            await interaction.followup.send(
                t('privateroom.messages.error_create_failed'),
                ephemeral=True
            )
            return False, None

    async def send_room_info(self, channel, user, start_date, end_date):
        """在私人房间中发送信息嵌入消息"""
        embed = discord.Embed(
            title=t('privateroom.messages.room_info_title').format(
                owner=user.display_name
            ),
            color=discord.Color.green()
        )

        embed.add_field(
            name="",
            value=t('privateroom.messages.room_info_owner').format(
                owner=user.mention
            ),
            inline=False
        )

        embed.add_field(
            name="",
            value=t('privateroom.messages.room_info_created').format(
                start_date=start_date.strftime("%Y-%m-%d %H:%M")
            ),
            inline=False
        )

        embed.add_field(
            name="",
            value=t('privateroom.messages.room_info_warning'),
            inline=False
        )

        embed.add_field(
            name="",
            value=t('privateroom.messages.room_info_expires').format(
                end_date=end_date.strftime("%Y-%m-%d %H:%M")
            ),
            inline=False
        )

        embed.set_footer(text=t('privateroom.messages.room_info_footer'))

        # 如果用户有头像，添加为嵌入消息的缩略图
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        elif self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        await channel.send(embed=embed)

    async def send_purchase_confirmation(self, user, channel, end_date, is_restore=False):
        """向用户发送私信确认购买或恢复成功"""
        try:
            if is_restore:
                # 恢复房间成功消息
                title = t('privateroom.messages.room_restore_success_title')
                description = t('privateroom.messages.room_restore_success_description')
            else:
                # 购买房间成功消息
                title = t('privateroom.messages.purchase_success_title')
                description = t('privateroom.messages.purchase_success_description')

            embed = discord.Embed(
                title=title,
                description=description.format(
                    end_date=end_date.strftime("%Y-%m-%d %H:%M")
                ),
                color=discord.Color.green()
            )

            # 创建跳转按钮
            view = discord.ui.View()
            button = discord.ui.Button(
                style=discord.ButtonStyle.link,
                label=t('privateroom.messages.purchase_success_button'),
                url=channel.jump_url
            )
            view.add_item(button)

            # 发送私信
            await user.send(embed=embed, view=view)

        except discord.HTTPException as e:
            logging.error(f"Failed to send purchase confirmation to user {user.id}: {e}")

    async def send_renewal_success_embed(self, channel, user, new_end_date, extend_days):
        """在私人房间中发送续费成功的嵌入消息"""
        embed = discord.Embed(
            title=t('privateroom.messages.renewal_room_success_title'),
            description=t('privateroom.messages.renewal_room_success_description').format(
                owner=user.mention,
                extend_days=extend_days,
                new_end_date=new_end_date.strftime("%Y-%m-%d %H:%M")
            ),
            color=discord.Color.green()
        )

        # 如果用户有头像，添加为嵌入消息的缩略图
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        elif self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)

        embed.set_footer(text=t('privateroom.messages.renewal_room_success_footer'))

        await channel.send(embed=embed)

    async def send_renewal_confirmation(self, user, channel, new_end_date, extend_days):
        """向用户发送私信确认续费成功"""
        try:
            embed = discord.Embed(
                title=t('privateroom.messages.renewal_dm_success_title'),
                description=t('privateroom.messages.renewal_dm_success_description').format(
                    extend_days=extend_days,
                    new_end_date=new_end_date.strftime("%Y-%m-%d %H:%M")
                ),
                color=discord.Color.green()
            )

            # 创建跳转按钮
            view = discord.ui.View()
            button = discord.ui.Button(
                style=discord.ButtonStyle.link,
                label=t('privateroom.messages.renewal_dm_success_button'),
                url=channel.jump_url
            )
            view.add_item(button)

            # 发送私信
            await user.send(embed=embed, view=view)

        except discord.HTTPException as e:
            logging.error(f"Failed to send renewal confirmation to user {user.id}: {e}")

    async def verify_shop_messages(self):
        """验证并清理不存在的商店消息"""
        removed_count = await self.db.clean_nonexistent_shop_messages(self.bot)
        if removed_count > 0:
            logging.info(f"Cleaned up {removed_count} non-existent shop messages")
        return removed_count

    @commands.Cog.listener()
    async def on_ready(self):
        """当机器人准备就绪时调用"""
        # 初始化数据库
        await self.db.initialize_database()

        # 验证并清理不存在的商店消息
        await self.verify_shop_messages()

        # 恢复商店消息的交互性
        await self.restore_shop_views()

        # 更新商店消息确保显示正确
        await self.update_shop_messages()

        logging.info("PrivateRoom Cog is ready")

    async def restore_shop_views(self):
        """恢复所有商店消息的交互视图"""
        shop_messages = await self.db.get_shop_messages()

        for channel_id, message_id in shop_messages:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue

            try:
                message = await channel.fetch_message(message_id)
                if message:
                    # 重新添加商店视图
                    view = PrivateRoomShopView(self)
                    await message.edit(view=view)

                    logging.info(f"Restored shop view for message {message_id} in channel {channel_id}")
            except (discord.NotFound, discord.Forbidden) as e:
                logging.error(f"Failed to restore shop view for message {message_id}: {e}")

    @app_commands.command(
        name="privateroom_list",
        description=locale_str(
            "List all active private rooms (admin only)",
            key="privateroom.privateroom_list.description",
        ),
    )
    async def list_rooms(self, interaction: discord.Interaction):
        """列出所有活跃的私人房间"""
        await interaction.response.defer()

        # Verify admin privileges
        if not await check_channel_validity(interaction):
            return

        try:
            # Get paginated rooms
            rooms, total_count = await self.db.get_paginated_active_rooms(page=1, items_per_page=10)

            if not rooms:
                await interaction.followup.send("目前没有活跃的私人房间。")
                return

            # Create pagination view
            view = RoomListView(self, rooms, total_count)

            # Get and send first page
            embed = await view.format_page()
            await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            logging.error(f"Error listing private rooms: {e}")
            await interaction.followup.send(f"获取房间列表时出错: {e}")


    @app_commands.command(
        name="privateroom_ban",
        description=locale_str(
            "Ban a user from the private room system (admin only)",
            key="privateroom.privateroom_ban.description",
        ),
    )
    @app_commands.describe(
        user=locale_str(
            "User to ban",
            key="privateroom.privateroom_ban.params.user",
        ),
    )
    async def ban_user(self, interaction: discord.Interaction, user: discord.User):
        """删除用户的私人房间并将其标记为不活跃"""
        # Verify admin privileges
        if not await check_channel_validity(interaction):
            return

        await interaction.response.defer(ephemeral=True)

        try:
            # Get user's active room
            active_room = await self.db.get_active_room_by_user(user.id)

            if not active_room:
                await interaction.followup.send(
                    t('privateroom.messages.ban_no_room').format(
                        user_mention=user.mention
                    ),
                    ephemeral=True
                )
                return

            # Get the room
            room_id = active_room['room_id']
            channel = self.bot.get_channel(room_id)

            if channel:
                # Delete the room in Discord
                await channel.delete(reason=f"Admin banned user {user.name} from having private rooms")

            # Mark the room as inactive in the database
            await self.db.deactivate_room(room_id)

            # Update the shop message to reflect the new available count
            await self.update_shop_messages()

            # Send success message
            await interaction.followup.send(
                t('privateroom.messages.ban_success').format(
                    user_mention=user.mention
                ),
                ephemeral=True
            )

        except Exception as e:
            logging.error(f"Error banning user from private rooms: {e}")
            await interaction.followup.send(
                t('privateroom.messages.ban_error').format(error=str(e)),
                ephemeral=True
            )

    async def update_shop_messages(self):
        """Update all shop messages with current available room count"""
        try:
            # Get active room count
            active_count = await self.db.get_active_rooms_count()
            available_count = self.conf.get('max_rooms', 40) - active_count

            # Get all shop messages
            shop_messages = await self.db.get_shop_messages()

            if not shop_messages:
                # 没有商店消息，不需要更新
                return

            for channel_id, message_id in shop_messages:
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    continue

                try:
                    message = await channel.fetch_message(message_id)
                    if not message:
                        continue

                    # Update the embed description
                    embed = message.embeds[0]
                    embed.description = t('privateroom.messages.shop_description').format(
                        points_cost=self.conf['points_cost'],
                        duration=self.conf['room_duration_days'],
                        hours_threshold=self.conf['voice_hours_threshold'],
                        booster_hours=self.conf.get('booster_discount_hours', 0),
                        available_rooms=available_count,
                        max_rooms=self.conf.get('max_rooms', 40)
                    )

                    # Update the message
                    await message.edit(embed=embed)

                except (discord.NotFound, discord.Forbidden):
                    continue
                except Exception as e:
                    logging.error(f"Error updating shop message {message_id} in channel {channel_id}: {e}")
        except Exception as e:
            logging.error(f"Error in update_shop_messages: {e}")
