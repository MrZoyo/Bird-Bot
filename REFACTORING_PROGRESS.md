# 重构进度追踪

> 与 [REFACTORING_PLAN.md](./REFACTORING_PLAN.md) 并行，记录每条 P 任务的完成状态、实施笔记、关键决策。
> **Context 爆掉重开时从这里恢复状态，决定下一步。**

规则：
- 每条 P 任务的 commit message 必须带 `(P0-4)` / `(P0-1)` 等标签，便于 `git log --grep='(P0-4)'` 精确定位。
- 每完成一条就更新本文件（状态改为 ✅ + 写实施笔记），与该任务的源码改动**分两次 commit**（源码一次，progress 更新一次；progress 更新的 commit message 用 `docs: track progress after <task>`）。
- 状态图例：⬜ 未开工 / 🔄 进行中 / ✅ 完成 / ⏸ 暂停 / ❌ 放弃

---

## P0 系列收官小结（2026-04-23）

**成就**：
- `grep -rn "^\s*except:" bot/` 为空（P0-4，21 处裸 except 全收窄）
- `grep -rn "aiosqlite" bot/cogs/` 为空（P0-1/2/3 全部 cog 不再直连 aiosqlite；47+ 处 SQL 全迁到 manager）
- 新增 5 个 manager：`GiveawayDatabaseManager`、`CheckStatusDatabaseManager`、`NotebookDatabaseManager`、`VoiceChannelDatabaseManager`，以及 `PrivateRoomDatabaseManager` 扩展；`RoleDatabaseManager` 在 create_invitation 跨域复用。

**顺手修的 bug（迁移路上发现的）**：
- `giveaway_cog.update_giveaway_description` 缺 `db.commit()`，命令 `/ga_description` 实际不生效 → P0-1 迁 manager 时补上
- `check_status_cog` 的建表竞态（on_ready listener vs `before_loop.wait_until_ready()` 并发） → P0-3a 迁 cog_load 修掉

**共 8 个 commit**（源码 + progress 各一次）：P0-4 / P0-1 / P0-2 / P0-3a / P0-3b / P0-3c / P0-3d + `docs: track progress after ...`

**测试期顺手修的 bug（2026-04-23）**：
- **`fix(role): readable fallback for Discord role hierarchy 403`** — 测试点星座按钮触发 `discord.errors.Forbidden (50013)` 裸 traceback。根因：Discord 的 role hierarchy 约束（Bot top_role 必须严格高于被操作 role；Administrator 不能越过此规则）。4 个 role View 都有同 pattern。
  - 抽出 `bot/utils/role_helpers.py` 的 `safe_member_role_edit()` 统一处理；Forbidden 时 log 具体哪个 role 层级过高 + 给用户可读中文提示。
  - 运维侧解法：把 Bot role 拖到所有功能性 role 之上（已由用户完成）。
  - 代码侧兜底属锦上添花，为将来再次出现层级乱序提供快速诊断路径。
  - 不是 P0 系列引入的 regression，是原代码未兜底的显性暴露。
  - Commit grep: `git log --grep='hierarchy'`

**未做的收尾工作（显性未做，供后续接手）**：
- 功能层所有路径**未测试服验证**（代码改动面非常大，建议用户起测试服跑一轮 —— 尤其是 giveaway 的完整流程、voice_channel 的建房/锁/解/声音板/重启恢复）
- `voice_channel_cog` 里 `save_channel_configs` 还在写 JSON 文件，未迁 DB —— 这是 P2-5 决策范围（判定 `channel_configs` 迁 DB），不属 P0
- 建表位置："全部迁 `cog_load`" 只是 P0-3 的规模；giveaway 的 `initialize_database()` 目前在 `on_ready` 调（原代码就这样）；`cog_load` vs `on_ready` 的全面对齐是 P1-2 范围
- 所有 cog 的 `start()` 后台任务仍在 `__init__`（P1-2 治理）
- ruff E722 规则未加（P3-5）—— 裸 except 治理成果暂没机器锁死

---

## 总进度速览

| 阶段 | 任务 | 状态 | 备注 |
|---|---|---|---|
| P0 | P0-4 裸 except 治理 | ✅ | 21 处清零 |
| P0 | P0-1 giveaway 抽 db | ✅ | 21 处清零 + 修 update_giveaway_description commit bug |
| P0 | P0-2 privateroom 直连规范化 | ✅ | 1 处清零 |
| P0 | P0-3a check_status 补 db manager（含建表竞态修复） | ✅ | 3 处清零 + 竞态修复 |
| P0 | P0-3b notebook 补 db manager | ✅ | 7 处清零 |
| P0 | P0-3c create_invitation 补 db manager | ✅ | 1 处清零（复用 RoleDatabaseManager） |
| P0 | P0-3d voice_channel 补 db manager | ✅ | 12 处清零 + 顺手删 tickets_new_cog 死 import |
| **P0 整体** | **P0 系列全部完成** | ✅ | `grep -rn "aiosqlite" bot/cogs/` 整个清零 |
| P1 | P1-5 日志 rotation | ✅ | 3 个 logger 统一 TimedRotatingFileHandler |
| P1 | P1-2 ban_cog 迁 cog_load | ✅ | 建表 → cog_load；recover_tempbans → on_ready 首次 |
| P1 | P1-1 命令同步逻辑 | ✅ | sync 迁 setup_hook；on_ready 只留 presence/日志 |
| P1+P2 | 配置系统 2.0（P1-6 + P1-4 + P2-3 + P2-5） | ⬜ | 绑定一次冲刺做 |
| P1 | P1-7 Slash 元数据本地化 | ⬜ | 与配置 2.0 并行/紧接 |
| P1 | P1-3 大 cog 拆包 | ⬜ | 配置 2.0 之后 |
| P2 | P2-1 数据库连接复用 | ⬜ | 需 close() 生命周期前置 |
| P2 | P2-2 Schema 迁移机制 | ⬜ | |
| P3 | P3-1 依赖管理统一 | ⬜ | |
| P3 | P3-2 硬编码路径梳理 | ⬜ | |
| P3 | P3-3 清理空 bot.db | ⬜ | |
| P3 | P3-4 补自动化测试 | ⬜ | |
| P3 | P3-5 引入 ruff / linter | ⬜ | 锁 E722 保 P0-4 |
| P3 | P3-6 归档目录清理规划 | ⬜ | |

---

## P0-4 ✅ 裸 except 治理（2026-04-22）

**Commit grep**: `git log --grep='(P0-4)'`

**验收**：`grep -rn "^\s*except:" bot/` = 清零（21 → 0）；全部改过文件 `python3 -m py_compile` 通过。

**动过的文件 + 策略**：

| 文件 | 处数 | 收窄策略 |
|---|---|---|
| `bot/utils/privateroom_db.py` | 1 | `aiosqlite.OperationalError`（ALTER TABLE 重复列名） |
| `bot/cogs/voice_channel_cog.py` | 1 | `(discord.NotFound, discord.HTTPException)`（`fetch_user`） |
| `bot/cogs/ban_cog.py` | 2 | `(discord.NotFound, discord.HTTPException)`（`fetch_user` 列表兜底） |
| `bot/cogs/shop_cog.py` | 5 | `OSError`×2（`os.unlink`）；`(discord.NotFound, discord.Forbidden, discord.HTTPException)`×2（`fetch_message`/`edit`）；`Exception + logging.exception`×1（db cleanup 兜底） |
| `bot/cogs/tickets_new_cog.py` | 12 | `(discord.Forbidden, discord.HTTPException)`×6（DM `user/creator.send`）；`discord.HTTPException`×5（交互响应 `followup.send`/`response.send_message`/`edit_original_response`）；`Exception + logging.exception`×1（`_validate_channel_permissions` 兜底，从"静默 return False"→"记日志 + return False"） |

**值得记忆的通用模式**（未来审核类似代码可直接套）：
- Discord DM 发送 → `(discord.Forbidden, discord.HTTPException)`
- `bot.fetch_user` / `channel.fetch_message` → `(discord.NotFound, discord.HTTPException)`（加 `Forbidden` 若是 fetch_message）
- `interaction.followup.send` / `response.send_message` / `edit_original_response` → `discord.HTTPException`（覆盖 `InteractionResponded` 等子类）
- `os.unlink(temp)` → `OSError`
- SQLite `ALTER TABLE ADD COLUMN` → `aiosqlite.OperationalError`（重复列名是运维级 no-op）
- "最后兜底返回 False/None" 且不确定异常来源 → `except Exception: logging.exception(...)`（不再静默）

**未做（留给其他任务）**：
- 未加 ruff `E722` 规则锁死成果 —— P3-5 做
- `tickets_new_cog:824/831` 交互兜底链（followup 失败→response 再失败→放弃）逻辑保留原样，只收窄异常；更根本的重构等 P1-3 拆包时一并处理

---

## P0-1 ✅ giveaway 抽 db（2026-04-23）

**Commit grep**: `git log --grep='(P0-1)'`

**验收**：`grep -n "aiosqlite" bot/cogs/giveaway_cog.py` 清零（21 → 0）；`python3 -m py_compile` 通过；manager 直接 import / 实例化 OK。功能层（创建 / 参与 / 退出 / 开奖 / 超时）**待用户在测试服验证**。

**迁移映射表**（供未来审查）：

| 原 cog 方法 | 新 manager 方法 | 处理方式 |
|---|---|---|
| `fetch_all_giveaways(is_end)` | `fetch_all_giveaways(include_ended)` | thin wrapper |
| `update_giveaway(id, winners)` | `update_giveaway_winners(id, winners)` | 保留 cog 方法（需连锁 `cleanup_ended_giveaways`） |
| `mark_giveaway_as_ended` | 同名 | 保留 cog 方法（需连锁 cleanup） |
| `add_participant_to_giveaway(id, pid, interaction)` | `add_participant(id, pid)` | 保留 cog 方法（签名带 interaction，实际未用） |
| `remove_participant_from_giveaway` | `remove_participant` | thin wrapper |
| `check_participant_eligibility` | `fetch_giveaway_requirements` + `fetch_user_achievements` | 保留 cog 方法（含 interaction 响应） |
| `fetch_participant_ids / fetch_winner_ids / is_participant / fetch_giveaway` | 同名 | thin wrapper |
| `update_giveaway_description / update_giveaway_duration / cleanup_ended_giveaways / save_giveaways` | 对应 manager 方法 | thin wrapper |
| `load_giveaways` | 用 `load_giveaway_views` 拿 SQL | 保留 cog 方法（含 Discord `fetch_message`/`edit`） |
| `update_participant_achievements` | `increment_giveaway_achievements` | 薄化为 "fetch ids + manager 调用" |
| `on_ready` 里的两段建表 | `initialize_database()` | on_ready 只调一行 |
| `GiveawayForm.insert_giveaway / fetch_all_giveaway_ids` | `db.*` 直接调 | **删 form 方法**，调用点改 `self.db.xxx()` |
| `GiveawayForm.fetch_giveaway` | — | **删（零调用死代码）** |

**辅助类获取 db 的方式**：`GiveawayForm.__init__` 加 `db` 参数（显式），实例化点 `cog:654` 传 `db=self.db`。`GiveawayParticipationView` / `GiveawayConfirmationView` / `GiveawayCheckParticipantView` **不传 db** —— 它们原本就通过 `bot.get_cog('GiveawayCog').xxx()` 调 cog 上的 thin wrapper，cog wrapper 在，View 调用链无需改动。

**顺手修的真实 bug**：
- `update_giveaway_description` 原本缺 `await db.commit()`（`giveaway_cog.py:1082-1086` 旧代码），意味着 `/ga_description` 命令**实际不生效**（事务回滚）。迁到 manager 后补了 commit。这个 bug 不在文档里列出，是迁移路上发现的。

**顺手清理的死代码**：
- `GiveawayParticipationView.__init__` / `GiveawayConfirmationView.__init__` 里 `self.main_config` / `self.db_path`（仅赋值不使用）。
- `GiveawayForm.fetch_giveaway`（方法本体无调用点）。

**未做（留给其他任务）**：
- `tickets_new_cog.py:14 import aiosqlite` 是死 import（该 cog 没直连），但不在 P0-1 范围，留给后续清理（顺便 P1-3 拆包时也会处理）。
- 建表从 `on_ready` 迁到 `cog_load` 是 P1-2 工作，本轮只迁到 manager 的 `initialize_database()`，调用点仍在 `on_ready`。

**未来类似迁移的模板**（下一个 P0-2/P0-3 直接套）：
1. grep 列出所有 `aiosqlite.connect` 调用点，按所属类归类。
2. 决定辅助类拿 db 的方式（推荐 `db=` 构造参数）。
3. 设计 manager：纯 SQL 方法返回 dict/list；夹 Discord 交互的保留在 cog。
4. 新建 manager 类 → `bot/utils/__init__.py` 导出 → cog `__init__` 实例化 → 替换直连。
5. 建表从 `on_ready` 挪到 `manager.initialize_database()`，`on_ready` 调一行。
6. `grep "aiosqlite"` 该文件为空即验收；`python3 -m py_compile` 过一遍。

---

## P0-2 ✅ privateroom 直连规范化（2026-04-23）

**Commit grep**: `git log --grep='(P0-2)'`

**范围**：`bot/cogs/privateroom_cog.py` 仅有 1 处直连（`get_last_month_voice_hours`，查 `monthly_achievements.time_spent`）。

**做法**：`PrivateRoomDatabaseManager` 新增 `get_user_monthly_voice_seconds(user_id, year, month) -> float`，cog 只保留时间窗口（上月）计算 + 秒→小时换算。

**跨表访问处理**：`monthly_achievements` 表归属 achievement 领域，但 privateroom_cog 只依赖 `PrivateRoomDatabaseManager`；为保持单 manager 依赖、避免无谓引入 `AchievementDatabaseManager`，该方法先放在 privateroom 侧。同 P0-1 的 `increment_giveaway_achievements` 策略，未来跨 manager 引用成常态时再统一梳理。

**验收**：`grep -n "aiosqlite" bot/cogs/privateroom_cog.py` 清零（含 import）；`py_compile` 通过。功能层需用户在测试服验证购买/续费路径（涉及 voice hour 门槛的逻辑才会触发这个方法）。

**目标**：`bot/cogs/privateroom_cog.py` 里仍直连 `aiosqlite.connect` 的点，改走已存在的 `PrivateRoomDatabaseManager`；manager 缺的方法就补。

**验收**：`grep -n "aiosqlite" bot/cogs/privateroom_cog.py` 为空或只剩 import。

---

## P0-3 其余 cog 补 db manager

**内部顺序（按文档风险排序）**：

1. ✅ **P0-3a check_status** — 完成（2026-04-23）
2. ⬜ **P0-3b notebook**（342 行，小，练手）— 下一步
3. ⬜ **P0-3c create_invitation**（606 行）
4. ⬜ **P0-3d voice_channel**（1094 行，最大，需评估新 `voice_channel_db.py` 还是扩展既有 manager）

**终局验收**：`grep -rn "aiosqlite.connect" bot/cogs/` 为空。

---

### P0-3a ✅ check_status（2026-04-23）

**Commit grep**: `git log --grep='(P0-3a)'`

**做的事**：
- 新建 `bot/utils/check_status_db.py` + `CheckStatusDatabaseManager`（3 方法：`initialize_database` / `record_status` / `fetch_status_by_date_prefix`）。
- cog `__init__` 加 `self.db = CheckStatusDatabaseManager(self.db_path)`。
- 新增 `async def cog_load(self): await self.db.initialize_database()` —— **建表迁到 cog_load**。
- 删除 `on_ready` listener（它本来只做建表）。
- 替换 `check_voice_status_task` 的 INSERT 和 `print_voice_status` 的 SELECT 为 manager 调用。
- 删除 `import aiosqlite`。

**竞态 bug 说明（供回溯）**：
- `__init__` 里 `self.check_voice_status_task.start()` 启动 10 分钟后台循环；`before_loop` 做 sleep + `wait_until_ready()`。
- 旧的建表在 `@Cog.listener() on_ready` 里；`before_loop` 的 `wait_until_ready()` 和 `on_ready` listener 都在 READY 后并发放行，**顺序不保证**。
- task 首次跑到 INSERT 时如果建表 listener 还没完成 → `sqlite3.OperationalError: no such table: status`，被 `except Exception` 静默吞为一行 log。
- 迁到 `cog_load` 后：cog 加载完成（bot 起步期）就已经建表 → **永远早于** task 的任何执行。

**未做（留给 P1-2）**：后台任务 `start()` 仍在 `__init__`，没动（P1-2 专门治理此类 pattern）。本轮只修竞态。

---

### P0-3b ✅ notebook（2026-04-23）

**Commit grep**: `git log --grep='(P0-3b)'`

**做的事**：
- 新建 `bot/utils/notebook_db.py` + `NotebookDatabaseManager`（7 方法）。
- `insert_event_and_ensure_admin` 保留**单连接组合事务**语义（MAX(count) → INSERT event → SELECT admin → INSERT admin if missing），和原 cog 行为一致。
- 所有 cog 方法改为 thin wrapper（`ConfirmationView` 通过 `bot.get_cog('NotebookCog').xxx()` 调用链不变）。
- 建表迁 `cog_load`，`on_ready` listener 删除（与 P0-3a 对齐；此 cog 无后台任务，动作纯属一致性）。
- 清掉冗余的 `datetime` import（时间戳生成下沉 manager）。

**无竞态修复**（这个 cog 没有后台任务在 `__init__` 启动）。

---

### P0-3d ✅ voice_channel（2026-04-23）

**Commit grep**: `git log --grep='(P0-3d)'`

**做的事**：
- 新建 `bot/utils/voice_channel_db.py` + `VoiceChannelDatabaseManager`（11 方法），所有 SQL 操作 `temp_channels` 单表。
- `initialize_database()` 内含 schema migration 逻辑（老部署的 `ALTER TABLE ... ADD COLUMN` 补列），保持原 `ensure_temp_channels_table` 语义。
- cog `__init__` 加 `self.db = VoiceChannelDatabaseManager(db_path)`；`cog_load` 调 `self.db.initialize_database()`；原 `ensure_temp_channels_table` 方法整个删除。
- `cleanup_task` / `cleanup_channel` / `on_ready` 原本是"单连接里 SELECT+for 循环+条件 DELETE"—— 改为"先 `fetch_all_channel_ids()` 一次，Python 里循环"，SQL 单点化。
- `on_ready` 里的独立 `aiosqlite.connect` 块整体删除。
- `RoomControlPanelView.__init__` 加 `db` 参数；2 处实例化点（`send_control_panel` + `restore_control_panels` 恢复流程）传 `self.db`；unlock/lock/soundboard 3 个 callback 改为 manager 调用。

**保留的历史行为（不改）**：
- `cleanup_channel` 原本是"SELECT check → DELETE 被注释 → Discord 删频道"。DB 记录留给下次 `cleanup_task` 发现 `bot.get_channel == None` 时统一清。迁 manager 后行为等价（用 `db.exists(channel_id)` 替 SELECT 判断），DB 仍然不删 —— 这是历史设计（可能是为了避免误删），保留。

---

### P0-3c ✅ create_invitation（2026-04-23）

**Commit grep**: `git log --grep='(P0-3c)'`

**做的事**：仅 1 处直连（`TeamInvitationView.create_embed` 读 `user_signatures`）。`user_signatures` 归 role 域，`RoleDatabaseManager.get_user_signature(user_id) -> Optional[Dict]` 已存在，直接复用。

**不建 InvitationDatabaseManager 的理由**：此 cog 本身没有持久化状态表，若仅为一次跨域读而新建空 manager，是为形式而形式。跨 manager 复用是更轻的方案（manager 只持 `db_path`，无状态，共享安全）。

**做法**：
- `CreateInvitationCog.__init__` 加 `self.role_db = RoleDatabaseManager(db_path)`。
- `TeamInvitationView.__init__` 加 `role_db` 参数；两处实例化点（`on_message` 路由 + `/invitation`）传入。
- `create_embed` 的 SQL 改为 `await self.role_db.get_user_signature(author.id)`，`is_disabled=True` 时 signature 视为 None（语义保留）。
- 顺手清 View 里的 `main_config` / `db_path` 死属性；删 `import aiosqlite`。

---

---

## Context 恢复指南

**接手者第一步**（尤其新 Claude / context 重开）：

1. `cat REFACTORING_PLAN.md` 了解整体 P0~P3 分级。
2. `cat REFACTORING_PROGRESS.md`（本文件）找当前 🔄 / 下一个 ⬜。
3. `git log --oneline -15` 查看最近 commit 节奏。
4. `git status` 确认工作树是否干净；如脏，要么是上一轮没收尾，要么是用户新改动。
5. 用 `git log --grep='(P0-4)'` 查看某 P 任务的完整 commit 历史。

**工作流**：每完成一条 P 任务 → 源码 commit（message 带 `(PX-Y)` 标签）→ 更新本文件把 ⬜ 改 ✅ 并填笔记 → 单独 commit progress。

**不要做的事**：
- 不要一次 commit 多个 P 任务的改动 —— 破坏 `git log --grep` 精确定位。
- 不要跳过"写实施笔记"这一步 —— 将来审核/回溯的核心价值就是笔记，不是代码。
- 不要 amend 已发布 commit 去改 progress —— 顺序向前走，记错了就新 commit 修正。

---

## P1-5 ✅ 日志 rotation（2026-04-23）

**Commit grep**: `git log --grep='(P1-5)'`

**动的文件**：
- `bot/main.py`：3 个 logger（root / `keyword_detection` / `room_activity`）统一换 `TimedRotatingFileHandler(when='midnight', backupCount=<conf>, encoding='utf-8')`。用一个 `_rotating_handler(path)` 闭包共享 formatter + backupCount 设置，避免三处粘贴。
- `bot/config/config_main.json.example` + `bot/config/config_main.json`：加可选键 `log_backup_count`（默认 14，`int(conf.get(...))`），运维可调。

**放弃 `basicConfig` 的理由**：原本 main log 走 `logging.basicConfig(filename=...)`；basicConfig 的限制是只在 root logger 没 handler 时生效第一次，后续重复调用静默失败，且它只给 root 配一个 `FileHandler`，没法注入 rotation。改为显式 `root_logger.addHandler(_rotating_handler(...))`，三路日志用同一套参数。

**行为等价性**：
- 日志文件路径、format、level、`propagate=False`（keyword / room）均不变。
- Root logger 从"basicConfig 的隐式单 handler"变成"显式单 rotating handler"，`logging.info(...)` 直接调用路径不变。
- 首次运行现有 `./data/*.log` 会继续追加；午夜跨天时 `TimedRotatingFileHandler` 自动把旧内容挪到 `*.log.YYYY-MM-DD`，新写入回到 `*.log` 主文件。

**验收**：
- `python3 -m py_compile bot/main.py` 过。
- `json.load` 两个 config 都能解析。
- 功能验收需跑过一次 00:00 才能肉眼看到 rotation 产物；但由于行为是 stdlib 标准实现、参数三处统一、无竞争条件，无需测试服联调。

**未做（后续任务范围）**：
- 不覆盖 discord.py / aiosqlite 自己的 logger（它们默认 propagate 到 root → 会走 main.log rotation；如要独立拆分等 P2 再说）。
- 没给 rotation 加"按大小 + 按时间"组合（`maxBytes`）。按大小限额是另一需求；目前纯按天够用。

---

## P1-2 ✅ ban_cog 迁 cog_load（2026-04-23）

**Commit grep**: `git log --grep='(P1-2)'`

**做的事**：
- `__init__` 删掉 `self.init_task = asyncio.create_task(self.initialize_db())`。
- `cog_unload` 删掉 `if not self.init_task.done(): self.init_task.cancel()` 分支。
- 新增 `async def cog_load(self): await self.db.initialize_database()` —— 建表在 cog 加载就位时同步完成，任何异常会被 discord.py 的 cog 加载错误路径冒出来（不再被 `create_task` 异步吞掉）。
- 原 `async def initialize_db(self)` 整段删除（已 inline）。

**拆分 recover_tempbans 到 on_ready 的理由（非 PLAN 字面要求，但必须）**：
- `cog_load` 在 discord.py 的 `setup_hook` 链里执行，**早于 gateway 连接**。此时 `self.bot.get_guild(guild_id)` 永远返回 `None`。
- `recover_tempbans` 逻辑：`guild = self.bot.get_guild(guild_id); if not guild: deactivate_tempban(...)` —— 如果把整个 `initialize_db()` 直接 `await` 在 `cog_load` 里，**每个活跃 tempban 都会被误判为"guild 不存在"而被标为 inactive**，严重 regression。
- 原 `create_task` 版本是"可能跑早可能跑晚"的不确定竞态；naive PLAN 迁移把它变成"确定性跑早"、一定坏。
- 解法：`cog_load` 只做表创建；`recover_tempbans` 挪到 `@commands.Cog.listener() on_ready` 下，加 `self._tempban_recovery_done` 标志位，保证**首次 READY 跑一次**（`on_ready` 因断线重连会重复 fire，没 flag 会重复 schedule unban，造成同一 tempban 被 schedule 两次的 bug）。

**验收**：
- `grep -n "init_task\|initialize_db" bot/cogs/ban_cog.py` 清零（仅剩 `self.db.initialize_database()` 这一行，是 manager 方法名，语义正确）。
- `python3 -m py_compile bot/cogs/ban_cog.py` 过。
- 功能验收：重启 bot → 原活跃 tempban 应被正确识别（不会被 deactivate）；过期 tempban 应被执行 unban 并 deactivate。这需要测试服或生产跑一次带活跃 tempban 记录的重启才能确认。

**未动**（PLAN P1-2 明确"不扩到其他 cog"）：
- `self.cleanup_tempbans.start()` / `self.check_expired_tempbans.start()` 仍在 `__init__` —— 后台任务启动时机是另一个模式（`tasks.loop` 本身有 `before_loop` + `wait_until_ready` 处理），不在本轮范围。
- 其他 cog 的类似 pattern（`achievement_cog` / `shop_cog` / `tickets_new_cog` / `voice_channel_cog`）按 PLAN 说明**已经在用 `cog_load`**，本轮核查时无需改动。

---

## P1-1 ✅ 命令同步逻辑（2026-04-23）

**Commit grep**: `git log --grep='(P1-1)'`

**做的事**：
- `bot/main.py` 的 `on_ready` listener 移除 `tree.clear_commands(guild=...)` + `tree.sync(guild=...)` + `tree.sync()` 三行。
- 新增 `async def sync_commands_once(bot)`，`setup_hook` 里 `await setup_bot(bot)` 之后调一次。
- 用 `discord.Object(id=guild_id)` 代替 `for guild in bot.guilds` 里的真 `Guild` 对象 —— `setup_hook` 跑在 gateway 连接**之前**，`bot.guilds` 为空，但 sync 只需要 id 即可。
- sync 失败不再致命：`discord.HTTPException` 被捕获 + `logging.error(..., exc_info=True)` + 打印；bot 继续用上次同步过的命令定义启动（不因 sync 瞬时失败而拒绝服务）。

**on_ready 保留的职责**：只有"登录日志 + 对每个 guild 判断是否目标服 + 设置 presence/日志 not-allowed"。这部分每次重连都要跑（presence 会因 session 重置而丢失，必须 re-apply）。

**为什么选 `setup_hook` 而不是 "on_ready + flag"**：
- PLAN 给了两种选项："迁移到 setup_hook，或在 cog 上加 self._synced 标志位，仅首次同步"。
- setup_hook 方案的优点：
  - 职责分离清晰 —— sync 是"启动期一次性动作"，presence/连接日志是"每连接一次的动作"。
  - 无需维护可变 flag 状态（也没有 cog 可挂 —— 这段逻辑在 `main.py` 不在 cog）。
  - 失败处理更自然：在 setup_hook 里 try/except 是启动期配置错误路径，on_ready 里做同样的 try 会把 HTTP 错误混进"每次 ready 事件处理"里语义模糊。
- 选 flag 方案的唯一理由会是"担心 setup_hook 里 http 不可用"，但 discord.py 已保证 setup_hook 在 login 之后执行（`bot.http` 已可用），OK。

**rate limit 影响**：
- 原代码：每次 `on_ready`（首连 + 每次断线重连）都 `tree.sync()`（全局 + guild 各一次）。Discord 全局命令 sync 有严格 rate limit（200/day/app）—— 长期运行 + 频繁重连的环境可能被限流，且 sync 实际会对 command list 做 diff 对比，没变的情况下 API 也会重复计费配额。
- 迁后：启动仅一次 sync，计 2 次（guild + global）。`synccommands` 手动命令仍保留，运维手动强制 resync 路径不变。

**验收**：
- `python3 -m py_compile bot/main.py` 过。
- 功能验收需跑起 bot 观察：首次启动日志出现 `"Startup sync: N global commands synced."`；重连后 `on_ready` 日志不再出现 `"Global commands synced"` 字样。
- 若 setup_hook 阶段 Discord API 返回 401/403（token 无效），会 log 出来但 bot 仍尝试启动 —— 注意生产部署后 grep 这条 log 做启动健康检查。

**未做（后续任务范围）**：
- `synccommands` 手动命令里的 `except Exception` 仍是宽捕获（非本次 P1-1 范围 —— P0-4 已通过，这一处原本就在豁免名单外；若要收窄留 P3-5 ruff E722 / 类似 narrow exception lint 规则统一清理）。
- 从更大的架构角度，slash command 的 sync 应该只在"命令定义确实变了"时做。缓存 command hash 比较的优化留给未来（不在 PLAN）。
