# 隐私与数据处理

<p align="center">
  <a href="README.zh-CN.md"><img src="https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87%E9%A6%96%E9%A1%B5-2EA44F?style=for-the-badge" alt="返回中文 README"></a>
  <a href="PRIVACY.md"><img src="https://img.shields.io/badge/READ_IN-ENGLISH-5865F2?style=for-the-badge&amp;logo=googletranslate&amp;logoColor=white" alt="Read in English"></a>
</p>

本文说明 Bird Bot 保存哪些数据、保存原因，以及运营者应如何保护这些数据。Bird Bot 由运营者自行托管；数据保存在运营者本地的 SQLite 数据库、日志和备份文件中，不会发送到本仓库控制的托管服务。

## Discord 特权 Intent

Bird Bot 只申请当前功能所需的 Gateway Intent：

- `Guild Members`：欢迎消息、成员数量显示、按身份组展开工单管理员、邀请加入/离开归因，以及 slash 命令中选择的成员对象。
- `Message Content`：组队关键词检测和消息数量成就。
- `Voice States`：临时语音房、语音时长成就、私人房资格和语音状态命令。
- `Guild Messages` 和 `Guild Reactions`：消息/反应成就、面板和交互恢复。

Bird Bot 不申请 `Guild Presences`，也不使用在线/离线状态、活动、平台信息或 rich presence 数据。

Discord 的特权 Intent 审核指南将 `Guild Presences`、`Guild Members` 和 `Message Content` 列为特权 Intent，并说明这些 Intent 因可访问的数据而默认关闭。运营者只应启用 Bird Bot 使用的两个特权 Intent：Server Members Intent 和 Message Content Intent。

参考：<https://docs.discord.com/developers/gateway/getting-started-with-privileged-intent-review>

## 存储的数据

Bot 保存恢复面板、跟踪进度和在重启后继续定时任务所需的 Discord snowflake ID 与功能状态。

- 语音房：临时语音频道 ID、创建者用户 ID、控制面板消息 ID、房间类型、音效板状态和时间戳。
- 组队展示：用户 ID、来源频道 ID、语音频道 ID、简短组队消息内容、玩家数量、游戏类型、邀请消息 ID 和过期时间。
- 成就：用户 ID、消息/反应数量、语音时长、月度计数、现役语音会话和管理员手动操作记录。
- 商店与签到：用户 ID、积分余额、交易记录、签到日期、连续签到、补签状态和签到面板消息 ID。
- 私人房：所有者用户 ID、私人房频道/分类 ID、开始/结束日期、状态标记和商店面板消息 ID。
- 工单：thread ID、工单创建者 ID、类型名称、工单编号、加入工单的成员 ID、接单/关闭状态和关闭原因。
- 身份组与签名：持久化身份组面板消息 ID、用户 ID、用户提交的签名、签名修改时间和签名禁用标记。
- 封禁：用户 ID、服务器 ID、管理员 ID、封禁原因、解封时间、活动状态和 Discord 删除消息天数设置。
- 抽奖：抽奖 ID、频道/消息 ID、创建者 ID、奖品/说明文本、参与者 ID、中奖者 ID、要求和结束状态。
- 邀请防护与排行榜：服务器/用户 ID、邀请者用户 ID、邀请码、邀请频道 ID、使用次数、归因状态、加入/离开计数、排行榜消息/频道 ID，以及 ignored/active 邀请链接状态。邀请奖励会写入 Shop 余额和交易表。
- 状态检查样本：带时间戳的聚合语音人数和活跃频道数。
- 配置表：工单类型、语音频道规则、游戏类型映射和面板消息位置等功能初始化状态。

Bot 不会主动在数据库中保存 Discord access token。Bot token 和运行配置位于被忽略的本地 `bot/config/*.yaml` 文件中。

## 日志与备份

运行日志是 `main.yaml` 配置的本地文件：

- Bot 主日志。
- 关键词检测日志。
- 房间活动日志。

日志使用名称和 ID 标识 Discord 实体，帮助服务器运营者排查管理和房间问题。日志保留数量由 `log_backup_count` 控制。

`BackupCog` 每 6 小时复制一次 SQLite 数据库并保留最近 20 个自动备份；`/backup_now` 创建的手动备份单独保留。启用数据库加密后，这些备份仍保持加密，因为它们是加密数据库文件的逐字节副本。

## 数据库加密

配置密钥后，Bird Bot 使用 SQLCipher 对 SQLite 数据库进行静态加密。运行时密钥必须来自环境变量，不能写入 YAML：

- `DCGSH_DB_KEY`：SQLCipher 使用的密码。
- `DCGSH_DB_KEY_FILE`：包含密码的文件路径。
- `DCGSH_DB_CREATE_KEY_FILE=1`：密钥文件不存在时生成一次。
- `DCGSH_DB_REQUIRE_ENCRYPTION=1`：未配置密钥时拒绝启动。

本地测试中，`run.py` 会在导入 Bot 前读取仓库根目录下的 `.env`。该文件已被 git 忽略，可以将 `DCGSH_DB_KEY_FILE` 指向 `.local_secrets/local-test-db.key` 等 ignored 本地密钥文件。启动器已提供的环境变量不会被覆盖；`.env` 中相对的 `DCGSH_DB_KEY_FILE` 从 `.env` 所在目录解析。生产启动器应优先使用主机环境变量或 secret manager，也可以完全不使用本地 `.env`。

配置密钥后，所有运行时数据库管理器都通过 `bot.utils.db_connect.connect_database()` 打开 SQLite。该入口应用 `PRAGMA key`，并在执行功能 SQL 前验证数据库可读。

将现有明文数据库加密：

```bash
export DCGSH_DB_KEY_FILE='/secure/bird-bot/db.key'
export DCGSH_DB_CREATE_KEY_FILE=1
python -m tools.encrypt_database data/bot.db data/bot.encrypted.db \
  --backup-source backup/db_backup_manual/plain-before-encryption.db
mv data/bot.encrypted.db data/bot.db
unset DCGSH_DB_CREATE_KEY_FILE
export DCGSH_DB_REQUIRE_ENCRYPTION=1
```

PowerShell：

```powershell
$env:DCGSH_DB_KEY_FILE = 'C:\secure\bird-bot\db.key'
$env:DCGSH_DB_CREATE_KEY_FILE = '1'
python -m tools.encrypt_database data/bot.db data/bot.encrypted.db --backup-source backup/db_backup_manual/plain-before-encryption.db
Move-Item -Force data/bot.encrypted.db data/bot.db
Remove-Item Env:DCGSH_DB_CREATE_KEY_FILE
$env:DCGSH_DB_REQUIRE_ENCRYPTION = '1'
```

迁移时创建的明文备份属于敏感数据。验证加密数据库后，将它移到离线加密备份位置或安全删除。

生成的密钥文件同样属于敏感数据。请保留安全的离线副本；密钥丢失后，现有加密数据库和备份将无法解密。

## 保留与删除

- 组队邀请在配置的运行窗口后过期；当前默认值为 5 分钟。
- 托管频道已不存在时，对应临时语音房记录会被删除。
- Ban 数据库清理流程可以删除 inactive 临时封禁记录；active 记录保留到解封处理完成。
- 日志按照 `log_backup_count` 轮转。
- 每个自动备份目录保留最近 20 个数据库备份。
- 管理员可以通过身份组/签名工具清除用户签名。
- 其他功能数据在审计、排行榜、重启恢复或管理历史仍需要时保留。运营者备份后可以从 SQLite 数据库中手动删除数据。

## 运营者检查清单

- 在 Discord Developer Portal 中只启用必需的特权 Intent：Server Members Intent 和 Message Content Intent。
- 除非未来功能明确需要 presence 数据并同步更新本文，否则不要启用 Presence Intent。
- 不要将 `bot/config/*.yaml`、`.env`、`.local_secrets/`、`data/*.db`、备份和日志提交到 git。
- 数据库迁移后，在生产环境设置 `DCGSH_DB_REQUIRE_ENCRYPTION=1`。
- 将 `DCGSH_DB_KEY` 保存在主机 secret manager 中，或将 `DCGSH_DB_KEY_FILE` 放在仓库外并限制访问权限。
- 只在首次生成密钥文件时设置 `DCGSH_DB_CREATE_KEY_FILE=1`，随后移除。
- 不要向支持频道发送 Bot token、数据库密钥、完整日志或明文数据库 dump。
- 替换生产 `data/bot.db` 前，使用数据库副本测试迁移。
