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
| P1+P2 | 配置系统 2.0（P1-6 + P1-4 + P2-3 + P2-5） | ✅ | step 0-9 全部完成（P1-4 最小版；pydantic 全量留 follow-up） |
| P1 | P1-7 Slash 元数据本地化 | ✅ | SlashTranslator + 176 key commands.yaml |
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

---

## 配置系统 2.0 冲刺（P1-6 + P1-4 + P2-3 + P2-5，绑定一次做）

> PLAN 参考：§P1-6、§P1-4、§P2-3、§P2-5。step 编号沿用 PLAN §P1-6 的步骤 0~9。
> Commit 规约：`(P1-6.0)` / `(P1-6.2)` / ... 方便 `git log --grep='(P1-6\.0)'` 精确定位 sub-step。

### Step 汇总表

| Step | 做什么 | 状态 |
|---|---|---|
| 0 | `.gitignore` 阶段 A 规则 + 清历史泄露 | ✅ |
| 1 | 硬编码文案清单扫描（非改码，调研） | ⬜（每 cog 迁移时就地做） |
| 2 | `requirements.txt` + `requirements.lock` 加 `ruamel.yaml` | ✅ |
| 3 | `bot/utils/config.py` 改造（YAML 分派 + `get_locale` + async `save_config`） | ✅ |
| 4 | `bot/utils/i18n.py` 新建（`t()` + fallback 链） | ✅ |
| 5 | `tools/migrate_config_to_yaml.py` + `tools/seed_db.py` + `tools/field_classification.yaml` | ✅ |
| 6 (DB 基础设施) | `ticket_types` / `channel_configs` 表 + CRUD + cog 重写 | ✅ |
| 6 (pilot) | `spymode_cog` + `checkstatus_cog` 迁 t() + locale | ✅ |
| 7 (save_config 统一) | `ban` / `role` / `create_invitation` / `tickets_new` 四处改 `await config.save_config(...)` （P2-3） | ✅ |
| 7 (剩余 cog 文案迁移) | welcome / shop / teamup_display / achievements / giveaway / privateroom / role / voice_channel / ban / tickets_new / invitation 文案迁 `t()` | ✅ |
| 7 (无独立 config 的 cog) | notebook / game_dnd / backup（`required_configs: []`，跳过） | ➖ |
| 8 (P1-4) | 启动 schema 校验 | 🟡 最小版本（`main.locale` / `log_backup_count` 默认 + 现有 required key 检查）；pydantic 全量校验留 follow-up |
| 9 | 清理（阶段 B `.gitignore` + 删 JSON fallback + `.json` → `old_function/`） | ✅ |

### P1-6.0 ✅ step 0: .gitignore 阶段 A + 历史泄露（2026-04-23）

**Commit grep**: `git log --grep='(P1-6\.0)'`

**动的**：
- `.gitignore` 加 4 条：`bot/config/*.yaml`、`tools/migration_db_seed.json`、`tools/migration_report.md`、`old_function/**/*.json|*.yaml`。
- 留 `bot/config/*.json`（阶段 A 全程保留，step 10 阶段 B 再拿掉）。
- `.json.example` / `.yaml.example` 后缀不匹配 `*.json` / `*.yaml`，**自动**脱敏模板保持可提交，无需单独排除规则。
- `git rm --cached` 清历史泄露：`old_function/config/config_tickets.json` + `config_rating.json`（工作树保留、仅移出 index；git 历史里的泄露不走 filter-repo 重写，按 PLAN 已拍板"认历史账"）。

**AGENTS.md 状态**：line 35 "安全与配置提示" 已于之前冲刺写入 `old_function/**/*.json|*.yaml` 归档硬规则，本 step 无需再改。

**验收**：
- `git check-ignore` 探 6 种路径全部按预期（真 yaml 忽略 / `.example` 不忽略 / `locales` 不忽略 / 迁移产物忽略）。
- `git log --oneline -1` 显示 step 0 commit 生效。

**下一步**：step 2（依赖加 `ruamel.yaml`），step 1 的硬编码清单扫描合并到 step 7 per-cog 迁移时执行（PLAN step 1 是"调研清单"，实际抽文案的动作在每个 cog 迁移 PR 里）。

### P1-6.2 ✅ step 2: 依赖加 ruamel.yaml（2026-04-23）

**Commit grep**: `git log --grep='(P1-6\.2)'`

**动的**：
- `requirements.txt` 尾部追加 `ruamel.yaml`（带注释说明用途）。
- `requirements.lock` 用 `uv pip compile requirements.txt -o requirements.lock` 重新生成；新增 `ruamel-yaml==0.19.1`（pure-Python on cpython>=3.12，无 `ruamel-yaml-clib` 传递依赖）。

**pyproject.toml 没动**：按 PLAN 的"P3-1 时一起改，不留三处声明漂移"原则，暂 `dependencies = []`。

**验证方法**：`uv pip compile` 无错；lock diff 只增一行 `ruamel-yaml==0.19.1`。

### P1-6.3 ✅ step 3: config.py 改造（2026-04-23）

**Commit grep**: `git log --grep='(P1-6\.3)'`

**新接口**：
- `get_config(name, silent=)`：先查 `bot/config/<name>.yaml`（ruamel.yaml round-trip load），不存在则回退读 `config_<name>.json`。迁移期两种格式共存；step 10 清 JSON 分支。
- `get_locale(name, lang=None) -> dict`：读 `bot/locales/<lang>/<name>.yaml`，按 `(lang, name)` tuple 缓存。`lang=None` 从 `main.locale` 取，缺则 `zh_CN`。
- `async def save_config(name, data=None, *, reload=True) -> dict`：**ruamel.yaml round-trip 写入**保留原文件注释 + **同目录 tempfile + `os.replace` 原子替换**，`asyncio.to_thread` 卸到线程池避免阻塞事件循环。`data=None` 时写当前内存态 `self._configs[name]`（匹配"就地改 self.conf 然后持久化"的常见 pattern）。

**微改**：`load_config(file_path=...)` 参数整体移除（`grep -rn "load_config("` 确认无外部调用点传过）。

**smoke test 结果**（`/tmp/yaml-venv` 带 ruamel.yaml 的隔离环境）：
- YAML 优先 / JSON fallback 两条路径都走通
- save_config 写完后 `# top comment` 仍在文件顶部（round-trip 有效）
- save_config 原子性靠 `os.replace`（tempfile 与目标在同文件系统）
- `reload_all` / `reload_config` / `reload_locale` 行为正确
- missing locale file 返回 `{}` 而非异常（让 i18n.t 的 fallback 链接手）

**ruamel.yaml 实例 per-call 而非全局**：避免多协程并发 save 时共享状态问题；创建成本可忽略（构造函数内部几乎无工作）。

### P1-6.4 ✅ step 4: i18n.py 新建（2026-04-23）

**Commit grep**: `git log --grep='(P1-6\.4)'`

**新文件 `bot/utils/i18n.py`**：`def t(key, *, lang=None, **kwargs) -> str`，配套从 `bot/utils/__init__.py` 导出。

**语义**：
- dot-path 查找：`t('role.starsign.aries')` → 命名空间 `role` + 路径 `[starsign, aries]` → `bot/locales/<lang>/role.yaml` 的 `starsign.aries`。
- fallback 链：requested lang → `zh_CN` baseline → `KeyError`（消息含 dot-path + 所有尝试过的语言）。
- 命名空间缺失（无 dot）→ 立即 `KeyError`，避免"以 key 为值"的静默回退导致线上显示英文 key。
- kwargs 走 `str.format_map`，译文里写 `'已为你添加了星座：{name}'` 即可被 caller `t('...', name='Zoyo')` 填充。
- 非 str 叶节点（如误指向 dict）按"未命中"处理 + 触发 fallback 链（最终 KeyError）。

**Lazy vs eager 加载**：PLAN 建议"启动时一次性加载"，当前实现是 lazy（首次访问 namespace 触发 `config.get_locale` + 缓存）。功能等价，启动路径更干净；eager preload 可在未来需要时加一行 `for ns in list_locales(): config.get_locale(ns)`。

**smoke test**：基本查询 / format_map / 缺 key 抛 KeyError / 非法 key 被拒 / `lang='en_US'` 落回 `zh_CN` 全过。

**下一步**：step 5 —— 写 `tools/migrate_config_to_yaml.py` + `tools/seed_db.py` + `tools/field_classification.yaml`。这一步是"生成迁移产物"的纯工具代码，不触碰现有 cog；写完可在本仓跑一次生成出所有 `<name>.yaml`（本地，不 commit）作为后续 step 7 试点迁移的输入。

### P1-6.5 ✅ step 5: 迁移脚本 + 分类表（2026-04-23）

**Commit grep**: `git log --grep='(P1-6\.5)'`

**新文件**：
- `tools/field_classification.yaml`：每 cog 的 `yaml` / `locale` / `db` 显式路径覆盖；heuristic 兜底（`messages` 子树 → locale、scalar → yaml、`_message/_title/_label/...` 后缀 → locale）。
- `tools/migrate_config_to_yaml.py`：读 `bot/config/config_<name>.json` → 输出 `<name>.yaml` + `<name>.yaml.example`（ID 脱敏为 `1145141919810`、token 脱敏为 `YOUR_BOT_TOKEN`）+ `locales/zh_CN/<name>.yaml` + `tools/migration_db_seed.json` + `tools/migration_report.md`。支持 `--only <cog>` 单 cog 迁移。
- `tools/seed_db.py`：读 `migration_db_seed.json`，调 `VoiceChannelDatabaseManager.upsert_channel_config` / `TicketsNewDatabaseManager.upsert_ticket_type` 做 DB 初始灌入。幂等（upsert）。

**Smoke**：对 14 个 `config_*.json` 跑完无错；spymode（23 keys → locale，0 yaml）、checkstatus（5 → locale）、ban（4 yaml + messages → locale）、welcome（9 yaml + dm 子树 + 3 locale）、role（7 yaml + 43 locale）等都按 classification 分流。heuristic 兜底被标记为 `locale?` / `yaml?` 进 `migration_report.md` 供人工 review。

**`tools/seed_db.py` 设计要点**：
- 直接复用生产的 DB manager（`VoiceChannelDatabaseManager` / `TicketsNewDatabaseManager`），共享 schema 定义 & upsert CRUD。
- 先调 `initialize_database()`（幂等）保证 fresh `bot.db` 也能 seed。
- 不清 destination 表 —— 靠 upsert 幂等，操作员看到不在 seed 里的"旧"行可自行清理（不做自动破坏）。
- 未知 cog name 只 warn 跳过；未来新增 DB 字段只需在 `seed_handlers` 加条目。

---

### P1-6.6 ✅ step 6a: DB 基础设施 + 两大 cog 重写（2026-04-23）

**Commit grep**: `git log --grep='(P2-5)'`（两条 commit）

**voice_channel**：
- `VoiceChannelDatabaseManager` 加 `channel_configs` 表 + `list_channel_configs` / `upsert_channel_config` / `delete_channel_config`。
- `voice_channel_cog.__init__` 不再读 `self.conf['channel_configs']`；`cog_load` 调 `list_channel_configs()` 填 `self.channel_configs` 内存缓存（热路径不变）。
- 三处 `save_channel_configs()` callsite（AddChannelForm / 两个 DeleteChannelConfirmView.confirm）换 upsert / delete + 内存态同步。
- 删 `save_channel_configs` 方法 + 不用的 `aiofiles / json / Path` import。

**tickets_new**：
- `TicketsNewDatabaseManager` 加 `ticket_types` 表（`type_name` PK + `type_data` JSON）+ `list_ticket_types` / `upsert_ticket_type` / `rename_ticket_type`（transactional DELETE+INSERT 避免半写）/ `remove_ticket_type`。
- `tickets_new_cog.__init__` `pop('ticket_types', None)` 从 `self.conf` 挪出来，永远不让 `config.save_config('tickets_new', self.conf)` 把 DB 字段回写到 YAML。
- `cog_load` 调 `list_ticket_types()` 填 `self.ticket_types` 缓存 + 提供 `_refresh_ticket_types()` 帮助函数。
- 20+ 处 `self.conf['ticket_types']` / `self.conf.get('ticket_types', ...)`（cog 和 View 的读）全部改 `self.ticket_types` / `self.cog.ticket_types`。
- TicketTypeModal add / edit / rename 路径：local `type_data` dict + `upsert_ticket_type` / `rename_ticket_type` + `_refresh_ticket_types`。**移除**原来的 `db_manager.save_config('ticket_types', ...)` bogus 调用（从没 work 过，AttributeError 静默）和 `self.cog.conf = await db_manager.get_config()` 的 clobber（会把 messages/admin 从 memory 里擦掉）。
- DeleteConfirmView.confirm_delete 同模式。
- `add_global_admin` / `add_type_admin` / `remove_type_admin` 的类型级 admin 增删也改走 `upsert_ticket_type`（之前只改 `self.ticket_types` 内存态 + 存 `self.conf` → 重启就丢）。
- `save_config` 方法换成 `await config.save_config('tickets_new', self.conf)` 的 P2-3 统一写回 + 保护性 `pop('ticket_types', None)`。
- 删不用的 json / aiofiles / Path import。

**pilot spymode 完成**：23 keys → `bot/locales/zh_CN/spymode.yaml`，cog 的 24 处 `self.conf['xxx']` / `.format(...)` 全部改 `t('spymode.xxx', **kwargs)`。移除 `self.conf` 实例缓存、unused `Button/View` 导入。

**pilot checkstatus 完成**：5 migration-script 生成的 keys + 15 手动抽出的硬编码（date_format_error / log_type_main/keyword/room / voice_stats_* / error_generic 等）→ `bot/locales/zh_CN/checkstatus.yaml`。cog 重写：去掉 `self.conf.update(main_config)` 的 silent-mutation hack，改为 `self.logging_file / self.keyword_log_file / self.room_log_file` 直接从 main 读；所有 `t()` 按 call site 展开；重复的 `/where_is` slash + context menu DRY 成 `_send_where_is()` 辅助方法。

---

### P1-6.7a ✅ step 7a: save_config 统一（P2-3）（2026-04-23）

**Commit grep**: `git log --grep='(P2-3)'`（一条 commit），`git log --grep='unify save_config'`

**改的 4 个 callsite**（保留在 YAML 的，按 P2-5 判定表分类）：
- `ban_cog.save_config` → `await config.save_config('ban', self.config_data)`；删掉 aiofiles / json / Path 手动 I/O 和 `Config().reload_config(...)` 的 reload 舞蹈。
- `create_invitation_cog.save_config` → `await config.save_config('invitation', self.conf)`。老代码只写 `ignore_channel_ids` 一个字段回 JSON，其它任何 in-memory mutation 都会被吞（现在改整体回写）。
- `role_cog.set_signature_requirement` 的 `config.save_config('role', self.role_config)` 改 `await config.save_config(...)`。这是 PLAN 记录的 AttributeError bug：老代码调用同步形式，但 `Config.save_config` 当时根本不存在 → 每次 `/signature_set_requirement` 都 silent fail。所在函数本身是 `async def`，加 `await` 直接生效。
- `tickets_new_cog.save_config` → `await config.save_config('tickets_new', self.conf)`（在 ticket_types DB 迁移 commit 里顺手改掉，一并清 aiofiles/json import）。

**删掉的 2 处 DB-判定 writer**（见 P1-6.6）：
- `voice_channel_cog.save_channel_configs` 方法整体删除，三处 callsite 改 DB upsert/delete。
- `tickets_new_cog` 的两处 `db_manager.save_config('ticket_types', ...)` 整体删除，改 CRUD upsert + `_refresh_ticket_types`。

---

### P1-6.8 🟡 step 8: P1-4 schema 校验（最小版本）（2026-04-23）

**Commit grep**: `git log --grep='P1-4 minimal'`

**做了**：`bot/utils/config.py._verify_main_config` 加 defaults 兜底：
- `main.locale` 缺失 → `zh_CN`（对齐 P1-6 决策 B2）
- `main.log_backup_count` 缺失 → `14`（对齐 P1-5）
必填 key（token / logging_file / db_path / guild_id）行为不变（print warning + 设 None）。

**没做**（follow-up）：pydantic / dataclass 全量 schema；per-cog locale key 完整性校验；starsign / mbti / slug-mapped 字段跨 config/locale 对齐校验。理由：这些校验对"所有 cog 已迁完 locale"预设依赖强；step 7 剩余批量迁移没完成前，校验会在没有 locale 的路径上误报。

---

### P1-7 ✅ Slash 命令元数据本地化（2026-04-23）

**Commit grep**: `git log --grep='(P1-7a)'` / `git log --grep='(P1-7b)'`

**两条 source commit**：
- `(P1-7a)`：基础设施 + notebook pilot。
- `(P1-7b)`：其余 13 cog + check_status 4 slash + commands.yaml 补齐到 176 key。

**结构**：
- `bot/utils/slash_translator.py`：`app_commands.Translator` 子类。`Locale.chinese` → `zh_CN`；其他 locale 返回 `None`（Discord fallback 到 `locale_str.message` 英文字面量）。`TranslationContextLocation.{command_name,group_name,parameter_name,choice_name}` 跳过（Discord `name` 字段 ASCII 约束，中文会被拒）。其余类型从 `string.extras['key']` 读 dot-path 在 `bot/locales/<lang>/commands.yaml` 查表；miss warn-once-per-(lang,key)。
- `bot/main.py` setup_hook：`await bot.tree.set_translator(SlashTranslator())` **在** `sync_commands_once` 之前 —— 否则注册时 Discord 拿到的 payload 没翻译。
- `bot/locales/zh_CN/commands.yaml`：176 key，按 `<cog>.<cmd>[.params.<arg>].description` 结构。

**call site 形式**：
```python
description=locale_str(
    "Ban a user from the server",            # English fallback shown to non-zh-CN clients
    key="ban.ban.description",               # dot-path into commands.yaml
)
```
- `message` = 英文字面量 = non-zh-CN 用户看到的 fallback。
- `extras['key']` = lookup key。没有 `key=` 的 `locale_str` 直接被 translator 跳过（保持纯英文行为）。

**覆盖范围**：
- 14 cog × 138 个 decorator 全迁。每个原本没有显式 `description=` 的命令（如 notebook 的 4 个）都显式补了英文 description —— 没补前 Discord 在非 zh-CN 客户端会用空描述或 docstring 里的字符串（行为依赖实现细节，不稳定）。
- `check_status.where_is_menu` 的 ContextMenu 保留硬编码 `name='Where Is'` —— ContextMenu 走独立的 name_localizations 路径，不在 Translator 链里；留 follow-up。

**验收**（运行时）：
- 简体中文客户端：`/notebook_log` 在命令补全栏显示 `"为指定成员记录一条事件日志"`（zh_CN 命中）。
- English 客户端：显示 `"Log an event for a specific member"`（`locale_str.message` fallback；Translator 返回 None）。
- 未命中的 key：bot.log 里出现 `Slash translator miss (...): key=...` 一次警告，用户侧仍然看到英文 fallback。

**静态校验**：`python3 -c "walk every key in /tmp/cmdkeys.txt"` —— 176 key 全部在 commands.yaml 有对应 string node，missing=0。

**为什么 P1-7 和 P1-6 不混（关键设计区别）**：
- P1-6 的 `t()`：服务器端单一 `main.locale`，bot 的回复文本统一选一门语言。
- P1-7 的 Translator：Discord 客户端的**每个用户**分别看自己 locale 的 slash metadata，bot 不感知。二者共享 YAML 目录但是**不同的 loader**，不能让 `t()` 去读 `commands.yaml`（会混淆两种语义）。

---

### P1-6.9 ✅ step 9 清理 + Config 2.0 整体收官（2026-04-23）

**Commit grep**: `git log --grep='(P1-6\.9)'`

**做的事**（一条源码 commit + 一条 progress commit）：
- `.gitignore` 阶段 B：去掉 `bot/config/*.json` 规则（YAML 成为 canonical；legacy JSON 的真 ID 防泄改由 `old_function/**/*.json` 规则接管）。加注释点到本文件 step 9 做 cross-ref。
- `git mv bot/config/config_*.json.example` → `old_function/config/`（14 个模板，rename 保留在 git history）。
- `mv bot/config/config_*.json` → `old_function/config/`（普通 mv；源本来就未追踪；目标端 `old_function/**/*.json` 规则继续挡）。
- `bot/utils/config.py`：删除 `load_config` 的 JSON fallback 分支、`get_json_path` 方法、`import json`；`config_exists` 收窄为 YAML-only。`_verify_main_config` 的 setdefault 兜底保留（处理老部署迁 YAML 时缺失可选 key 的场景）。
- README Setup：step 4 改 `*.yaml.example` → `*.yaml`；step 5 的 "config_main.json" → "main.yaml"；新插一步（step 7）点到 `tools/migrate_config_to_yaml.py` + `tools/seed_db.py` + 本文件 "Upgrade 协议"；后续步骤编号 +1。`config` utility 段落整段重写（YAML / atomic writes / i18n loader 四条）。
- AGENTS.md：项目结构段改 `*.yaml.example` 并提 `bot/locales/<lang>/<cog>.yaml` + `bot.utils.i18n.t()`；安全配置段落更新 `.json.example` → `.yaml.example`；归档段落追加"本次 config_*.json `git mv` 到 `old_function/` 的事实"供将来 cross-ref。

**验收**：
- `grep -rn "get_json_path\|import json" bot/utils/config.py` 清零；`config_exists` 唯一剩下的 caller 是 `bot/main.py:130` 的启动校验，行为不变。
- `python3 -m py_compile bot/utils/config.py bot/main.py` 过。
- `ls bot/config/*.json` 返回空；`old_function/config/` 含 14 组 JSON + `.example`。
- `git check-ignore -v old_function/config/config_ban.json` 仍由 `old_function/**/*.json` 规则挡住（真 ID 不会 regress 进 git）。
- `git check-ignore bot/config/ban.yaml.example` 空（`.example` 模板保持 trackable）。

**Config 2.0 sprint 收官快照**（step 0-9 全 ✅）：
- P1-6（YAML 迁移 + i18n）：`bot/config/<name>.yaml` + `bot/locales/<lang>/<name>.yaml` 成形，`bot.utils.i18n.t()` 为统一 call-site。
- P1-4（最小 schema）：`_verify_main_config` 的 setdefault 兜底 `locale` / `log_backup_count`；required key 缺失只 warn + None（老行为保留）。pydantic 全量 / slug-mapped key 对齐留 follow-up。
- P2-3（统一 save_config）：`ban` / `create_invitation` / `role` / `tickets_new` 四处 callsite 走 `await config.save_config(name, data)` 原子回写；治好了 3 个 silent-fail latent bug（详见 step 7 子节）。
- P2-5（JSON 子树 → DB 表）：`voicechannel.channel_configs` / `tickets_new.ticket_types` 迁 `voice_channel_db` / `tickets_new_db` 表 + upsert CRUD + `tools/seed_db.py` 幂等灌库。

**commit 链**（方便 `git log --grep` 追溯 sprint 全貌）：
- `(P1-6.0)`：阶段 A gitignore + 历史泄露清。
- `(P1-6.2)`：requirements.lock 加 ruamel.yaml。
- `(P1-6.3)`：config.py YAML 分派 + async save_config + get_locale。
- `(P1-6.4)`：i18n.py 新建。
- `(P1-6.5)` / `(P1-6.5b)`：迁移脚本 + seed_db.py + field_classification.yaml。
- `(P2-5)` ×2：DB 基础设施（channel_configs / ticket_types）+ cog 重写。
- `(P1-6.6)`：pilot（spymode / checkstatus）。
- `(P2-3)`：save_config 四处统一。
- `(P1-6.7 *)` ×14：每 cog 一条文案迁移 commit。
- `(P1-4 minimal)`：`_verify_main_config` setdefault。
- `(P1-6.9)`：阶段 B 清理 + 文档更新（**本 commit**）。

---

### P1-6.7 ✅ step 7 批量迁移完成（2026-04-23）

**Commit grep**: `git log --grep='(P1-6\.7)'`

**每 cog 一条 commit**：spymode / checkstatus / teamup_display / welcome / achievements / role / invitation / giveaway / shop / ban / privateroom / tickets_new / voicechannel / main（14 commit）。模式一致：`self.conf['messages']['xxx']` → `t('<cog>.messages.xxx')`（消息子树）或 `t('<cog>.xxx')`（扁平 key）；数据字段仍走 `config.get_config('<cog>')[key]`；合并 `self.messages = cog.conf['messages']` 的局部绑定到直接 `t()` call。

**模式汇总**：
- 简单 cogs（spymode / checkstatus / teamup_display / welcome）：大多数 cog 是手动 / 半手动重写，补充硬编码中文字串。
- 中等 cogs（achievements / role / invitation / giveaway / shop）：Python sed 脚本按 locale-key set 做 bracket-form `self.conf['KEY']` → `t('<cog>.KEY')` 替换。
- 复杂 cogs（ban / privateroom / tickets_new）：`messages:` 子树 + `messages.get('KEY', fallback)` 模式；写了 balanced-paren parser 处理含括号 / 跨行 default 的场景（见 ban 的 commit 描述）。
- voice_channel：channel_configs → DB（step 6a 已做）；文案层面 `control_panel.*` 子树暂留 yaml（nested 子树拆分留 follow-up）；只生成 yaml.example + locale 文件占位。

**清理的 latent bugs**：
- `ban_cog.save_config` 手动 JSON I/O + 双 reload 路径 → `await config.save_config(...)`（P2-3 已 commit）。
- `create_invitation_cog.save_config` 只写 `ignore_channel_ids` 一个字段（其它 mutation 全丢）→ `await config.save_config('invitation', self.conf)` 整体回写（P2-3 commit）。
- `role_cog.set_signature_requirement` 的 `config.save_config('role', ...)` sync-form AttributeError silent fail → `await config.save_config(...)`（P2-3 commit）。
- `tickets_new_cog` 两处 `db_manager.save_config('ticket_types', ...)` + `self.conf = await db_manager.get_config()` clobber → 删除 + 改 `ticket_types` CRUD（P2-5 commit）。

**识别但未修**（follow-up）：
- `welcome_cog.WelcomeDMView.member_count_button` 读取路径错（conf 顶层 vs dm 子树），silent fallback 到硬编码 "アルタ" 字符串 —— 保留原 behavior，不在本轮修。
- `migrate_config_to_yaml.py` 的 ID 脱敏 heuristic 漏 `admin_roles / admin_users / invite_link` 等（ban / tickets_new 的 yaml.example 手动脱敏）。脚本需扩 sanitizer 模式识别（Discord snowflake 大小判定或更广 key 白名单）。
- control_panel（voice_channel） + dm（welcome） + signature（role）的混合 data+text 子树：text leaf 抽 locale 需要脚本或 cog 层支持 nested classification。当前这些整块留在 yaml。

### 剩余工作（跨会话接手）

Config 2.0 sprint **整体收官**（step 0-9 全 ✅）；P1-7 slash 元数据本地化 ✅。下一轮可接手的 follow-up：

**🟡 important**：
1. 完整 P1-4 schema（pydantic / dataclass）+ per-cog locale key 对齐校验（slug-mapped 字段：starsign / mbti / gender / role_type_name）+ commands.yaml key 对齐校验（一个 locale_str `key=` 漏 yaml 节点时启动 warn / fail-fast）。
2. 迁移脚本 sanitizer 扩 ID 白名单或 snowflake-magnitude 检测（修 `admin_roles` / `admin_users` / `invite_link` 漏脱敏 bug）。
3. nested 子树文案抽 locale：`welcome.dm.*` / `role.signature.*` / `voicechannel.control_panel.{title,footer,messages,buttons,description_template}` 目前整块留在 yaml。

**🟢 nice-to-have**：
4. P1-3 大 cog 拆包（`tickets_new_cog` / `privateroom_cog` / `ban_cog` 按 PLAN `cog.py + views.py + modals.py + embeds.py + service.py`）。
5. P3-5 ruff（锁 P0-4 成果 + 未来裸 except 防线）。
6. `welcome_cog.WelcomeDMView.member_count_button` 的 conf 读取路径 bug（顶层 vs dm 子树，silent fallback 到硬编码 "アルタ"）。
7. P1-7 后续：`check_status.where_is_menu` 的 ContextMenu `name='Where Is'` 目前硬编码英文；Discord `ContextMenu.name` 不走 Translator 链（所有 context 不经 translate 路径），想本地化需要构造时手写 `name_localizations={Locale.chinese: '...'}` dict（与 slash name 的 ASCII 约束不同，Context Menu name 允许中文）。

---

### Upgrade 协议（生产部署执行）

老部署升级到这一组 commit 后的正确顺序（不可反过来）：

```bash
git pull
uv pip sync requirements.lock      # 装 ruamel.yaml
python tools/migrate_config_to_yaml.py   # 生成 yaml / locale / seed
# → review tools/migration_report.md, 按需更新 field_classification.yaml 重跑
python tools/seed_db.py            # channel_configs + ticket_types 灌 DB
# 重启 bot
```

**跳过 `seed_db.py` 会发生**：auto-create 房间入口全丢（`voicechannel.channel_configs` 表空）、所有 ticket type 消失（`ticket_types` 表空）。JSON fallback 兜不了 DB-bound 字段。

---

**下一步**：剩余 11 cog 的 `self.conf['messages']` → `t()` 迁移（每 cog 一个 commit，按 PLAN step 7 的"use count 升序"建议顺序）。每个 cog 迁完后更新本文件 status。
