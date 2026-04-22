# 重构进度追踪

> 与 [REFACTORING_PLAN.md](./REFACTORING_PLAN.md) 并行，记录每条 P 任务的完成状态、实施笔记、关键决策。
> **Context 爆掉重开时从这里恢复状态，决定下一步。**

规则：
- 每条 P 任务的 commit message 必须带 `(P0-4)` / `(P0-1)` 等标签，便于 `git log --grep='(P0-4)'` 精确定位。
- 每完成一条就更新本文件（状态改为 ✅ + 写实施笔记），与该任务的源码改动**分两次 commit**（源码一次，progress 更新一次；progress 更新的 commit message 用 `docs: track progress after <task>`）。
- 状态图例：⬜ 未开工 / 🔄 进行中 / ✅ 完成 / ⏸ 暂停 / ❌ 放弃

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
| P0 | P0-3d voice_channel 补 db manager | ⬜ | 下一步；最重，放最后 |
| P1 | P1-5 日志 rotation | ⬜ | 下一轮 |
| P1 | P1-2 ban_cog 迁 cog_load | ⬜ | 下一轮 |
| P1 | P1-1 命令同步逻辑 | ⬜ | 下一轮 |
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
