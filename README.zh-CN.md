# Bird Bot

<p align="center">
  <a href="README.md">
    <img src="https://img.shields.io/badge/READ_IN-ENGLISH-5865F2?style=for-the-badge&amp;logo=googletranslate&amp;logoColor=white" alt="Read in English">
  </a>
  <a href="docs/zh-CN/CHANGELOG.md">
    <img src="https://img.shields.io/badge/CURRENT_RELEASE-v2.0.3-5865F2?style=for-the-badge&amp;logo=discord&amp;logoColor=white" alt="当前版本：Bird Bot v2.0.3">
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/PYTHON-3.12-3776AB?style=for-the-badge&amp;logo=python&amp;logoColor=white" alt="Python 3.12">
  </a>
  <a href="https://discordpy.readthedocs.io/">
    <img src="https://img.shields.io/badge/DISCORD.PY-2.7.1%2B-5865F2?style=for-the-badge&amp;logo=discord&amp;logoColor=white" alt="discord.py 2.7.1 或更高版本">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/LICENSE-MIT-2EA44F?style=for-the-badge&amp;logo=opensourceinitiative&amp;logoColor=white" alt="MIT 许可证">
  </a>
</p>

Bird Bot 是一款面向中文游戏社区的自托管 Discord Bot。它以模块化服务整合临时语音房、组队工具、成就、积分经济、工单、管理和服务器运维功能。

所有持久化数据均保存在运营者本地的 SQLite 数据库、日志和备份中。需要静态加密的部署可以启用 SQLCipher。

[![Bird Gaming Discord](https://discord.com/api/guilds/1146359014968537089/widget.png?style=banner2)](https://discord.gg/birdgaming)

> Bird Bot 当前每个进程只支持一个 Discord 服务器。仓库内置界面语言为 `zh_CN`；暂未实现多服务器运行和其他 locale。

## 功能

| 领域 | Bird Bot 提供的功能 |
| --- | --- |
| 语音房与组队 | 临时语音房、房间控制面板、关键词触发的组队邀请和实时组队展示板 |
| 社区欢迎 | 欢迎图片、欢迎频道消息和可配置的欢迎私信 |
| 成就与身份组 | 消息、反应、语音时长和签到成就；排行榜；身份组领取面板；个性签名 |
| 积分与私人房 | 每日签到、补签、余额、交易记录、私人房购买、续费和到期处理 |
| 工单 | 基于 thread 的工单、按类型分配管理员、持久化控件、状态跟踪和统计 |
| 管理 | 永久封禁、临时封禁、禁言、`@everyone` 垃圾消息防护、通知频道和重启后恢复临时封禁 |
| 邀请管理 | 过期邀请清理、邀请归因、批量池化结算、排行榜和可配置积分奖励 |
| 抽奖与游戏 | 持久化抽奖、D&D 骰子表达式和互动式 SpyMode 游戏 |
| 运维 | 日志查看、语音活动报告、自动数据库备份和手动备份 |

对应功能支持持久化 Discord 面板时，Bot 会在重启后恢复面板。部署者可以通过功能开关只加载需要的 cog。

按命令查看具体行为和注意事项，请阅读[功能参考](docs/zh-CN/FEATURES.md)。运行时边界和共享模块见[架构说明](docs/zh-CN/ARCHITECTURE.md)。

## 预览

| 组队面板 | 成就面板 | 排行榜面板 |
| --- | --- | --- |
| ![组队面板](pics/discord-intent-review/teamup-panel.png) | ![成就面板](pics/discord-intent-review/achievement-panel.png) | ![排行榜面板](pics/discord-intent-review/rank-panel.png) |

## 环境要求

- Python 3.12 或更高版本；仓库通过 `.python-version` 固定使用 Python 3.12.3
- 使用 [`uv`](https://docs.astral.sh/uv/) 管理锁定环境
- 一个带 Bot 用户的 Discord 应用
- 已启用 Discord **Server Members Intent** 和 **Message Content Intent**
- 主机能够写入配置的数据库、日志和备份路径

Bird Bot 不申请 Presence Intent。最简单的初始权限配置是同时使用 `bot`、`applications.commands` scope 和 Administrator 权限。完成所有已启用功能的验证后，运营者可以收紧权限；InviteGuard、临时语音房、工单、管理和身份组分配仍需对应的 Discord 权限。

## 快速开始

### 1. 创建 Discord Bot

在 [Discord Developer Portal](https://discord.com/developers/applications) 中：

1. 创建应用并添加 Bot 用户。
2. 在 Bot 设置中启用 **Server Members Intent** 和 **Message Content Intent**。
3. 使用 `bot` 和 `applications.commands` scope 邀请 Bot。
4. 记录 Bot token、服务器 ID 和管理员频道 ID，供配置使用。

如果应用需要提交 Discord 特权 Intent 审核，请阅读 [Discord 权限申请指南](docs/zh-CN/DISCORD_INTENT_APPLICATION_GUIDE.md)。

### 2. 安装项目

```bash
git clone https://github.com/MrZoyo/Bird-Bot.git
cd Bird-Bot
uv sync --python 3.12.3
```

直接依赖定义在 `pyproject.toml` 中，`uv.lock` 用于复现环境。`requirements.lock` 只是兼容性导出文件，请勿手动编辑。

### 3. 创建本地配置

复制主配置模板和计划启用功能的模板：

```bash
cp bot/config/main.yaml.example bot/config/main.yaml
cp bot/config/voicechannel.yaml.example bot/config/voicechannel.yaml
```

在 PowerShell 中将 `cp` 替换为 `Copy-Item`。

编辑 `bot/config/main.yaml`，至少设置：

- `token`
- `guild_id`
- `admin_channel_id`
- 数据库和日志路径（默认值不适合当前部署时）
- `features` 下的每个开关

禁用所有尚未配置的功能。启用的 cog 如果缺少必需配置或配置为空，会在启动时跳过，相关命令也不会注册。

真实的 `bot/config/*.yaml` 文件包含部署 ID 和敏感信息，因此已被 git 忽略。只提交脱敏后的 `*.yaml.example` 模板。

### 4. 启动 Bot

```bash
uv run python run.py
```

Bird Bot 启动时会加载已启用的 cog，恢复支持的持久化视图和后台任务，然后同步全局 slash 命令。控制台会列出已加载和已跳过的 cog。

## 配置

`bot/main.py::COG_SPECS` 是现役 cog 及其必需配置文件的权威来源。

| 功能键 | Cog | 必需本地配置 |
| --- | --- | --- |
| `voicechannel` | 临时语音房 | `voicechannel.yaml` |
| `welcome` | 欢迎图片、频道消息和私信 | `welcome.yaml` |
| `invitation` | 组队关键词检测与邀请 | `invitation.yaml` |
| `invite_guard` | 邀请清理、归因、排行榜和奖励 | `invite_guard.yaml` |
| `dnd` | D&D 骰子 | 无 |
| `checkstatus` | 日志和语音状态工具 | 无 |
| `achievements` | 成就与排行榜 | `achievements.yaml` |
| `spymode` | SpyMode 游戏 | 无 |
| `giveaway` | 抽奖 | `giveaway.yaml` |
| `role` | 身份组领取与签名 | `role.yaml`、`achievements.yaml` |
| `backup` | 数据库备份 | 无 |
| `tickets` | 基于 thread 的工单 | `tickets.yaml` |
| `shop` | 签到与积分经济 | `shop.yaml` |
| `privateroom` | 私人房购买与续费 | `privateroom.yaml`、`role.yaml` |
| `ban` | 封禁、临时封禁和禁言 | `ban.yaml` |
| `teamup_display` | 组队展示板 | `teamup_display.yaml` |

配置遵循四条规则：

1. `./data/bot.db` 等相对路径从仓库根目录解析，而不是从进程工作目录解析。
2. 用户可见文案放在 `bot/locales/<lang>/`；运行时 ID、路径、颜色、价格、限制和内容元数据放在 YAML 配置中。
3. 可变的初始化数据（包括语音房入口规则和工单类型）保存在 SQLite 中，并通过 Discord 命令管理。
4. `welcome_text` 保留在 `welcome.yaml`，因为部署通常会在其中嵌入服务器专用 URL 和自定义 emoji ID。

## 首次 Discord 初始化

Bot 上线后，只初始化已启用的功能：

| 功能 | 常用初始化命令 |
| --- | --- |
| 临时语音房 | `/vc_add`、`/vc_list`、`/vc_remove` |
| 组队展示板 | `/teamup_init`、`/teamup_type_add`、`/teamup_type_list` |
| 工单 | `/tickets_init`、`/tickets_add_type`、`/tickets_admin_list` |
| 签到经济 | `/create_checkin_embed` |
| 私人房 | `/privateroom_setup`、`/privateroom_init` |
| 身份组与签名面板 | `/create_role_pickup`、`/create_starsign_pickup`、`/create_mbti_pickup`、`/create_gender_pickup`、`/create_signature_pickup` |
| 邀请排行榜 | `/invite_create_embed`、`/invite_sync` |
| 欢迎流程 | `/testwelcome` |

Discord 命令选择器会显示 slash 命令说明和选项帮助。部分管理命令只能在 `main.admin_channel_id` 中运行，或要求功能专属的身份组和用户权限。

## 数据、隐私与加密

Bird Bot 只保存已启用功能所需的状态，包括 Discord ID、面板位置、成就、余额、工单、管理记录、邀请归因、日志和备份。项目本身不会把这些数据发送到其运营的托管服务。

不要把以下文件提交到版本库或发到支持频道：

- `bot/config/*.yaml`
- `.env` 和 `.local_secrets/`
- `data/*.db`
- 日志和数据库备份
- SQLCipher 密钥

数据库加密由以下环境变量控制：

| 变量 | 用途 |
| --- | --- |
| `DCGSH_DB_KEY` | 直接提供 SQLCipher 密码 |
| `DCGSH_DB_KEY_FILE` | 从文件读取密码 |
| `DCGSH_DB_CREATE_KEY_FILE=1` | 密钥文件不存在时生成一次 |
| `DCGSH_DB_REQUIRE_ENCRYPTION=1` | 未配置加密密钥时拒绝启动 |

`run.py` 会读取仓库根目录下被忽略的 `.env`，但不会覆盖启动器已经提供的变量。生产部署应使用主机环境变量或 secret manager。

投入生产前请阅读[隐私与数据处理说明](docs/zh-CN/PRIVACY.md)，其中包含完整数据清单、保留规则、备份说明和从明文 SQLite 迁移到 SQLCipher 的流程。

## 升级部署

生产服务器可能会定制 `bot/locales/` 下的已追踪文案和 `resources/images/` 下的图片。升级时保留这些修改：

```bash
git stash push -m "production overrides"
git pull --ff-only
git stash pop
uv sync --frozen --python 3.12.3
```

升级前：

1. 备份 `data/bot.db`。
2. 如果启用了加密，备份对应的 SQLCipher 密钥文件。
3. 检查上游配置模板变化，并把相关新键应用到本地 YAML。
4. 重启 Bot，检查启动日志中是否有跳过的 cog 或迁移错误。

需要时，数据库 schema 迁移会在启动阶段执行。生产 checkout 包含服务器专用 locale 或图片修改时，切勿使用 `git reset --hard` 或其他强制覆盖式更新。

## 从 2.0 之前的 JSON 配置迁移

Config 2.0 使用 YAML、locale 文件和数据库中的可变初始化数据。请使用旧配置和数据库的副本测试迁移：

```bash
uv run python tools/migrate_config_to_yaml.py
# 检查 tools/migration_report.md 和生成的 YAML/locale 输出。
uv run python tools/seed_db.py
```

迁移会将旧的 `config_tickets_new.json` 数据映射到当前工单系统，并跳过已移除的 RatingCog 和旧 TicketsCog 来源。迁移输出可能包含真实 Discord ID，因此已被 git 忽略。

## 项目结构

```text
.
├── run.py                    # 加载本地环境并启动 Bot
├── bot/
│   ├── main.py               # Bot 工厂、功能注册、cog 加载和命令同步
│   ├── cogs/                 # 现役功能包
│   ├── config/               # 公开 *.yaml.example 和本地 ignored *.yaml
│   ├── locales/              # 用户可见的 locale 文案
│   └── utils/                # 配置、数据库、i18n、日志、媒体和共享工具
├── resources/                # 运行时字体和图片
├── docs/                     # 功能与架构等详细文档
├── tools/                    # 迁移、加密、locale 检查和维护工具
├── tests/                    # 离线 pytest 和模拟 Discord 交互测试
├── data/                     # 本地数据库和日志；运行时文件被忽略
└── backup/                   # 自动和手动数据库备份
```

每个现役 cog 都是 `bot/cogs/` 下的一个包。运行时数据库访问统一通过 `bot.utils.db_connect.connect_database()`，让明文 SQLite 和 SQLCipher 部署共用同一连接路径。

## 开发

安装测试和 lint 依赖：

```bash
uv sync --extra test --extra lint --python 3.12.3
```

运行本地检查：

```bash
uv run pytest -q
uv run ruff check bot tests tools
uv run python -m compileall bot tests tools
uv run python -X utf8 tools/check_locales.py
uv lock --check
```

自动化测试使用临时数据库和模拟 Discord 交互。权限、命令同步、重启后的持久化视图、rate limit、私信和客户端渲染仍需在测试服务器验证。

贡献前请阅读 `CLAUDE.md`。它定义了当前架构、日志格式、迁移规则、测试命令和安全要求。现役文档与测试应始终和 `bot/main.py::COG_SPECS` 一致；NotebookCog、RatingCog 和旧的 channel-based TicketsCog 已停用。

## 文档

| 文档 | 用途 |
| --- | --- |
| [功能参考](docs/zh-CN/FEATURES.md) | 现役 cog 的详细行为、命令、默认值和注意事项 |
| [架构说明](docs/zh-CN/ARCHITECTURE.md) | 运行流程、数据归属、数据库层、UI 和扩展点 |
| [更新日志](docs/zh-CN/CHANGELOG.md) | 最新版本中文摘要和英文完整历史入口 |
| [隐私与数据处理](docs/zh-CN/PRIVACY.md) | 存储数据、特权 Intent、保留规则、备份和 SQLCipher |
| [Discord 权限申请指南](docs/zh-CN/DISCORD_INTENT_APPLICATION_GUIDE.md) | Discord 特权 Intent 申请填写说明 |
| [旧实现归档说明](docs/zh-CN/LEGACY_ARCHIVE.md) | 旧实现和旧模板的归档位置 |

## 许可证

Bird Bot 使用 [MIT License](LICENSE)。
