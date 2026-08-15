# Bird Bot 架构说明

<p align="center">
  <a href="../../README.zh-CN.md"><img src="https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87%E9%A6%96%E9%A1%B5-2EA44F?style=for-the-badge" alt="返回中文 README"></a>
  <a href="../en/ARCHITECTURE.md"><img src="https://img.shields.io/badge/READ_IN-ENGLISH-5865F2?style=for-the-badge&amp;logo=googletranslate&amp;logoColor=white" alt="Read in English"></a>
</p>

最后检查：2026-08-15

本文说明 Bird Bot 的运行边界和共享模块。项目开发指南 `CLAUDE.md` 是开发、迁移、日志和测试规则的权威来源。

## 运行流程

Bird Bot 通过 `run.py` 启动：

1. 定位仓库根目录。
2. 通过 `runtime_env.load_env_file()` 加载根目录下被忽略的 `.env`。
3. 环境加载完成后再导入 `bot.main.run_bot()`。
4. 读取并验证 `bot/config/main.yaml`。
5. 明确启用成员、消息内容、语音状态、服务器消息和服务器反应 Intent；Presence Intent 保持关闭。
6. 遍历 `bot.main.COG_SPECS`，跳过已禁用或缺少必需配置的 cog。
7. 初始化每个已加载 cog、数据库管理器、持久化视图和后台任务。
8. 同步应用命令。
9. 关闭时先停止 cog 任务，再关闭保留的数据库管理器。

`COG_SPECS` 是现役模块注册表。新增或移除模块时，必须同时更新代码、配置模板、locale 文件、测试和用户文档。

## 包边界

```text
bot/
├── main.py               # Bot 工厂、现役 cog 注册、加载、日志和命令同步
├── cogs/                 # 每个现役功能一个包
├── config/               # 公开模板和 ignored 部署配置
├── locales/              # locale 管理的用户可见文案
└── utils/                # 共享配置、数据库、UI、路径、日志和任务工具
```

现役 cog 使用包结构，不再使用扁平的 `*_cog.py` 文件。一个功能包通常包含：

- `cog.py`：事件监听、命令、流程编排和后台任务；
- `views.py`：按钮和持久化视图；
- `modals.py`：用户输入；
- 按需增加 `embeds.py`、`service.py` 或 `full_message.py` 等专用工具。

Cog 负责协调 Discord 交互。持久化数据访问归属于 `bot/utils/` 下对应功能的数据库管理器；跨功能复用的行为归属于共享工具。

## 数据归属

Bird Bot 将部署设置、翻译文本、可变状态和二进制资源分开管理。

| 数据 | 归属 | 示例 |
| --- | --- | --- |
| 部署配置 | ignored `bot/config/*.yaml` | token、服务器/频道/身份组 ID、路径、价格、限制、颜色 |
| 公开配置 schema | tracked `bot/config/*.yaml.example` | 脱敏默认值和字段注释 |
| 用户可见文本 | `bot/locales/<lang>/*.yaml` | 回复、面板标题、modal 标签、命令翻译 |
| 可变运行状态 | SQLite 或 SQLCipher 数据库 | 余额、工单、成就、房间、面板消息 ID |
| 部署内容 | 按类型放入配置、locale 或 `resources/` | 欢迎 URL、字体、面板图片 |
| 历史输入 | `legacy-old-files-archive` 分支 | 旧 JSON 模板和已移除实现 |

`welcome_text` 是有意保留在配置中的用户文案例外，因为部署通常会嵌入真实 Discord URL 和自定义 emoji ID。成就定义和身份组领取选项名也属于结构化内容元数据，因为文本与阈值、类型 ID 和身份组 ID 绑定。

## 配置与 locale 加载

`bot.utils.config.Config` 加载并缓存 `bot/config/<name>.yaml`。它使用 ruamel.yaml round-trip 模式，让命令写回配置时保留注释。配置更新先写入同目录临时文件，再通过 `os.replace()` 原子替换。

运行时相对路径通过 `bot.utils.paths` 从仓库根目录解析。从其他工作目录启动 Bot 不会改变数据库或日志位置。

`bot.utils.i18n.t()` 从 `bot/locales/<lang>/` 解析 locale 键。Slash 命令名称和说明使用 `bot/locales/zh_CN/commands.yaml` 中的 `locale_str` 键。仓库当前只提供 `zh_CN`。

ID、路径、颜色、时间格式、数值限制和功能元数据放在配置中；通用回复、表单标签、按钮文本和面板文案放在 locale 文件中。

## 数据库层

所有运行时连接都通过 `bot.utils.db_connect.connect_database()` 创建。这个统一入口会：

- 打开配置的 SQLite 路径；
- 应用 `DCGSH_DB_KEY` 或 `DCGSH_DB_KEY_FILE` 提供的 SQLCipher 密钥；
- 在功能查询前验证数据库可读；
- 生产环境设置 `DCGSH_DB_REQUIRE_ENCRYPTION=1` 时强制要求密钥。

各功能管理器负责 schema 创建和查询。跨版本 schema 修改使用 `bot.utils.schema_migrations`。部分管理器会保持异步连接，因此关闭阶段会从已加载 cog 收集这些管理器，在后台循环停止后逐一关闭。

### 数据库管理器

| 模块 | 职责 |
| --- | --- |
| `achievement_db.py` | 成就计数、月度状态、语音会话、排行榜和手动操作 |
| `ban_db.py` | 临时封禁生命周期、管理历史和现役任务恢复 |
| `check_status_db.py` | 聚合语音活动样本 |
| `giveaway_db.py` | 抽奖、参与者、要求和中奖者 |
| `invite_guard_db.py` | 邀请链接、归因锁、加入/离开总数和排行榜计数 |
| `privateroom_db.py` | 房间所有权、到期时间、保存设置、封禁和商店面板 |
| `role_db.py` | 持久化领取视图、签名状态、修改槽位和权限标记 |
| `shop_db.py` | 余额、交易、签到、补签额度和面板记录 |
| `tickets_db.py` | 工单类型、配置、thread 状态、成员、管理员和统计 |
| `voice_channel_db.py` | 入口频道规则、临时房间和控制面板状态 |
| `teamup_display_manager.py` | 展示板、游戏类型映射和现役组队条目 |

迁移或直接维护部署数据库前必须备份。加密和密钥处理流程见[中文隐私说明](PRIVACY.md)。

## Discord UI 与持久化

Bird Bot 同时使用 embed 和 Discord Components v2。持久化面板会把频道和消息 ID 写入 SQLite，并在启动后重新注册兼容视图。

`bot.utils.components_v2` 提供共享构建工具。各功能的 `views.py` 负责交互回调，`modal_helpers.py` 负责可复用的 modal 模式。文本输入以 discord.py 2.7.1 为目标，并用 `discord.ui.Label` 包裹。

组队邀请的满员状态只有一个共享格式化入口：`bot.cogs.create_invitation.full_message.update_invitation_message_to_full()`。邀请面板和语音房面板都调用它，使 embed 和 Components v2 消息最终呈现为相同的红色、无按钮状态。

## 共享工具

| 模块 | 职责 |
| --- | --- |
| `channel_validator.py` | 默认管理员频道检查，以及 context/interaction 的语音状态验证 |
| `components_v2.py` | Components v2 通用构建和 payload 工具 |
| `db_connect.py` | 明文 SQLite 和 SQLCipher 的统一连接入口 |
| `db_lifecycle.py` | 发现并按顺序关闭数据库管理器 |
| `file_utils.py` | 目录树、归档、大小检查和临时文件清理 |
| `i18n.py` | 运行时 locale 查找 |
| `log_helpers.py` | Discord 用户、频道、身份组和服务器的标准日志格式 |
| `media_handler.py` | 有大小限制的媒体下载、哈希、命名和清理 |
| `modal_helpers.py` | 共享 modal 回复和验证工具 |
| `paths.py` | 仓库根目录路径标准化和父目录创建 |
| `role_helpers.py` | 共享身份组查找和分配行为 |
| `schema_migrations.py` | 有序数据库 schema 迁移 |
| `signature_cooldown.py` | 固定槽位的签名冷却计算 |
| `slash_translator.py` | 从 locale 键翻译 Discord 应用命令 |
| `task_helpers.py` | 后台任务登录状态启动保护 |

## 后台任务

后台循环必须等待 Discord 客户端可用，并在 cog unload 时干净停止。`bot.utils.task_helpers.wait_until_ready_or_stop()` 防止离线测试或关闭竞态留下未处理任务。

当前周期任务包括：

- 每十分钟采样语音活动；
- 每两分钟刷新组队展示板；
- 每六小时自动备份数据库；
- 清理临时语音房并恢复面板；
- 完成抽奖并恢复持久化视图；
- 处理私人房到期；
- 恢复临时封禁并按计划解封；
- InviteGuard 清理、邀请链接同步、批量归因和排行榜刷新；
- 签到面板刷新和每日切换。

任务先修改状态再编辑 Discord 时，必须明确操作顺序并用模拟交互或任务测试覆盖。例如，签到面板编辑成功后才推进每日状态；私人房续费在扣费前必须回读已持久化的到期时间。

## 日志

根 logger 写入主日志。关键词检测和房间活动使用不向上透传的独立 logger。日志路径和轮转保留数来自 `main.yaml`。

每个 Discord 实体都应包含名称和 ID：

- 用户：名称不同时写作 `display_name / username (id)`，相同时写作 `display_name (id)`；
- 频道、thread、身份组或服务器：`name (id)`；
- 无法解析的原始 ID：`unknown (id)`。

使用 `fmt_user`、`fmt_channel`、`fmt_role` 和 `fmt_guild`。数字 ID 使用 ASCII 括号。

## 生产环境定制

仓库提供通用 locale 文案和图片。生产 clone 可以为自己的社区修改 `bot/locales/` 和 `resources/images/` 下的 tracked 文件，同时保持真实 YAML 配置为 ignored。

升级时先 `git stash`，拉取上游变更，再恢复 stash 并主动解决内容冲突。生产 checkout 包含本地内容修改时，切勿执行 `git reset --hard` 或其他强制覆盖式更新。

通用改进应回流上游。服务器名称、邀请码、时区假设和其他部署事实应留在 ignored 配置或部署专属内容中。

## 扩展 Bot

新增现役 cog 时：

1. 参考最接近的现有功能，在 `bot/cogs/` 下创建包。
2. 使用功能键和必需配置名将 cog 加入 `bot.main.COG_SPECS`。
3. 为结构化运行数据添加脱敏且带注释的 `*.yaml.example` 模板。
4. 添加用户文案和命令 locale 键。
5. 通过管理器和 `connect_database()` 访问数据库。
6. 为配置元数据、数据库行为和交互顺序添加离线测试。
7. 更新[中文功能参考](FEATURES.md)、README 配置表和相关测试。

只有依赖 Discord 本身的行为才使用测试服务器验证：权限、命令同步、重启后的持久化视图、rate limit、私信投递和客户端渲染。
