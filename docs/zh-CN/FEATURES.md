# Bird Bot 功能参考

<p align="center">
  <a href="../../README.zh-CN.md"><img src="https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87%E9%A6%96%E9%A1%B5-2EA44F?style=for-the-badge" alt="返回中文 README"></a>
  <a href="../en/FEATURES.md"><img src="https://img.shields.io/badge/READ_IN-ENGLISH-5865F2?style=for-the-badge&amp;logo=googletranslate&amp;logoColor=white" alt="Read in English"></a>
</p>

最后检查：2026-08-16

本文介绍每个现役 cog 的运行行为和 slash 命令。安装与最短初始化流程见[中文 README](../../README.zh-CN.md)。

`bot/main.py::COG_SPECS` 是现役 cog 及配置依赖的权威来源。Slash 命令名称来自各 cog 的命令装饰器；Discord 显示的本地化说明和选项帮助来自 `bot/locales/zh_CN/commands.yaml`。

## 语音房与组队

### VoiceStateCog

功能键：`voicechannel`
配置：`bot/config/voicechannel.yaml`

VoiceStateCog 将配置的入口频道变为临时语音房启动器。成员进入入口频道后，Bot 创建房间、移动成员、将房间写入 SQLite，并在最后一名成员离开后删除房间。

每个托管房间都有包含四个操作的控制面板：

- 解锁房间；
- 锁定房间；
- 将关联的组队邀请标记为满员；
- 启用或禁用音效板权限。

Cog 会在重启后恢复已记录的面板，并清理 Discord 中已不存在频道对应的数据库记录。入口频道规则保存在 SQLite 中并通过命令管理；`voicechannel.yaml` 保存面板颜色。

| 命令 | 用途 |
| --- | --- |
| `/check_temp_channel_records` | 列出已记录临时房间，帮助定位过期记录 |
| `/vc_add <channel>` | 注册语音入口频道 |
| `/vc_remove [channel] [channel_id]` | 通过频道选择或原始 ID 移除入口频道 |
| `/vc_list` | 列出已注册入口频道 |

### CreateInvitationCog

功能键：`invitation`
配置：`bot/config/invitation.yaml`

CreateInvitationCog 创建带有作者当前语音房直达链接的组队消息。它支持显式 `/invt` 调用，也支持在普通消息中自动检测组队短语。

自动检测首先要求命中“标记 + 人数”：标记可以是 `缺`、`等`、`=`、`＝` 或 `q`。只有这个基本条件成立后，才检查标记前的字符；独立的 `1`、`１` 或 `一` 会选择更柔和的单人提示。例如 `1q4`、`一等全世界` 会命中，而 `1等`、`一q` 和常见用法 `稍微一等` 都不会触发。

长度恰好为 6 个字符，且不含等号、中文或空格的消息会静默忽略。消息包含 `flex`、`rank`、`aram` 或 `hks` 时不应用这条兼容过滤，匹配不区分大小写。

邀请可以包含作者签名。作者不在语音频道时，回复会链接到配置的房间入口频道，并根据组队信息选择普通创房提示或更柔和的单人提示。忽略列表可以排除指定用户和文字频道。语音房控制面板和邀请面板共用满员更新路径，因此最终状态一致。

| 命令 | 用途 |
| --- | --- |
| `/invt [title]` | 为当前语音房创建组队邀请 |
| `/invt_checkignorelist` | 显示被忽略的用户和频道 |
| `/invt_addignorelist <channel>` | 将文字频道加入忽略列表 |
| `/invt_removeignorelist [channel] [channel_id]` | 通过频道选择或原始 ID 移除忽略频道 |

### TeamupDisplayCog

功能键：`teamup_display`
配置：`bot/config/teamup_display.yaml`

TeamupDisplayCog 为现役组队邀请维护一个或多个实时展示板。展示板按照 SQLite 中保存的游戏类型分组，使用房间直达链接，并每两分钟刷新一次。

Cog 也会清理过期或无效的邀请记录。`display.refresh_interval_minutes` 是兼容字段，当前任务间隔在代码中固定为两分钟。由于组队条目已改用房间直达链接，不再创建 Discord invite，`display.invitation_expire_minutes` 已不再使用。

| 命令 | 用途 |
| --- | --- |
| `/teamup_init <channel>` | 创建或注册展示板 |
| `/teamup_type_add <channel> <game_type>` | 将来源频道映射到游戏类型 |
| `/teamup_type_delete [channel] [channel_id]` | 移除游戏类型映射 |
| `/teamup_type_list` | 列出游戏类型映射 |

## 欢迎与社区状态

### WelcomeCog

功能键：`welcome`
配置：`bot/config/welcome.yaml`

WelcomeCog 在成员加入时发送可配置的欢迎频道消息、包含成员头像和成员数量的生成图片，以及可选私信。字体和图片来自 `resources/`；通用私信文案来自 locale 文件。

`welcome_text` 有意保留为部署专属配置，因为其中通常含有真实服务器 URL 和自定义 emoji ID。私信发送失败不会阻止公开欢迎消息。

| 命令 | 用途 |
| --- | --- |
| `/testwelcome [member] [member_number]` | 使用指定成员和人数预览欢迎流程 |

### AchievementCog

功能键：`achievements`
配置：`bot/config/achievements.yaml`

AchievementCog 记录反应、消息、语音时长和签到统计。它提供成员进度、月度视图、分类排行榜、按钮驱动的 `/rank` 面板，以及带审计记录的管理员调整。

当前的非月度 `/achievements` 页面使用 Components v2 容器，并以原生分割线区分成就分类。右上角大头像依次使用被查询用户的自定义头像、Bot 的自定义头像、用户的 Discord 默认头像。指定月份的视图继续使用 embed。

成就定义和对应身份组 ID 保存在 `achievements.yaml`。与已禁用功能关联的分类会在运行时隐藏。ShopCog 禁用时，`checkin_sum` 和 `checkin_combo` 不显示；已停用的抽奖成就分类即使 GiveawayCog 启用也保持隐藏。

| 命令 | 用途 |
| --- | --- |
| `/achievements [member] [date]` | 显示成就进度，可指定 `2026-08` 等月份 |
| `/increase_achievement <member> [reactions] [messages] [time_spent]` | 确认后增加进度 |
| `/decrease_achievement <member> [reactions] [messages] [time_spent]` | 确认后减少进度 |
| `/achievement_ranking [date]` | 显示分类排行榜 |
| `/check_ach_ops` | 查看手动成就操作记录 |
| `/rank [date]` | 打开互动排行榜面板 |

### RoleCog

功能键：`role`
配置：`bot/config/role.yaml`、`bot/config/achievements.yaml`

RoleCog 创建成就、星座、MBTI 和性别身份组的持久化领取面板。发布面板前会验证配置的身份组 ID，并支持可选初始身份组。

签名子系统通过成就数据检查语音时长资格。每个用户有三个固定的签名修改槽位；`role.signature.cooldown_days` 控制已用槽位何时重新可用。`role.signature.max_changes_per_week` 只为兼容旧配置保留，运行时代码不会读取。

| 命令 | 用途 |
| --- | --- |
| `/create_role_pickup <channel>` | 创建成就身份组面板 |
| `/create_starsign_pickup <channel>` | 创建星座身份组面板 |
| `/create_mbti_pickup <channel>` | 创建 MBTI 身份组面板 |
| `/create_gender_pickup <channel>` | 创建性别身份组面板 |
| `/create_signature_pickup <channel>` | 创建签名面板 |
| `/signature_permission_toggle <user_id> <disable>` | 启用或禁用指定用户的签名 |
| `/signature_clear <user_id>` | 清空用户签名和修改记录 |
| `/signature_set_requirement <minutes>` | 设置语音时长要求 |
| `/signature_check <user_id>` | 查看用户签名状态 |

## 积分经济与私人房

### ShopCog

功能键：`shop`
配置：`bot/config/shop.yaml`

ShopCog 提供积分余额、交易记录、每日签到和补签。公开签到面板为持久化面板，每个用户会收到只对自己可见的签到和查询反馈。

示例配置中，每日签到奖励 10 积分，每次补签消耗 50 积分，每月最多补签三次。部署者可以修改这三个值。补签校验会阻止早于首次手动签到的日期，并在写入成功后重新计算连续签到。

面板刷新可以安全重试：短暂的 Discord HTTP 或权限失败会保持面板有效；只有确认频道或消息不存在时才停用。Discord 接受面板编辑后才推进每日状态。

| 命令 | 用途 |
| --- | --- |
| `/create_checkin_embed <channel>` | 创建并注册签到面板 |
| `/balance_change <user>` | 通过管理员表单调整余额 |
| `/balance_history [user]` | 浏览交易记录 |
| `/checkin_history <user>` | 查看指定用户的签到明细 |

### PrivateRoomCog

功能键：`privateroom`
配置：`bot/config/privateroom.yaml`、`bot/config/role.yaml`

PrivateRoomCog 使用 Shop 余额出售限时私人语音房。它创建配置的 Discord 频道结构，在 SQLite 中保存所有权和到期时间，应用语音活跃度与 Booster 折扣，并清理到期房间。

示例配置中，购买获得 31 天使用期，可在最后七天续费，每次续费延长 31 天。正常续费从已保存的 `end_date` 延长；如果现役房间的日期已经过期，则从当前时间延长，避免向用户收取已经过去的天数。

已记录房间丢失时，用户可以恢复保存的房间设置。管理员可以初始化商店、查看房间、修复到期状态、重置初始化状态，以及禁止指定用户使用该功能。

| 命令 | 用途 |
| --- | --- |
| `/privateroom_init` | 初始化或刷新私人房系统 |
| `/privateroom_setup <channel>` | 配置商店面板和分类 |
| `/privateroom_reset` | 重置私人房初始化状态 |
| `/privateroom_fix <user> <days>` | 设置现役房间的剩余有效期 |
| `/privateroom_list` | 列出现役房间 |
| `/privateroom_ban <user>` | 禁止用户执行私人房操作 |

## 工单与管理

### TicketsCog

功能键：`tickets`
配置：`bot/config/tickets.yaml`

TicketsCog 使用私密 Discord thread。工单类型、面板位置、thread 记录和类型专属管理员保存在 SQLite 中；`tickets.yaml` 提供全局管理员身份组和用户列表。

Cog 提供 modal 确认、待处理/已接单/已关闭状态、自动添加管理员成员、包含跳转链接的私信通知、持久化控件、统计，以及启动时清理 Discord 中已不存在的 thread。私信失败不会中断工单创建或关闭。

| 命令 | 用途 |
| --- | --- |
| `/tickets_init [ticket_channel] [info_channel]` | 初始化系统；未指定时创建频道 |
| `/tickets_add_user <user>` | 将成员加入当前工单 |
| `/tickets_stats` | 显示工单统计 |
| `/tickets_admin_list` | 显示全局管理员配置 |
| `/tickets_admin_add_role <role>` | 添加全局管理员身份组 |
| `/tickets_admin_remove_role <role>` | 移除全局管理员身份组 |
| `/tickets_admin_add_user <user>` | 添加全局管理员用户 |
| `/tickets_admin_remove_user <user>` | 移除全局管理员用户 |
| `/tickets_accept` | 接受当前工单 |
| `/tickets_close [reason]` | 关闭当前工单 |
| `/tickets_refresh_buttons` | 刷新现有工单控件 |
| `/tickets_refresh_main` | 刷新主工单面板 |
| `/tickets_add_type` | 通过 modal 添加工单类型 |
| `/tickets_edit_type` | 编辑工单元数据、说明、颜色或管理员 |
| `/tickets_delete_type` | 删除工单类型并刷新主面板 |

### BanCog

功能键：`ban`
配置：`bot/config/ban.yaml`

BanCog 提供永久封禁、定时临时封禁、Discord timeout，以及可选的未授权 `@everyone` 垃圾消息自动防护。它持久化现役临时封禁，在重启后恢复计时器，记录管理员操作，并发送可配置通知。

功能访问权限由 `ban.yaml` 中的身份组和用户列表控制。通知频道和临时封禁返回链接可以通过命令更新。时长支持 `30m`、`12h`、`7d`、`2w` 等格式；Discord 将 timeout 限制为 28 天。垃圾消息防护默认关闭，示例封禁时长为一天，并删除过去一小时的消息记录。旧 `delete_message_days` 配置保持兼容。服务器所有者、Discord 管理员、配置的 Ban 管理员，以及可在 `main.admin_channel_id` 发言的成员不受防护规则影响。临时封禁私信会提醒误点恶意广告的用户在重新加入前启用多因素认证。

| 命令 | 用途 |
| --- | --- |
| `/ban <user> <reason> [delete_message_days]` | 永久封禁成员 |
| `/tempban <user> <duration> <reason> [delete_message_days]` | 封禁成员直到指定时长结束 |
| `/mute <user> <duration> <reason>` | 应用 Discord timeout |
| `/ban_list_tempbans` | 列出现役临时封禁 |
| `/ban_admin_list` | 显示管理员和通知设置 |
| `/ban_admin_add_role <role>` | 向身份组授予管理权限 |
| `/ban_admin_delete_role <role>` | 撤销身份组的管理权限 |
| `/ban_admin_add_user <user>` | 向用户授予管理权限 |
| `/ban_admin_delete_user <user>` | 撤销用户的管理权限 |
| `/ban_set_notification_channel <channel>` | 设置管理通知频道 |
| `/ban_remove_notification_channel` | 清除通知频道 |
| `/ban_set_invite_link <invite_link>` | 设置临时封禁私信使用的返回链接 |
| `/ban_remove_invite_link` | 清除返回链接 |

### InviteGuardCog

功能键：`invite_guard`
配置：`bot/config/invite_guard.yaml`

InviteGuardCog 将邀请清理与邀请排行榜结合。清理任务扫描配置的服务器，删除不在邀请码和创建者白名单中的过期邀请，并支持 dry-run。示例配置使用三天最大有效期和 24 小时间隔。

成员加入时，排行榜会比较缓存和当前 Discord invite 的 `uses` 值。Cog 保存邀请者总数、成员归因锁、加入/离开计数和邀请链接元数据。成员重新加入不会再次奖励。

新成员会在一个短暂批处理窗口内结算。邀请使用量的总增量与批次人数相等时，Cog 为各邀请者记账；包含多个邀请的批次使用 `pooled_count`。增量不匹配、被忽略、自邀请或其他不可靠批次会标记为 ambiguous，不发放积分。邀请缓存锁会阻止五分钟后台同步在结算过程中消费增量。

即使 ShopCog 已禁用，成功归因仍可写入 Shop 积分；重新启用 ShopCog 后数据继续可用。如果存在有效排行榜面板，Cog 可以向每位获得奖励的邀请者发送包含摘要、图片和面板直达链接的私信。私信或图片失败不会回滚归因和积分。

| 命令 | 用途 |
| --- | --- |
| `/invite_sync` | 刷新邀请链接状态和排行榜面板 |
| `/invite_check_user <member>` | 查看邀请总数和归因状态 |
| `/invite_create_embed <channel>` | 创建 Components v2 排行榜面板 |

Discord 不会在 `on_member_join` 中提供邀请码。Bot 离线、缺少邀请列表权限、成员通过 vanity/Discovery 加入或增量不一致时，归因可能保持 unknown 或 ambiguous。

## 抽奖与游戏

### GiveawayCog

功能键：`giveaway`
配置：`bot/config/giveaway.yaml`

GiveawayCog 使用基于 modal 的草稿流程填写奖品、时长、提供者、活跃要求、中奖人数和可选图片。发布后的抽奖使用持久化参加控件和私密的参加/退出反馈。

抽奖状态、参与者和中奖者保存在 SQLite 中。Cog 会在重启后恢复现役抽奖控件，支持取消和提前结束，并在联系中奖者时隔离单个私信失败。

| 命令 | 用途 |
| --- | --- |
| `/ga_create` | 打开抽奖草稿 |
| `/check_giveaway` | 导出当前抽奖记录 |
| `/ga_cancel <giveaway_id>` | 取消现役抽奖 |
| `/ga_end <giveaway_id>` | 结束抽奖并选择中奖者 |
| `/ga_time_extend <giveaway_id> <time>` | 延长结束时间 |
| `/ga_participant <giveaway_id>` | 列出参与者 |
| `/ga_description <giveaway_id> <description>` | 替换公开说明 |
| `/ga_sendtowinner <giveaway_id> <message>` | 向中奖者发送消息 |

### DnDCog

功能键：`dnd`
配置：无

DnDCog 计算由带符号常数和骰子项组成的表达式。`d6` 等标准骰子生成 1 到 6；`d06` 等以零开头的骰子生成 0 到 6。表达式可以包含多个项，`5#3+4d6` 会重复执行表达式五次。

每次调用中，每个骰子项最多 100 颗骰子，每颗骰子最多 1,000 面。

| 命令 | 用途 |
| --- | --- |
| `/dnd_roll <expression> [x]` | 执行一次表达式，或重复 `x` 次 |

### SpyModeCog

功能键：`spymode`
配置：无

SpyModeCog 为命令发起者所在语音频道的成员创建双队报名面板。发起者选择队伍人数和每队间谍数，报名后开始游戏；Bot 在揭晓阶段前通过私信发送秘密身份。

| 命令 | 用途 |
| --- | --- |
| `/spymode [team_size] [spy]` | 创建游戏；默认每队五人、每队一名间谍 |

## 运维

### CheckStatusCog

功能键：`checkstatus`
配置：除 `main.yaml` 外无其他配置

CheckStatusCog 每十分钟采样一次聚合语音活动并写入 SQLite。运营者可以查看当前语音状态、生成日/月/年图表，或读取配置的主日志、关键词日志和房间活动日志。`/where_is` 和 `Where Is` 成员 context menu 会私密返回语音位置和跳转按钮。

| 命令 | 用途 |
| --- | --- |
| `/print_voice_status <date>` | 绘制 `YYYY-MM-DD`、`YYYY-MM` 或 `YYYY` 的活动图 |
| `/check_log <x> [log_type]` | 返回指定日志的最后 `x` 行 |
| `/check_voice_status` | 显示当前语音频道人数 |
| `/where_is <member>` | 私密查找成员所在语音频道 |

### BackupCog

功能键：`backup`
配置：除 `main.yaml` 外无其他配置

BackupCog 按主机本地时间在 00:00、06:00、12:00 和 18:00 复制配置的 SQLite 数据库。`backup/db_backup/` 保留最近 20 个自动备份；手动备份写入 `backup/db_backup_manual/`，同样保留 20 个。

SQLCipher 数据库的备份是直接文件副本，因此仍保持加密。请在独立的受保护备份中保存匹配的密钥文件。

| 命令 | 用途 |
| --- | --- |
| `/backup_now` | 创建手动数据库备份 |

## 已移除的运行时功能

NotebookCog、RatingCog 和旧的 channel-based TicketsCog 未注册到运行时，不应出现在现役配置模板或 Discord 命令选择器中。历史实现和脱敏旧模板位于 `legacy-old-files-archive` 分支，详情见[中文旧实现归档说明](LEGACY_ARCHIVE.md)。
