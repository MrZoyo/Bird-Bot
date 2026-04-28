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
- ruff E722 规则已加（P3-5）—— 裸 except 治理成果已有机器检查；全量 E/F/W/B 规则留 lint debt 任务

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
| P1 | P1-3 大 cog 拆包 | ✅ | tickets_new + privateroom + ban 三 pilot 全 ✅；service.py 统一评估留 follow-up |
| P1 | P1-3b 全量 cog 包化 + games 聚合 | ✅ | 三档全收官；`bot/cogs/` 顶层只剩包目录 + `__init__.py` |
| P1 | P1-3c tickets_new → tickets 历史命名清理 | ✅ | 282 处 grep 清零（代码层）；DB SQL 表名保留方案 A；migrate+seed LEGACY_NAME_MAP 落位 |
| P1 | P1-3d service.py 横扫 + ban probe | ✅ | 横扫后选 ban 做第一刀；纯 helper + Embed builder 入 `ban/service.py`，task/state 留 cog |
| P1 | P1-8a tickets_new ticket-type CRUD 返回值校验 | ✅ | 三处接 `ok` + 失败分支走 locale；新增 3 个 failure key |
| P1 | P1-8b giveaway initialize_database 迁 cog_load | ✅ | cog_load 先建表后 start task；on_ready 只留 load_giveaways |
| P1 | P1-8c feature flag 类型校验提示 / 行为对齐 | ✅ | `is_feature_enabled` 非 bool 改返 False，和 schema warning 对齐 |
| P2 | P2-1 数据库连接复用 | ✅ | 生命周期基础设施 + voice / achievement / shop 高频 manager 持久连接均完成 |
| P2 | P2-2 Schema 迁移机制 | ✅ | `schema_version` + 手写 migrations helper；首批接入 voice / privateroom / ban |
| P2 | P2-3 `save_config` 写回统一策略 | ✅ | 统一 YAML writer + 当前写回路径核对完成 |
| P3 | P3-1 依赖管理统一 | ✅ | `pyproject.toml` + tracked `uv.lock` 为主，`requirements.lock` 为兼容导出，`requirements.txt` 退役 |
| P3 | P3-2 硬编码路径梳理 | ✅ | repo-root path helper + main runtime path normalization + backup Path 化 |
| P3 | P3-3 清理空 bot.db | ✅ | 删除 tracked 0-byte root `bot.db`，保留 ignored `data/bot.db` |
| P3 | P3-4 补自动化测试 | ✅ | pytest smoke 覆盖配置/runtime metadata/log helpers、临时 JSON→YAML 迁移、后台 loop guard + 9 个 DB manager；Notebook 明确不纳入 |
| P3 | P3-5 引入 ruff / linter | ✅ | 只启用 E722 锁 P0-4；全量规则留后续 |
| P3 | P3-6 old 归档分支 | ✅ | tracked old_function/old_updates 转存 legacy-old-files-archive |
| P3 | P3-7 日志 id/name 双记录 | ✅ | fmt_user/fmt_channel/fmt_role + role/voice/tickets 首批 callsite |
| P3 | P3-8 NotebookCog 废弃 / 移除 | ✅ | runtime 入口移除；旧代码在 legacy-old-files-archive；DB 历史表保留 |

---

## 当前接手点（2026-04-27）

**P1-3d service.py 横扫 + ban probe 已完成**：`bot/cogs/` 顶层现在只剩 `__init__.py` 和包目录，不再有平面 `*_cog.py`。本轮横扫后没有直接动 tickets / privateroom，而是选 ban 做第一刀：
- `bot/cogs/ban/service.py` 新增无生命周期状态 helper：`parse_duration`、权限判断、管理频道判断、邀请链接校验、4 个通知 / DM Embed builder。
- `bot/cogs/ban/cog.py` 继续持有 Discord API 出口、DB 调用、`tempban_tasks` 与 task loop，避免过早搬状态。
- 顺手把邀请链接格式错误提示迁到 `ban.invalid_invite_link` locale key。

**P1-3b 全量包化历史 commit**：
- `c774018 refactor(shop role): split cogs into packages (P1-3b)`
- `a1ceefa chore(old_function): archive shop role pre-split cogs (P1-3b)`
- `777d3e2 docs: track progress after P1-3b Tier 3`

**P2-1a 生命周期基础设施已完成**：所有现有 DB manager 继承 `BaseDatabaseManager`，未迁移的 manager 关闭时仍等价 no-op；`DCGameServerHelperBot.close()` 会捕获当前 cog 上的 manager，先交给 discord.py 正常卸载 cog / 触发 `cog_unload()` 停后台 task，再关闭 manager。

**P2-1b voice 持久连接 probe 已完成**：`BaseDatabaseManager` 提供 opt-in 持久连接 helper；`VoiceChannelDatabaseManager` 复用单个 `aiosqlite.Connection`，每个 SQL 方法用 manager 级 `asyncio.Lock` 序列化，`initialize_database()` 打开连接、`close()` 释放连接。

**P2-1c achievement 持久连接 probe 已完成**：`AchievementDatabaseManager` 复用单个 `aiosqlite.Connection`，manager 级 `asyncio.Lock` 串行化所有 SQL；初始化建表、常规成就读写、月度榜单、语音 session、manual operation、shop 签到联查都走同一持久连接 helper。写失败会 `rollback()`，cursor 显式关闭。

**P2-1d shop 持久连接 probe 已完成**：`ShopDatabaseManager` 复用单个 `aiosqlite.Connection`，签到、余额、补签、transaction history、checkin embed 相关路径都走同一 manager 级 lock。余额+流水、补签+streak 重算这类多 SQL 路径保持在同一事务内，避免 public 方法嵌套锁导致死锁。

**P2-2 schema 迁移机制已完成基础设施 + 首批 payload**：新增 `bot/utils/schema_migrations.py`，提供 `schema_version` 表、`SchemaMigration`、`apply_schema_migrations()` 和 `add_column_if_missing()`。首批接入已有真实迁移逻辑：voice `temp_channels` runtime 列补齐、privateroom `renewal_reminder_sent` 补列、ban `tempbans` 唯一约束重建。

**当前测试策略（2026-04-25 用户决定）**：先把重构主线全部做完，再从头逐个功能做测试服全量验证；当前不因单个 probe 未跑测试服而阻塞后续重构。

**P2-3 `save_config` 写回统一策略已完成**：
- `bot/utils/config.py` 已有统一 `async save_config()`：ruamel round-trip、sibling tempfile、`os.replace`、写后 reload。本轮补了按 config name 串行化和 `deepcopy` 写入快照，避免管理员命令并发保存时 dump 到正在变动的对象。
- YAML 写回现行路径已核对：ban / tickets / invitation / role 均走 `await config.save_config(...)`；tickets 的 `self.conf` 会剔除 `ticket_types`，避免把 DB 子树写回 YAML。
- 已迁 DB 路径已核对：voice channel configs 不再有 `save_channel_configs`；ticket types 走 `TicketsDatabaseManager` 的 `list/upsert/rename/remove_ticket_type`，`tools/seed_db.py` 与 `tools/field_classification.yaml` 同步。
- 本轮额外把 `CreateInvitationCog.save_config()` 改为保存后回填 `self.conf`、`self.ignore_user_ids`、`self.ignore_channel_ids`，和 ban/tickets 的 reload 行为对齐。
- 提权验证已通过：`./.venv/Scripts/python.exe -m compileall bot`、`./.venv/Scripts/python.exe -X utf8 tools/check_locales.py`、`./.venv/Scripts/python.exe -m pip check`、`git diff --check`、`save_config` 临时目录 smoke。

**P3-1 依赖管理统一已完成**：
- `pyproject.toml` 现在维护直接依赖；`uv.lock` 已生成并从 `.gitignore` 放行，作为 canonical lock 进入 git。
- `requirements.txt` 已退役删除；`requirements.lock` 仅作为兼容导出，由 `uv export --format requirements.txt --no-hashes --no-emit-project --frozen --output-file requirements.lock` 从 `uv.lock` 生成。
- README / AGENTS / `tools/migrate_config_to_yaml.py` / `tools/seed_db.py` 的安装与升级协议已同步为 `uv sync`。
- `PySimpleGUI` 在 `pyproject.toml` 约束为 `<5`，避免依赖入口重构夹带 4.x → 6.x 大版本变化；本轮 lock 仍保持 `pysimplegui==4.60.5.1`。
- 本地工作区是 Windows `.venv` 暴露在 WSL 下；`uv sync --frozen --dry-run --python 3.12.3` 通过，但提示会替换 `.venv`。本轮未实际运行 `uv sync` 改这个环境，而是用 `./.venv/Scripts/python.exe -m pip install -r requirements.lock` 按兼容锁同步现有 Windows venv。
- 提权验证已通过：`uv lock --check`、`uv sync --frozen --dry-run --python 3.12.3`、`./.venv/Scripts/python.exe -m pip install -r requirements.lock`、`./.venv/Scripts/python.exe -m pip check`、直接依赖 import smoke、`./.venv/Scripts/python.exe -m compileall bot`、`./.venv/Scripts/python.exe -X utf8 tools/check_locales.py`、`git diff --check`。

**P3-2 硬编码路径梳理已完成**：
- 新增 `bot/utils/paths.py`：`PROJECT_ROOT` / `project_path()` / `resolve_project_path()` / `ensure_parent_dir()`，统一把相对运行时路径解析到仓库根目录。
- `bot/utils/config.py` 在 `main.yaml` load + schema 校验后，集中把 `logging_file` / `keyword_log_file` / `room_log_file` / `db_path` 规范成仓库绝对路径；各 cog / db manager 继续读 `main.db_path`，不逐个改业务文件。
- `bot/main.py` 的 rotating log handler 会先解析路径并创建父目录；`CheckStatusCog` 的 `/check_log` 读取路径也显式走 helper，兼容缺省 `keyword_log_file` / `room_log_file`。
- `BackupCog` 不再用 `./backup/...` + `os.path`，改成 `Path` 目录和文件操作，且不会把 `.gitkeep` 当成可轮换备份删除。
- README / AGENTS / `bot/config/main.yaml.example` 已同步：默认主库是 `data/bot.db`，相对 runtime path 按仓库根目录解析。
- 提权验证已通过：路径解析 smoke（从非仓库 CWD 加载 main config）、changed-module import smoke、`./.venv/Scripts/python.exe -m compileall bot`、`./.venv/Scripts/python.exe -X utf8 tools/check_locales.py`、`./.venv/Scripts/python.exe -m pip check`、`git diff --check`。

**P3-3 清理根目录空 `bot.db` 已完成**：
- 清理前确认：`./bot.db` 为 0 bytes 且被 git 跟踪；`./data/bot.db` 为 602112 bytes，属于真实运行库并被 `.gitignore` 的 `data/*.db` 保护。
- 已删除 tracked root `bot.db`，并在 `.gitignore` 加 `/bot.db`，避免旧启动路径或手工误操作再次把根目录库带回 git。
- 未触碰 `data/bot.db`、`data/*.log`、`backup/` 里的真实运行数据。
- 验证：`find . -maxdepth 2 -name 'bot.db' -printf '%p %s bytes\n'` 只剩 `./data/bot.db 602112 bytes`；`git ls-files bot.db data/bot.db` 为空；`git check-ignore -v bot.db data/bot.db` 命中 `/bot.db` 和 `data/*.db`。

**P3-4 补自动化测试已完成并扩展（2026-04-27）**：
- `pyproject.toml` 新增 `project.optional-dependencies.test = ["pytest>=8.0"]` 和 pytest 配置；`uv.lock` 已通过 `uv lock` 更新，新增 pytest 及其传递依赖。`requirements.lock` 仍是 runtime 兼容导出，不包含 test extra。
- 当前 smoke suite 覆盖确定保留的离线路径：配置模板 / runtime `COG_SPECS` import、log helpers、CheckStatus、Tickets、VoiceChannel、PrivateRoom、Ban、Role、Giveaway、Shop、Achievement。所有 DB 测试均使用 `tmp_path` 临时 sqlite，不触碰真实 `data/bot.db`。
- 按用户要求新增单独临时迁移测试：`tests/test_migrate_config_to_yaml_temp.py` 用 `tmp_path` 验证旧 `config_*.json` 能转换为新 YAML / `.yaml.example` / locale / `migration_db_seed.json` / report，并覆盖 `tickets_new→tickets` legacy mapping；已明确跳过移除系统的 `config_tickets.json`（旧 ticket）和 `config_rating.json`。该测试服务于升级窗口，未来 JSON 迁移脚本退役时可一并删除。
- `tests/test_task_helpers.py` 覆盖未登录客户端下后台 `tasks.loop.before_loop` 自动 stop 的 helper，避免离线 cog-load smoke 污染日志。
- `tests/test_tickets_db.py` 在原 ticket type/config 基础上新增工单生命周期、成员、接单、关闭、统计、历史 smoke。
- 本轮写 ban smoke 时发现并修复真实日期 bug：`BanDatabaseManager.get_tempban_stats()` / `cleanup_old_records()` 原用 `utcnow().replace(day=day-30)`，每月前 30 天会 `ValueError`；已改为 `timedelta(days=...)`。
- 临时写过的 `test_notebook_db.py` 已删除；NotebookCog 已纳入 P3-8 移除计划，P3-4 不给 notebook 增加测试覆盖，避免把待移除功能固化。
- README / AGENTS / `REFACTORING_TEST_CHECKLIST.md` 已同步：测试 extra 用 `uv sync --extra test`，自动化 gate 用 `python -m pytest`；Discord 交互路径按模块清单在测试服手工验证。
- 提权验证已通过：`./.venv/Scripts/python.exe -m pytest -q`（21 passed，只有 discord.py `audioop` deprecation warning）、`./.venv/Scripts/python.exe -m ruff check bot tests`、`./.venv/Scripts/python.exe -m compileall bot tests`、`./.venv/Scripts/python.exe -X utf8 tools/check_locales.py`、`./.venv/Scripts/python.exe -m pip check`、`uv lock --check`、`uv sync --frozen --dry-run --extra test --extra lint --python 3.12.3`、`git diff --check`。

**P3-8 NotebookCog 废弃 / 移除已完成**：
- 用户于 2026-04-27 确认 notebook 希望移除；此前 PLAN/PROGRESS 只有 notebook 的历史重构记录，没有 active removal 条目，已在 `REFACTORING_PLAN.md` 新增 P3-8。
- 已移除 runtime registration / feature flag / utils export / slash metadata / README 现役功能段落 / 测试清单 active 项；旧代码先归档到 `old_function/`，随后在 P3-6 转存到 `legacy-old-files-archive` 分支，不继续从 runtime import。
- 归档路径在 `legacy-old-files-archive` 分支：`old_function/cogs/notebook/`、`old_function/notebook_db.py`。
- DB 历史表 `event_logs` / `admins` 默认保留，不在 P3-8 中删除生产数据；如未来要清表，单独走 schema migration / 数据归档任务。
- 验证：runtime 范围 `rg -n "NotebookCog|notebook" bot/main.py bot/cogs bot/utils bot/config bot/locales README.md REFACTORING_TEST_CHECKLIST.md` 只剩测试清单里的明确已移除说明；`./.venv/Scripts/python.exe -m compileall bot tests`、`./.venv/Scripts/python.exe -X utf8 tools/check_locales.py`、`./.venv/Scripts/python.exe -m pytest -q`、`./.venv/Scripts/python.exe -m pip check`、`git diff --check` 均通过。

**P3-5 ruff / linter 已完成**：
- `pyproject.toml` 新增 `lint` extra（`ruff>=0.8.0`）和 Ruff 配置；当前只启用 `E722`，排除 `old_function` / `old_test`，避免归档代码和全仓风格债影响主线。
- `uv.lock` 已锁定 `ruff==0.15.12`；runtime `requirements.lock` 重新导出后无差异，不包含 lint extra。
- README / AGENTS 已同步 `uv sync --extra lint` 与 `python -m ruff check bot tests`。
- 提权验证已通过：`./.venv/Scripts/python.exe -m ruff check bot tests`、`./.venv/Scripts/python.exe -m pytest -q`、`./.venv/Scripts/python.exe -m compileall bot tests`、`./.venv/Scripts/python.exe -X utf8 tools/check_locales.py`、`./.venv/Scripts/python.exe -m pip check`、`uv lock --check`、`uv sync --frozen --dry-run --extra test --extra lint --python 3.12.3`、`uv export --format requirements.txt --no-hashes --no-emit-project --frozen --output-file requirements.lock`、`git diff --check`。

**P3-6 old 归档分支已完成**：
- 新建分支 `legacy-old-files-archive`，提交 `772344b docs: index legacy old file archive (P3-6)`；分支内保留 main 原 tracked `old_function/` 与 `old_updates.md`，并新增 `LEGACY_ARCHIVE_INDEX.md` 统计说明。
- 归档统计：32 个旧文件 / 16939 行，其中 `old_function/cogs/` 13 个、`old_function/config/*.json.example` 16 个、legacy DB manager 2 个、`old_updates.md` 1 个。
- main 分支删除 tracked `old_function/` / `old_updates.md`，新增 `LEGACY_ARCHIVE.md` 指向归档分支；README / AGENTS / `.gitignore` 已同步。`old_test/` 仍是 ignored 本地实验目录，不纳入已脱敏归档分支。

**P3-7 日志 id/name 双记录已完成**：
- `bot/utils/log_helpers.py` 新增 `fmt_user` / `fmt_channel` / `fmt_role`，统一输出 `name (id)`；raw id 兜底为 `unknown (id)`，不为日志补做 Discord API fetch。
- `bot/utils/__init__.py` 导出三个 helper；`tests/test_log_helpers.py` 覆盖 display_name 优先、channel/role name、raw id fallback。
- 首批替换范围：`bot/cogs/role/views.py` 的角色授予 / 移除 / starter role hierarchy 日志；`bot/cogs/voice_channel/cog.py` 的控制面板恢复、room、creator 日志；`bot/cogs/tickets/cog.py` 的 ticket thread、admin、creator 错误日志。
- README / AGENTS / `REFACTORING_TEST_CHECKLIST.md` 已同步新日志规则和测试服抽查项。

**测试准备收尾（2026-04-27）**：
- `REFACTORING_TEST_CHECKLIST.md` 已从历史 P0 checklist 重写为“自动化 gate + 按模块测试流程”。用户后续跟着该文件测试，不再需要从旧任务顺序反推功能路径。
- 当前自动化基线：`pytest` 为 21 passed；ruff、compileall、locale check、pip check、`uv lock --check`、test/lint extra dry-run 和 `git diff --check` 均通过。覆盖配置/runtime metadata/log helpers、主要 DB manager smoke、临时 JSON→YAML 迁移 smoke 和后台 loop 离线 guard。手工清单仍覆盖 Discord 权限、按钮、command sync、后台任务、DM 失败等必须真实测试服验证的路径。
- 启动 smoke 补遗：用户真实启动暴露 `WelcomeCog: 'welcome_text'`、`ShopCog: 'checkin_button_daily_text'`。已修复 Shop 按钮文案从 locale 读取；Welcome 在本地 YAML 缺 `welcome_text` 时用 `welcome_text_fallback` 不阻塞加载；同时修正 Welcome 资源路径为仓库根 `resources/`，并把迁移分类里的 `welcome_text` 显式留在 YAML。真实本地配置下 `create_bot()` + `setup_bot()` 不连接 Discord 的 load smoke 已加载 15 个 cog。
- 离线 load smoke 补遗：未登录客户端直接跑 `setup_bot()` 会让后台 `tasks.loop.before_loop` 的 `wait_until_ready()` 抛 `RuntimeError("Client has not been properly initialised")`，日志表现为多条 `Task exception was never retrieved`。新增 `bot.utils.task_helpers.wait_until_ready_or_stop()`，离线环境自动 stop loop；真实登录后的 bot 仍正常等待 ready。

**下一棒默认**：P0-P3 重构主线已全部收齐。下一步先跑 checklist 的自动化 gate，再按模块进入测试服全量功能验证。

**环境验证规则**：环境 / import / 启动验证必须提权到沙箱外跑真实环境。项目 Windows `.venv` 已用 `ensurepip` 补出 pip，并通过 `./.venv/Scripts/python.exe -m pip install -r requirements.lock` 按 lock 补齐依赖（含 `ruamel-yaml==0.19.1`）；本轮 project venv import smoke 已通过。后续如果项目 venv 再缺包，直接补环境，不只记录缺失。

**当前工作区预期**：只剩未跟踪 `.codex`（本地状态，不碰）。

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
- 已加 ruff `E722` 规则锁死成果 —— P3-5 已完成；更宽的 E/F/W/B 规则未开
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
2. ✅ **P0-3b notebook** — 完成（2026-04-23）
3. ✅ **P0-3c create_invitation** — 完成（2026-04-23）
4. ✅ **P0-3d voice_channel** — 完成（2026-04-23）

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
- `synccommands` 手动命令里的 `except Exception` 仍是宽捕获（非本次 P1-1 范围 —— P0-4 已通过，这一处原本就在豁免名单外；P3-5 只锁 naked `except:`，若要继续收窄宽捕获需另开 follow-up）。
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
| 8 (P1-4) | 启动 schema 校验 | ✅ dataclass MainConfig + validate_main_config + tools/check_locales.py 静态 key 对齐（含 commands.yaml P1-7 收尾） |
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

### nested 子树文案抽 locale（2026-04-23）

**Commit grep**: `git log --grep='voicechannel.*control_panel'` / `git log --grep='role.*signature'`

**两条 source commit**：
1. `refactor(voicechannel): extract control_panel text to locale` —— `control_panel.{title,footer,description_template,buttons,messages}` 从 yaml 抽到 `bot/locales/zh_CN/voicechannel.yaml`；yaml 只剩 `control_panel.colors.{public,private}` 两个 int。Cog 的 `self.messages` / `self.button_labels` / `self.control_panel_conf` 三个 dict 缓存全删，按钮 label + 所有 message 走 `t('voicechannel.control_panel.*')`。28 key。
2. `refactor(role): extract signature text to locale` —— `signature.{pickup_*,modal_*,*_message,admin_check_*}` 等 30 text key 抽到 locale；yaml 只剩 `signature.{max_length,max_changes_per_week,time_requirement,helper_role_id}` 四个数据字段。cog 的 `self.signature_config` 整体删（没 caller 了），`SignatureModal` / `SignatureView` 的 callbacks + `RoleCog` 的 admin 命令全走 t()。顺带把硬编码 `"更新签名失败，请稍后重试。"` 也抽了（新 key `signature.update_failed_message`）；loop var `t` 改名 `ts` 避免 shadow i18n helper。

**welcome.dm 显式不抽**（决策记录）：
- `welcome.dm.description0_title` = `"小鸟知道你在想什么・永久邀请链接"` —— 含服务器品牌名
- `welcome.dm.description1_title` = `"https://discord.gg/Birdgaming"` —— 每部署的邀请 URL
- `welcome.dm.description2_title` = `"🐦小鸟知道你在想什么・欧服综合游戏社区 🏮"` —— 品牌 + slogan
- `welcome.dm.description2[*]` = 服务器介绍段落（深绑定本服）
- `welcome.dm.footer` = `"小鸟知道你在想什么・欧服综合游戏社区"` —— 品牌 footer
- `welcome.dm.member_count_button` = `"你是小鸟的第 {member_count} 名成员"` —— 品牌 + placeholder

这些内容 60% 以上和本部署的"小鸟"品牌 / 真实邀请链接深绑，和一般意义上"可翻译的 UI 文案"不同。把它们搬到 `bot/locales/zh_CN/welcome.yaml` 会让 locale 文件承担"deploy-specific 配置"的角色，违反 P1-6 locale vs yaml 的边界（locale = 通用翻译，yaml = 每部署数据）。留 yaml 即可，后续若有多部署再说。

对应地 `check_locales.py` 目前不会抱怨：`welcome.yaml` locale 里保留图片文案和 `welcome_text_fallback` 等通用 key；部署专属 `welcome_text` 仍留在 config YAML，不进 tracked locale。

**验收**：`tools/check_locales.py` 从 502 t() key 长到 553，全部映射到 locale 字符串叶子，零 MISSING。三个 follow-up（voicechannel / role.signature / welcome.dm）全部闭环（后者以显式决策结束，不是遗漏）。

---

### sanitizer 扩 ID 白名单 + URL + 嵌入 snowflake（2026-04-23）

**Commit grep**: `git log --grep='sanitizer snowflake'`

**动的**：`tools/migrate_config_to_yaml.py`。

**三层防御**（由窄到宽，首个匹配即终止路由）：
1. `ID_KEY_PATTERNS` 扩到包含 `admin_roles` / `admin_users` / `mod_roles` / `mod_users` / `blocklist` / `banlist`（无 `_id` 后缀的 snowflake 列表）。
2. `URL_KEY_PATTERNS`（`_link` / `_url` / `invite_link` / `invite_url`）走 `_sanitize_url_like` 把整串换成 `https://discord.gg/YOUR_INVITE_CODE` 占位。
3. `_sanitize_snowflake_scalar` 兜底：
   - scalar int / 纯数字 str ≥ `10**17` → 换 `1145141919810`（schema drift 时的 fail-closed）。
   - 自由文本里嵌的 Discord token（invite URL、`discord.com/channels/.../...` deep-link、自定义 emoji `<:name:id>`、`<@id>` / `<#id>` / `<@&id>` mention）用预编译 regex 做字段级替换，只改 ID 部分，周围中文 / 英文 prose 原样保留。

**验收**：对 14 个 `old_function/config/config_*.json` 端到端跑 `migrate_config_to_yaml` → `sanitize_for_example` → YAML dump；每个生成的 `.yaml.example` 只剩 `1145141919810`（sanitizer 占位）和 `123456789012345678`（原始 JSON 里模态对话框的文档占位符）。零真实 snowflake、零真实 invite URL、零 guild/channel deep-link 残留。

**为什么要 fail-closed 兜底**：原脚本的 heuristic 是白名单 —— 任何键名打错或没列到的新字段都会静默漏过。三层结构里第三层（snowflake 规模 + 嵌入 regex）确保即使前两层都没对上，真 ID 仍被换掉。Discord snowflake 从 2017 后就稳定 ≥ 10^17，所以规模阈值几乎零误伤（"1145141919810" 这个经常被引用的 meme placeholder 恰好也满足阈值，刚好一起被当占位符处理，无副作用）。

---

### P1-4 ✅ 完整 schema + 静态 locale key 对齐（2026-04-23）

**Commit grep**: `git log --grep='(P1-4)'`（原最小版本）+ `git log --grep="(P1-4)"` 新 commit。latent-bug 修复 commit：`git log --grep='ban.*flatten'`。

**三条 commit**（单次推进）：
1. `fix(ban): flatten locale yaml to match 't(ban.KEY)' call shape` —— step 7 的 ban 迁移把 yaml 留在 `messages:` 子树下，但 cog 调 `t('ban.no_permission')`（扁平）—— 每次 `/ban` / `/tempban` / `/mute` / 管理员命令都会 KeyError 从未测过。扁平化 yaml（`messages:` 去掉、66 key 提顶）修掉。
2. `feat(config): dataclass schema + static locale key checker (P1-4)` —— 新建 `bot/utils/config_schema.py` + `tools/check_locales.py` + 接到 `config.py`。
3. `docs: track progress after P1-4 ...`（**本 commit**）

**bot/utils/config_schema.py**：
- `MainConfig` dataclass：每个 field 有类型 + 默认值；required (`token` / `logging_file` / `db_path` / `guild_id`) + optional + defaulted (`locale='zh_CN'` / `log_backup_count=14`)。
- `validate_main_config(data) -> List[str]`：tolerant 返 warning list，不 raise；applies defaults in-place；检测 non-dict root / wrong-type values / feature 非 bool。
- **零新依赖**（纯 dataclass + typing），不引 pydantic。
- **留给后续**：per-cog schemas（`admin_roles: List[int]` / `ticket_types` 固定 key 等）shape-variable，PLAN 建议 P1-3 拆包时一并做。

**bot/utils/config.py `_verify_main_config` 接到 schema**：
```python
def _verify_main_config(self) -> None:
    from bot.utils.config_schema import validate_main_config
    for warning in validate_main_config(self._configs['main']):
        print(warning)
```
- 3 行，替代原来的 required_keys 列表 + setdefault 双重维护。
- 行为等价：缺 required key 仍然 print warning + 设 None，bot 继续启动。

**tools/check_locales.py**：
- walk `bot/cogs/*.py`：两条 regex（保守、literal-string-only）抽 `t('ns.key')` / `locale_str("english", key="ns.key")`。
- walk `bot/locales/<lang>/*.yaml`：递归所有 string leaf 转 dot-path。
- 两组比：t() keys 对 per-cog yaml、locale_str keys 对 `commands.yaml`。
- 报 MISSING（cog 引用但 yaml 缺）/ ORPHAN（yaml 有但没人引用，info）。exit code 非零 = 有 MISSING。
- 设计约束：动态 key（ternary / f-string / 函数调用返回 key）不抓 —— 工具 header 明说是 "high-confidence lower bound"，不是全集。
- **运行结果**（fix ban 扁平化之后）：502 t() keys + 170 locale_str keys 全部对齐，`RESULT: All referenced keys are present ✅`。

**验收**：
- `/tmp/yaml-venv/bin/python tools/check_locales.py` exit 0。
- `python3 -m compileall -q bot/` 通过。
- dataclass schema 的 4 个 smoke case（minimal / missing required / wrong type / non-dict）全通过。
- 已知漏报（高 confidence）：voice_channel / welcome 的 nested 子树留 yaml，工具报 "no t() references" 是 info 不是 bug。

**本轮顺手修的 latent bug（step 7 regression 清算）**：
- `ban_cog` 的 99 处 `t('ban.KEY')` 调用全部 KeyError —— yaml 层级与 cog 约定不匹配。flatten yaml 修好；P1-4 工具立即收敛到 0 MISSING。
- 没有其他 cog 有类似问题（check_locales.py 输出确认 privateroom / tickets_new / teamup_display 的 nested `messages.` 层级与 cog 里 `t('xxx.messages.*')` 对齐）。

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
- ~~`welcome_cog.WelcomeDMView.member_count_button` 读取路径错（conf 顶层 vs dm 子树），silent fallback 到硬编码 "アルタ" 字符串~~ —— 已在 `fix(welcome)` 修复（见下节）。
- `migrate_config_to_yaml.py` 的 ID 脱敏 heuristic 漏 `admin_roles / admin_users / invite_link` 等（ban / tickets_new 的 yaml.example 手动脱敏）。脚本需扩 sanitizer 模式识别（Discord snowflake 大小判定或更广 key 白名单）。
- ~~control_panel（voice_channel） + dm（welcome） + signature（role）的混合 data+text 子树~~：voicechannel.control_panel ✅ 抽到 locale（见下"nested 子树文案抽 locale"一节），role.signature 同样 ✅，welcome.dm 显式决定不抽（60%+ 条目 deploy-specific，抽会违反 locale/yaml 边界）。

---

### P1-3 ✅ 大 cog 拆包 pilot：tickets_new（2026-04-24）

**Commit grep**: `git log --grep='(P1-3'`

**做了什么**：`bot/cogs/tickets_new_cog.py`（2666 行）拆成 `bot/cogs/tickets_new/` 包：

| 文件 | 类 | 行数 |
|---|---|---|
| `embeds.py` | `EmbedColors` | 13 |
| `modals.py` | `TicketConfirmModal` / `AddUserModal` / `CloseTicketModal` / `TicketTypeModal` | 420 |
| `views.py` | `TicketCreateView` / `TicketThreadView` / `AdminTypeSelectView` / `TypeSelectView` / `DeleteConfirmView` | 352 |
| `cog.py` | `TicketsNewCog`（slash commands + service-like methods） | 1910 |
| `__init__.py` | re-export of `TicketsNewCog` | 3 |

**保守选择**：**没抽 `service.py`**。原 `is_admin_for_type` / admin CRUD / `format_admin_list` / `_format_admin_entries` / `add_admins_to_ticket` 等 10 个 service 候选方法都留在 cog.py。理由：抽出会改 `self.ticket_types` / `self.conf` 的归属边界，跨类引用点多；单独评估一次 commit 更清晰；privateroom/ban pilot 做同样保守选择一致性更好。未来需要的话作为二轮 follow-up。

**机械性要点**：
- `views.py` / `modals.py` 里的类以 `cog` 作构造参数（原本就是这个 pattern），没 behavioural 变化。
- modals ↔ views 的 cycle（`CloseTicketModal.on_submit` 调 `TicketThreadView.create_with_status`）靠 **lazy import** 打破：`from .views import TicketThreadView` 写在 method 体内。其它方向单向（`views.py → modals.py` 顶层 import，没有反向）。
- `custom_id` 是参数化字符串（`create_ticket_{type_name}` / `accept_ticket_{thread_id}` 等），不依赖 class path —— `bot.add_view(...)` 注册的 persistent view 跨模块迁移安全。
- `bot/main.py:93` 的 `module_path` 由 `"bot.cogs.tickets_new_cog"` 改成 `"bot.cogs.tickets_new"`；loader 用 `importlib.import_module + getattr`，不需要 `setup(bot)` 入口。
- 旧文件 `git mv bot/cogs/tickets_new_cog.py old_function/cogs/tickets_new_cog_pre_split.py`（CLAUDE.md 约定的 deprecated-snapshot 位置）。

**顺手修的 latent bug**：
- 原 `tickets_new_cog.py` 完整文件 **没有 `from bot.utils.i18n import t`**，但 130+ 处 `t(...)` 调用。每次 ticket 按钮点击的 handler 走到 `t()` 就会 NameError（按 method body lazy-eval 的原因没在 import 时炸，但任何一次 runtime 触发都死）。新包的 modals.py / views.py / cog.py 每个都补齐了正确 import。
- `tools/check_locales.py` 的 `COGS_DIR.glob('*.py')` → `rglob('*.py')`（带 `__pycache__` 过滤）。flat glob 看不到 package 子文件，本 commit 前它报 182 条 `tickets_new.yaml` orphan false positive；修复后 553 t() key + 170 locale_str key 全部 resolve。顺便 forward-compatible 下一轮 privateroom/ban pilot。

**验证**：
- `python -m py_compile` 五个 .py 文件 OK。
- Runtime import smoke test（stub 掉 discord / bot.utils 依赖）：`bot.cogs.tickets_new` 正常 load，`TicketsNewCog.__module__ == 'bot.cogs.tickets_new.cog'`，modals ↔ views lazy-import cycle 可解。
- `python tools/check_locales.py` ✅ all keys present。
- **未做**：测试服 `/tickets_init` → 创建 → accept → close 全链路跑一遍（依赖 token / DB / 真服务器）。下次触摸 tickets 流程 前建议跑一次。

**剩下 pilot**：
- `ban_cog.py`（1430 行）—— 按同模式拆。views / modals 体量小，但 service 候选（ban 超时任务、冻结期判断等）明显；二轮再决定是否抽 service.py。

### P1-3 ✅ 大 cog 拆包 pilot：privateroom（2026-04-24）

**Commit grep**: `git log --grep='privateroom.*P1-3'`

**做了什么**：`bot/cogs/privateroom_cog.py`（1993 行）按 tickets_new 同模板拆成 `bot/cogs/privateroom/` 包：

| 文件 | 类 | 行数 |
|---|---|---|
| `modals.py` | `PurchaseModal` | 85 |
| `views.py` | `ConfirmPurchaseView` / `PrivateRoomShopView` / `ResetConfirmView` / `RoomListView` | 254 |
| `cog.py` | `PrivateRoomCog` + task loops + 业务方法 | 1655 |
| `__init__.py` | re-export | 3 |

**与 tickets_new pilot 的差异**：
- **没 `embeds.py`**：原文件没 `EmbedColors` 常量类，也没独立的 embed builder function，所有 `discord.Embed(...)` 都是 cog method 里 inline 构造。没得抽。
- **没 lazy import**：`PurchaseModal.on_submit` 只回调 `self.cog.create_private_room` / `process_advance_renewal` / `restore_private_room` 等 cog 方法，**完全不引用任何 view**。views → modals 是唯一方向（`ConfirmPurchaseView.confirm_callback` 创建 `PurchaseModal`），顶层 `from .modals import PurchaseModal` 即可。
- **service 候选更薄**：没 tickets_new 那种 `is_admin_for_type` / admin CRUD 那一坨明显的业务层；基本就是 shop + privateroom DB 交互 + 折扣计算，留在 cog 里问题不大。

**Persistent view**：本 cog **没调 `bot.add_view(...)`**（grep 确认）—— 所有 `PrivateRoomShopView` / `ConfirmPurchaseView` 都是 ephemeral（每次 interaction 重新 `view=PrivateRoomShopView(self)`）。`custom_id` 用字符串字面量（`confirm_purchase` / `purchase_privateroom` 等），跨模块也不破链。

**顺手清的**：cog.py 的 import 块去掉两个死 import：
- `import json` —— 全文件零引用。
- `from typing import List` —— 只在一条 docstring 文案里出现（`"List all active private rooms"`），不是类型注解。
- 保留了 `Optional / Dict / Tuple / Any` —— 都在真实 annotation 里。

**已知小瑕疵（识别但未修）**：
- `RoomListView.format_page` L300-301 两条中文裸字面量（`"用户 ID: {user_id}"` / `"未找到 (ID: {room_id})"`）—— 其它地方全走 `t()`，这两条没迁。
- `cog.py setup_shop` L503 裸字面量 `"指定的频道必须是文字频道。"`、`reset_system` L467 `f"重置系统时出错: {e}"`、`list_rooms` L1565 `"目前没有活跃的私人房间。"` / `f"获取房间列表时出错: {e}"` 几条错误/提示消息未走 i18n。
- 这些都是拆包前就存在的问题，P1-7 配的 `t()` 迁移 sprint 里也没覆盖。留作 follow-up，本 pilot 不扩大 scope。

**验证**：
- `python -m py_compile` 四个 .py + main.py OK。
- Runtime import smoke test（stub discord / bot.utils）：`PrivateRoomCog.__module__ == 'bot.cogs.privateroom.cog'`，4 view + 1 modal 类全部可导入。
- `tools/check_locales.py`：553 t() key + 170 locale_str key 全 resolve（与 tickets_new pilot 后相同，无 regression）。
- **未做**：测试服 `/privateroom_init` → `/privateroom_setup` → 购买 → 续费 / 恢复全链路跑一遍（依赖 token / 真服务器 / seeded shop 余额）。

### P1-3 ✅ 大 cog 拆包 pilot：ban（2026-04-24）

**Commit grep**: `git log --grep='(ban):.*P1-3'`

**做了什么**：`bot/cogs/ban_cog.py`（1430 行）按 tickets_new / privateroom 同模板拆成 `bot/cogs/ban/` 包。P1-3 三 pilot 全部收官：

| 文件 | 类 | 行数 |
|---|---|---|
| `views.py` | `RejoinServerView` | 11 |
| `cog.py` | `BanCog` + 2 `@tasks.loop` + 13 slash commands + 7 通知/调度方法 | 1418 |
| `__init__.py` | re-export | 3 |

**与前两棒的差异**：
- **UI 层极薄**：只有 1 个 View（`RejoinServerView`，9 行；tempban DM 上一个静态 link button）。**0 Modal**，**0 EmbedColors**。所以没 modals.py 也没 embeds.py。
- **没 lazy import**：无 modal → view 反向依赖（没 modal）。单向 `cog.py → views.py` 顶层 import 即可。
- **没 persistent view**：`bot.add_view()` 从未调用；`RejoinServerView` 每次 `send_tempban_dm` 构造一次即用即弃。

**保守选择：没抽 `service.py`**。这一棒原本是"评估抽 service"的候选点（handoff 块里明说），做了 Explore cross-reference 报告（见 session transcript），结论：

- **值得抽**：`parse_duration` + `has_ban_permission` + `is_admin_channel_only_check` 三个纯/半纯函数 ~40 行；`recover_tempbans` + `check_expired_tempbans` 两个 task body ~70 行；`send_*_notification` / `send_*_dm` 四个 embed-builder + send 混合方法 ~200 行（只能分离 embed 构建 + 保留 channel.send 在 cog）。
- **预计收益**：cog.py 从 1418 → ~1050 行（~-370 行）。
- **拒绝抽的理由**：三棒保守一致性 > 单棒收益。前两棒（tickets_new / privateroom）都没抽 service，第三棒单独抽会破一致性；而且 `schedule_unban_with_db` 依赖 `self.tempban_tasks` 字典的状态，完全抽需要把字典也 move 到 service 或注入，跨类 state 管理边界要重新设计。更合理的是**三家一起**在一轮 follow-up 里按统一模式抽 service（见"🟢 nice-to-have"）。
- service 候选方法清单见下（留给 follow-up）：
  - **task-driven**：`recover_tempbans` (L84-151), `check_expired_tempbans` (L153-198), `cleanup_tempbans` (L531-536)
  - **pure-ish 业务**：`parse_duration` (L225-248), `has_ban_permission` (L205-223), `is_admin_channel_only_check` (L70-82)
  - **state-coupled**：`schedule_unban_with_db` (L501-529) — 依赖 `self.tempban_tasks`，抽要配字典转移或接口注入。
  - **embed builder + send 混合**：`send_ban_notification` (L250-337), `send_mute_notification` (L339-393), `send_tempban_dm` (L395-449), `send_mute_dm` (L451-499) — 抽 `build_*_embed` 留 `channel.send` 在 cog。

**顺手清的死代码**：
- `from bot.utils import ... check_channel_validity ...` —— 该 cog 从来不用；注释里提了两次"same logic as check_channel_validity"但 import 进来的 symbol 从没被 call。
- 文件底部 `async def setup(bot): await bot.add_cog(BanCog(bot))` —— `bot/main.py` 的 loader 是 `importlib.import_module + getattr + bot.add_cog(cls(bot))`，不走 discord.py 的 extension-style `setup()` 入口。Dead code from pre-COG_SPECS era。

**已知小瑕疵（识别但未修）**：
- 中文字面量硬编码：`ban_admin_list` L882 `(不存在)`、L904 同上、L925 同上；L943 `"🔗 邀请链接"` 字段名；`ban_set_invite_link` L1283 格式提示；`ban_list_tempbans` L1350/1356/1361 的 embed field 文案 + 页脚。共 ~10 条应走 `t()` 但没走。
- 11 处 `except Exception as e:`（非 naked `except:`，不违反 P0-4 的 E722），可以再收窄成 `discord.Forbidden` / `asyncio.TimeoutError` 等具体异常 —— 留作 follow-up。

**验证**：
- `python -m py_compile` 三个 .py + main.py OK。
- Runtime import smoke test（stub discord / bot.utils）：`BanCog.__module__ == 'bot.cogs.ban.cog'`，`RejoinServerView` 加载 OK。
- `tools/check_locales.py`：553 t() + 170 locale_str key 全 resolve（与前两棒 pilot 后相同，无 regression）。
- **未做**：测试服 `/ban` → `/tempban` → `/mute` → tempban 到期自动解封 + 重启恢复的完整链路跑一遍（依赖 token / 真 guild / seeded DB + 24h 以上的自然时间观察）。

## P1-3c ✅ tickets_new → tickets 历史命名清理（2026-04-24）

**Commit grep**: `git log --grep='(P1-3c)'`

**三条 commit**（按计划一次收尾）：
1. `6f41b63 refactor(tickets_new→tickets): rename package, db manager, configs, locale (P1-3c)` —— 代码层 rename。
2. `afd3aff chore(migrate): add tickets_new→tickets legacy name mapping (P1-3c)` —— 迁移脚本 shim。
3. `<本 commit>` docs 更新（PROGRESS + PLAN + CLAUDE + README）。

**代码层改动**（282 处 grep 命中 → 0）：

| 目标 | 当前 → 改成 |
|---|---|
| 包目录 | `bot/cogs/tickets_new/` → `bot/cogs/tickets/` |
| 类名 | `TicketsNewCog` → `TicketsCog` |
| DB manager | `bot/utils/tickets_new_db.py` / `TicketsNewDatabaseManager` → `tickets_db.py` / `TicketsDatabaseManager` |
| 配置 YAML | `bot/config/tickets_new.yaml(.example)` → `tickets.yaml(.example)` |
| locale yaml | `bot/locales/zh_CN/tickets_new.yaml` → `tickets.yaml` |
| 191 处 `t('tickets_new.*')` + 23 处 `key="tickets_new.*"` | `t('tickets.*')` / `key="tickets.*"` |
| `get_config('tickets_new')` / `save_config('tickets_new', ...)` | `'tickets'` |
| `bot/main.py` COG_SPECS（feature/cog_name/module_path/class_name/required_configs 5 处） | 全对齐 `tickets` |
| `bot/utils/__init__.py` re-export | `from .tickets_db import TicketsDatabaseManager` |
| `bot/locales/zh_CN/commands.yaml` + `tools/field_classification.yaml` 顶级 key | `tickets:` |
| `tools/seed_db.py` 函数 `seed_tickets_new` + registry key | `seed_tickets` / `'tickets'` |

**DB 表名保留（方案 A 明确决策）**：

PLAN §P1-3c 原假设"DB 表名已经是干净的（ticket_types）"，实施时发现 `tickets_db.py` 里还有**三张老表名**：`tickets_new`、`ticket_new_members`、`ticket_new_config`（30+ 处 SQL 引用）。决策表：

| 方案 | 选择？ | 理由 |
|---|---|---|
| A. 只改代码层，DB 表名保留 | ✅ 选 | 老部署零数据迁移风险；3 commit 范围内收尾；schema 改名留给 P2-2 专打 |
| B. 同步改 DB 表名 + auto-migrate | ❌ | 扩大到 4-5 commit，引入 ALTER TABLE RENAME 分支，需物光/满 DB 验证 |
| C. 暂停 P1-3c 等 P2-2 | ❌ | 代码层 rename 和 schema 互不阻塞，推迟没收益 |

SQL 表名残留（保留，不违反 P1-3c 目标）：
- `CREATE TABLE IF NOT EXISTS tickets_new (...)` / `... ticket_new_members` / `... ticket_new_config` 三张 DDL
- 对应 INSERT/SELECT/UPDATE/DELETE 语句里的表名（30 次）
- `FOREIGN KEY (thread_id) REFERENCES tickets_new(thread_id)` 一条 FK 约束

**LEGACY_NAME_MAP 设计**（commit 2）：

- `tools/migrate_config_to_yaml.py`：`cog_name = LEGACY_NAME_MAP.get(source_name, source_name)`。源文件仍叫 `config_tickets_new.json`，产物用新名 `tickets.yaml`。`--only tickets_new` 和 `--only tickets` 都解析到目标 `tickets`。
- `tools/seed_db.py`：迭代 seed 时 `cog_name = LEGACY_NAME_MAP.get(source_name, source_name)` 再去 `seed_handlers.get`。老手工 seed 文件用 `tickets_new` key 也能走到 `seed_tickets` handler。
- 打印时显式 `tickets_new→tickets` 让运维看到 shim 命中。

**顺手清的 README 锚点冲突**：

README.md 原本存在双重入口——`Tickets_New_Cog` (当前) + `Tickets_Cog (Legacy)` (archived to old_function) / `tickets_new_db` + `tickets_db` (legacy)。P1-3c rename 会让新名字和 legacy 锚点冲突。处理方式：
- 新主入口 `Tickets_Cog` / `tickets_db` 取代原 `Tickets_New_Cog` / `tickets_new_db`。
- legacy 入口加 `_Legacy` / `_legacy` 后缀避免 anchor 碰撞：`Tickets_Cog_Legacy` / `tickets_db_legacy`。
- 同时修了 README 的 `/tickets_new_stats` / `/tickets_new_accept` 等 4 处 slash 命令误写（实际命令名本来就是 `/tickets_*` 不带 `_new`，这是 README 自身的历史文档 bug）。

**CLAUDE.md 本地同步（不入 git）**：CLAUDE.md 在 `.gitignore:109` 里，每个开发者按需本地定制。P1-3c 期间同步把本地副本里的 3 处 `tickets_new` / `TicketsNewCog` 提及改到新名（cog 描述、db manager 描述、legacy 迁移史注脚），但**这些改动不随 commit 分发**。如果团队里其它成员仓库有自己的 CLAUDE.md，需要本地手动同步；或者未来把 CLAUDE.md 从 .gitignore 移出后重新入库。

**运行时兼容 shim 不加**（PLAN 标可选；用户选了"不加"）：`bot/utils/config.py.get_config('tickets_new')` 不做自动映射。全量 grep 已确保代码层无 `tickets_new` 残留（仅 SQL 表名 + 历史注释保留）。future regression 直接 KeyError / missing config，比 silent warn 更快暴露。

**验收**：
- `python3 -m py_compile` 全文件 OK
- `tools/check_locales.py`: 556 t() + 170 locale_str key 全 resolve ✅
- stub-based import smoke: `TicketsCog.__module__ == 'bot.cogs.tickets.cog'` ✅，`TicketsDatabaseManager.__module__ == 'bot.utils.tickets_db'` ✅
- **未做**（测试服）：
  - `/tickets_init` → 创建 ticket type → 提交工单 → accept → close 全链路（依赖真 Discord + token + 干净 bot.db）
  - 冷启带老 `config_tickets_new.json` 跑 `migrate_config_to_yaml.py`，确认产物落位 `tickets.yaml`

**未做（follow-up 记录）**：
- `REFACTORING_TEST_CHECKLIST.md` L103 `1.5 tickets_new_cog` 测试条目未改 —— 属历史测试清单，描述某历史时期的清查；本轮不扩大文档 scope。有用户跑全量测试时一并清理。
- DB 三张表 `tickets_new` / `ticket_new_members` / `ticket_new_config` 仍带旧名 —— 留 P2-2 Schema 迁移机制或 P1-3c 收尾二轮处理。
- old_function/ 里的 `tickets_new_cog_pre_split.py` / `tickets_cog.py` 等历史归档**不动**（CLAUDE.md 约定"old_function 只承载已废弃代码"，rename 不应触及）。

**Follow-up commit `790367e`（2026-04-24 晚，外部审核发现）**：3 条 P1-3c 初版漏掉的 latent bug：

| # | 问题 | 后果（未修时） | 修复 |
|---:|---|---|---|
| 1 | `bot/config/main.yaml.example:30` 仍写 `tickets_new: true` | 运维从模板拷贝 → `features.tickets_new: false` 时静默被新代码忽略 → `features.tickets` 缺失走 default=True → 以为禁用的 cog 实际被加载 | 模板改 `tickets: true` |
| 2 | migrate 脚本未 rename `main.features.tickets_new` | 老部署 `config_main.json` 的 `features.tickets_new` 产出到 `main.yaml` 后仍是旧 key；同上静默 bug | `_rename_legacy_feature_keys()` 在 `cog_name=='main'` 时对 `features` 做 in-place rename，new 赢 legacy |
| 3 | migrate 的 `--only` + per-file dispatch 两处 map 后，同时存在 `config_tickets.json`（legacy channel-based，schema 不同）和 `config_tickets_new.json`（thread-based）会 silently overwrite，按 sort 谁后谁赢 | 老部署若两种 JSON 并存，会覆盖错的那份到 `tickets.yaml` | duplicate target pre-check，collision 直接 exit 1 + 报告冲突文件 |

3 个问题都属于 P1-3c commit 1/2 应该做但漏掉的。follow-up commit 对等地补齐。

## P1-3b 第一档 ✅ 小 cog + games/ 聚合（2026-04-24 晚）

**Commit grep**: `git log --grep='(P1-3b)'`

**9 commit**（8 planned + 1 follow-up）：

| # | Commit | 类型 | 内容 |
|---:|---|---|---|
| 1 | `4ca13d1` | refactor | backup（81 行，最小包：`__init__ + cog`） |
| 2 | `a7ba9a3` | refactor | teamup_display（472 行，最小包）。初版**声称 drop header + `setup()` 但实际编辑在 `git add` 之后才落地**，见 commit 3 |
| 3 | `27e7e68` | refactor | **P1-3b follow-up**: 真正把 `teamup_display/cog.py` 的 stale header 和 `async def setup(bot)` 删掉 |
| 4 | `b8578b4` | refactor | game_dnd → `games/dnd/`（106 行，最小包，首次建 `games/` 聚合目录，顺手丢 dead `from ..utils import config` import） |
| 5 | `eafc81f` | refactor | game_spymode → `games/spymode/`（323 行，标准包：`__init__ + cog + views`）。4 View 类（SpyModeView + 3 Button 子类）放 views.py；`from ..utils.i18n` 归一到 `from bot.utils.i18n` |
| 6 | `a5afa80` | refactor | welcome（285 行，标准包，1 View）。PEP 8 import 重排 |
| 7 | `0891d89` | refactor | notebook（311 行，标准包，2 View：ConfirmationView + EventPaginationView）。同名 `ConfirmationView` 在 achievement 也有，不冲突（不同模块） |
| 8 | `d026b34` | refactor | check_status（465 行，标准包，1 View MemberPositionView）。where_is ContextMenu 通过 cog `__init__` / `cog_unload` 注册/摘除，跨模块仍 OK |
| 9 | `332e7e7` | refactor | create_invitation（638 行，标准包，2 View：TeamInvitationView + DefaultRoomView）。`TeamInvitationView.room_full_button_callback` 通过 `bot.get_cog('CreateInvitationCog')` 回 cog；跨模块查找按 class name 工作。顺手丢 dead `import datetime` |
| 10 | 本 commit | docs | PROGRESS + PLAN 更新（Tier 1 标 ✅，handoff 指向 Tier 2） |

**骨架分档速记**（实际落地）：

| cog | 行数 | 包骨架 | Views 放 | 备注 |
|---|---:|---|---|---|
| backup | 81 | 最小 | — | 纯 Cog |
| teamup_display | 472 | 最小 | — | 纯 Cog，`TeamupDisplayCog.db_manager.xxx` 跨域被 create_invitation/voice_channel 调用 |
| games/dnd | 106 | 最小 | — | 无 UI |
| games/spymode | 323 | 标准 | views.py | SpyModeView + 3 Button |
| welcome | 285 | 标准 | views.py | WelcomeDMView |
| notebook | 311 | 标准 | views.py | ConfirmationView + EventPaginationView |
| check_status | 465 | 标准 | views.py | MemberPositionView |
| create_invitation | 638 | 标准 | views.py | TeamInvitationView + DefaultRoomView |

**规划偏差 / errata**：

- PLAN §P1-3b 第一档原估 5-8 commit，实际 9 commit（8 planned + 1 teamup_display follow-up）。follow-up 的根因是 teamup_display commit 里 Edit 工具对新 git-mv'd 文件首次编辑要先 Read 过——前两个 Edit 被拒再修但随后 `git add` 命令漏了 cog.py 的新改动。引入的教训：**`git mv` 后第一次 Edit 目标文件前，先 Read 一次**，避免"以为做完了但其实没 add"。
- PLAN §P1-3b 第一档 pilot 模板 step 4 写"git mv 旧文件到 old_function/cogs/<name>_cog_pre_split.py"——本轮 **不**按这个做（前三个 P1-3 pilot 确实做了 pre_split 归档，但本档 8 个 cog 都是小/中规模，平铺文件本身就足够，老版本通过 git history 可以恢复。`old_function/` 目录保持为放已废弃功能用）。实际的 pilot 模板变成"`git mv` 到 `<name>/cog.py` + 补 `__init__.py`（+ 可能 views.py） + 编辑 main.py"三步即可。
- `bot/cogs/games/__init__.py` 留空（0 字节）。PLAN §P1-3b 写"可选 games/_lib.py / games/common.py——当有第 3 个游戏、且出现可共享代码时再建"，本轮完全遵守，不预建空常量模块。

**顺手做的轻量清理**（夹在 rename commit 里）：

| cog | 清理内容 |
|---|---|
| 全部 8 | 删 stale `# bot/cogs/<name>_cog.py` 文件头注释 |
| game_dnd | 删 dead `from ..utils import config` import（无调用点） |
| game_spymode | `from ..utils.i18n` → `from bot.utils.i18n`（深一层后相对 import 路径变了，顺带规范成绝对） |
| welcome | import 按 PEP 8 重排：stdlib / 3rd-party / local |
| notebook | import 按 PEP 8 重排 |
| create_invitation | 删 dead `import datetime`（无调用点） |

**非 Tier 1 范围但被路过看到的已知 follow-up**（不在本档修）：

- `bot/cogs/voice_channel_cog.py:459` comment "`# 获取create_invitation_cog的配置`" —— voice_channel 还没包化，该注释里的模块名引用是 Tier 2 会一并 revise 的 stale。留 Tier 2 一并看。
- `REFACTORING_TEST_CHECKLIST.md` 未更新（仍引用老文件名）—— 测试清单同文档 scope，用户跑测试时自行 refactor。
- `bot/cogs/__init__.py` 未新增 re-export —— 本档 COG_SPECS 是 string-based `module_path`，`__init__` 不需要 re-export；维持与 P1-3 三 pilot 相同 convention。

**验证**（每个 pilot 跑一次）：

- `python3 -m py_compile bot/cogs/<name>/*.py bot/main.py`：全部 ✅
- `/tmp/yaml-venv/bin/python tools/check_locales.py`：556 t() + 170 locale_str 持续全 resolve ✅（Tier 1 没新增或删除 locale key，纯搬运）
- stub-based runtime import smoke：每个新包的 class `__module__` 对 `bot.cogs.<name>.cog` 或 `bot.cogs.<name>.views` ✅

**未做（测试服用户自行验证）**：

- 8 个 cog 的功能金路径：backup_now、teamup_init、dnd_roll、spymode（流程）、on_member_join（触发 WelcomeDMView）、notebook_log / notebook_member / notebook_all / notebook_delete、check_log / check_voice_status / where_is、触发 TeamInvitationView 的 keyword 匹配 + room_full button。
- 冷启启动日志中 "Loaded 16 cogs: …" 包含全部 16 个 feature。
- 所有 persistent view 的 custom_id 无 regression（只有 create_invitation 的 `"room_full_button"` 是字符串字面量，不受 rename 影响）。

## P1-3b 第二档 ✅ 中型 cog（2026-04-24 晚）

**Commit grep**: `git log --grep='(P1-3b)'`（continues the Tier 1 tag scheme）

**3 commit**，与 PLAN 第二档估算（3-4 commit）一致：

| # | Commit | cog | 骨架 | 代码量（行）| 要点 |
|---:|---|---|---|---:|---|
| 9 | `b716f3b` | achievement | 标准 | 928 | 5 View 入 views.py（AchievementRefreshView / ConfirmationView / AchievementRankingView / AchievementOperationView / RankView）；所有 View 通过 `bot.get_cog('AchievementCog')` 访问 cog，无静态循环；drop dead `import datetime`（被 `from datetime import datetime` 遮蔽）+ `from discord.ui import Button, View`（Button/View 全在 views.py 里）+ stale header |
| 10 | `4fddadc` | voice_channel | 完整 | 1018 | modals.py 只放 AddChannelForm；views.py 放 CheckTempChannelView + RoomControlPanelView（含 persistent `custom_id=f"unlock_{id}" ...` 四按钮）；cog.py 收到 505 行（inner `DeleteChannelConfirmView` 保留在 `delete_channel_config_command` 方法内部）；**drop 模块级死 `DeleteChannelConfirmView`**（L70-L111，零 caller，enhanced inner 覆盖）；修 stale comment `create_invitation_cog` → `create_invitation`；hoist lazy `import re` 到顶 |
| 11 | `f164ec1` | giveaway | 完整 | 1062 | views.py：GiveawayParticipationView（persistent participate/exit `custom_id = f"participate_{id}"`）+ GiveawayConfirmationView + GiveawayCheckParticipantView；modals.py：GiveawayForm（`send_modal`-triggered，`on_submit` 内实例化两个 View 并通过 `bot.get_cog('GiveawayCog').giveaways[id] = view` 交给 cog）；cog.py 收到 671 行；drop cog 层 dead imports (`ui`, `components`, `Button`, `View`, `string`, `re`) |

**骨架分档速记**（实际落地）：

| cog | 包骨架 | views.py | modals.py | cog.py 行数（新）|
|---|---|---|---|---:|
| achievement | 标准 | 5 View | — | 466 |
| voice_channel | 完整 | 2 View | 1 Modal | 505 |
| giveaway | 完整 | 3 View | 1 Modal | 671 |

**关键结论**：
- Views → Cog 全部走 `bot.get_cog('<ClassName>')`（不是 static import），所以包化**不引入**新的 import cycle。
- `modals → views` 在 giveaway 有一条单向依赖（GiveawayForm 构造 GiveawayParticipationView / GiveawayConfirmationView）；仅一个方向，顶层 import 即可，不需要 lazy import。
- voice_channel 里发现的模块级死 `DeleteChannelConfirmView`（42 行）属于历史债 —— enhanced inner class 一直 shadow 它。按 Tier 1 相同的 drive-by 清死代码标准，一并删除 + 在 commit body 明示"dead（0 caller）"即可。

**顺手做的轻量清理**（夹在 rename commit 里）：

| cog | 清理内容 |
|---|---|
| 全部 3 | 删 stale `# bot/cogs/<name>_cog.py` 文件头注释 |
| achievement | 删 dead `import datetime`（被 `from datetime import datetime` 遮蔽）+ `from discord.ui import Button, View`（全部归 views.py）；imports 按 PEP 8 重排 |
| voice_channel | 删 dead 模块级 `DeleteChannelConfirmView`（42 行）；narrow `from discord import app_commands, ui` → 只留 `app_commands`；drop `from discord.ui import Button`；修 L459 stale comment；lazy `import re` 抬到 views.py 顶 |
| giveaway | drop cog 层 dead imports `ui`, `components`, `Button`, `View`, `string`, `re`（全部只在 views/modals 层用）；imports 按 PEP 8 分组 |

**验证**（每个 pilot 跑一次）：

- `python3 -m py_compile bot/cogs/<name>/*.py bot/main.py`：全部 ✅
- `/tmp/yaml-venv/bin/python tools/check_locales.py`：556 t() + 170 locale_str 持续全 resolve ✅（Tier 2 没新增或删除 locale key，纯搬运）
- stub-based runtime import smoke：每个新包的 class `__module__` 对 `bot.cogs.<name>.cog` / `bot.cogs.<name>.views` / `bot.cogs.<name>.modals` ✅

**未做（测试服用户自行验证）**：

- achievement 金路径：`/achievements_board`（触发 AchievementRefreshView）、`/achievement_ranking`（AchievementRankingView）、`/rank_board`（RankView）、`/achievement_operation_log`（AchievementOperationView）、`/update_achievements`（ConfirmationView）。
- voice_channel 金路径：建房（on_voice_state_update）、`/add_channel_config`（AddChannelForm）、控制面板四按钮（unlock / lock / full / soundboard）、`/check_temp_channel`（CheckTempChannelView 分页）、`/delete_channel_config`（inner DeleteChannelConfirmView）、restart 后 `cog_load` 恢复 temp channels。
- giveaway 金路径：`/ga_create`（GiveawayForm）→ participate（GiveawayParticipationView）→ 自动 / 手动 end → 查参与者（GiveawayCheckParticipantView）；以及 P1-8b 已修的冷启 `check_giveaways` 首 tick 不再 race building。

**规划偏差 / errata**：

- PLAN 第二档原估 "3-4 commit"，实际 3 commit（计划内）；无 follow-up。
- voice_channel 的模块级死 `DeleteChannelConfirmView` 未在 Tier 1 的 handoff clean-up list 里提到（Tier 1 errata 只记了 L459 stale comment）。属于"本棒包化过程中才被 grep 捞出"的 drive-by 清理。
- giveaway 原 file 的 Modal 直接 import 两个 View，所以 Modal → View 的静态耦合本身是 pre-existing，不是包化后才有；改完后从跨文件耦合变成跨模块 import，语义一致。

## P1-8 审核补遗（2026-04-24，第 11 轮审核）

三条 hygiene pass，详见 PLAN §P1-8。按 "影响半径 × 代码量" 从小到大收尾。

**WIP 先落盘的两个 sibling commit**（属审核路径上顺手发现，不在 P1-8a/b/c 范围）：

| Commit | 改动 | 原因 |
|---|---|---|
| `de362ba fix: two latent bugs ...` | `tickets_new/views.py:278` `cog.conf.get('ticket_types')` → `cog.ticket_types` | P1-3 pilot 拆包后 cog.py:33 已 `pop('ticket_types', None)`，views.py 这一处漏改 → `TypeSelectView` 下拉永远空 |
| 同上 | `main.py` COG_SPECS: `CheckStatusCog` / `SpyModeCog` 的 `required_configs` 从 `["checkstatus"]` / `["spymode"]` 清空 | `bot/config/` 里没有这俩 yaml，`_get_missing_configs` 会把两个 cog 跳掉 → `/check_status` 和 spymode 游戏加载不了 |

### P1-8c ✅ feature flag 类型校验行为对齐（2026-04-24）

**Commit grep**: `git log --grep='(P1-8c)'`

**问题**：`config_schema.py:132` warning 说 "will be ignored as false"；但 `config.py:112` `is_feature_enabled` 对非 bool 值回退 `default=True`（两个调用点 `main.py:234` / `achievement_cog.py:506` 都传 default=True）。运维写 `features: {shop: "false"}`（字符串）会让日志记 warning 但 shop 仍被加载——警告与行为相反。

**做法**：`is_feature_enabled` 三个显式分支：
- key 不在 features dict → 返回 `default`（维持原"key 缺失"语义，两个调用点不变）
- 值是 bool → 返回 bool 值
- 值存在但非 bool → **返回 `False`**（和 warning 对齐）

只改"key 存在但类型错"这一分支方向。调用点盘查 `grep -rn 'is_feature_enabled' bot/`：两个调用点（`main.py:234` / `achievement_cog.py:506`）都用隐式 `default=True`，语义未变。

**smoke**（`yaml-venv` 直接 import `bot/utils/config.py`，猴子替 `get_feature_flags`）：

```
A. key 缺失：default=True → True；default=False → False  （透传）
B. bool True / False                            → 原值
C. str "false" / "true" / int 1 / None          → 一律 False（不再回 default=True）
```

**未做（测试服）**：
- `main.yaml` 写 `features: {shop: "false"}` 冷启，确认 shop cog 未加载 + schema warning 出日志
- 正常布尔 / 不写 flag 两条回归路径

改动面只 4 行净变，行为变化严格局限于 "key 存在但类型错" 分支。

**顺手发现（未做）**：`config_schema.py:134` 的 warning 文案提 "got `<type>`"，不带 key 原值。如果用户真误写，日志里看到 `got str` 但不知道是 `"false"` / `"yes"` / `"1"`，排障得去翻 yaml —— 留作独立 follow-up。

### P1-8b ✅ giveaway initialize_database 迁 cog_load（2026-04-24）

**Commit grep**: `git log --grep='(P1-8b)'`

**问题**：`giveaway_cog.__init__:438` 启动 `check_giveaways.start()`；`on_ready:1061` 才 `await self.db.initialize_database()`。READY 触发后两个协程并发放行，Python 不保证顺序——首 tick 若先于建表到达，SELECT/INSERT 直接 `sqlite3.OperationalError: no such table: giveaway`（表名单数，见 `giveaway_db.py:27`），被 `check_giveaways` 的 `except Exception` 静默吞为一行 log。

**做法**（对齐 `check_status` / `voice_channel` / `ban`（P1-2）的 `cog_load` 模式）：

| 位置 | 动作 |
|---|---|
| `giveaway_cog.py:437` | 新增 `async def cog_load(self)`: 先 `await self.db.initialize_database()`、再 `self.check_giveaways.start()` |
| `giveaway_cog.py:438`（原 `self.check_giveaways.start()`） | 删，迁到 `cog_load` |
| `giveaway_cog.py:1061`（原 on_ready `await self.db.initialize_database()`） | 删；保留 `await self.load_giveaways()`（guild cache 需 READY 后才稳） |

**cog_unload 缺失**（独立 latent leak，不扩大 scope）：
- `giveaway_cog` 原本**没有** `cog_unload`（与 `ban` P1-2 对齐后有所不同）；task 在 cog reload 时不会被 cancel。
- 当前部署无 reload 命令 / hot-reload 路径，风险只在开发期；记为 follow-up。

**验证**：
- `python3 -m py_compile` 通过
- `grep` 验收：`cog_load` 在 437、`on_ready` 在 1061、`__init__` 再无 `check_giveaways.start`、`on_ready` 再无 `initialize_database`
- **未做（测试服）**：`rm bot.db` 冷启，首次 `check_giveaways` tick 日志无 `no such table` / `OperationalError`

### P1-8a ✅ tickets_new ticket-type CRUD 返回值校验（2026-04-24）

**Commit grep**: `git log --grep='(P1-8a)'`

**问题**：`tickets_new/modals.py:361`（rename）、`:392`（upsert）、`tickets_new/views.py:329`（delete）各自 `await db_manager.<method>()` 但不接返回值。三个 manager 方法 (`tickets_new_db.py:94/117/151`) 的实现是 `try/except` + `return False`——SQLite 写入失败（锁 / 磁盘满 / schema 异常）时 `commit` 被 except 吞、方法 return False，但原代码继续跳到 `_refresh_ticket_types()` + 发 "✅ ..."，用户错觉成功。

**根因**：P1-3 pilot 拆 `tickets_new_cog` 成包时照抄原逻辑（原逻辑没检查）；manager 的 `return False` 语义是 P2-5 迁 `ticket_types` 到 DB 时才引入——两条路没合上。

**改点**：

| 位置 | 操作 |
|---|---|
| `modals.py:361` rename | `ok = await rename_ticket_type(...)` + `if not ok: send(ticket_type_rename_failure) + return` |
| `modals.py:392` upsert | `ok = await upsert_ticket_type(...)` + `if not ok: send(ticket_type_upsert_failure) + return` |
| `views.py:329` delete | `ok = await remove_ticket_type(...)` + `if not ok: send(ticket_type_delete_failure) + return` |

**新增 locale key**（`bot/locales/zh_CN/tickets_new.yaml` 的 `messages:` 子树）：
```yaml
ticket_type_rename_failure: ❌ 重命名失败，请联系管理员
ticket_type_upsert_failure: ❌ 保存失败，请联系管理员
ticket_type_delete_failure: ❌ 删除失败，请联系管理员
```

**范围约束**：failure 文案从 hardcoded 改走 locale 只针对 "manager return False 的静默失败路径"。两个 catch-all `except Exception` 里原本的 hardcoded `"❌ 操作失败"` / `"❌ 删除失败"` 文案**不在本补丁范围**（异常路径不同于 return False 路径），留给 P1-7 i18n 补遗或 P1-3c rename 时扫。

**P1-3c rename 前置说明**：新 key 走 `tickets_new.messages.*`，因 rename 尚未完成；P1-3c sed 会把 `tickets_new.*` → `tickets.*` 一并扫到，不构成阻塞。

**验证**：
- `python3 -m py_compile` modals + views OK
- `tools/check_locales.py`：556 t() + 170 locale_str key 全 resolve（比之前多 3 个 failure key）
- **未做（测试服）**：`chmod 400 bot.db` 或临时 rename 表重现失败路径，看用户端从 "✅" 变成 "❌ ...请联系管理员"

### P1-8 全收官（2026-04-24）

三条 hygiene pass 全绿：
- `044b17c` P1-8c - `is_feature_enabled` 非 bool 返回 False
- `fc77465` P1-8b - giveaway `initialize_database` 迁 `cog_load`
- `c62bb23` P1-8a - tickets_new CRUD 三处接返回值

3 源码 commit + 3 docs commit + 2 WIP 落盘 commit(`9e56242` docs + `de362ba` fix sibling) = 8 commit。P1-8 表格全 ✅。当时下一棒建议走 **P1-3c** rename（374 处 grep + LEGACY_NAME_MAP，3 commit）→ **P1-3b 第一档**（8 个小 cog + games/ 定型，8-10 commit）。

> **Update 2026-04-24（晚些时候）**：P1-3c 已完成（`6f41b63` / `afd3aff` / 本 docs commit）。当时下一棒默认走 **P1-3b 第一档**。

### 剩余工作（跨会话接手）

Config 2.0 sprint **整体收官**（step 0-9 全 ✅）；P1-7 slash 元数据本地化 ✅；P1-4 dataclass schema + 静态 key 对齐 ✅；**P1-3 大 cog 拆包三 pilot 全 ✅**（tickets_new 2666 → 1910 行 + privateroom 1993 → 1655 行 + ban 1430 → 1418 行；主 cog 都缩减或至少 UI 层隔离到包子模块）；**P1-8 审核补遗 hygiene pass 全 ✅**（2026-04-24，P1-8a/b/c 三条合计 8 commit、~20 行净变，详见本文件 §P1-8）；**P1-3c tickets_new → tickets rename ✅**（2026-04-24，3 commit，代码层 282 处 grep 清零，DB 三张表名按方案 A 保留留给 P2-2）。

**2026-04-24 后续规划**（用户决定）：P1-3 扩展为 **§P1-3b 全量 cog 包化 + games 聚合** + **§P1-3c tickets_new → tickets rename**（见 PLAN 对应章节）。该规划已于 2026-04-25 全部收官；service.py 横扫也已完成 ban probe；P2-1 数据库连接复用高频路径和 P2-2 schema migration 基础设施也已完成。当前默认下一棒是 P2-3 `save_config` 写回统一策略；全部重构完成后再统一全量功能测试。

下一轮可接手的 follow-up：

**🟡 important**（全量包化序列）：
1. ~~**P1-3c**（先做）~~：✅ 已完成（2026-04-24，3 commit `6f41b63` / `afd3aff` / 本 docs commit）。
2. ~~**P1-3b 第一档**~~：✅ 2026-04-24 晚（9 commit，详见本文件 §P1-3b 第一档）。
3. ~~**P1-3b 第二档**~~：✅ 2026-04-24 晚（3 commit：achievement `b716f3b` / voice_channel `4fddadc` / giveaway `f164ec1`；详见本文件 §P1-3b 第二档）。
4. ~~**P1-3b 第三档**~~：✅ 2026-04-25（shop + role；shop persistent view `custom_id` 已核为稳定字面量）。
5. ~~**service.py 横扫评估**~~：✅ 已完成（2026-04-25，ban probe；tickets / privateroom 暂不批量抽）。
6. per-cog 配置 schema（shop / ban / tickets / voicechannel / privateroom 等）：`bot/utils/config_schema.py` 里 dataclass 形状锁死，让 `admin_roles: List[int]` / `ticket_types: Dict[str, TicketType]` 等固定 shape 字段不会静默腐烂。

**🟢 nice-to-have**（P1-3b 后横扫）：
1. **service.py 后续抽离**（ban probe 后再评估）：三家已 pilot 的候选清单：
   - **tickets_new/tickets**: `is_admin_for_type` / admin CRUD / `format_admin_list` / `add_admins_to_ticket` 等 10 个方法 ~500-700 行
   - **privateroom**: `calculate_discount` / `get_last_month_voice_hours` / `is_booster` / `check_and_send_renewal_reminders` + shop/renewal embed builder ~300 行
   - **ban**: `parse_duration` / `has_ban_permission` / `is_admin_channel_only_check` / `build_*_notification_embed` 已抽；`recover_tempbans` / `check_expired_tempbans` / `schedule_unban_with_db` 因依赖 bot/guild/db/task state 暂留 cog。
   - state 管理前置设计：tickets 先定 `ticket_types/conf` 所有权；privateroom 先定购买 / 续费状态边界；ban 后续若继续抽 task，需要决定 `tempban_tasks` 是否转移到 service。
2. P3-5 ruff 已完成最小落点（E722 锁 P0-4 成果）；E722 以外的规则如 F401 unused imports、B904 raise from 暂未启用，留 lint debt follow-up。
3. P1-7 后续：`check_status.where_is_menu` 的 ContextMenu `name='Where Is'` 目前硬编码英文；Discord `ContextMenu.name` 不走 Translator 链，想本地化需要构造时手写 `name_localizations={Locale.chinese: '...'}` dict（与 slash name 的 ASCII 约束不同，Context Menu name 允许中文）。
4. 各 pilot 留下的 i18n 漏网之鱼统一扫一遍（privateroom 里 5-6 条 + ban 里 ~10 条中文字面量；都是拆包前就存在，未扩大 scope）。做 P1-7 续篇时一并迁。
5. `tickets_new_cog.py` 原先有 `import aiosqlite` 的死 import（Explore 在 P0-1 阶段就标记过，P1-3 tickets_new pilot 已顺手删）。ban / privateroom 没这个问题，不需要。

---

### Upgrade 协议（生产部署执行）

老部署升级到这一组 commit 后的正确顺序（不可反过来）：

```bash
git pull
uv sync                            # 装 ruamel.yaml
python tools/migrate_config_to_yaml.py   # 生成 yaml / locale / seed
# → review tools/migration_report.md, 按需更新 field_classification.yaml 重跑
python tools/seed_db.py            # channel_configs + ticket_types 灌 DB
# 重启 bot
```

**跳过 `seed_db.py` 会发生**：auto-create 房间入口全丢（`voicechannel.channel_configs` 表空）、所有 ticket type 消失（`ticket_types` 表空）。JSON fallback 兜不了 DB-bound 字段（况且 step 9 后 JSON fallback 已删）。

**升级产物速览**：
- `bot/config/<name>.yaml`（每个 enabled cog 一份 + `main.yaml`；gitignore，本地填真值）
- `bot/locales/zh_CN/<name>.yaml`（按 cog 一份 + `commands.yaml` 是 slash 元数据专用；tracked）
- `bot.db`（追加了 `channel_configs` 和 `ticket_types` 两张表）

---

### 下一个可接手的任务（压缩 context / 新 session 直接看这里）

**最新方向**（2026-04-24 用户明确）：P1-3 三 pilot 已证明包化路径可行，用户决定把 **P1-3 的范围扩展到全量 cog**（让 `bot/cogs/` 下只剩包目录、不再有平面 `*_cog.py`），并**把 2 个游戏 cog 聚合到 `bot/cogs/games/`**，为未来加新游戏留扩展点。相关详细计划见 **REFACTORING_PLAN.md §P1-3b**。同时规划了 **§P1-3c**：把 `tickets_new` 这个 V1.6.5b 遗留命名清掉、改回 `tickets`，但迁移脚本要保留 `tickets_new → tickets` 的名字映射以兼容老部署的 `config_tickets_new.json` 源头。

**P1-8 审核补遗（2026-04-24，第 11 轮审核）**：三条之前 P 任务的遗漏尾巴，改动面都很小但都有可观测的错位行为。作为 P1-3b 启动前的 hygiene pass：

| 条目 | 位置 | 归属原 P | 严重度 | 状态 |
|---|---|---|---|---|
| P1-8a tickets_new ticket-type CRUD 未校验 DB 返回值 | `bot/cogs/tickets_new/modals.py:361/392`、`views.py:329` | P1-3 pilot + P2-5 未对齐 | 中（用户错觉成功） | ✅ `c62bb23` |
| P1-8b giveaway `initialize_database` 迁 `cog_load` | `bot/cogs/giveaway_cog.py:438/558/1061` | P0-1 + P1-2 未收尾 | 中（启动期竞态，冷启可能炸） | ✅ `fc77465` |
| P1-8c feature flag 类型校验提示 / 行为对齐 | `bot/utils/config_schema.py:132` vs `bot/utils/config.py:112` | P1-4 未对齐 | 低到中（静默启用误配的 cog） | ✅ `044b17c` |

**P1-8 全收官** ✅。后续节奏：~~P1-3c `tickets_new` → `tickets` rename~~（2026-04-24 已完成）→ ~~P1-3b 第一档（8 个小 cog + games/ 定型）~~（2026-04-24 晚，9 commit）→ ~~P1-3b 第二档（achievement / voice_channel / giveaway）~~（2026-04-24 晚，3 commit）→ ~~P1-3b 第三档（shop + role）~~（2026-04-25 完成）。

`service.py` 抽离决定**后置** —— 包化完成后每家都有标准骨架，此时再横向评估 service 候选（本次 session 没动的原因：和三家保守 pilot 一致性更重要；全量包化后评估成本更低）。

---

### P1-3b 完成状态：全量 cog 包化 + games 聚合

**当前 `bot/cogs/` 清单**（2026-04-24 晚 Tier 1 收官后盘点）：

| cog | 行数 | 类数 | 建议骨架 | 风险点 | 状态 |
|---|---:|---:|---|---|---|
| tickets | 1910 | — | ✅ 已完成（P1-3 pilot + P1-3c rename） | — | ✅ |
| privateroom | 1662 | — | ✅ 已完成（P1-3 pilot） | — | ✅ |
| ban | 1418 | — | ✅ 已完成（P1-3 pilot） | — | ✅ |
| role | 1151 | 7 (5V+1M+1Cog) | ✅ 完整包（Tier 3） | — | ✅ |
| shop | 1101 | 5 (2V+2M+1Cog) | ✅ 完整包（Tier 3） | persistent view 已核：`custom_id` 三个稳定字面量 | ✅ |
| giveaway | 1062 | — | ✅ 完整包（Tier 2 `f164ec1`） | — | ✅ |
| voice_channel | 1018 | — | ✅ 完整包（Tier 2 `4fddadc`；drop 1 dead 模块级 View） | — | ✅ |
| achievement | 928 | — | ✅ 标准包（Tier 2 `b716f3b`） | — | ✅ |
| create_invitation | 638 | 3 (2V+1Cog) | ✅ 标准包（Tier 1 `332e7e7`） | — | ✅ |
| teamup_display | 472 | 1 (Cog) | ✅ 最小包（Tier 1 `a7ba9a3` + follow-up `27e7e68`） | — | ✅ |
| check_status | 465 | 2 (1V+1Cog) | ✅ 标准包（Tier 1 `d026b34`） | — | ✅ |
| games/spymode | 323 | 5 (3Btn+1V+1Cog) | ✅ **games/spymode/**（Tier 1 `eafc81f`） | — | ✅ |
| notebook | 311 | 3 (2V+1Cog) | ✅ 标准包（Tier 1 `0891d89`） | — | ✅ |
| welcome | 285 | 2 (1V+1Cog) | ✅ 标准包（Tier 1 `a5afa80`） | — | ✅ |
| games/dnd | 106 | 1 (Cog) | ✅ **games/dnd/**（Tier 1 `b8578b4`） | — | ✅ |
| backup | 81 | 1 (Cog) | ✅ 最小包（Tier 1 `4ca13d1`） | — | ✅ |

**骨架三档**（详见 PLAN §P1-3b）：
- **最小包**（`__init__ + cog.py`）：纯 Cog、无 UI。
- **标准包**（`__init__ + cog + views.py`）：有 View 无 Modal（或 Modal ≤1）。
- **完整包**（`__init__ + cog + views + modals [+embeds] [+service]`）：UI 层厚。

`service.py` 和 `embeds.py` 只在**有内容时才建**，不留空文件。

**建议执行顺序**（可分档收尾，不强求一次全做）：

| 档 | 任务 | 预估 commit 数 | 实际 | 状态 |
|---|---|---:|---:|---|
| 1（热身 + games 定型） | backup → teamup_display → game_dnd→games/dnd → game_spymode→games/spymode → welcome → notebook → check_status → create_invitation | 8-10 | 9（8 planned + 1 follow-up） | ✅ 2026-04-24 |
| 2（中型 UI） | achievement → voice_channel → giveaway | 3-4 | 3 | ✅ 2026-04-24 晚 |
| 3（大 + persistent view） | shop（persistent view！）→ role | 2-3 | 2 | ✅ 2026-04-25 |
| 收尾 | PROGRESS / PLAN 更新 | 1 | 1 | ✅ 2026-04-25 |

第一档已收官 —— `games/` 目录骨架定型完成（empty `__init__.py` 占位，按 PLAN 不预建 `_lib.py` / `common.py`）。第二档收官 —— 3 个中大 cog 全部进包，顺手 drop 掉 `voice_channel` 里一个模块级死 `DeleteChannelConfirmView`（其 enhanced inner class 一直在覆盖它，但没人实例化模块级版本）。第三档收官 —— shop / role 均已进包，P1-3b 全量包化完成。

**每棒 pilot 模板**（复制照抄）：

```bash
# 0. Explore agent cross-reference 报告（参考 ban pilot 那次的 prompt 结构），限 500 字
#    包含：类清单 / 归属 / import 拓扑 / 循环依赖 / persistent view / t import 检查
#    / slash 命令清单 / 风险点

# 1. 建目录
mkdir -p bot/cogs/<name>   # 或 bot/cogs/games/<name>

# 2. git mv 旧文件到新包（保留 git rename 识别，后续 git log --follow 能跟到 cog.py）
git mv bot/cogs/<name>_cog.py bot/cogs/<name>/cog.py
# games 两个：
# git mv bot/cogs/game_dnd_cog.py bot/cogs/games/dnd/cog.py
# git mv bot/cogs/game_spymode_cog.py bot/cogs/games/spymode/cog.py
#
# 默认不归档到 old_function/。Tier 1 八棒（backup / teamup_display / game_dnd /
# game_spymode / welcome / notebook / check_status / create_invitation）都直接
# git mv，没造 pre_split 副本——git history 本身足够。归档到 old_function/ 的
# 判断标准是"原文件体量大（≥1400 行）且被切成 4-5 个兄弟 .py，整文件历史不再
# 连续"，参考 P1-3 三 pilot（tickets_new / privateroom / ban）的做法。
# Tier 2 的 giveaway / voice_channel 在这个门槛上，Tier 3 的 shop / role 也是，
# 本档按"原文件被拆成 ≥3 个兄弟 .py 就归档"简单规则判断即可。

# 3. 写 __init__.py + [views.py] + [modals.py] + [embeds.py]
#    照抄 ban / privateroom / tickets 三 pilot 的粒度
#    注意：Edit 新 cog.py 之前先 Read 一次 —— git mv 产物对 Edit 工具而言是
#    "未读文件"，首次 Edit 会被拒；被拒后如果 patched 才 Read，后续 git add
#    容易漏掉补的编辑（参考 Tier 1 teamup_display follow-up commit `27e7e68`）。

# 4. 改 bot/main.py 的 COG_SPECS 对应 module_path
#    普通：bot.cogs.<name>_cog → bot.cogs.<name>
#    games: bot.cogs.game_dnd_cog → bot.cogs.games.dnd
#           bot.cogs.game_spymode_cog → bot.cogs.games.spymode

# 5. 三连验证
python3 -m py_compile bot/cogs/<path>/*.py bot/main.py
/tmp/yaml-venv/bin/python tools/check_locales.py
python3 << 'PY'
# stub-based import smoke —— 模板参考 ban pilot session 的 Python 片段
# （也可以去 git log --grep='(P1-3 pilot)' 的 ban commit body 找）
PY

# 6. commit（两个）
git commit -m "refactor(<name>): split cog into package (P1-3b)"
# 如果顺手清了死代码 / latent bug，commit message 里列清单
```

**Commit 前置警告**：
- **shop pilot 必须手工验证 persistent view**：`bot/cogs/shop_cog.py:647` 的 `self.bot.add_view(self.checkin_view)` 是 persistent 注册点。检查 CheckinEmbedView 的 `custom_id` 是不是纯字符串字面量（当前是，但必须在 commit 前再 grep 确认）；如果任何 custom_id 含类路径或动态值，迁移后老的 persistent view 记录会失效。
- **games/ 目录的 `__init__.py`**：建一个空的（或 docstring 说明"游戏 cog 聚合点"）。当前不需要 re-export 任何东西。
- **COG_SPECS 里的 `feature` / `cog_name` / `required_configs` 不变**，只改 `module_path`（参考三家 pilot 的 commit）。

---

### P1-3c 完成状态：`tickets_new` → `tickets` rename

**为什么当时先做这个**：P1-3b 里还要做 tickets pilot 之外的 13 个 cog，但是 tickets 本身**已经是包**了，只是名字带 `_new`。先把名字改干净，后续 P1-3b 过程中就不用再顾虑它。

**374 处 grep 命中**，分布在 11 个文件（`tickets_new` + `TicketsNew` 两种命名）。清单 / 重命名映射 / 迁移脚本兼容方案 **全部在 PLAN §P1-3c**。

**关键点**：`tools/migrate_config_to_yaml.py` 和 `tools/seed_db.py` 必须加：

```python
LEGACY_NAME_MAP = {'tickets_new': 'tickets'}
cog_name = LEGACY_NAME_MAP.get(cog_name, cog_name)
```

**3 commit**：
1. `refactor(tickets_new→tickets): rename package, db manager, configs, locale (P1-3c)`
2. `chore(migrate): add tickets_new→tickets legacy name mapping (P1-3c)`
3. `docs: track progress after tickets_new rename (P1-3c)`

---

### 下一候选：P2-3 `save_config` 写回统一策略（PLAN §P2-3）

P1-3 / P1-3b 拆包完 ✅，P1-3c rename 也完成（2026-04-24），service.py 横扫 + ban probe 也完成（2026-04-25），P2-1 数据库连接复用高频路径（voice / achievement / shop）完成（2026-04-25），P2-2 schema migration 基础设施 + 首批 payload 完成（2026-04-26）。现在默认进入 P2-3：梳理运行中的配置写回路径，先按当前包化后的真实文件名重新确认问题范围，再动代码；全部重构完成后再统一全量功能测试。

P1-3c 留下的 DB 表名 `tickets_new` / `ticket_new_*` 清理没有在 P2-2 首批 payload 里做；如果将来决定清理，应通过新 `schema_version` migration 增量完成。

如果要做：P2-3 文档里部分文件名仍是历史平面 cog 名，开工前先用 `rg save_config bot` / `rg ticket_types bot/cogs bot/utils` 对当前包结构复核，不要直接照旧路径改。

---

### 最短新 session 启动清单

1. `sed -n '43,90p' REFACTORING_PROGRESS.md`（看总表 + 当前接手点）
2. `git log --oneline -10`（确认最近有 P1-3d ban service probe + docs commit）
3. `find bot/cogs -maxdepth 1 -type f -print`（应只剩 `bot/cogs/__init__.py`）
4. `sed -n '897,930p' REFACTORING_PLAN.md`（确认 P2-1 / P2-2 已收官）
5. `sed -n '930,990p' REFACTORING_PLAN.md`（看 P2-3 save_config 写回问题范围；注意先复核现状）
6. 决定路径：
   - **P1-8 hygiene pass 已全收官**（2026-04-24）：P1-8c ✅（`044b17c`）/ P1-8b ✅（`fc77465`）/ P1-8a ✅（`c62bb23`）；不必再展开 PLAN §P1-8，历史追溯才需要
   - **P1-3c 已收官**（2026-04-24）：`6f41b63` / `afd3aff` + 2 docs commit。详见本文件 §P1-3c。
   - **P1-3b 第一档已收官**（2026-04-24 晚）：8 cog + `games/` 骨架，9 commit（含 1 follow-up）。详见本文件 §P1-3b 第一档。
   - **P1-3b 第二档已收官**（2026-04-24 晚）：achievement / voice_channel / giveaway 共 3 commit。详见本文件 §P1-3b 第二档。
   - **P1-3b 第三档已收官**（2026-04-25）：shop + role 完整包。
   - **P1-3d service.py 横扫 + ban probe 已收官**（2026-04-25）：详见本文件 §P1-3d。
   - **P2-1a 生命周期基础设施已收官**（2026-04-25）：详见本文件 §P2-1a。
   - **P2-1b voice 持久连接 probe 已收官**（2026-04-25）：详见本文件 §P2-1b。
   - **P2-1c achievement 持久连接 probe 已收官**（2026-04-25）：详见本文件 §P2-1c。
   - **P2-1d shop 持久连接 probe 已收官**（2026-04-25）：详见本文件 §P2-1d。
   - **P2-2 schema 迁移机制已收官**（2026-04-26）：详见本文件 §P2-2。
   - **下一棒默认**：进入 P2-3 `save_config` 写回统一策略；功能测试整体后置到重构全部完成后。

用户只说"继续"的话，默认进入 **P2-3 `save_config` 写回统一策略**。P2-1 高频 manager 长连接已完成；P2-2 schema migration 基础设施已完成；功能测试不穿插阻塞重构，统一留到全部重构结束后从头验证。

### 本次 session 补充（2026-04-24 P1-8 hygiene pass 收官 session）

**上一轮 session**（commit `3e135d0`，同日早些时候）：只做规划文档 —— 补齐 PLAN §P1-3b / §P1-3c + 更新 PROGRESS handoff；**代码 0 行改动**。

**本轮 session**（commits `9e56242` → `f75117d`，共 8 个）：把 P1-8 hygiene pass 全做完 + 两处 sibling latent bug 顺手落盘：

| # | Commit | 类型 | 内容 |
|---:|---|---|---|
| 1 | `9e56242` | docs | 落盘 §P1-8 规划到 PLAN + PROGRESS（上轮 session 写了但未 commit） |
| 2 | `de362ba` | fix | sibling 1: `tickets_new/views.py:278` `cog.conf.get('ticket_types')` → `cog.ticket_types`（P1-3 pilot 后遗留空下拉 bug）；sibling 2: `main.py` `CheckStatusCog`/`SpyModeCog` 虚假 `required_configs` 清空（`bot/config/` 无此 yaml，会被 `_get_missing_configs` 跳过加载） |
| 3 | `044b17c` | fix | **P1-8c**：`is_feature_enabled` 非 bool 返 False，和 schema warning 对齐（4 行） |
| 4 | `87ad4ec` | docs | P1-8c progress 笔记 |
| 5 | `fc77465` | refactor | **P1-8b**：giveaway `initialize_database()` 迁 `cog_load`，避免 on_ready 和 task 建表竞态（+2 -2 行） |
| 6 | `38f9b05` | docs | P1-8b progress 笔记 |
| 7 | `c62bb23` | fix | **P1-8a**：tickets_new CRUD 三处接返回值 + False 分支走新 locale key；`rename_failure` / `upsert_failure` / `delete_failure` 三个新 key（+24 -3 行） |
| 8 | `f75117d` | docs | P1-8a progress 笔记 + P1-8 整体收官总结 |

**规划偏差（已在文档内嵌 errata）**：
- PLAN §P1-8b 第 4 条原假设 "cog_unload 里已有的 cancel 不动"，实施时发现 `giveaway_cog` **没有** `cog_unload`。本轮不扩大 scope 新建，latent leak 留作 follow-up（部署无 reload 命令，只影响开发 hot reload）。PLAN §P1-8b 已加 errata 标注。

**未做（测试服用户自行验证）**：
- P1-8c：`main.yaml` 写 `features: {shop: "false"}` 冷启 → shop 未加载 + schema warning 出日志
- P1-8b：`rm bot.db` 冷启 → 首 tick 无 `no such table: giveaway`
- P1-8a：`chmod 400 bot.db` / rename 表 → 用户看到 "❌ 重命名/保存/删除失败，请联系管理员" 而非 "✅ ..."

**P1-8 全收官后的当时 handoff 建议（历史记录）**：
- ~~§P1-3c rename~~ ✅ 2026-04-24 完成（`6f41b63` / `afd3aff` + docs commit）
- 当时下一棒：§P1-3b 第一档（backup → teamup_display → game_dnd→games/dnd → game_spymode→games/spymode → welcome → notebook → check_status → create_invitation 共 8 cog，8-10 commit；现已完成）
- service.py 抽离评估、per-cog 配置 schema 锁形 —— 全量包化完成后再横扫

### P1-3c rename session 补充（2026-04-24 晚些时候）

**本轮 session**（3 commit）：
| # | Commit | 类型 | 内容 |
|---:|---|---|---|
| 1 | `6f41b63` | refactor | P1-3c 静态 rename：`tickets_new/` → `tickets/`、`TicketsNewCog` → `TicketsCog`、t() key 批量 + 191 处、commands.yaml/COG_SPECS 对齐。DB 三张老表名按方案 A 保留（决策见 §P1-3c） |
| 2 | `afd3aff` | chore | migrate_config_to_yaml.py + seed_db.py 加 `LEGACY_NAME_MAP = {'tickets_new': 'tickets'}`，兼容老部署 `config_tickets_new.json` 源头 |
| 3 | `9273394` | docs | PROGRESS §P1-3c 笔记 + 表格 ✅ + handoff 更新；PLAN §P1-3c 加 ✅ + errata；README 锚点冲突修正 + 4 处 slash 命令误写顺手清。CLAUDE.md 也改了 3 处但它是 gitignored，不随 commit 分发 |
| 4 | `790367e` | fix | P1-3c follow-up：3 个 latent bug（`main.yaml.example` features key 未同步；migrate 脚本未 rename `main.features.tickets_new`；duplicate target detection 缺失）|
| 5 | 本 commit | docs | 修正 §P1-3c 里"CLAUDE.md 更新"的叙述，明确 gitignored 不入 git |

**规划偏差（已在文档内嵌 errata）**：
- PLAN §P1-3c "DB 表名已经是干净的（ticket_types）" 不准确 —— 实际有三张老表 `tickets_new` / `ticket_new_members` / `ticket_new_config`。实施时做决策表选方案 A（保留表名、只改代码层），避免扩大到 schema migration。
- README.md 里发现 4 处早已存在的 slash 命令名误写（`/tickets_new_stats` 等——实际命令名从未带 `_new`）。P1-3c 顺手修，归属 README 自身历史文档 bug，不在原 PLAN 清单里。

### P1-3b 第一档 session 补充（2026-04-24 晚 Tier 1 收官）

**本轮 session**（10 commit：9 功能 + 1 docs）：

| # | Commit | 类型 | 内容 |
|---:|---|---|---|
| 1 | `4ca13d1` | refactor | backup 最小包（81 行） |
| 2 | `a7ba9a3` | refactor | teamup_display 最小包（472 行） —— 初版 header/`setup()` drop 声称但漏 add |
| 3 | `27e7e68` | refactor | **P1-3b follow-up**：补齐 teamup_display 的 header/setup drop |
| 4 | `b8578b4` | refactor | game_dnd → `games/dnd/`（106 行）+ 建 `games/` 空目录 |
| 5 | `eafc81f` | refactor | game_spymode → `games/spymode/`（323 行，标准包） |
| 6 | `a5afa80` | refactor | welcome 标准包（285 行） |
| 7 | `0891d89` | refactor | notebook 标准包（311 行） |
| 8 | `d026b34` | refactor | check_status 标准包（465 行） |
| 9 | `332e7e7` | refactor | create_invitation 标准包（638 行） |
| 10 | 本 commit | docs | PROGRESS + PLAN 更新（Tier 1 ✅，handoff 指 Tier 2） |

**规划偏差 / session-level 教训**：

- PLAN §P1-3b 第一档原估 5-8 commit，实际 9 commit（多 1 是 teamup_display follow-up，从 "git mv 后首次 Edit 目标文件前要先 Read" 的流程 slip 里产生）。
- PLAN §P1-3b 的 pilot 模板里 step 4 写"`git mv` 旧文件到 `old_function/cogs/<name>_cog_pre_split.py`"——本档 **不**按此执行。前三个 P1-3 pilot（tickets_new / privateroom / ban）因体量大才做了 pre_split 归档；Tier 1 这 8 个都是 ≤638 行的小/中 cog，git history 本身就能提供历史恢复路径，额外 `pre_split` 副本只会让 `old_function/` 变成杂物间。**Tier 2 / Tier 3 按 cog 体量决定是否归档**。
- `bot/cogs/games/__init__.py` 留空（0 字节），按 PLAN 要求。

**顺手清的轻量代码卫生**（混在 rename commit 里，commit message 都点名）：

- 全部 8 个 cog：删 stale `# bot/cogs/<name>_cog.py` header 注释
- game_dnd：删 dead `from ..utils import config` import
- game_spymode：`from ..utils.i18n` → `from bot.utils.i18n`（深一层绝对路径）
- welcome / notebook：import PEP 8 重排
- create_invitation：删 dead `import datetime`

**顺手纠正的非 Tier 1 范围观察**（不在本档修，给 Tier 2 准备）：

- `bot/cogs/voice_channel_cog.py:459` 注释 `# 获取create_invitation_cog的配置` 引用旧文件名 —— voice_channel 还没包化，Tier 2 一并 revise。
- `REFACTORING_TEST_CHECKLIST.md` 未更新（未被 Tier 1 扫到）。

**当时下一棒建议**：§P1-3b 第二档（achievement → voice_channel → giveaway）。voice_channel 迁 DB 已做（P0-3d），giveaway 建表迁 cog_load 已做（P1-8b），两家拆包都是纯 UI 层整理；achievement 是单 cog 5-View 的经典标准包，风险低。（现已完成）

### P1-3b 第三档 session 补充（2026-04-25）

**本轮 session**（2 个源码/归档 commit + 本 progress 更新）：

| # | 类型 | 内容 |
|---:|---|---|
| 1 | `c774018` refactor | shop → `bot/cogs/shop/` 完整包：`cog.py` 492 行、`views.py` 465 行、`modals.py` 164 行；role → `bot/cogs/role/` 完整包：`cog.py` 639 行、`views.py` 479 行、`modals.py` 55 行；`bot/main.py` module path 同步到 `bot.cogs.shop` / `bot.cogs.role` |
| 2 | `a1ceefa` chore | 归档 pre-split 副本到 `old_function/cogs/shop_cog_pre_split.py` / `old_function/cogs/role_cog_pre_split.py` |

**实施笔记**：
- shop persistent view 已核：`CheckinEmbedView` 三个按钮 `custom_id` 是 `checkin_daily` / `checkin_makeup` / `checkin_query` 字符串字面量，不依赖模块路径。
- shop 迁深一层后修正了 `resources/images/checkin.png` 的相对路径：`../../resources` → `../../../resources`。
- role 拆分粒度：`SignatureModal` 入 `modals.py`；`AchievementRoleView` / `StarSignView` / `MBTIView` / `GenderView` / `SignatureView` 入 `views.py`；`_escape_markdown_table_cell` 留 `cog.py`。
- 验证：`python3 -m compileall bot/cogs/shop bot/cogs/role bot/main.py` ✅；`/tmp/yaml-venv/bin/python tools/check_locales.py` ✅；`find bot/cogs -maxdepth 1 -type f -name '*_cog.py'` 为空。
- 普通 import smoke 未完成：系统 Python 缺 `discord`，`/tmp/yaml-venv` 缺 `aiosqlite`；提权到沙箱外后 Windows `.venv/Scripts/python.exe` 可启动，且已有 `discord 2.7.1` / `aiosqlite 0.22.1`，但缺 `ruamel.yaml`。`uv pip sync requirements.lock --python ./.venv/Scripts/python.exe` 在 WSL 下未识别该 Windows venv。未据此判定运行期通过，留测试服冷启验证。

**下一棒建议（历史）**：先做 service.py 横扫评估，列候选和收益，不直接抽；如果收益不够，转 P2-1 数据库连接复用的生命周期设计。

### P1-3d service.py 横扫 + ban probe（2026-04-25）

**横扫结论**：
- **tickets** 仍是最厚候选，但 `is_admin_for_type` / admin CRUD / `format_admin_list` / `add_admins_to_ticket` 牵动 `ticket_types` DB cache 与 `conf` 归属，第一刀风险偏高。
- **privateroom** 候选集中在折扣、booster、续费提醒、购买 / 恢复流程，但会牵动 shop DB、privateroom DB、Discord channel 创建和支付状态流，不适合直接当 probe。
- **ban** 有相对孤立的纯 helper 和 Embed builder，且 state-coupled 的 `tempban_tasks` 可以原地保留，因此选 ban 做第一刀。

**做了什么**：
- 新增 `bot/cogs/ban/service.py`，承接 `parse_duration`、`member_has_ban_permission`、`is_admin_channel`、`is_valid_discord_invite_link`。
- 4 个通知 / DM Embed builder 抽到 service：`build_ban_notification_embed`、`build_mute_notification_embed`、`build_tempban_dm_embed`、`build_mute_dm_embed`。
- `bot/cogs/ban/cog.py` 从 1418 行降到 1232 行；发送消息、Discord API、DB 调用、task loop、`tempban_tasks` 字典仍留在 cog。
- 顺手把 `/ban_set_invite_link` 的硬编码错误提示迁到 `bot/locales/zh_CN/ban.yaml` 的 `invalid_invite_link`。

**验证（沙箱外）**：
- `python3 -m compileall bot/cogs/ban bot/locales` ✅
- `/tmp/yaml-venv/bin/python tools/check_locales.py` ✅（557 `t()` + 170 `locale_str`）
- `git diff --check` ✅
- 创建一次性 `/tmp/dcgsh-verify` 并 `uv pip sync requirements.lock --python /tmp/dcgsh-verify/bin/python` 后，ban import / service helper smoke ✅
- 项目 Windows `.venv` 先 `ensurepip` 补出 pip，再 `./.venv/Scripts/python.exe -m pip install -r requirements.lock` 补齐依赖；`./.venv/Scripts/python.exe -m pip check` ✅；project venv ban import / service helper smoke ✅
- 最终 project venv 验证：`./.venv/Scripts/python.exe -m compileall bot` ✅；`./.venv/Scripts/python.exe -X utf8 tools/check_locales.py` ✅（不加 `-X utf8` 时 Windows GBK stdout 会在打印 ✅ 时假失败）

**后续建议**：
- 下一步默认转 **P2-1 数据库连接复用** 的生命周期设计，先定 manager `close()` 与 bot shutdown hook。（已执行，见 §P2-1a）
- 如果继续 service.py，建议先不批量抽 tickets / privateroom；等重构主线再次回到 service 层时，再分别设计 `TicketsService` 的 `ticket_types/conf` 所有权和 `PrivateRoomService` 的购买 / 续费状态边界。相关功能测试统一放到全部重构完成后。

### P2-1a 数据库生命周期基础设施（2026-04-25）

**做了什么**：
- 新增 `bot/utils/db_lifecycle.py`：
  - `BaseDatabaseManager.close()` 对未迁移 manager 仍等价 no-op，先建立生命周期合同，不改变现有 per-call `aiosqlite.connect` 行为。
  - `collect_database_managers_from_cogs()` 从 cog 直接属性收集 manager，并按对象 id 去重。
  - `close_database_managers()` 逐个 await `close()`，单个 manager 关闭失败只记录日志，不阻断其它资源释放。
- 现有 11 个 DB/DB-like manager 全部继承 `BaseDatabaseManager`：achievement / ban / check_status / giveaway / notebook / privateroom / role / shop / tickets / voice_channel / teamup_display。
- `bot/main.py` 新增 `DCGameServerHelperBot(commands.Bot)`；`close()` 先捕获当前 cog 上的 manager，再调用 `super().close()`。discord.py 会在 `super().close()` 中 remove cog 并触发 `cog_unload()`，所以后台 task 先停，随后再关闭 manager。

**刻意没做**：
- 没把任何 manager 改成长连接；P2-1 仍是 🔄，不是 ✅。
- 没递归扫描 View / Modal 内部临时创建的 manager。下一阶段不要先转换这些散落 manager；优先转换 cog 直接持有、生命周期能被 bot close 捕获的 manager。

**验证（沙箱外，项目 `.venv`）**：
- `./.venv/Scripts/python.exe -m compileall bot` ✅
- `./.venv/Scripts/python.exe -X utf8 tools/check_locales.py` ✅
- `git diff --check` ✅
- 不联网 Bot.close smoke ✅：dummy cog 的事件顺序为 `['cog_unload', 'manager_close']`，确认 task/cog unload 早于 manager close。

**下一棒建议**：
- P2-1b / P2-1c / P2-1d 建议已执行：`VoiceChannelDatabaseManager`、`AchievementDatabaseManager` 和 `ShopDatabaseManager` 持久连接 probe 完成。
- P2-1 高频路径和 P2-2 schema migration 基础设施已收官；下一步进入 P2-3 `save_config` 写回统一策略，全量功能测试统一后置。

### P2-1b voice DB 持久连接 probe（2026-04-25）

**做了什么**：
- `BaseDatabaseManager` 新增 opt-in 持久连接 helper：`_get_persistent_connection_lock()` / `_get_persistent_connection()`；`close()` 会在 manager 已持有持久连接时关闭它，对未迁移 manager 仍等价 no-op。
- `VoiceChannelDatabaseManager` 迁到单连接模式：实例初始化时创建 manager 级 `asyncio.Lock`，`initialize_database()` 首次打开连接；所有读写 helper 都在 lock 内完成 execute / fetch / commit。
- 写操作失败时显式 `rollback()` 后再抛出，避免持久连接留下半开事务。
- 语音 cog / View / Modal 调用面不变，只替换 manager 内部连接生命周期。

**刻意没做**：
- 没把 shop/tickets 等其它 manager 一次性迁成长连接。
- 没引入连接池；SQLite + 当前 bot 单进程场景先用 manager 单连接 + lock。

**验证（沙箱外，项目 `.venv`）**：
- `./.venv/Scripts/python.exe -m compileall bot` ✅
- `./.venv/Scripts/python.exe -X utf8 tools/check_locales.py` ✅
- `./.venv/Scripts/python.exe -m pip check` ✅
- 临时 sqlite voice DB smoke ✅：`initialize_database()`、`upsert/list/delete channel_configs`、`insert/update/fetch/delete temp_channels`、旧表补列迁移、连接复用、`close()` 释放后重开。

**下一棒建议**：
- P2-1c 已执行：`AchievementDatabaseManager` 持久连接 probe 完成。
- P2-1d 已执行：`ShopDatabaseManager` 持久连接 probe 完成。
- voice_channel 的建房、删除空房、控制面板按钮、bot 重启恢复 View 等功能测试统一放到全部重构完成后的全量测试清单里。

### P2-1c achievement DB 持久连接 probe（2026-04-25）

**做了什么**：
- `AchievementDatabaseManager` 初始化时创建 manager 级 `asyncio.Lock`，并 opt-in 使用 `BaseDatabaseManager` 的持久连接 helper。
- `initialize_database()`、常规 achievements / monthly_achievements 读写、leaderboard / rank、voice session、manual operation、shop 签到联查都改为复用同一个 `aiosqlite.Connection`。
- 多 SQL 写路径在同一 lock 内完成，写失败显式 `rollback()`；cursor 通过内部 helper 显式关闭，避免持久连接下泄漏 cursor。
- 调用面不变，achievement cog / shop 联查路径不需要改。

**刻意没做**：
- 当轮没迁 `ShopDatabaseManager`，避免一次性把签到、余额、补签和 embed panel 路径全部卷进同一个改动；P2-1d 已单独迁完。
- 没引入连接池；继续沿用 manager 单连接 + lock 的渐进式策略。

**验证（沙箱外，项目 `.venv`）**：
- `./.venv/Scripts/python.exe -m compileall bot` ✅
- `./.venv/Scripts/python.exe -X utf8 tools/check_locales.py` ✅
- `./.venv/Scripts/python.exe -m pip check` ✅
- `git diff --check` ✅
- 临时 sqlite achievement DB smoke ✅：初始化建表、成就/月度成就写入、leaderboard/rank、voice session、manual operation、shop 签到联查、负例 rollback、连接复用、`close()` 释放后重开。

**下一棒建议**：
- P2-1d 已执行：`ShopDatabaseManager` 持久连接 probe 完成。
- achievement 的真实 Discord 命令与按钮测试统一放到全部重构完成后的全量测试清单里。

### P2-1d shop DB 持久连接 probe（2026-04-25）

**做了什么**：
- `ShopDatabaseManager` 初始化时创建 manager 级 `asyncio.Lock`，并 opt-in 使用 `BaseDatabaseManager` 的持久连接 helper。
- `initialize_database()`、余额、签到、补签、transaction history、checkin embed panel 相关读写都改为复用同一个 `aiosqlite.Connection`。
- `update_user_balance_with_record()` 改为余额更新 + transaction 记录同一事务；`add_makeup_record()` 改为补签记录 + streak 重算同一事务，避免持久连接下 public 方法嵌套锁导致死锁。
- 写失败显式 `rollback()`；cursor 通过内部 helper 显式关闭。

**刻意没做**：
- 没迁低频 manager（ban/tickets/notebook 等）。P2-1 收口范围是 voice / achievement / shop 三个高频 manager；其它 manager 等 profiling 或功能改动时再单独迁。
- 没引入连接池；继续沿用 manager 单连接 + lock。

**验证（沙箱外，项目 `.venv`）**：
- `./.venv/Scripts/python.exe -m compileall bot` ✅
- `./.venv/Scripts/python.exe -X utf8 tools/check_locales.py` ✅
- `./.venv/Scripts/python.exe -m pip check` ✅
- `git diff --check` ✅
- 临时 sqlite shop DB smoke ✅：初始化建表、余额读写、余额+流水事务、负例 rollback、签到重复检测、补签 slot、streak 重算、transaction history/count、checkin embed 创建/统计/reset/deactivate、连接复用、`close()` 释放后重开。
- 临时 sqlite achievement/shop interop smoke ✅：shop 签到 + 补签后，achievement 的 `get_user_achievements()`、月度签到数据、签到总数 / 连签榜单均能读到一致数据。

**下一棒建议**：
- P2-2 已执行：`schema_version` + 手写 migrations helper + 首批 payload 完成。
- shop 的真实 Discord 签到、补签、余额、embed panel 功能测试统一放到全部重构完成后的全量测试清单里。

### P2-2 Schema 迁移机制（2026-04-26）

**做了什么**：
- 新增 `bot/utils/schema_migrations.py`：
  - `schema_version` 表按 namespace 记录当前版本、说明和更新时间。
  - `SchemaMigration` + `apply_schema_migrations()` 提供手写 migration 链。
  - `add_column_if_missing()` / `get_table_columns()` 统一处理 SQLite 补列。
- `VoiceChannelDatabaseManager` 接入 `voice_channel` namespace v1：补齐 `temp_channels` 的控制面板、soundboard、room type runtime 列。
- `PrivateRoomDatabaseManager` 接入 `privateroom` namespace v1：补齐 `privateroom_rooms.renewal_reminder_sent`。
- `BanDatabaseManager` 接入 `ban` namespace v1：把旧 `tempbans` 的 `UNIQUE(user_id, guild_id, is_active)` 重建为 `UNIQUE(user_id, guild_id)`，保留原先“同 user/guild 只保留最大 id 记录”的策略。

**刻意没做**：
- 没处理 `tickets_new` / `ticket_new_*` DB 表名历史遗留；如果后续要改名，走新的 schema migration 机制单独做 payload。
- 没引入 yoyo/alembic；当前迁移量小，手写 helper 更容易审计。

**验证（沙箱外，项目 `.venv`）**：
- `./.venv/Scripts/python.exe -m compileall bot` ✅
- `./.venv/Scripts/python.exe -X utf8 tools/check_locales.py` ✅
- `./.venv/Scripts/python.exe -m pip check` ✅
- `git diff --check` ✅
- 临时 sqlite schema migration smoke ✅：旧 voice 表补列、旧 private room 表补列、旧 ban tempbans 约束重建、重复运行 migration 不重复执行、`schema_version` namespace/version 写入正常。

**下一棒建议**：
- 进入 P2-3 `save_config` 写回统一策略。注意 PLAN §P2-3 里部分路径仍是旧平面 cog 名，开工前先按当前包结构用 `rg save_config bot` / `rg ticket_types bot/cogs bot/utils` 复核实际问题范围。
