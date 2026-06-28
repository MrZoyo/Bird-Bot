# Discord 权限申请填写说明

本文给负责提交 Discord Developer Portal 权限申请的人使用。请按当前 `main` 分支代码和公开仓库内容填写，不要申请当前代码没有使用的权限。

## 基本链接

隐私政策链接：

```text
https://github.com/MrZoyo/Bird-Bot/blob/main/PRIVACY.md
```

可用于表单的截图链接：

```text
成就面板：
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/achievement-panel.png

排行榜面板：
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/rank-panel.png

组队邀请面板：
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/teamup-panel.png
```

如果表单要求直接图片文件链接，也可以使用 raw 链接：

```text
https://raw.githubusercontent.com/MrZoyo/Bird-Bot/main/pics/discord-intent-review/achievement-panel.png
https://raw.githubusercontent.com/MrZoyo/Bird-Bot/main/pics/discord-intent-review/rank-panel.png
https://raw.githubusercontent.com/MrZoyo/Bird-Bot/main/pics/discord-intent-review/teamup-panel.png
```

## 权限选择总览

申请的 Privileged Gateway Intent：

```text
Server Members Intent: 申请
Message Content Intent: 申请
Presence Intent: 不申请
```

原因：当前代码只启用了 `members` 和 `message_content`，并明确关闭 `presences`。Bot 不使用在线/离线状态、活动状态、平台状态或 rich presence 数据。

## APP 详情

问题：您的 APP 具备哪些功能？请尽可能详细描述，可附上相关图片或视频链接。

建议填写：

```text
Bird Bot 是一个面向 Discord 社区运营的服务器管理与互动 Bot，主要功能包括：

1. 自动语音房系统：用户进入指定语音频道后，Bot 自动创建临时语音房并移动用户；房间无人后自动清理；房主可以通过控制面板切换公开/私人、标记满员、开关音效板等。
2. 组队邀请系统：用户在文字频道发送符合规则的组队消息时，Bot 会识别关键词，生成可加入当前语音房的组队面板，并同步到组队展示板。
3. 欢迎系统：新成员加入服务器时发送欢迎频道消息、欢迎图片和私信引导。
4. 成就与排行榜系统：统计成员消息数、反应数、语音在线时长、签到记录等，用于成就进度、成就身份组领取和排行榜展示。
5. 商店与每日签到系统：成员可以每日签到、补签、查看积分余额；管理员可以管理积分交易。
6. 私人房间系统：成员可以购买和续费私人房间，Bot 会记录到期时间并在到期后自动删除房间。
7. 工单系统：成员可以创建私密 thread 工单，Bot 会按工单类型自动加入对应管理员/管理身份组成员，并记录工单状态。
8. 身份领取系统：成员可以领取星座、MBTI、性别标识、成就身份组，并设置个性签名。
9. 抽奖、临时封禁、备份、服务器语音状态查询等辅助管理功能。

Bot 仅用于服务器管理、成员互动、成就统计和功能面板恢复，不会将 Discord 数据出售、共享给第三方，或用于机器学习/AI 模型训练。

截图链接：
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/teamup-panel.png
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/achievement-panel.png
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/rank-panel.png
```

问题：您是否已发布公开的隐私政策，向用户说明其数据的使用方式？

选择：

```text
Yes
```

隐私政策 URL：

```text
https://github.com/MrZoyo/Bird-Bot/blob/main/PRIVACY.md
```

## Server Members Intent

问题：您为什么需要服务器成员 Intent？

建议填写：

```text
Bot 需要 Server Members Intent 来支持服务器成员相关的核心功能：

1. 欢迎系统需要接收成员加入事件，生成欢迎消息、欢迎图片、成员计数，并向新成员发送入服引导私信。
2. 工单系统需要读取指定管理员身份组下的成员，将这些成员自动加入对应的私密工单 thread，并发送通知。
3. 成就、身份领取、私人房间和管理命令需要可靠地识别 Discord Member 对象、成员身份组和成员权限。
4. 语音状态查询功能需要展示某个成员当前所在语音频道以及同频道成员列表。
5. 私人房间和部分管理功能需要检查成员是否持有特定身份组，例如房间折扣/资格判断。

这些数据只用于服务器内功能执行、权限判断、面板恢复和管理审计，不用于广告、画像、出售或外部共享。
```

问题：请提供能演示您使用场景的截图和 / 或视频链接。

可填写：

```text
成就面板：
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/achievement-panel.png

排行榜面板：
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/rank-panel.png
```

问题：您是否会在平台外（Discord 之外）存储任何 API 数据？

选择：

```text
Yes
```

问题：您存储的 API 数据是否不超过 30 天？

建议选择：

```text
No
```

说明：Bot 会长期保存一些服务器功能所需的数据，例如成就统计、签到记录、积分余额、工单记录、私人房间到期时间、临时语音房记录、抽奖记录、临时封禁记录、面板 message ID 等。这些数据用于功能恢复、排行榜、审计和管理，不是临时缓存。

问题：用户如何联系您申请删除其活跃数据？

建议填写：

```text
用户可以联系服务器管理团队申请删除数据，主要方式是：

1. 在服务器内联系管理员；
2. 使用 Bot 的工单系统提交数据删除请求。

管理员确认请求后，可以删除或清理该用户相关的活跃数据，例如签名、工单记录、积分/签到记录、成就统计、私人房间记录、组队记录或其他功能状态数据。
```

问题：您是否按照开发者政策要求，对静态存储的数据进行加密处理？

选择：

```text
Yes
```

说明：当前代码支持 SQLCipher 数据库静态加密，生产环境应配置 `DCGSH_DB_KEY` 或 `DCGSH_DB_KEY_FILE`，并设置 `DCGSH_DB_REQUIRE_ENCRYPTION=1`。

## Message Content Intent

问题：用户是否可选择退出消息内容数据的追踪？

选择：

```text
Yes
```

可补充说明：

```text
用户可以通过联系服务器管理员或提交工单申请退出/删除相关数据。管理员也可以将特定频道或用户加入组队关键词检测忽略列表，使 Bot 不再处理这些位置或用户的组队消息。
```

问题：您是否会将消息内容数据存储至平台外（Discord 之外）？

选择：

```text
Yes
```

说明：Bot 会为了组队展示和问题排查短期保存组队关键词消息内容，也会将关键词检测事件写入本地日志。普通功能状态和用户主动输入的数据保存在本地 SQLite 数据库中。

问题：您存储的用户消息内容数据是否不超过 30 天？

建议选择：

```text
No
```

说明：当前运行配置默认日志轮转保留 14 个日备份文件，组队展示数据默认约 5 分钟过期并清理；但由于运营方可能保留手动备份或按实际服务器政策调整日志保留，因此这里按保守口径填写 `No`。如提交人确认生产环境严格保证所有消息内容日志和备份均不超过 30 天，也可以改为 `Yes`，但需要与实际运维策略保持一致。

问题：用户如何联系您申请删除其活跃数据？

建议填写：

```text
用户可以联系服务器管理团队，或通过 Bot 工单系统提交删除请求。管理员确认后，可以清理该用户相关的消息内容数据，例如组队展示记录、个性签名、工单相关记录或其他功能中保存的用户输入文本。
```

问题：您是否按照开发者政策要求，对静态存储的数据进行加密处理？

选择：

```text
Yes
```

问题：您是否会将消息内容数据用于训练机器学习或 AI 模型？

选择：

```text
No
```

问题：您为何需要消息内容 Intent？

建议填写：

```text
Bot 需要 Message Content Intent 来实现服务器内的组队关键词检测和消息成就统计：

1. 组队邀请系统会读取普通文字频道中的消息内容，使用规则和正则表达式识别组队关键词，例如排队、缺人、队伍人数等，然后自动回复语音房组队邀请面板。
2. 成就系统会监听成员消息事件，用于累计消息数量成就和月度消息排行榜。
3. Bot 不会读取这些消息内容用于广告、画像、出售、外部共享或 AI/机器学习训练。
4. 对于组队展示，Bot 只保存短期展示所需的组队文本、频道 ID、用户 ID、语音频道 ID 和过期时间；过期邀请会被清理。其他持久化文本仅限功能必要内容，例如用户主动设置的签名、工单关闭原因、抽奖描述等。
```

问题：请提供能演示您使用场景的截图和 / 或视频链接。

可填写：

```text
组队邀请面板：
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/teamup-panel.png

成就面板：
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/achievement-panel.png

排行榜面板：
https://github.com/MrZoyo/Bird-Bot/blob/main/pics/discord-intent-review/rank-panel.png
```

## 提交前检查

提交前确认：

```text
1. 只勾选 Server Members Intent 和 Message Content Intent。
2. 不勾选 Presence Intent。
3. 隐私政策链接使用公开仓库的 PRIVACY.md。
4. 删除数据联系方式写“联系管理员或提交工单”。
5. 静态数据加密选择 Yes，并确认生产环境已启用 SQLCipher 数据库加密。
6. 机器学习/AI 训练选择 No。
7. 截图链接使用 main 分支下的公开 GitHub 链接。
```
