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
| P0 | P0-1 giveaway 抽 db | ⬜ | 下一步 |
| P0 | P0-2 privateroom 直连规范化 | ⬜ | |
| P0 | P0-3a check_status 补 db manager（含建表竞态修复） | ⬜ | 内部最优先 |
| P0 | P0-3b notebook 补 db manager | ⬜ | |
| P0 | P0-3c create_invitation 补 db manager | ⬜ | |
| P0 | P0-3d voice_channel 补 db manager | ⬜ | 最重，放最后 |
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

## P0-1 ⬜ giveaway 抽 db

**状态**：待开工（下一步）

**目标**：把 `bot/cogs/giveaway_cog.py` 里所有 `aiosqlite.connect(self.db_path)` 直连迁到新建的 `bot/utils/giveaway_db.py` 的 `GiveawayDatabaseManager`。

**关键风险点**（REFACTORING_PLAN.md P0-1 已列）：
1. 20+ 处直连散布在 **cog 本体 + 辅助类（Modal/View/Form）**。
2. 辅助类获取 manager 的方式必须**全文件一致**——推荐显式 `db=` 构造参数传入（依赖显式、易测试），另一个选项是 `bot.get_cog('GiveawayCog').db`。
3. 参考现有 manager 风格：`ShopDatabaseManager`、`BanDatabaseManager`。

**开工步骤**：
1. `grep -n "aiosqlite" bot/cogs/giveaway_cog.py` 导出完整清单，逐行标记"cog 方法 / 辅助类"，建迁移映射表。
2. 确定辅助类获取 manager 的方式（推荐 `db=` 构造参数）。
3. 新建 `bot/utils/giveaway_db.py` + `GiveawayDatabaseManager`，迁 SQL。
4. `bot/utils/__init__.py` 导出 `GiveawayDatabaseManager`。
5. cog 里 `self.db = GiveawayDatabaseManager(...)`；所有 Modal/View 实例化点加 `db=self.db`。
6. 验收：`grep -n "aiosqlite" bot/cogs/giveaway_cog.py` 为空（含 import）。
7. 测试服跑一遍：创建 / 参与 / 退出 / 开奖 / 超时。

---

## P0-2 ⬜ privateroom 直连规范化

**目标**：`bot/cogs/privateroom_cog.py` 里仍直连 `aiosqlite.connect` 的点，改走已存在的 `PrivateRoomDatabaseManager`；manager 缺的方法就补。

**验收**：`grep -n "aiosqlite" bot/cogs/privateroom_cog.py` 为空或只剩 import。

---

## P0-3 ⬜ 其余 cog 补 db manager

**内部顺序（按文档风险排序）**：

1. **P0-3a check_status**：最高优先。`__init__:55` 启动 10min 循环任务、`status` 表的 `CREATE TABLE IF NOT EXISTS` 在 `on_ready:428-437` 才执行 —— 存在"任务先于建表"竞态。抽 manager 时把建表迁到 `cog_load`，顺手修掉竞态。
2. **P0-3b notebook**（342 行，小，练手）。
3. **P0-3c create_invitation**（606 行）。
4. **P0-3d voice_channel**（1094 行，最大，需评估新 `voice_channel_db.py` 还是扩展既有 manager）。

**终局验收**：`grep -rn "aiosqlite.connect" bot/cogs/` 为空。

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
