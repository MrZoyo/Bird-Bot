# P0 重构测试 Checklist

> 本清单覆盖 P0 系列（P0-4 / P0-1 / P0-2 / P0-3a~d）**全部改过的功能路径**，配合 `REFACTORING_PROGRESS.md` 使用。
> 目标：用户在测试服手工过一遍，确认无 regression 后再推生产或进入 P1。

## 使用说明

- 每个测试项打勾：`[ ]` → `[x]`；如果有问题打 `[!]` 并在下面写一行"现象：xxx"。
- 每节标注 **改动来源**（哪个 commit / 哪条 P 任务）和 **破坏性风险**（如果这里坏了，影响什么）。
- 🔴 = 必测（核心路径） / 🟡 = 推荐测（失败路径） / 🟢 = 可选（边缘场景）
- **测试服** 而非生产服；配置里 `guild_id` 指向测试环境；数据库用测试副本。
- 进入每节前先看"触发方式"，知道怎么创造场景。

---

## 0. 启动期健康检查

> 破坏性风险：冷启动失败意味着所有 manager 初始化出问题，下面所有项都白测。

- [x] 🔴 **Bot 冷启动无 ImportError**
  - 操作：重启 bot，观察启动日志
- 预期：不出现 `ImportError: No module named 'giveaway_db'`（或 check_status / voice_channel_db）之类的错误
  - 意义：验证 `bot/utils/__init__.py` 的新增导出都对

- [x] 🔴 **启动日志里**无 `no such table`**之类异常**
  - 操作：grep `tail -200 ./logs/main.log | grep -iE "no such table|operational error"`
  - 预期：空输出；特别是**不应**出现 `no such table: status`（P0-3a 修的竞态 bug 的典型症状）
  - 意义：验证 `cog_load` 期的 `initialize_database()` 都跑通

- [!] 🟡 **老部署升级路径**（如果是在有旧 `bot.db` 的环境上启动）
  - **✅ 已在 ⁠商店 创建私人房间商店。** 这个消息不要作为私有回复。
  - 操作：在一个已有 `privateroom_rooms` / `temp_channels` 数据的副本上启动
  - 预期：
    - `privateroom_db` 的 `ALTER TABLE ... renewal_reminder_sent` 如果列已存在，不报错（P0-4 修的收窄）
    - `voice_channel_db.initialize_database()` 自动补齐老库缺的列（`control_panel_message_id` 等）
  - 意义：验证 schema migration 在 manager 版本下仍工作

- [x] 🟡 **Bot shutdown 干净**
  - 操作：给 bot 发 `kill -TERM`（或 Ctrl+C）
  - 预期：不卡死、无 `asyncio.CancelledError` 被裸 except 吞的警报（P0-4 修复前裸 except 会吞 CancelledError）
  - 意义：验证裸 except 改动没把 shutdown 路径搞坏

---

## 1. P0-4 裸 except 治理（21 处）

> **commit**：`git log --grep='(P0-4)'`
> 改动基本都在"失败时的 fallback"路径上，正常测试不会触发。想触发需要故意制造失败条件。

### 1.1 `privateroom_db.initialize_database` ALTER TABLE

- [x] 🟡 **重复列容错**
  - 操作：bot 启动、运行一段时间后再次重启
  - 预期：第二次启动时 `ALTER TABLE privateroom_rooms ADD COLUMN renewal_reminder_sent` 会失败（列已存在），静默跳过；日志无 ERROR
  - 收窄类型：`aiosqlite.OperationalError`

### 1.2 `voice_channel_cog.restore_control_panels` fetch_user 容错

- [x] 🟢 **Creator 已离开服务器的控制面板恢复**
  - 前置：有一个带控制面板的临时房间，然后让 creator 离开服务器（或用一个已退服的测试账号 ID）
  - 操作：重启 bot
  - 预期：该房间的控制面板仍然恢复成功（creator 显示为 None），不会因为 fetch_user 抛异常而吞掉整个 restore 流程
  - 收窄类型：`(discord.NotFound, discord.HTTPException)`

### 1.3 `ban_cog` 管理员列表显示

- [x] 🟡 **管理员 ID 有失效的情况**
  - 前置：`config_ban.json` 的 `admin_users` 里故意塞一个不存在的用户 ID（或已删账号）
  - 操作：跑 `/ban_config_view`（或类似查看管理员列表的命令，按实际命令名）
  - 预期：列表能完整显示，失效的 ID 显示 `<@ID> (不存在)`，不会因此整个命令失败

- [x] 🟡 **tempban 列表里有失效用户**
  - 前置：数据库里有一条 tempban 记录，对应用户已删账号
  - 操作：跑 `/ban_list_temp`（或类似）
  - 预期：列表能显示，失效用户条目显示为 `用户 {id}` 兜底格式

### 1.4 `shop_cog`

- [x] 🟢 **makeup 查询按钮的临时文件清理**
  - 操作：点击 makeup check-in 查询按钮（生成图片文件）
  - 预期：响应成功；后续没有 `/tmp/` 残留文件（实际上即使有 OSError 也不影响功能）
  - 意义：收窄到 `OSError` 就好

- [x] 🟡 **每日 embed 更新时 embed 消息已被删**
  - 前置：有一个活跃的 daily checkin embed，手动删除那条消息
  - 操作：等跨天（或手动调 `daily_embed_update` 任务），观察 log
  - 预期：数据库里这个 embed 被标记为 inactive；不会因为 fetch_message NotFound 崩掉
  - 收窄类型：`(discord.NotFound, discord.Forbidden, discord.HTTPException)`

- [x] 🟡 **bot 重启后 embed views 恢复（消息已删场景）**
  - 前置：同上，手动删掉一条活跃 checkin embed 消息
  - 操作：重启 bot
  - 预期：该条 embed 被 deactivate，不报错；其他正常 embed 恢复正常

- x] 🟢 **checkin history 文件清理**
  - 操作：`/checkin_history`（或你们的 checkin 历史命令）
  - 预期：文件正常下发；后续 `/tmp/` 清理不抛错

- [x] 🟢 **checkin embed 更新失败的兜底 deactivate**
  - 场景：checkin 后触发 `update_checkin_embeds_after_checkin`，其中一条 embed 消息出错
  - 预期：错误被 `logging.exception(...)` 记录（不再是静默 `pass`）；其他 embed 仍然更新

### 1.5 `tickets_new_cog`（12 处，大部分是 DM 失败 fallback）

> 触发 DM 失败最简单的方式：用**关闭了 DM 的测试账号**（设置 → 隐私 → 关 "允许服务器成员向我发私信"）

- [ ] 🟡 **接受 ticket 时 DM creator 失败**
  - 前置：creator 账号关闭 DM
  - 操作：管理员点击 "Accept" 按钮
  - 预期：Accept 成功，thread 状态正确更新；只是 DM 送不出去，不影响主流程

- [ ] 🟡 **Add user 到 ticket 时 DM 失败**
  - 前置：被加的用户关闭 DM
  - 操作：`/tickets_add_user` 或 modal 加人
  - 预期：加人成功；DM 失败静默

- [ ] 🟡 **Close ticket 时 DM creator 失败**
  - 前置：creator 关闭 DM
  - 操作：关 ticket
  - 预期：关闭成功 + thread 归档；DM 失败静默

- [ ] 🟡 **Close ticket 时交互响应失败兜底**
  - 场景：关 ticket 过程中异常，followup + response 都失败
  - 难以手动触发；靠代码 review 验证即可
  - 预期：不至于崩链

- [ ] 🟡 **创建 ticket 时发 DM 给创建者失败**
  - 前置：创建者关 DM
  - 操作：点 ticket 创建按钮
  - 预期：ticket 创建成功；DM 失败静默

- [ ] 🟡 **创建 ticket 失败的兜底响应链**
  - 场景：`ticket_thread_create_error` 的 followup/response 都失败。和上面 Close 同理，代码 review 验证

- [ ] 🟢 **`_validate_channel_permissions` 的异常 log**
  - 场景：Bot 权限检查抛异常（罕见）
  - 预期：返回 False，日志里有 `_validate_channel_permissions failed` traceback（之前是**静默** return False）

- [ ] 🟡 **accept command 的 DM 失败**
  - 前置：creator 关 DM
  - 操作：在 thread 里 `/tickets_accept`
  - 预期：accept 成功，DM 失败静默

- [ ] 🟡 **close command 的 DM 失败**
  - 前置：creator 关 DM
  - 操作：`/tickets_close reason:xxx`
  - 预期：关闭成功，DM 失败静默

- [ ] 🟢 **`/tickets_refresh_buttons` 进度刷新失败**
  - 场景：正在刷新大量 ticket，edit_original_response 被 Discord 限流或过期
  - 预期：progress 显示停滞但主循环继续跑完；失败被静默收窄为 `discord.HTTPException`

---

## 2. P0-1 giveaway 抽 db

> **commit**：`git log --grep='(P0-1)'`
> 改动最重、最容易出 regression。**重点测**。

### 2.1 创建与参与

- [x] 🔴 **`/ga_create` 命令成功弹出 Modal**
  - 操作：在合法频道跑 `/ga_create reaction_req:0 message_req:0 timespent_req:0`
  - 预期：Modal 弹出；填入 `1d` duration、`1` winner、`测试奖品` prizes 等

- [x] 🔴 **Modal 提交后正确入库 + 发 embed**
  - 操作：在 Modal 里填完提交
  - 预期：
    - giveaway channel 出现包含"参加"按钮的 embed
    - 数据库 `giveaway` 表新增一条记录
    - （可选验证）SQLite 直接 `SELECT * FROM giveaway ORDER BY rowid DESC LIMIT 1` 看字段完整

- [x] 🔴 **用户点击"参加"按钮**
  - 操作：另一个账号点参加
  - 预期：
    - ephemeral 消息"已加入"
    - embed 里 participants 数 +1
    - `participant_ids` 字段追加该 user_id

- [x] 🔴 **重复参加同一 giveaway**
  - 操作：同一账号再点参加
  - 预期：显示"已加入"消息 + 退出按钮

- [x] 🔴 **用户点击"退出"按钮**
  - 操作：已参加的账号点退出
  - 预期：
    - ephemeral 消息"已退出"
    - embed participants 数 -1
    - `participant_ids` 字段移除该 user_id

- [ ] 🟡 **有门槛的 giveaway**
  - 操作：`/ga_create reaction_req:5 message_req:100 timespent_req:60`
  - 前置：用一个 achievements 记录都不够的账号去参加
  - 预期：参加失败，显示"你不满足条件"类提示（来自 `check_participant_eligibility`）

- [ ] 🟡 **achievements 表没有用户记录的场景**
  - 前置：全新账号从未互动过
  - 操作：该账号参加有门槛的 giveaway
  - 预期：ephemeral 显示 `User {id} does not exist in the achievements table`

### 2.2 管理命令

- [ ] 🔴 **`/check_giveaway` 列出所有 giveaway**
  - 操作：`/check_giveaway`
  - 预期：返回一个 txt 文件包含所有 giveaway 记录

- [ ] 🔴 **`/ga_cancel <id>`**
  - 操作：取消一个未结束的 giveaway
  - 预期：
    - embed 标题加上"【已取消】"前缀，变红色
    - 按钮全 disable
    - `is_end = 1`

- [ ] 🔴 **`/ga_end <id>` 提前结束**
  - 前置：有至少 1 个参与者的进行中 giveaway
  - 操作：`/ga_end <id>`
  - 预期：
    - 立刻开奖
    - embed 标题加"【提前结束】"，winners 字段显示
    - 中奖者收到 DM（若 DM 开着）
    - 中奖者的 `achievements.giveaway_count` +1

- [ ] 🟡 **`/ga_end` 无参与者的 giveaway**
  - 操作：对空 giveaway `/ga_end`
  - 预期：winners 显示"无"或配置里的 `giveaway_embed_no_winner` 文本；不崩

- [ ] 🔴 **`/ga_time_extend <id> <minutes>`**
  - 操作：给一个进行中 giveaway 延长 30 分钟
  - 预期：
    - embed 的 timeend 字段更新
    - 标题加"【已延长】"label
    - DB 中 `duration` 字段 +30

- [ ] 🔴 **`/ga_participant <id>`**
  - 操作：查看某 giveaway 的参与者列表
  - 预期：pagination view 列出所有 participant_ids，支持翻页

- [x] 🔴 **`/ga_description <id> <new_description>` ← P0-1 顺手修了 commit 缺失 bug**
  - 操作：修改一个进行中 giveaway 的描述
  - 预期：
    - **重启 bot 后再 `/check_giveaway`，新 description 仍在** ← 这是关键
    - embed 的 Description 字段立即更新
  - **改前行为**（反证）：原代码缺 `db.commit()`，重启后 description 会回到旧值（本轮 P0-1 修好）

- [ ] 🟡 **`/ga_sendtowinner`**
  - 前置：一个已结束有 winner 的 giveaway
  - 操作：`/ga_sendtowinner <id> <message>`
  - 预期：所有 winner 收到 DM；如果有 winner 关了 DM，响应里列出 failed_to_send

### 2.3 自动开奖与定时循环

- [x] 🔴 **30 秒检查循环自动开奖**
  - 操作：创建一个 duration=1（1 分钟）的 giveaway，加 1-2 个参与者，等 1 分钟以上
  - 预期：
    - 到期后最多 30 秒内，embed 标题加 "【已结束】" label 变红
    - winner 字段填充
    - 参与者（即 winner）的 `achievements.giveaway_count` +1（lifetime + 当月 monthly）
    - giveaway_views 表里这条记录被清掉

- [ ] 🟡 **消息被删后自动开奖**
  - 前置：创建一个短 duration giveaway，手动删掉那条消息
  - 操作：等到期
  - 预期：channel 收到一条"giveaway 已删除"的 embed；DB 标记 is_end=1

### 2.4 重启恢复

- [ ] 🔴 **重启后未结束的 giveaway 按钮仍可点**
  - 前置：有 1 个进行中的 giveaway
  - 操作：重启 bot
  - 预期：
    - 启动日志无 error
    - 到 giveaway 频道，点参加按钮仍然 work
    - `load_giveaways()` 把 view 重新附加到 message 上

---

## 3. P0-2 privateroom 改动

> **commit**：`git log --grep='(P0-2)'`
> 仅影响 `get_last_month_voice_hours`，调用链：私房**购买**/**续费**时的折扣计算。

- [x] 🔴 **私房购买时的折扣计算（有语音时长记录）**
  - 前置：一个测试账号在 `monthly_achievements` 表有**上个月**的 `time_spent` 记录（可以手动 INSERT 模拟）
  - 操作：该账号触发私房购买流程
  - 预期：折扣 embed 里的 `actual_hours` 显示为该账号上月语音小时数（`time_spent` 秒数 / 3600）

- [x] 🔴 **私房购买时（无语音时长记录）**
  - 前置：全新账号无 `monthly_achievements` 记录
  - 操作：私房购买流程
  - 预期：`actual_hours = 0`，走最低折扣档；不报错

- [ ] 🟡 **私房续费时的折扣计算**
  - 前置：有一个活跃私房的账号
  - 操作：触发续费流程
  - 预期：和购买同样逻辑 —— 能正确读到上月语音时长

- [ ] 🟢 **上月跨年（1 月时读取去年 12 月）**
  - 难以测，靠代码 review：`get_last_month_voice_hours` 里 `if now.month == 1: last_month = 12; last_year = now.year - 1` 仍然正确

---

## 4. P0-3a check_status 改动

> **commit**：`git log --grep='(P0-3a)'`
> 包含建表竞态修复。

- [x] 🔴 **冷启动无 `no such table: status` 错误**
  - 操作：删除测试 DB 的 `status` 表（或用全新 DB）后重启 bot
  - 预期：
    - 启动日志**无** `no such table: status`
    - 10 分钟后后台任务首次执行时，`status` 表已存在且能写入
  - 意义：验证建表从 `on_ready` 迁到 `cog_load` 后竞态消除

- [x] 🔴 **后台 10 分钟语音状态采样**
  - 操作：等一整 10 分钟周期（或手动触发任务，如果有 debug 入口），或直接 `SELECT * FROM status ORDER BY timestamp DESC LIMIT 5`
  - 预期：有新行、timestamp 正确、people 和 channels 数值合理

- [x] 🔴 **`/print_voice_status date:YYYY-MM-DD` 按日视图**
  - 前置：该日期至少有几条 status 采样
  - 操作：`/print_voice_status date:2026-04-23`（今天日期）
  - 预期：返回两张折线图（people / rooms），有峰值标注

- [ ] 🟡 **`/print_voice_status date:YYYY-MM` 按月视图**
  - 前置：本月有多日数据
  - 操作：`/print_voice_status date:2026-04`
  - 预期：按天聚合的峰值图

- [ ] 🟡 **`/print_voice_status date:YYYY` 按年视图**
  - 前置：本年有多月数据
  - 操作：`/print_voice_status date:2026`
  - 预期：按月聚合的柱状图

- [ ] 🟡 **`/print_voice_status` 格式非法**
  - 操作：`/print_voice_status date:abc`
  - 预期：显示"日期格式不支持..."提示；不崩

- [ ] 🟢 **`/print_voice_status` 无数据日期**
  - 操作：`/print_voice_status date:2020-01-01`
  - 预期："No data found" 提示

---

## 5. P0-3b notebook 改动（P3-8 已移除）

NotebookCog 已在 P3-8 从 runtime 移除，不再作为测试服全量验证项目。历史数据表 `event_logs` / `admins` 默认保留，不在本清单中测试清表或迁移。

---

## 6. P0-3c create_invitation 改动

> **commit**：`git log --grep='(P0-3c)'`
> 仅改了签名读取路径，走 `RoleDatabaseManager.get_user_signature`。**签名三态**是核心测试点。

### 6.1 签名三态

> 要有三个测试账号：A（无签名）、B（有签名且启用）、C（有签名但 `is_disabled=1`）。
> 可直接 SQL 设置：`INSERT INTO user_signatures (user_id, signature, is_disabled) VALUES (B_id, '我是B的签名', 0), (C_id, 'C被禁用的', 1);`

- [ ] 🔴 **账号 A（无签名）触发邀请**
  - 操作：账号 A 进语音，在文字频道发"一起打游戏"之类关键词（或跑 `/invitation`）
  - 预期：邀请 embed **不含**签名字段

- [ ] 🔴 **账号 B（有签名，enabled）触发邀请**
  - 操作：账号 B 同上
  - 预期：邀请 embed **含**签名字段，值为 B 的 signature 字符串

- [ ] 🔴 **账号 C（有签名，is_disabled=1）触发邀请**
  - 操作：账号 C 同上
  - 预期：邀请 embed **不含**签名字段（即使 DB 里有 signature 内容，`is_disabled=True` 就当作无签名）

### 6.2 邀请基础流程

- [ ] 🔴 **关键词自动路由（`on_message`）**
  - 操作：在测试频道发 "组队" 或配置里 trigger 关键词
  - 预期：bot 自动 reply 一个包含"加入房间"按钮的 embed
  - 注：发送者必须在语音频道，否则走其他路径

- [ ] 🔴 **`/invitation` 命令**
  - 操作：在语音频道里的账号跑 `/invitation title:"测试组队"`
  - 预期：发出带 embed 的组队消息

- [ ] 🟡 **"房间满员"按钮**
  - 操作：邀请消息发出后，按钮是 `roomfull_button_label`；由邀请发起者点击
  - 预期：
    - embed 标题改为 `{roomfull_title} ~~原标题~~`
    - 变红色
    - 按钮全移除（`view=None`）
    - 从 teamup display 移除

- [ ] 🟢 **非发起者点"房间满员"**
  - 操作：另一个账号点同一个按钮
  - 预期：显示 `interaction_target_error_message`，embed 不变

---

## 7. P0-3d voice_channel 改动

> **commit**：`git log --grep='(P0-3d)'`
> 12 处 SQL 迁移 + schema migration 保留 + View 加 db 参数。**功能最重、测试点最多**。

### 7.1 建房基础流程

- [x] 🔴 **加入 trigger 频道自动建房**
  - 前置：`config_voicechannel.json` 的 `channel_configs` 里有一个 trigger channel（type: "public" 或 "private"）
  - 操作：加入该 trigger 频道
  - 预期：
    - 自动创建一个新的 voice channel（名字是 `{name_prefix}-{display_name}`）
    - 用户被自动移入
    - 该频道的文字聊天里出现**控制面板**（4 个按钮：解锁 / 上锁 / 满员 / 声音板）
    - `temp_channels` 表新增一行：`channel_id`, `creator_id`, `is_soundboard_enabled=1`, `current_room_type` 等于配置的 type

- [x] 🔴 **private 类型房默认是 private**
  - 前置：trigger 频道配置 `type: "private"`
  - 操作：加入
  - 预期：`current_room_type='private'`，其他用户无法加入（`@everyone` 无 connect 权限）

### 7.2 控制面板按钮

- [x] 🔴 **"解锁"按钮 → 设为 public**
  - 操作：房主点解锁
  - 预期：
    - `@everyone` 获得 connect 权限
    - DB `current_room_type` 更新为 'public'
    - 面板 embed 刷新
    - ephemeral 消息

- [x] 🔴 **"上锁"按钮 → 设为 private**
  - 操作：房主点上锁
  - 预期：
    - `@everyone` 失去 connect 权限
    - DB `current_room_type` 更新为 'private'
    - 面板 embed 刷新

- [x] 🔴 **"满员"按钮**
  - 操作：房主点满员
  - 预期：embed 更新为满员样式（标题变红、`update_message_to_full`）；按钮被移除

- [x] 🔴 **"声音板"按钮（开）→ 关**
  - 操作：房主点一次切换
  - 预期：
    - 相应权限变化（`use_soundboard` / `use_external_sounds`）
    - DB `is_soundboard_enabled` 切换 0/1
    - 面板 embed 刷新

- [ ] 🟡 **非房主点任意按钮**
  - 操作：其他账号进入该房后点控制面板按钮
  - 预期：显示 `not_in_voice` 或权限错误提示（取决于具体按钮；lock 按钮只允许房主还是所有人在房内 —— 按实际行为验证）

- [ ] 🟡 **用户不在该语音频道时点按钮**
  - 操作：离开频道后按钮仍可见，点一下
  - 预期：显示 `not_in_voice`

### 7.3 `/list_voice_channels` / `/add_voice_channel` / `/remove_voice_channel`

> 这三个是"自动建房 trigger"的增删改，动的是 `channel_configs` JSON（**P2-5 判定要迁 DB**，本轮未做）。只需回归性验证没坏。

- [ ] 🟡 **`/list_voice_channels`**
  - 操作：执行
  - 预期：显示当前所有 trigger channel 配置

- [ ] 🟡 **`/add_voice_channel`**
  - 操作：添加一个新的 trigger
  - 预期：成功、配置写入 `config_voicechannel.json`、后续加入该频道能建房

- [ ] 🟡 **`/remove_voice_channel`**
  - 操作：移除一个 trigger
  - 预期：成功、配置更新

### 7.4 `/check_temp_channel_records`

- [x] 🔴 **查看临时频道记录**
  - 前置：至少有 1 个活跃的 temp channel
  - 操作：执行
  - 预期：分页显示所有 `temp_channels` 表记录（新的在前）

### 7.5 清理路径

- [x] 🔴 **所有用户离开后频道自动清理**
  - 操作：建房后让所有人离开
  - 预期：
    - `cleanup_channel` 触发
    - Discord 频道被删除
    - 如果 category 空了也被删
    - （DB 记录**保留**，由下次 cleanup_task 清）

- [x] 🔴 **小时级 cleanup_task 清理孤儿 DB 记录**
  - 前置：DB 有一条 `temp_channels` 记录但 Discord 频道已不存在（手动模拟：SQL `INSERT INTO temp_channels (channel_id, creator_id) VALUES (999999, 123)`）
  - 操作：等 1 小时或手动触发 `cleanup_task`
  - 预期：该孤儿行被 `DELETE`

### 7.6 重启恢复（最关键）

- [x] 🔴 **重启后控制面板 View 恢复**
  - 前置：有 1-2 个活跃的 temp channel + 控制面板
  - 操作：重启 bot
  - 预期：
    - 启动日志里 `restore_control_panels` 成功报告 `X success, Y failed, Z cleaned`
    - 到房间的文字聊天点任意按钮，仍然 work（说明 new `RoomControlPanelView(..., self.db, ...)` 被正确重新附加）
    - **特别验证**：点上锁/解锁/声音板，DB 的 `current_room_type` / `is_soundboard_enabled` 真的更新 ← 这是 P0-3d 改 db 参数传递的核心测试点

- [ ] 🟡 **重启后某 temp channel 已不存在的清理**
  - 前置：活跃 temp channel 被手动删掉，但 DB 记录还在；重启前控制面板消息还在原位
  - 操作：重启 bot
  - 预期：
    - `on_ready` 里 `fetch_all_channel_ids()` 拿到列表
    - `bot.get_channel(id)` 返回 None → `delete_temp_channel` 清掉 DB 记录
    - 不影响其他正常 temp channel

- [ ] 🟡 **重启后控制面板消息已被删**
  - 前置：DB 有 `control_panel_message_id` 但那条消息被手动删除
  - 操作：重启
  - 预期：
    - `restore_control_panels` 里 `fetch_message` 抛 NotFound
    - 调 `clear_control_panel_data(channel_id)` → DB 里 `control_panel_message_id` 置 NULL
    - 计入 `cleaned_count`
    - 下次该 channel 还在、用户还在，新进的人不会自动出面板，但房间本身还活着（按 DB 行为）

### 7.7 schema migration

- [ ] 🟡 **老部署升级（缺列场景）**
  - 前置：用一个只有**旧 schema**（没 `control_panel_message_id` / `control_panel_channel_id` / `is_soundboard_enabled` / `current_room_type` 列）的 `bot.db` 副本启动
  - 操作：冷启动
  - 预期：
    - 启动日志有 `[MIGRATION] Adding column <name> to temp_channels` ×4
    - 列补齐后，建房/面板功能全部正常

---

## 8. 回归性检查（未改动的核心路径，快速 smoke）

> 即使没改，也可能因 import 链破坏而连带出问题。挑 5 个最常用功能快速跑一遍：

- [x] 🔴 **签到** `/checkin`（或按钮）
- [x] 🔴 **查询余额** `/balance` / 签到查询按钮
- [x] 🔴 **成就查询** `/achievements` / ranking
- [!] 🔴 **角色领取**（星座 / MBTI / 性别其中一个）
- [x] 🔴 **工单创建**（点按钮创建一个测试工单，然后关掉）

---

## 9. 日志检查（全过程）

整轮测试跑完后看一次日志：

- [ ] 🔴 `grep -iE "no such table|no such column" ./logs/main.log` **为空**
- [ ] 🔴 `grep -iE "AttributeError" ./logs/main.log` **为空**（特别是 `save_config` 之类的历史 bug）
- [ ] 🟡 `grep -iE "Traceback" ./logs/main.log | wc -l` **比对照期基本持平或更少**
- [ ] 🟡 `grep "bare except" ./logs/main.log` 当然是空（不太会打这个字样，主要确认没出乱七八糟的 `NoneType` / `KeyError` 被静默吞的现在不会被吞的情况）
- [ ] 🟢 **P3-7 用户 / 频道 / 角色日志格式抽查**
  - 操作：触发一次角色领取、一次临时语音房恢复或清理、一次工单创建 / 管理员通知路径后，grep 最近日志
  - 预期：涉及用户、频道 / thread、角色的新增日志使用 `name (id)`；只有 raw id 且无缓存对象时显示 `unknown (id)`
  - 意义：验证 `fmt_user` / `fmt_channel` / `fmt_role` 已接入首批高价值 callsite，排障时不用只靠裸 ID

---

## 结果登记

测试完成后在 `REFACTORING_PROGRESS.md` 的 P0 系列收官小结里补一条：

```
**功能层验证**：2026-XX-XX 由 MrZoyo 在测试服完整跑了 REFACTORING_TEST_CHECKLIST.md，通过 / 问题：...
```

如果有红色项目 `[!]` 不通过，不要直接进 P1 —— 先把问题告诉 Claude，定位回溯哪个 commit 引入的，修完再进下一阶段。
