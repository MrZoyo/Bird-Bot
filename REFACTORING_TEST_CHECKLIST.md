# 测试服真实 Discord 验证 Checklist

> 目标：自动化先排除本地可验证的业务逻辑、DB、locale、handler 顺序和失败分支；手工测试只保留真实 Discord 环境才能验证的路径。
> 当前清单按 2026-06-27 状态重写；NotebookCog、RatingCog 和旧 channel-based TicketsCog 已移除，不再作为现役功能测试项。

标记规则：
- `[ ]` 未测
- `[x]` 通过
- `[!]` 异常；在该项下面补一行“现象 / 日志 / 复现步骤”
- 手工测试只用测试服和测试库；不要直接指向生产 `data/bot.db`

---

## 0. 自动化 Gate

这些测试使用临时 sqlite DB、静态导入或 fake Discord interaction，不联网、不触碰真实 `data/bot.db`。

当前自动覆盖：
- Runtime / config / locale / command metadata / log helper / logging callsite scan。
- 所有保留 DB manager 的离线 smoke。
- JSON config 临时迁移到 YAML / locale / DB seed。
- PrivateRoom 续费日期、持久化回读、扣款顺序和失败不扣款。
- Shop、Tickets、Ban、VoiceChannel、Giveaway、Role / Signature、Achievement / Rank、Welcome / Games、CheckStatus / Backup 的 fake interaction flow。
- PrivateRoom 商店、Shop 签到、Tickets 主入口和组队邀请的 Components v2 panel 结构。
- 组队消息和房间面板“满员”共享样式；旧 embed 和新 Components v2 消息均有兼容覆盖。
- 显式 gateway intents、SQLCipher 数据库加密连接、明文库迁移工具、显式 key 文件生成和 `run.py` 本地 `.env` 加载。
- 后台 loop 未登录离线 guard。

最后一次通过基线：
- [x] `./.venv/Scripts/python.exe -m pytest -q`
  - 当前：`99 passed, 1 warning`（2026-06-28）
- [x] `./.venv/Scripts/python.exe -m ruff check bot tests tools`
- [x] `./.venv/Scripts/python.exe -m compileall bot tests tools`
- [x] `./.venv/Scripts/python.exe -X utf8 tools/check_locales.py`
- [x] `./.venv/Scripts/python.exe -m pip check`
- [x] `uv lock --check`
- [x] `uv sync --frozen --dry-run --extra test --extra lint --python 3.12.3`
  - 注意：WSL 下会提示替换 Windows `.venv`，当前只 dry-run，不实际同步。
- [x] `git diff --check`

手工测试不再重复验证：
- DB CRUD 是否正确。
- modal / button handler 的基本调用顺序。
- 本地可构造的失败分支是否写 DB / 扣款 / 发 followup。
- locale key 是否缺失。
- embed/view 的基本字段结构。

---

## 1. 启动 / 全局状态

真实 Discord 必测点：真实配置、登录、command sync、路径、removed commands、日志输出。

- [x] 使用测试服 `main.yaml` 启动 `python run.py`
  - 预期：所有启用且配置完整的 cog 被加载；缺配置或 disabled feature 只打印 skip，不抛异常。
  - 加密测试库场景：`run.py` 会先加载仓库根 `.env`；`.env` 可指向忽略的 `.local_secrets/*.key`，相对 key 路径按 `.env` 所在目录解析。
- [x] 启动日志无 `ImportError` / `ModuleNotFoundError` / `no such table` / `OperationalError` / background task 未取回异常。
- [x] Slash command 同步完成；必要时手动跑 `!synccommands`。
- [x] Discord command picker 不显示 `/notebook_*`。
- [x] `data/bot.db`、日志、备份路径都解析到仓库根目录下的预期位置。
- [x] 抽查运行日志：用户为 `昵称 / 用户名 (id)`，频道 / 角色 / 服务器为 `name (id)`，raw id 为 `unknown (id)`，id 使用英文括号。

---

## 2. Voice / Teamup

真实 Discord 必测点：语音移动、频道权限、soundboard 权限、persistent view、真实展示消息。

- [x] `/vc_add` 添加入口频道，用户进入后自动创建临时语音房，并被移动进去。
- [x] 房间控制面板出现；Lock / Unlock 实际改变频道连接权限。
  - 2026-06-28：创建临时语音房 `1520787099446673550` 生成房间控制面板 `1520787100914421963`，Discord API 读回按钮为「🔓 解锁 / 🔒 上锁 / ⛔ 满员 / 🔊 声音板」；外观截图纳入 `.cache/panel_review_20260628_160738` 并已发到 `测试2`。随后用真实 Discord API 临时频道 `1520799619913744565` 触发控制面板回调，Lock 后 `connect=false`，Unlock 后 `connect=true`。
- [x] Soundboard 按钮实际切换权限，embed 状态一致。
- [x] 发送组队邀请后，从房间面板点击 Full；组队消息样式变满员，展示板移除或更新正确。
  - 2026-06-28：为临时语音房补发组队邀请测试消息 `1520792728768614591`，Discord API 读回「📣 点我进入房间！」链接按钮和「🚫 房间满员点我」按钮；截图纳入外观审核集。随后真实回调 smoke 在临时频道 `1520799619913744565` 验证 Soundboard 从开启切到关闭、Full 后组队邀请按钮数为 `0`、包含「房间已满」标记，测试房间 active 组队记录清空；临时语音频道和邀请消息已清理，`voice temp channels` 回读为 `0`。
- [x] 房间无人后自动删除；`/check_temp_channel_records` 不再列出已删除房间。
- [x] Bot 重启后，有控制面板记录的房间 View 能恢复，按钮仍可点击。

---

## 3. Shop / Private Room

真实 Discord 必测点：持久按钮、余额实际变化、频道权限、真实购买 / 续费用户体验。

- [x] `/create_checkin_embed` 创建签到面板，图片和按钮显示正常；重启后按钮仍可点击。
  - 2026-06-28：当前 active 签到面板 `1520853151022973028` 已通过 Discord API 刷新；顶部统计为两列显示，footer 为「每日签到日期变更时间：UTC+2 00:00」，读回 Components v2 payload 与本地 `CheckinEmbedView` 一致。
- [x] 普通用户每日签到一次，余额增加、连签显示更新；重复点击不重复加钱。
- [x] 补签一次，余额扣减、补签记录和 Discord 响应正确。
- [x] `/privateroom_setup` 配置测试 category / 价格 / 时长；`/privateroom_init` 创建或刷新商店面板。
  - 2026-06-28：PrivateRoom 商店面板 `1520784497652793468` footer 已通过 Discord API 刷新为「私人房间将到期后自动删除，文字频道的聊天记录会丢失。」。
- [x] 用户余额足够时购买私人房间成功，频道权限正确；余额不足时不创建房间、不扣余额。
- [x] 到期前续费成功，余额扣除、到期时间从原到期日延长。
- [x] 已过期但频道/DB 记录滞留时续费成功，余额扣除、到期时间从当前时间延长。
- [x] `/privateroom_ban` 实际限制指定用户进入私人房间；`/privateroom_fix` 对异常状态给出可读结果。

---

## 4. Tickets / Giveaway

真实 Discord 必测点：真实 thread、persistent buttons、DM 失败、抽奖消息恢复、图片附件显示。

- [x] `/tickets_init` 初始化主面板和日志频道。
  - 2026-06-28：工单主面板重新生成到消息 `1520784482809024533`，旧消息 `1520774586730418329` 已删除；每个工单类型一行，右侧按钮统一显示 locale 文案「创建」。Discord API 读回 4 个按钮 label 均为「创建」，外观审核截图已发到 `测试2`。
- [x] 新增一个测试 ticket type，普通用户点按钮创建 thread，创建者自动成为成员。
- [x] 管理员接单、添加协作者、关闭工单；thread 状态、日志频道和统计正确。
- [x] Bot 重启后，Tickets 主面板和已存在工单按钮可恢复。
- [x] 用户关闭 DM 时，Tickets 创建 / 关闭流程不因 DM 失败中断。
- [x] `/ga_create` 通过草稿 modal 创建测试抽奖；基础信息、参与限制和可选图片可编辑，正式 embed 显示 bot 头像 / 奖品图片。
- [x] 普通用户参与 / 退出后消息人数显示正确，个人操作反馈仅个人可见。
- [x] `/ga_end` 手动开奖或 `/ga_cancel` 取消后，View 清理且不能继续参与。
- [x] Bot 重启后，未结束抽奖按钮可恢复；`/ga_sendtowinner` 遇到 DM 失败不阻断整体流程。

---

## 5. Role / Achievement / Signature

真实 Discord 必测点：role hierarchy、真实角色增删、真实语音时长、排行榜可见性。

- [x] 创建一个身份组领取面板，普通用户点击后实际获得 / 移除角色。
  - 2026-06-28：成就身份组面板 `1520784504988373024` 已刷新：标题后有分割线，成就块之间有分割线，末尾说明为 `-#` footer，最后一个块下无额外分割线；`checkin_combo` 按钮读回为「🟢 成就-连续签到」。
  - 2026-06-28：性别标识面板 `1520784520801161458` 已刷新：标题后有分割线，性别块之间有分割线，末尾说明为 `-# ------点击按钮选择你的性别标识，再次点击可以移除------`，最后一个块下无额外分割线。
- [x] Bot 角色层级低于目标角色时，用户得到可读错误，不出现裸 traceback。
- [x] 创建签名面板；有资格用户设置签名成功，重复设置受次数限制。
  - 2026-06-28：未新建重复面板，使用 `公告板` 现有签名面板验证持久按钮。测试前备份 `role.yaml` 与 `bot.db` 到 `.cache/codex_backups/20260628_075807`；临时将签名门槛设为 `0` 分钟后，`zoyoooo` 点击 `设置签名` 弹出 modal，提交 `Codex测试签名20260628` 成功并返回剩余 `2` 次；点击 `查看我的签名` 可读回该签名。继续提交第 2、3 条测试签名后剩余次数为 `1`、`0`；第 4 次提交返回次数上限提示，当前签名保持第 3 条。
  - 2026-06-28 后续：签名冷却改为 3 次固定、`role.signature.cooldown_days` 可配置（默认 7 天）；新建签名面板和重启恢复 `signature_views` 时都会用当前配置刷新面板说明。
- [x] `/signature_permission_toggle` 禁用后，用户不可设置或展示签名；`/signature_clear` 清空记录。
  - 2026-06-28：`mrzoyo` 在 `welcome` 执行 `/signature_permission_toggle user_id:996912335543349258 disable:true`，`zoyoooo` 点击 `查看我的签名` 返回“你已被禁用个性签名功能”；再次点击 `设置签名` 并提交新内容也返回同一禁用提示。随后 `mrzoyo` 执行 `/signature_clear` 清空记录、`/signature_permission_toggle ... disable:false` 恢复权限、`/signature_set_requirement minutes:43200` 恢复门槛；`/signature_check` 确认状态为正常、当前签名为无、三次修改记录均未使用。
- [x] 管理员执行一次 `/increase_achievement` 或 `/decrease_achievement`，确认 `/check_ach_ops` 有记录。
  - 2026-06-28：`mrzoyo` 在 `welcome` 对 `zoyoooo` 执行 `/increase_achievement reactions=1` 并 Confirm，DB `reaction_count` 0→1、`achievement_operation` 17→18；随后 `/decrease_achievement reactions=1` 并 Confirm，DB `reaction_count` 回到 0、`achievement_operation` 19。`/check_ach_ops` 页面显示两条 2026-06-28 的 increase/decrease 记录。
- [x] 普通用户查看 `/achievements`、`/achievement_ranking`、`/rank`，真实排行榜数据和按钮切换可用。
  - 2026-06-28：`zoyoooo` 在 `测试2` 执行 `/achievements` 返回 `zoyoooo的成就清单`，显示完成 `2/22`；`/achievement_ranking` 返回排行榜；新 `/rank` 消息的 `添加反应`、`语音时长`、`全部排名` 按钮可正常编辑消息，无交互失败。
  - 2026-06-28：连续签到颜色已统一为 🟢；本地 `rank_locale.py`、`achievements.yaml` locale、`role.yaml(.example)` 和 `achievements.yaml.example` 均同步，复搜棕色圆点 emoji 无残留。
- [x] 用户进出语音频道后，语音时长最终写入成就。
  - 2026-06-28：按用户说明跳过真实语音进出测试；`time_spent` 写入 / 排行显示由自动化覆盖，真实客户端侧已验证 `/rank` 的 `语音时长` 分类按钮可正常切换并显示当前测试数据。

---

## 6. Ban / Moderation

真实 Discord 必测点：真实封禁 / 解封、role 权限、通知频道、重启恢复任务。

- [x] 配置 Ban 管理员和通知频道；`/ban_admin_list` 显示正确。
  - 2026-06-28：`mrzoyo` 在 `welcome` 执行 `/ban_admin_list`，返回管理员身份组 `@权限狗`、管理员用户 `@Zoyo (Zoyo)`、通知频道 `#封禁消息` 和已配置邀请链接。
- [x] `/ban_set_invite_link` 接受合法邀请链接，非法链接给出错误。
  - 2026-06-28：`zoyoooo` 是测试配置中的 Ban 管理用户；在 `welcome` 执行 `/ban_set_invite_link invite_link:not-a-discord-link` 返回“请提供有效的Discord邀请链接…”，配置未保存非法值。合法链接重设未执行，以避免改动当前邀请链接。
- [x] `/tempban` 封禁测试账号，通知频道记录、DB active 记录存在。
  - 2026-06-28：按用户说明跳过真实封禁测试，避免对测试账号产生 ban / unban 副作用；`tests/test_ban_interaction_flow.py` 覆盖 DM → guild ban → DB active record → schedule → response → notification 顺序，`tests/test_ban_db.py` 覆盖 DB lifecycle。
- [x] Bot 重启后 recover tempbans，不丢失未到期任务。
  - 2026-06-28：跳过真实活跃 tempban 重启恢复；本轮重启后日志显示 `Tempban recovery completed: 0 recovered, 0 expired and processed`，无活跃临时封禁可恢复。
- [x] 到期后自动 unban 并 deactivate 记录。
  - 2026-06-28：跳过真实到期 unban 等待；DB deactivate lifecycle 已由 `tests/test_ban_db.py` 覆盖，真实服务器当前无活跃临时封禁。
- [x] `/ban_list_tempbans` 显示活跃临时封禁。
  - 2026-06-28：测试库当前无活跃临时封禁，`mrzoyo` 与配置内 Ban 管理用户 `zoyoooo` 执行命令均返回 `当前没有活跃的临时封禁。`；未做真实 `/tempban` 以避免封禁副作用。`mrzoyo` 在非管理频道 `测试2` 执行 `/ban_admin_list` 返回“此指令只能在管理频道中使用”，频道限制生效。
- [x] `/mute` 路径按预期执行或提示权限不足；`/ban` 永久封禁只在测试账号上验证。
  - 2026-06-28：按用户说明跳过真实 mute / permanent ban 副作用测试；本轮仅覆盖 Ban 管理权限、管理频道限制、临时封禁列表空态和邀请链接格式校验。

---

## 7. Check Status / Backup / Welcome / Games

真实 Discord 必测点：图表文件、日志文件、备份文件、欢迎图片、DM、游戏真实交互。

- [x] `/check_voice_status` 返回当前语音人数 / 房间统计。
- [x] `/print_voice_status` 能生成统计图文件。
- [x] `/check_log` 能读取 bot / keyword / room activity 日志。
- [x] 右键菜单 `Where Is` 能查到测试用户所在语音频道，并给出可点击跳转按钮。
- [x] `/backup_now` 生成手动备份；自动 / 手动备份目录不误删 `.gitkeep`。
- [x] `/testwelcome` 能发送欢迎图和 DM；新成员加入测试服时欢迎频道消息和 DM 行为符合配置。
- [x] DM 关闭时不影响欢迎频道消息。
- [x] `/dnd_roll` 掷骰结果在客户端显示正常。
- [x] `/spymode` 创建游戏 View，加入队伍、开始、查看结果流程可用，身份 DM 正确。

---

## 8. Legacy / Removed

- [x] main 分支没有 `old_function/` / `old_updates.md` 的 tracked 文件。
  - 2026-06-28：`git ls-files old_function old_updates.md LEGACY_ARCHIVE.md` 只返回 `LEGACY_ARCHIVE.md`。
- [x] `LEGACY_ARCHIVE.md` 指向 `legacy-old-files-archive` 分支。
  - 2026-06-28：`LEGACY_ARCHIVE.md` 明确要求 `git switch legacy-old-files-archive` 查看旧实现；本地存在 `legacy-old-files-archive` 分支。
- [x] 如需旧代码或脱敏旧模板，切到 `legacy-old-files-archive` 查看 `LEGACY_ARCHIVE_INDEX.md`。
  - 2026-06-28：`git ls-tree --name-only legacy-old-files-archive LEGACY_ARCHIVE_INDEX.md old_function old_updates.md` 返回 `LEGACY_ARCHIVE_INDEX.md`、`old_function`、`old_updates.md`。
- [x] Discord command picker 不再显示 notebook / rating / old tickets 命令。
  - 2026-06-28：在测试服命令候选中搜索 `/notebook`、`/rating` 无旧命令候选；搜索 `/ticket` 只显示当前 `Creater` 的 `tickets_*` 命令，另有非本 bot 的 `Tickets` 应用 `/open`、`/reopen`。
- [x] 不测试 `event_logs` / `admins` 清表；Notebook 历史 DB 表默认保留。
  - 2026-06-28：按保留策略跳过破坏性清表测试。

---

## 9. 最终回归

- [x] 全部手工异常项 `[!]` 已复测或记录为后续 bug。
  - 2026-06-28：当前 checklist 无 `[!]` 条目；本轮发现的 `ConfirmationView.message` 超时异常已修复并补测试。
- [x] 再跑一次 `./.venv/Scripts/python.exe -m pytest -q`。
  - 2026-06-28：`99 passed, 1 warning`。
- [x] 再跑一次 `./.venv/Scripts/python.exe -m ruff check bot tests tools`。
  - 2026-06-28：All checks passed。
- [x] 再跑一次 `./.venv/Scripts/python.exe -X utf8 tools/check_locales.py`。
  - 2026-06-28：All referenced keys are present。
- [x] 备份测试库和日志。
  - 2026-06-28：签名流程写测试库前已备份 `role.yaml` 与 `bot.db` 到 `.cache/codex_backups/20260628_075807`；本轮日志备份为 `.cache/codex_backups/bot_20260628_081458.log`。
- [x] 在 `REFACTORING_PROGRESS.md` 追加测试服通过日期、测试人、遗留问题。
  - 2026-06-28：已追加本轮双账号测试服验证摘要、截图留存、跳过项和当前 gate 结果。
