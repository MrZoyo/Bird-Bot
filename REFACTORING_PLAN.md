# 架构改进计划 (Refactoring Plan)

本文档记录在 2026-04-22 架构审查中发现的可提升项，按优先级分类。P0 为立即开工项，P1~P3 依次推进。

优先级标记：
- **P0**：现有代码已违反项目自身约束 / 存在明显埋雷，立即处理
- **P1**：架构性改进，影响长期可维护性
- **P2**：中期改进，收益明确但改动较大
- **P3**：工程化 / 整洁度改进，可以穿插处理

---

## P0：立即推进

### P0-1. `giveaway_cog.py` 抽出独立 db 管理器

**问题**
- `bot/cogs/giveaway_cog.py` 存在 20+ 处 `aiosqlite.connect(self.db_path)` 直连，SQL 写死在 cog 内部。
- `bot/utils/` 下**没有** `giveaway_db.py`，违反 CLAUDE.md 中 "Always use dedicated `*_db.py` managers, never direct `aiosqlite` in cogs"。
- 直连不仅在 `GiveawayCog` 本体，还散布到**辅助对象**（Modal / View / Form 等）中，例如 `bot/cogs/giveaway_cog.py:348`（`insert_giveaway`）、`:360`（`fetch_giveaway`）、`:369`（`fetch_all_giveaway_ids`）这些方法属于 `GiveawayCog` 之外的内部类。迁移时必须一并覆盖，否则会留下半拉子重构。

**影响范围**
- `bot/cogs/giveaway_cog.py`（1272 行，内含所有 giveaway 相关 SQL）

**建议做法**
1. 新建 `bot/utils/giveaway_db.py`，定义 `GiveawayDatabaseManager`。
2. **先全文搜索 `giveaway_cog.py` 内所有 `aiosqlite` 调用点**，分类整理：属于 cog 方法的、属于辅助类的，做一张迁移映射表，避免遗漏辅助类。
3. 迁移所有 SQL 到 manager 方法；参考现有 `ShopDatabaseManager`、`BanDatabaseManager` 的接口风格（`initialize_database()`、业务方法返回 dict/list）。
4. **辅助类（Modal / View / Form）获取 manager 的方式**，择一执行并全文件保持一致：
   - a. 构造时传入：例如 `GiveawayParticipationView(bot, giveaway_id, ..., db=self.db)`；View/Modal 里保存引用。
   - b. 通过 `bot.get_cog('GiveawayCog').db` 访问。
   推荐 a：依赖显式、易测试。
5. 在 `bot/utils/__init__.py` 导出 `GiveawayDatabaseManager`。
6. cog 里改为 `self.db = GiveawayDatabaseManager(config.get_config()['db_path'])`；确认所有 Modal/View 实例化点都传入了 `db`。

**验收**
- `grep -n "aiosqlite" bot/cogs/giveaway_cog.py` 结果为空（包括 import）。
- 辅助类 `__init__` 里有显式 `db` 参数，或全文统一通过 `bot.get_cog(...)` 访问。
- 现有 giveaway 功能在测试服全链路可运行（创建、参与、退出、开奖、超时）。

---

### P0-2. `privateroom_cog.py` 混用直连规范化

**问题**
`bot/cogs/privateroom_cog.py` 已经有对应的 `bot/utils/privateroom_db.py` 和 `PrivateRoomDatabaseManager`，却仍在 cog 内直接 `aiosqlite.connect`，破坏了既定分层。其余没有 manager 的 cog（`voice_channel_cog` / `check_status_cog` / `create_invitation_cog` / `notebook_cog`）归入 P0-3，不在本条范围内。

**建议做法**
1. 搜索 `privateroom_cog.py` 中所有 `aiosqlite.connect`，逐段确认对应操作。
2. 如果 `PrivateRoomDatabaseManager` 已有同语义方法，直接替换为 manager 调用。
3. 如果没有，**在 manager 中新增方法**，保持 cog 只做 Discord 交互、不写 SQL。
4. 完成后跑一次测试服验证温存设置、房间续费、权限恢复等路径。

**验收**
- `grep -n "aiosqlite" bot/cogs/privateroom_cog.py` 结果为空或仅剩 `import`（理想情况 import 也移除）。

---

### P0-3. 其余直连 cog 补齐 db manager

**问题**
以下 cog 尚无对应 db manager，SQL 直接写在 cog 中：
- `bot/cogs/check_status_cog.py`（3 处直连，且有**建表竞态**，见下）
- `bot/cogs/create_invitation_cog.py`
- `bot/cogs/notebook_cog.py`
- `bot/cogs/voice_channel_cog.py`

**推进顺序（按运行风险排序，不按体量）**

1. **`check_status_cog`（最优先）**：`__init__:55` 在实例化时就 `self.check_voice_status_task.start()` 启动 10 分钟循环；而 `status` 表的 `CREATE TABLE IF NOT EXISTS` 直到 `on_ready` 才执行（`:428-437`）。任务首次触发如果早于 `on_ready`（或 `before_loop` 的等待被短路）就会向尚未建表的库写入。抽出 `check_status_db.py` 时把建表迁到 `cog_load`，同时修掉这个竞态。
2. **`notebook_cog`（342 行）**：体量小，纯记录类功能，风险低，作为第二轮练手。
3. **`create_invitation_cog`（606 行）**：SQL 面窄，可以快速收敛。
4. **`voice_channel_cog`（1094 行）**：最大，且与 `achievement_db` / `privateroom_db` 有交互，放在最后，评估是否需要新建 `voice_channel_db.py` 还是扩展既有 manager。

**验收**
- `grep -rn "aiosqlite.connect" bot/cogs/` 结果为空。
- `check_status_cog` 的建表必须发生在首次后台任务运行之前（放到 `cog_load` 或在任务入口 `await self.db.initialize_database()`）。

---

### P0-4. 裸 `except:` 规范化

**问题**
全仓库共 **21 处** `except:`（不指定异常类型），会吞掉一切异常，包括 `KeyboardInterrupt`、`SystemExit`、`asyncio.CancelledError`，严重掩盖 bug。范围**不止 `bot/cogs/`**，`bot/utils/` 也有。

**影响范围**

| 文件 | 出现次数 |
|---|---|
| `bot/cogs/tickets_new_cog.py` | 12（行 217/324/448/465/814/824/831/1121/1426/1556/1591/1647） |
| `bot/cogs/shop_cog.py` | 5（行 280/675/696/790/988） |
| `bot/cogs/ban_cog.py` | 2（行 881/1282） |
| `bot/cogs/voice_channel_cog.py` | 1（行 1007） |
| `bot/utils/privateroom_db.py` | 1（行 50） |

**建议做法**
为每处裸 except 选择合适策略之一：

1. **明确异常类型**（最优）：
   ```python
   except (discord.NotFound, discord.Forbidden, discord.HTTPException):
       pass
   ```
2. **收窄 + 记录**（次优，保留"尽力而为"语义）：
   ```python
   except Exception as e:
       logging.exception("context description")
   ```
3. **移除**：如果这里本就不该捕获，删除 try/except。

**禁止**
- 不要再写 `except:` 裸捕获。
- 不要写 `except Exception: pass` 不记录 —— 至少 `logging.exception` 一下。

**验收**
- `grep -rn "^\s*except:" bot/` 结果为空（注意：范围是 `bot/`，同时覆盖 `cogs/` 和 `utils/`）。
- 新增 ruff 规则 `E722`（bare-except）作为长期保障（见 P3-5）。

---

## P1：架构性改进

### P1-1. `on_ready` 中命令同步逻辑重构
- **位置**：`bot/main.py:152-173`
- **问题**：每次 `on_ready` 都 `tree.clear_commands` + `tree.sync()`。on_ready 可能因重连多次触发，而 `tree.sync()` 有全局速率限制。
- **建议**：迁移到 `setup_hook`，或在 cog 上加 `self._synced` 标志位，仅首次同步。

### P1-2. `ban_cog` 的 DB 初始化迁移到 `cog_load`
- **现状核查**：`achievement_cog:557`、`shop_cog:639`、`tickets_new_cog:477`、`voice_channel_cog:557` 都已经在用 `async def cog_load(self)` 初始化 DB，**只剩 `bot/cogs/ban_cog.py:33` 还是 `self.init_task = asyncio.create_task(self.initialize_db())`**。
- **问题**：`create_task` 下表未就绪时命令可能已经接收，且初始化异常被异步吞掉。
- **建议**：把 `ban_cog.__init__` 里的 `init_task` 改成 `async def cog_load(self)` 中 `await self.initialize_db()`；删除 `cog_unload` 里对 `init_task` 的取消逻辑。
- **不要扩到其他 cog**：审查时先确认现状，避免重复劳动。

### P1-3. 大 cog 文件拆包
按体量降序：
1. `tickets_new_cog.py`（**2529 行**）→ `bot/cogs/tickets_new/` 包：`cog.py` + `views.py` + `modals.py` + `embeds.py` + `service.py`
2. `privateroom_cog.py`（1986 行）→ 类似拆法
3. `ban_cog.py`（1359 行）
4. `giveaway_cog.py`（1272 行）——P0-1 完成后再考虑
5. `voice_channel_cog.py`（1094 行）
6. `shop_cog.py`（1055 行）
7. `role_cog.py`（1016 行）

### P1-4. 配置结构校验
- **问题**：`self.conf['messages']['xxx']` 依赖运行时，配置漏 key 要触发命令时才炸。
- **建议**：用 `pydantic.BaseModel` 或 `dataclass` 给每份 config 写 schema，启动时统一校验。启动失败总好过线上崩。
- **与 P1-6 合并**：本条在 P1-6 步骤 8 落地，不单独推进。

### P1-5. 日志加 rotation
- **位置**：`bot/main.py` 的 `logging.basicConfig`。
- **问题**：无轮转，日志文件无限增长；且 `basicConfig` 只能生效一次。
- **建议**：改用 `logging.handlers.TimedRotatingFileHandler`（每天 rotate，保留 N 天）。keyword / room activity 日志同步处理。

### P1-6. 配置格式迁移 YAML + 文字/数据分层 + i18n 基础

#### 动机
- JSON 不支持注释。`config_main.json.example` 现在靠重复 `_comment` key 绕，`json.load` 只保留最后一个，等于白写。
- 文字（embed 正文 / 按钮 label / 用户反馈）与数据（channel id / role id / 阈值）混在同一文件，翻译、交接、非技术同学改文案都别扭。
- 大量**用户可见文本硬编码在 Python 里**（`notebook_cog:163-167`、`check_status_cog:152-178`、`role_cog:925-927` 等），哪怕迁 YAML，不动这部分也无法实现"切 locale 切整套文案"。
- 为未来支持多语言（至少简中 / 英文）打基础。

#### 已拍板的设计决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| A. YAML 库 | `ruamel.yaml` | 保留注释 + round-trip。P2-3 有部分运行时写回（管理员列表等），PyYAML 整段重写会吹掉人工注释；ruamel.yaml API 稍重但值得。 |
| B. i18n 粒度 | 全局单 locale | `main.yaml: locale: zh_CN`，整个 bot 共用。按 guild / 按用户更重，等第二语言稳定跑 1-2 周再评估。 |
| B2. 首轮交付语言 | **只交付 zh_CN**，不交付 en_US | 当前所有部署都是 zh_CN 用户，硬抽一套 en_US 翻译没有实际使用者，也容易翻错 / 漏译；但 i18n 框架本身（`bot/locales/<lang>/*.yaml` 目录结构、`t()` 的多语言能力）要保留可扩展性，未来接第二语言不需要改架构。以下文档里 `en_US/` 目录 / 映射 / 验收条目仅作"未来扩展位"保留，本 PR 不交付、不纳入验收。 |
| C. 文件分层 | 双目录分离 | `bot/config/` 放数据，`bot/locales/<lang>/` 放文字。翻译协作友好，译者不碰敏感 id。 |
| D. Slash 命令元数据 | 独立 P1-7 处理 | Discord 原生 `name_localizations` 一次注册多语言按用户客户端展示，机制跟 `t()` 不同，不混在本条。 |
| E. 过渡策略 | 一次性 PR + 迁移脚本 | 不维护代码层兼容（不保留 `self.conf['messages']['key']` 旧接口）。用 `tools/migrate_config_to_yaml.py` 帮老部署把 `*.json` 自动转 `*.yaml`。 |
| F. 敏感信息位置 | 继续放 `main.yaml`，**不引入** `.env` / `python-dotenv` 层 | `bot/config/*.yaml` gitignore + `old_function/` 归档硬规则已足够保护 token。env 额外增加一层运维切换点（启动脚本、systemd unit、部署文档都要同步），收益不抵成本。原 P2-4（Token 迁 env）据此撤销，见下方 P2-4 占位条目。 |

#### 三层分工（核心）

config 里的字段按三类分工，**不要求"所有文字清零"**：

| 类别 | 归属 | 管理员 / 翻译者体验 | 例 |
|---|---|---|---|
| 纯数据（id、阈值、channel id、开关） | `bot/config/*.yaml` + YAML 注释 | 注释告知用途，不随 locale 切 | `welcome_role_id: 0  # 新成员欢迎角色` |
| 结构 key / slug（英文稳定 id） | `bot/config/*.yaml` 的 key，同时是 `bot/locales/*/*.yaml` 的 key | 两边对齐的粘合剂，代码 `t(f"role.starsign.{slug}")` | `starsign.aries`、`mbti.intj` |
| 用户可见文本（embed / 按钮 / 反馈 / 图表标题） | `bot/locales/<lang>/*.yaml` | 随 `main.locale` 切换 | zh: "白羊座"；en: "Aries" |

示例（`role_cog` 星座部分）：

```yaml
# bot/config/role.yaml
#
# 星座身份组：由管理员在 Discord 创建后填入对应 role id。
# key 是英文 slug，对齐 locales/<lang>/role.yaml 下的同名 key。

starsign:
  aries:       { id: 0, emoji: "♈" }   # 白羊座
  taurus:      { id: 0, emoji: "♉" }   # 金牛座
  # ...
```

```yaml
# bot/locales/zh_CN/role.yaml
starsign:
  aries:   "白羊座"
  taurus:  "金牛座"
  # ...
  pickup_title: "请选择你的星座"
  success: "已为你添加了星座：{name}"
```

```yaml
# bot/locales/en_US/role.yaml
starsign:
  aries:   "Aries"
  taurus:  "Taurus"
  # ...
```

#### 目标目录结构

```
bot/
  config/
    main.yaml                    # token / db_path / features / locale
    main.yaml.example            # 模板（id 全部 1145141919810）
    shop.yaml
    shop.yaml.example
    tickets_new.yaml
    ban.yaml
    role.yaml
    ...
  locales/
    zh_CN/                       # 本 PR 唯一交付语言（见 P1-6 决策表 B2 条）
      shop.yaml
      tickets_new.yaml
      ban.yaml
      role.yaml
      ...
      commands.yaml              # slash 命令 description/params 翻译（P1-7 使用；name 不本地化）
    # en_US/                     # 预留目录位，本 PR 不创建、不交付；接第二语言时再加
tools/
  migrate_config_to_yaml.py      # JSON → YAML 一次性迁移脚本
```

#### 步骤

**步骤 0：前置准备（必做，放在 PR 最前面）**

- 改 `.gitignore`（**严格分两阶段**，不能混）：

  **阶段 A：本 PR 合入时（步骤 0~8 整个迁移期）**

  - **保留**旧规则 `bot/config/*.json`。迁移期老部署 / 未升级机器上还有填了真实 id 的旧 JSON，规则必须在位，否则 `git add .` 直接泄露。
  - **新增** `bot/config/*.yaml`（真实配置，含 token / id）。
  - **保留（不忽略）** `bot/config/*.yaml.example`（模板）和 `bot/locales/**/*.yaml`（翻译，不含敏感信息）。
  - **新增忽略迁移产物**：`tools/migration_db_seed.json`、`tools/migration_report.md`。原因：按 `AGENTS.md:31` 的约定，Guild/Channel/Role ID 属于机密；`migration_db_seed.json` 直接承载这些真实 id（voicechannel/ticket_types 的 channel/role 引用），`migration_report.md` 也可能在映射示例里引用真实 id。两者都必须视同配置文件不进 git。
  - **新增忽略 `old_function/` 下的真实配置**：`old_function/**/*.json`、`old_function/**/*.yaml`。配合下面"`old_function/` 归档硬规则"使用。`.json.example` / `.yaml.example` 后缀不匹配 `*.json` / `*.yaml`，**不受影响**，脱敏模板仍可入 git 便于查阅历史结构。

  **阶段 B：步骤 9 兼容清理时**

  - 此时所有 `bot/config/config_*.json` 已 `mv` 到 `old_function/`，`bot/config/` 下不再有 `.json` 文件。
  - **此时才删除** `bot/config/*.json` 忽略规则。
  - 新搬入 `old_function/` 的那批 `config_*.json` 自动被阶段 A 已加的 `old_function/**/*.json` 拦截，不会把真实 ID 带进新提交。**无需**额外脱敏，也**无需**把 `old_function/` 整体忽略。

  迁移脚本自身（`tools/migrate_config_to_yaml.py` / `tools/seed_db.py` / `tools/field_classification.yaml`）是代码 / 规则，**要** commit。

**`old_function/` 归档硬规则（本 PR 立即生效，同步更新 `AGENTS.md`）**

- `old_function/` 只承载**已废弃的代码**（cogs、辅助脚本、数据库管理器等）。代码归档可 commit，供历史查阅。
- `old_function/**/*.json`、`old_function/**/*.yaml` **一律 gitignore**（阶段 A 已加）。想手工查阅历史配置结构，靠 `.json.example` / `.yaml.example`（脱敏模板，不在忽略名单里）。
- 规则同步写进 `AGENTS.md` "安全与配置提示" 章节，确保后续 PR reviewer 能据此挡下违规提交。
- **历史遗留处理**：`git ls-files old_function/config/` 显示 `config_tickets.json` 和 `config_rating.json` **已被追踪**且含真实 ID（channel / category / role / user；见 `old_function/config/config_tickets.json:3-47`、`old_function/config/config_rating.json:3`）。本 PR 要做：
  - `git rm --cached old_function/config/config_tickets.json old_function/config/config_rating.json`（**仅移出追踪，工作树保留**），让新 `.gitignore` 规则生效。
  - **不做 `git filter-repo` 重写历史**：这些 ID 已在 git 历史里提交数十次，重写破坏性大、所有协作者需要强制 reclone；认作历史遗留泄露，从此不再新增。生产服如担心相关 role / channel 暴露风险，自行轮换权限。
  - 如你想走 filter-repo 重写路径（成本高但历史干净），单独开一次操作窗口，不混在本 PR。
- 更新文档：
  - `README.md:71` 和 `AGENTS.md:6` 的 "copy `config_*.json.example`" 改成 YAML 版流程。
  - 明确新的命名约定：`<name>.yaml` 而非 `config_<name>.yaml`（目录已足够区分 namespace）。
- `.example` 模板不手写，由迁移脚本生成（步骤 5）。

**老部署升级协议（必须写进 README 升级章节）**

所有迁移脚本位于新版代码的 `tools/` 下。正确顺序如下，**不能反过来**：

1. `git pull` 拉新版代码（包含迁移脚本 + 新 `config.py` + 新依赖声明）。
2. `uv pip sync requirements.lock` 更新依赖（装上 `ruamel.yaml`）。
3. **不要立刻启动 bot**。先跑 `python tools/migrate_config_to_yaml.py` 生成 YAML + locale 文件 + `tools/migration_db_seed.json` + `tools/migration_report.md`。跑完**必读 report** 做人工 review（`unclassified` 字段必须逐个决策）。
4. **跑 `python tools/seed_db.py`** 把 `migration_db_seed.json` 里的 DB 类字段（`voicechannel.channel_configs` / `tickets_new.ticket_types` 等，按 P2-5 判定）灌进数据库。**这一步是必须的**，跳过会导致下一步启动后这些字段是空的（自动创建房间入口丢光、所有 ticket types 丢光）。
5. 重启 bot。新 `config.py` 读 YAML；DB 已经 seed；旧 JSON 留在原位作 fallback 安全网，直到本 PR 步骤 9 才彻底清理。
6. 验证主要路径（建房、签到、工单类型 CRUD、ban 通知）后，手动把 `bot/config/config_*.json` `mv` 到 `old_function/`。

**DB 导入路径拍板**：只走**显式手动 `python tools/seed_db.py`** 一条路，**不做 cog 首次启动 bootstrap 自动导入**。理由：
- 升级动作应该可预期、可回滚。bootstrap 隐式导入会让"重启 bot"这个无副作用操作变得有副作用。
- 如果 seed 出错，显式脚本容易打印清楚；bootstrap 错误容易被 cog 初始化流程吞掉。
- 运维日志里一行 `python tools/seed_db.py` 能清晰对应"迁移过"这个事件。

**`get_config` 过渡期兼容**：步骤 3 的 `get_config` 保留 JSON fallback —— 保护窗口**严格限定为"步骤 2 之后、步骤 9 之前"**，即 `uv pip sync requirements.lock` 已装好 `ruamel.yaml`、但还有 cog 没迁完 YAML 的过渡阶段。**不保护"步骤 1 和 2 之间"**：那段时间 `ruamel.yaml` 没装，新 `config.py` 顶部 `import ruamel.yaml` 会直接 `ImportError`，连 fallback 分支都进不去 —— 这个窗口靠升级协议明确"先 sync 再启动 bot"来规避，**不做代码层 `ImportError` lazy import 兜底**（兜底会让启动失败点变模糊，运维定位反而更麻烦）。步骤 9 才彻底删 JSON 分支。

**步骤 1：硬编码文案抽取（前置，必做）**

以下文件里面向用户的字符串必须先抽到配置里，否则 locale 切换只能切"部分字符串"：

| 文件 | 范围 |
|---|---|
| `bot/cogs/notebook_cog.py:152-167` | embed "Log Event" / "Event Object" / "Event Description" |
| `bot/cogs/notebook_cog.py:153` | `@app_commands.describe(...)` 参数描述（slash 元数据归 P1-7，但字面量本轮抽） |
| `bot/cogs/check_status_cog.py:152-178` | matplotlib 图表 title / xlabel / ylabel / legend |
| `bot/cogs/role_cog.py:925-927` | "Signature requirement has been updated..." 等反馈 |
| `bot/cogs/welcome_cog.py` | DM 文案里的字面量（需全文扫一遍） |
| `bot/cogs/giveaway_cog.py` | 待扫（与 P0-1 抽 db 同步做更高效） |
| 其他 cog | 发现即补 |

**粗扫方法**（原 `grep -n '"[A-Z]'` 单条 grep 已作废 —— 只抓大写开头英文字面量，而当前仓库用户可见文本**以中文为主**，例：`bot/cogs/check_status_cog.py:115`（`"日期格式不支持，请使用..."`）、`bot/cogs/role_cog.py:372`（`"更新签名失败..."`）、`bot/cogs/ban_cog.py:1214`（`"请提供有效的Discord邀请链接..."`）—— 这些全部会被漏掉）。

改为三路 grep 互补，每个 cog 都跑一遍：

```bash
# 1. CJK 字面量（主力，抓所有含汉字的字符串）
grep -nEP '"[^"]*\p{Han}' bot/cogs/<name>.py

# 2. 大写开头英文字面量（抓残存的英文 button label / title / error message）
grep -nE '"[A-Z][^"]*"' bot/cogs/<name>.py

# 3. 出口维度反向粗扫（抓 f-string / 字符串拼接 / 多行 triple-quote 等字面量正则漏网的场景）
grep -nE '(\.(send|send_message|edit_original_response)|\.followup\.send|Embed|add_field|set_footer|ui\.(Button|Select|TextInput)|SelectOption|app_commands\.describe)\(' bot/cogs/<name>.py
```

三份清单合并去重，得到**候选清单**（非最终清单）。对每条判断：
- **用户可见出口**（抵达 `Embed` / `send*` / `Button.label` / `Select.placeholder` / `TextInput` / `app_commands.describe` 等）→ 抽到 locale；f-string / 拼接需重构为 `t("name.key", **kwargs)` 占位形式。
- **日志 / 调试 / `_comment` / key / path** → 保留原状。

**Agent 兜底（强烈建议）**：每个 cog 手工处理完、准备提交前，用 `general-purpose` 或 `Explore` agent 对该文件再扫一遍。prompt 要点："列出该文件里所有**未经过 `t()`** 但会抵达 discord.py 用户可见出口的字符串，包括 f-string、字符串拼接、条件表达式、多行 triple-quote、通过中间变量传递的字面量。"grep 对复合字符串的 recall 差，agent 在这一块明显更强；加这遍能显著减少漏抽，对密集文案 cog（`privateroom_cog` / `tickets_new_cog` / `welcome_cog`）尤其重要。

**步骤 2：引入依赖（闭环）**

当前仓库的安装入口是 `README.md:62` 的 `uv pip sync requirements.lock`，直接依赖清单在 `requirements.txt`，lock 文件由 `uv pip compile requirements.txt -o requirements.lock` 生成。任何**只改 `pyproject.toml`** 的做法都会漏装依赖，新版代码在老环境里直接 `ImportError: ruamel`。

必须同步更新的三份文件：

1. `requirements.txt`：加一行 `ruamel.yaml`。（**不**追加 `python-dotenv`：P2-4 已撤销，token 继续走 `main.yaml`，见 P1-6 设计决策表 F 条。）
2. `requirements.lock`：**在 PR 内重新生成**。`uv pip compile requirements.txt -o requirements.lock` 跑一遍并 commit 产物（当前 `requirements.lock:3-76` 明确没有 `ruamel.yaml`，不更新就挂）。
3. `pyproject.toml` 的 `[project].dependencies`：和 P3-1 合并做。暂时 P3-1 没动的话，本步骤先只改 `requirements.txt`/`lock` 两份就够，不要留下三处声明漂移。

`README.md` 的 Setup 第 2 步 `uv pip sync requirements.lock` 保持不变，升级协议就是"拉代码 + sync lock + 跑迁移器"，顺序写进步骤 0 的"老部署升级协议"。

**步骤 3：改造 `bot/utils/config.py`**

- `get_config(name)`：迁移期按扩展名分派（存在 `<name>.yaml` 用 yaml，否则 fallback 旧 `config_<name>.json`）。所有 cog 迁完后删 JSON 分支。
- 新增 `get_locale(name, lang=None) -> dict`：读 `bot/locales/<lang>/<name>.yaml`；`lang=None` 时取 `main.locale`。
- 新增 `async def save_config(self, name, data, *, reload=True)`（供 P2-3 使用）：走 `ruamel.yaml` round-trip + `tempfile + os.replace` 原子写入。
  - **接口必须是 async**（IO + 为了和 `aiofiles` / 未来锁机制兼容）。
  - **调用端按 P2-5 分流**（详细对照表见 P2-3 建议做法第 2 条）：
    - **保留 YAML 的四处**改 `await config.save_config(...)`：`ban_cog:50`、`tickets_new_cog:1937`、`create_invitation_cog:446`、`role_cog:923`。
    - **迁 DB 的两处**改走 db manager CRUD、**不走** `save_config`：`voice_channel_cog:1046`（`save_channel_configs` 整体删除）、`tickets_new_cog:2418/2504`（`db_manager.save_config('ticket_types', ...)` 改 `add/update/remove_ticket_type`）。
    - **`role_cog:923` 特别提醒**：当前是同步调用形式 `config.save_config(...)`，如果只加 async 方法不改调用端，只是把 `AttributeError` 换成"返回 coroutine 但不 await" —— 命令依然静默失败。`role_cog.set_signature_requirement`（`role_cog.py:913`）本身是 `async def`，加 `await` 直接可行。
- 去掉硬编码的 `config_<name>.json` 路径拼接。

**步骤 4：新增 `bot/utils/i18n.py`**

- 实现 `def t(key: str, *, lang: str | None = None, **kwargs) -> str`：
  - dot-path 查找：`t("role.starsign.aries")` → `locales/<lang>/role.yaml` 里 `starsign.aries`。
  - 缺 key 的 fallback 链：`lang` → `zh_CN`（基线语言）→ 抛 `KeyError`，消息包含 dot-path 和所有尝试过的语言。**本 PR 只交付 zh_CN**，所以 `lang=zh_CN` 时不会真走到 fallback；代码仍保留这段兜底逻辑，等接第二语言时自动生效。
  - `**kwargs` 走 `str.format_map`，允许 `{name}` / `{count}` 占位符。
- 全局单例持有 loaded locales，启动时一次性加载全部语言的全部 namespace（规模小，不用 lazy）。

**步骤 5：编写 `tools/migrate_config_to_yaml.py`**

- 输入：`bot/config/config_*.json`
- 输出（按 P2-5 判定表分流到三条路径）：
  - `bot/config/<name>.yaml`：保留在 YAML 的数据字段。**迁 DB 的字段必须从这里剔除**（例如 `voicechannel.channel_configs`、`tickets_new.ticket_types` 在原 `config_*.json` 里本来就存在，但迁移后的 YAML 不能有），否则 P2-3 的 `await config.save_config(...)` 会把 DB 子树回写 YAML 制造双数据源。
  - `bot/locales/zh_CN/<name>.yaml`：用户可见文本。
  - `bot/config/<name>.yaml.example`：模板。
  - `tools/migration_db_seed.json`：**P2-5 判定为"迁 DB"的字段**，不写 YAML；由 `python tools/seed_db.py` **显式手动导入**（拍板不做 bootstrap 自动导入，见步骤 0）。
  - `tools/migration_report.md`：对照表 + 人工 review 清单。
- **判定表驱动**（不是全量 YAML 化）：脚本读一份 `tools/field_classification.yaml`，按 P2-5 当前拍板结论，清单至少包含：
  ```yaml
  # tools/field_classification.yaml
  # main.* 默认走 yaml（token 随 main.yaml 入 gitignore；不引入 env，见 P1-6 设计决策表 F 条）
  ban:
    admin_roles: yaml
    admin_users: yaml
  tickets_new:
    ticket_types: db                   # → migration_db_seed.json, 目标表 ticket_types
    # 管理员列表相关字段: yaml（按实际 key 名补齐）
  invitation:
    ignore_channel_ids: yaml           # P2-5 已拍板留 YAML
  voicechannel:
    channel_configs: db                # → migration_db_seed.json, 目标表 channel_configs
  role:
    signature.time_requirement: yaml
  # ...
  ```
  没在清单里的字段按启发式（下一条）处理 + 在 `migration_report.md` 里标 "unclassified"，必须人工确认后补进清单重跑。
- 启发式分类（兜底）：
  - `messages` key 下的所有子项 → `locales/zh_CN/<name>.yaml` 对应位置。
  - 以 `_message` / `_title` / `_description` / `_footer` / `_label` 结尾的 key → `locales/zh_CN/<name>.yaml`。
  - id / 阈值 / 布尔 → `config/<name>.yaml`。
  - `{id, name, emoji}` 混合对象（如 `starsign_name`）→ 按 slug 拆：id 和 emoji 留 config，name 进 locale。
- 生成 `.example`：复制 config 后把所有 id-like 数值（`*_id` / `*_channel_id` / `*_role_id`）替换为 `1145141919810`，token 替换为 `YOUR_BOT_TOKEN`。
- **脚本不碰 Python 代码**，只处理配置文件。Python 代码的迁移（`self.conf['xxx']` → `t(...)`）必须人工做。
- 产出 `migration_report.md`：每个 JSON 字段 → 去向（yaml / locale / db / unclassified）+ 备注；unclassified 必须人工决策后再推进。

**步骤 6：迁移试点**

**不选 `notebook_cog`**（它没有独立 feature config，`required_configs: []`，无法验证"数据/文案分离"）。

推荐 **`spymode_cog`** 或 **`welcome_cog`**：
- `spymode_cog`（300 行）：有独立 config，文字占比高，验证 i18n 流程完整。
- `welcome_cog`：有数据（字体路径、图片路径、颜色 tuple）+ 用户可见文字（DM embed），三层分工都用得上。
- 建议先 `spymode_cog` 后 `welcome_cog`，覆盖"纯文字型"和"数据+文字混合型"两种场景。

**步骤 7：批量迁移**

- 顺序：按 `self.conf['messages']` 使用量升序（小的先，逐步积累模式库）。密集使用的 `privateroom_cog` / `teamup_display_cog` / `tickets_new_cog` 放最后。
- 每迁一个 cog：
  1. 抽硬编码文案（步骤 1）→
  2. 按字段归类清单拆到 `config/<name>.yaml` + `locales/zh_CN/<name>.yaml` →
  3. 改 Python：`self.conf['messages']['xxx']` → `t('name.xxx')`；`self.conf['id_field']` → `config.get_config('name')['id_field']` →
  4. **不删旧 `config_<name>.json` / `.example`**。旧 JSON 原地留作 fallback 安全网，直到步骤 9 统一清理（见"老部署升级协议"第 5-6 步、阶段 B）。
- **"不维护双轨" 的正确含义**：迁移期 YAML + JSON 可以并存（JSON 纯作 fallback），但**只有 YAML 是权威数据源** —— 运行时代码优先读 YAML，任何运行时写回（`await config.save_config(...)`）也只写 YAML；**禁止再手工编辑旧 JSON**（bot 不会回读，只会让你以为改了）。所有 cog 迁完、生产稳定运行后，步骤 9 一次性把 JSON 搬进 `old_function/`。

**步骤 8：启动校验（与 P1-4 合并）**

- 用 pydantic / dataclass 给每份 config 写 schema，启动时校验。
- **key 对齐校验**：对"slug 映射型"字段（`starsign` / `mbti` 等），校验 `config['starsign'].keys()` ⊆ 每个 locale 文件 `starsign` 下的 keys。缺任一 locale 的任一 slug 即启动失败，错误消息精确到 dot-path。
- `ruamel.yaml` 解析失败 = 启动失败，不 fallback。

**步骤 9：兼容路径清理**

- 所有 cog 迁完后：
  - `config.py` 删除 JSON loader 分支。
  - 把 `bot/config/config_*.json` / `.example` 整体 `mv` 到 `old_function/`（按项目约定保留历史）。
  - 更新 `README.md` 配置小节，删除"复制 `.example`"的 JSON 版说明。

#### 与其他项的耦合（必读）

- 与 **P1-4（配置结构校验）**：**合并做**，步骤 8 就是它。本条不落地 P1-4 就不完整。
- 与 **P2-3（save_config 统一）**：本条步骤 3 的 `save_config` 是 P2-3 的实现载体。P2-5 已把 5 处运行中写回分流为 **4 处留 YAML**（`ban / tickets_new 管理员 / create_invitation / role`，改 `await config.save_config(...)`）+ **2 处迁 DB**（`voice_channel.save_channel_configs` 整体删除、`tickets_new_cog:2418/2504` 的 `db_manager.save_config` 改走 `ticket_types` 表 CRUD）。两类改法别混。
- 与 **P2-5（可变配置该留 YAML 还是下沉 DB）**：建议 P1-6 前先定结论，避免迁完 YAML 又马上迁 DB。保留下来的 `save_config` 调用就走本条新接口。
- 与 **P1-3（大 cog 拆包）**：两者都大改同一批文件，冲突严重。**先 P1-6 后 P1-3**，或在拆包 PR 里顺手换配置格式。
- 与 **P1-7（Slash 元数据）**：可以同 PR 也可以分开。`locales/<lang>/commands.yaml` 的位置在本条定。
- 与 **P0 系列**：代码分层（P0-1~P0-3）和裸 except（P0-4）独立，无冲突，可并行。

#### 风险

- 运行时缺 key 只有触发到才暴露 → 必须跟 P1-4 schema 校验同 PR 合并，启动即拦截。
- YAML 缩进敏感，一个空格启动失败；CI 加 `python -c "from ruamel.yaml import YAML; YAML().load(open('...'))"` 对每个 yaml 预检。
- 迁移脚本的启发式分类必有漏网（中文字段名、非 `_message` 结尾的文案字段）→ 产出 `migration_report.md` 强制人工 review。
- 老部署升级顺序（完整 5 步，详见步骤 0"老部署升级协议"）：**`git pull` → `uv pip sync requirements.lock` → `python tools/migrate_config_to_yaml.py` → `python tools/seed_db.py` → 重启 bot**。脚本本身在新版代码里，**不能**在拉代码前跑。**漏掉 `seed_db.py` 这一步，启动后 `voicechannel.channel_configs` 和 `tickets_new.ticket_types` 会是空的**（P2-5 已判定这两项迁 DB），表现为"自动创建房间入口全没了、所有 ticket type 全没了"。新 `config.py` 保留 JSON fallback 作为安全网，但 fallback 只管 YAML 类配置，DB 类配置没 seed 就是空的 —— 安全网救不回来。
- **一次性 PR 范围大**，所有 cog 都动。按 cog 切小 commit，review 阶段逐 cog 过；否则 2000+ 行 diff 一次性 review 容易漏。

#### 验收

- `bot/config/` 下无 `.json`（已移入 `old_function/`）。`bot/locales/zh_CN/` 一套完整；`bot/locales/en_US/` **本 PR 不交付**（P1-6 决策表 B2 条），但 i18n 框架（目录约定 + `t()` 多语言能力 + schema 校验）实现完整。
- 抽样核查 zh_CN 下运行时响应文本（embed / 按钮 / 反馈 / matplotlib 图表）确实通过 `t()` 拉起、无硬编码漏网。抽样路径：签到 / 成就查询 / 创建工单 / ban 通知 / 私房购买 / 星座领取。**原"切 `locale: en_US` 重启验证"验收已撤销**，留给未来接第二语言时再做。
  - 注：slash 命令 description / params 的本地化由 **P1-7** 验收，不纳入本条。
- 未来新增第二语言（如 `en_US` / `ja_JP`）只需复制 `locales/zh_CN/` 改翻译，不改 Python；启动校验会在 key 缺失时报错。
- `grep -rn "conf\['messages'\]" bot/` 结果为空。
- 保留 YAML 的四处 `config.save_config(...)` 调用点（`ban_cog:50` / `tickets_new_cog:1937` / `create_invitation_cog:446` / `role_cog:923`）都以 `await` 形式调用；`role_cog:923` 的同步调用已改为 `await config.save_config('role', ...)`，`/signature_set_requirement` 执行后 `config_role.yaml` 实际落盘（之前的 `AttributeError` 静默失败消失）。
- 迁 DB 的两处旧写回已**删除**：`voice_channel_cog.save_channel_configs` 方法不复存在、调用点改走 `VoiceChannelDatabaseManager` 的 CRUD；`tickets_new_cog:2418/2504` 改调 `add_ticket_type / update_ticket_type / remove_ticket_type`。`grep -rn "save_channel_configs\|db_manager.save_config" bot/` 结果为空。
- `.gitignore` 已更新：`bot/config/main.yaml.example` 和 `bot/locales/**/*.yaml` 进 git；`bot/config/main.yaml`（含 token / 真实 id，属敏感配置）、`tools/migration_db_seed.json`、`tools/migration_report.md` 不进 git。
- `tools/migrate_config_to_yaml.py` 对 `bot/config/config_*.json` 可跑；`tools/seed_db.py` 对 `migration_db_seed.json` 可跑；两者跑完后新代码启动 + 关键路径可用。
- `tickets_new` ticket type CRUD（`/tickets_add_type` / 编辑 / 删除）**实际能落盘**：新增/删除后重启 bot，type 列表保持一致（之前 `db_manager.save_config(...)` AttributeError + `get_config` 不覆盖 ticket_types 造成重启丢失的故障，随 P2-5 迁 DB 同步修复）。

### P1-7. Slash 命令元数据本地化

> ⚠ **本条实现前必须先验证 API 细节**。当前仓库依赖 `discord-py==2.7.1`（`requirements.lock:25`），官方推荐的 slash 本地化链路是 `app_commands.locale_str` + `app_commands.Translator`，而不是直接传 `name_localizations={...}` / `description_localizations={...}` dict。两种用法都能工作，但 `locale_str + Translator` 是集中化的、可配合 P1-6 的 locale 文件；手填 dict 则散落在每个 `@app_commands.command(...)` 上。确认实现前先阅读：
> - https://discordpy.readthedocs.io/en/stable/interactions/api.html#discord.app_commands.locale_str
> - https://discordpy.readthedocs.io/en/stable/interactions/api.html#discord.app_commands.Translator
> - `CommandTree.set_translator(...)` 的用法

**背景**
Discord 对 slash 命令的 name / description 支持**原生本地化**：由客户端根据用户语言自动展示对应翻译。机制跟 P1-6 的 `t()`（根据 bot 的 `main.locale` 选一门语言回复用户）**完全不同**，不应混在同一套接口里。

**现状**
- 绝大多数 `@app_commands.command(name=..., description=...)` 和 `@app_commands.describe(...)` 都是硬编码英文（例：`notebook_cog:152-155`）。
- 没有 `locale_str` / `Translator` / `*_localizations` 使用点。

**推荐方案（locale_str + Translator，待验证）**

1. **slash 命令的 `description` 和参数 describe 字符串**改成 `locale_str("key")`，其中 `key` 是 dot-path（如 `"notebook.notebook_log.description"`）。**`name` 默认保持英文字面量、不套 `locale_str`** —— Discord 对 slash `name` 字符集有强约束（仅允许小写字母 / 数字 / 下划线 / 连字符，不许空格或大写），中文 name 会被 API 拒绝，所以默认不走本地化；后续若某组命令的 localized name 全部能满足约束再单独验证，不纳入本条默认流程（字符集限制详情见第 4 条 YAML 示例后的注）。Discord 注册命令时 `CommandTree` 会通过 Translator 把 `locale_str` 解析成各语言的版本：
   ```python
   @app_commands.command(
       name="notebook_log",
       description=locale_str("notebook.notebook_log.description"),
   )
   @app_commands.describe(
       event_object=locale_str("notebook.notebook_log.params.event_object"),
       event_description=locale_str("notebook.notebook_log.params.event_description"),
   )
   async def log_event(self, interaction, ...):
       ...
   ```
2. 写一个全局 Translator `bot/utils/slash_translator.py`，继承 `app_commands.Translator`，实现 `translate(string, locale, context)`：
   - 读 `bot/locales/<lang>/commands.yaml`（格式见下）。
   - 把 `locale` 从 Discord 内部表示（`Locale.chinese` 等）映射到仓库里的语言 slug。**本 PR 只需映射 Discord `zh-CN` → 仓库 `zh_CN`**，其他 locale 一律返回 `None`，让 Discord fallback 到 `locale_str` 的默认英文字面量（decorator 里 `name=` 处的直接字符串）。未来接第二语言时在这张映射表里加行即可。
   - 命中返回翻译字符串；未命中返回 `None`（Discord 会 fallback 到 `locale_str` 的默认值或 `name=`/`description=` 里的直接字符串）。
3. 在 `bot.setup_hook` 里 `await bot.tree.set_translator(SlashTranslator())`。
4. `bot/locales/<lang>/commands.yaml` 格式：
   ```yaml
   # bot/locales/zh_CN/commands.yaml
   notebook:
     notebook_log:
       description: "记录一次事件日志"
       params:
         event_object: "要记录的成员"
         event_description: "事件描述"
   ```
   注意：Discord slash **name 字段字符集受限**（小写字母 / 数字 / 下划线 / 连字符，且不许空格或大写），中文 name 会被 API 拒绝；一般只本地化 `description` 和 `params`，name 保持英文。

**备选方案（手填 localizations dict）**
直接往 `@app_commands.command(..., description_localizations={"zh-CN": "...", "en-US": "..."})` 里塞 dict。简单直接，但每个命令一遍模板代码、翻译散落各处。仅在 Translator 方案验证失败时采用。

**与 P1-6 的关系**
- `bot/locales/<lang>/commands.yaml` 的位置在 P1-6 定；加载机制本条决定。
- P1-6 的 `i18n.py` 处理**运行时响应文本**（bot `main.locale`），本条处理**命令元数据**（用户客户端 locale），共享 YAML 目录但用不同的 loader。不要让 `t()` 去读 `commands.yaml`。
- **不是 P1-6 的前置**，可以独立 PR。

**验收**
- 切换 Discord 客户端语言为**简体中文**：`/notebook_log` 在命令补全栏显示中文 description / 参数提示（来自 `locales/zh_CN/commands.yaml`，由 Translator 命中返回）。
- 切换 Discord 客户端语言为 **English**（或任何非 zh-CN locale）：显示 decorator `name=` / `description=` 处的**默认英文字面量**（即 `locale_str(...)` 的 fallback；当前 PR **不**通过 `locales/en_US/commands.yaml` 提供翻译，详见 P1-6 决策表 B2 条）。这条同时验证 Translator 在未命中时正确返回 `None`、未把 key 字符串当文案展示。
- 新增语言只需在 `locales/<lang>/commands.yaml` 加翻译，不改 Python。
- Translator 命中率通过日志验证：未命中的 key 打 warning（便于定位漏翻）。

---

## P2：中期改进

### P2-1. 数据库连接复用
- **问题**：所有 db 方法都 `async with aiosqlite.connect(...)`，每次新建连接。签到、成就统计、语音计时等高频路径开销偏大。
- **前置条件（必做）**：当前各 manager 没有统一的 `close()` 方法，`bot/main.py` 也没有资源回收钩子（只有 `run_bot()` 起 bot，没有 `on_close` / `close()` 调用）。如果直接改成长连接，进程退出时连接不会干净关闭，SQLite WAL/journal 可能残留。
- **建议（按顺序）**：
  1. 先设计生命周期：为所有 `*DatabaseManager` 统一补 `async def close(self)`；基类或 protocol 化。
  2. 在 bot 关闭钩子里（`commands.Bot.close` 重载 或 discord.py 的 `on_disconnect` 语义）遍历所有 cog，对持有 manager 的执行 `close()`。
  3. 再把 `async with aiosqlite.connect(...)` 改成长连接模式（`initialize_database` 打开 / `close()` 释放）。
  4. 高频路径先验证：achievements、shop、voice 三个。
- **替代方案**：如果不想维护生命周期，可评估 `aiosqlite.Connection` 池化库。

### P2-2. Schema 迁移机制
- **问题**：所有表仅靠 `CREATE TABLE IF NOT EXISTS`，列变更没有迁移路径。
- **建议**：
  - 简单方案：加 `schema_version` 表 + 手写迁移函数链。
  - 中等方案：引入 `yoyo-migrations` 或 `alembic`（sqlite 支持有限需评估）。

### P2-3. `save_config` 写回统一策略

**问题范围（全仓库 5 处运行中的写回 + 2 处隐藏 bug）**

| 位置 | 状态 |
|---|---|
| `bot/cogs/ban_cog.py:50` `save_config` | 有 try/except，会 reload |
| `bot/cogs/tickets_new_cog.py:1937` `save_config` | 有 try/except，会 reload |
| `bot/cogs/create_invitation_cog.py:446` `save_config` | **无 try/except**，也不 reload |
| `bot/cogs/voice_channel_cog.py:1046` `save_channel_configs` | 写 `config_voicechannel.json`，不 reload |
| `bot/cogs/role_cog.py:923` | 调用 `config.save_config('role', self.role_config)`，但 **`bot/utils/config.py` 里没有这个方法**，触发即 `AttributeError`。signature 功能小众，线上基本不触发。 |
| `bot/cogs/tickets_new_cog.py:2418`、`:2504` | 调用 `self.cog.db_manager.save_config('ticket_types', ...)`，**`bot/utils/tickets_new_db.py` 里没有这个方法**，触发即 `AttributeError`。**影响面远大于 role**：add / edit / delete ticket type 三个核心工单管理操作全部静默失败。紧接着 `:2421`、`:2507` 的 `db_manager.get_config()` 也只返回 `{ticket_channel_id, info_channel_id, main_message_id}` 三个字段（`tickets_new_db.py:106-111`），**根本不包含 `ticket_types`** —— 就算 `save_config` 能 work，reload 也拿不回来，内存里改的 ticket_types 重启即丢。 |

**严重性说明**：`tickets_new` 的这条 bug 影响面大（工单系统的类型管理完全不能用），症状被 discord.py 的 error handler 吞成"命令无响应"所以没人报过。**不独立拆 P0**：在旧 JSON 架构下补一个 `save_config('ticket_types', ...)` 方法只是过渡、迁 DB 后会被丢弃 —— 等于同一段逻辑写两遍。**跟 P1-6 一起修、直接走新架构**（`ticket_types` 表 + CRUD 四方法，见下面建议做法第 5 条）。

**核心问题**

1. 四处代码重复（读 JSON → `dict.update` → 写回 → 手动 reload），复制粘贴产物。
2. 手动 reload 方式不一致：ban / tickets 走 `Config()` 再 `reload_config('xxx')`；invitation / voice 压根没 reload。
3. 无写入原子性（未用 `tempfile + rename`），进程在 write 中途崩溃会留下半写 JSON。
4. `create_invitation_cog` 无异常处理，IO 失败会把错误抛到 Discord 交互层。
5. `role_cog:923` 是**潜在 AttributeError**，小众功能不升 P0，随本条一并修。
6. `tickets_new_cog:2418/2504` 是**实际发生的 AttributeError**，且 reload 路径也残缺；修法跟 role_cog 不同：`ticket_types` 字段按 P2-5 判定**应迁 DB**（字典映射 + 运行时频繁增删），所以不是补 `db_manager.save_config` 方法，而是让 ticket_types 走 db manager 的 CRUD 方法（增类型用 `add_ticket_type(name, data)`，删用 `remove_ticket_type(name)`，内存态改成每次从 DB 查询）。

**建议做法（与 P1-6 合并实现）**

1. `bot/utils/config.py` 新增 `async def save_config(self, config_name, data, *, reload=True)`：
   - 走 `ruamel.yaml` round-trip（保留注释）+ `tempfile.NamedTemporaryFile` + `os.replace` 原子写入。
   - 写完内部 reload，避免各 cog 各自 reload。
2. **仅"保留在 YAML"的写回路径改为 `await config.save_config(...)`**（按 P2-5 判定表分流，不要误把迁 DB 的也一并改了）。逐处对照：

   | 位置 | P2-5 去向 | 本条处理 |
   |---|---|---|
   | `ban_cog:50` `save_config` | YAML | 改为 `await config.save_config('ban', ...)` |
   | `tickets_new_cog:1937` `save_config`（管理员列表相关） | YAML | 改为 `await config.save_config('tickets_new', self.conf)`，**前提**：`self.conf` 必须不再包含 `ticket_types`（见下面第 5 条）。否则整包回写会把已迁 DB 的 `ticket_types` 又落回 YAML，制造双数据源。现行代码 `tickets_new_cog:1946` 的 `config_data.update(self.conf)` 正是这个坑点。 |
   | `create_invitation_cog:446` `save_config`（`ignore_channel_ids`） | 保留 YAML（P2-5 已拍板） | 改为 `await config.save_config('invitation', ...)` + 补交互层失败反馈 |
   | `role_cog:923` 同步 `config.save_config(...)` | YAML（`signature.time_requirement`） | 改为 `await config.save_config('role', ...)`（同时修掉 AttributeError；所在函数 `role_cog.py:913` 本身是 `async def`） |
   | `voice_channel_cog:1046` `save_channel_configs` | **DB** | **删除整个方法和所有调用点**，改走 `voicechannel_db.py` 的 CRUD（第 4 条） |
   | `tickets_new_cog:2418/2504` `db_manager.save_config('ticket_types', ...)` | **DB** | **删除调用**，改走新 `ticket_types` 表的 CRUD（第 5 条） |

   注意 `role_cog:923` 当前是同步形式，只加 async 方法、不改调用端 ≠ 修好：会从 `AttributeError` 变成"拿到一个 coroutine 但不 await" —— 命令依旧静默失败，只是症状变得更隐蔽。
3. `create_invitation_cog:446` 补交互层失败反馈（向用户显示"保存失败，请联系管理员"），别再裸抛到 Discord 交互层。
4. **迁 DB 的字段**（`voicechannel.channel_configs` + `tickets_new.ticket_types`，见 P2-5）：对应 `save_config` 调用**直接删除**，改走 db manager 的 CRUD；**不要**先补一个旧 YAML 版 `save_config` 再删掉，等于白写。
5. **`tickets_new_cog:2418/2504` 具体修法**：
   - 新建表 `ticket_types(type_name PRIMARY KEY, type_data JSON)`；
   - `TicketsNewDatabaseManager` 加 `add_ticket_type / update_ticket_type / remove_ticket_type / list_ticket_types` 四个方法；
   - **`self.conf` 彻底不再持有 `ticket_types` 这个 key**（关键：避免 `save_config('tickets_new', self.conf)` 把 DB 子树回写 YAML）。具体做法：
     - 初始化时从 YAML 读 `self.conf = config.get_config('tickets_new')`，然后 `self.conf.pop('ticket_types', None)` 丢掉（或者迁完后 YAML 里本来就没有这个 key —— 迁移脚本 + `field_classification.yaml` 要保证 ticket_types 不落 YAML）。
     - 新增 `self.ticket_types = {}` 缓存（或直接每次查 DB），由启动 / 增删时 `await self.db_manager.list_ticket_types()` 刷新。
     - 所有 `self.cog.conf['ticket_types']` 的读点改成 `self.cog.ticket_types` 或 `await self.cog.db_manager.list_ticket_types()`（当前已知至少 `tickets_new_cog:1997 / :2002` 等位置，批量 grep 确认）。
     - 所有写点（2418/2504 等）改成 `await self.cog.db_manager.add_ticket_type / remove_ticket_type(...)`，同时维护 `self.ticket_types` 缓存一致性。
   - `db_manager.get_config()` 不再负责 `ticket_types`（本来也没负责，`tickets_new_db.py:106-111` 只返回三个 channel id）。
   - **迁移脚本对齐**：`tools/field_classification.yaml` 里 `tickets_new.ticket_types: db`，迁移脚本生成 `bot/config/tickets_new.yaml` 时显式跳过 `ticket_types` 这个 key，把它写到 `migration_db_seed.json` 的 `ticket_types` 条目下，由 `seed_db.py` 灌入新表。
6. **`voice_channel_cog:1046` 具体修法**：
   - 新建表 `channel_configs`（`channel_id PRIMARY KEY, name_prefix, type, ...`）；
   - `VoiceChannelDatabaseManager`（P0-3 里新建的）提供 `upsert_channel_config / delete_channel_config / list_channel_configs`；
   - cog 里 `save_channel_configs` 方法整个删除，原三处调用（`:56 / :78 / :924`）改为对应 CRUD 操作；
   - **`self.channel_configs` 的处理**：cog 本来就用的是独立属性（不在 `self.conf` 里），没有"回写 YAML"的风险 —— 但仍要确保 `config_voicechannel.yaml` 里**没有** `channel_configs` 这个 key（`field_classification.yaml` 里 `voicechannel.channel_configs: db`，迁移脚本据此把该字段剔出 YAML）。voicechannel 相关的其他 YAML 字段（阈值等）继续走 `get_config('voicechannel')` 读取。

### P2-4. ~~Token / 敏感信息迁出 JSON~~（已撤销）

> **状态**：第九轮审核撤销，不会做。
>
> **理由**：当前项目没有 `.env` / 环境变量设计，未来也不计划引入。token 继续放 `main.yaml`，靠 `bot/config/*.yaml` gitignore + `old_function/` 归档硬规则（见步骤 0）保障不入 git；引入 env 层会额外增加启动脚本 / systemd unit / 部署文档的切换点，收益不抵成本。
>
> **设计决策位置**：P1-6 决策表 F 条。
>
> **编号保留占位**：不重编 P2-5 / P2-6，避免后续引用漂移。

### P2-5. 可变配置：留 YAML 还是下沉 DB

**背景**
P2-3 列的 5 处运行时写回都在写"动态数据"：管理员列表、ignore 频道、房间配置、签名阈值。这类东西**是否该继续用配置文件**，还是应该迁到 DB？

用户确认：**不一刀切全迁 DB**。判断标准如下。

**判定表**

| 配置项 | 当前位置 | 建议去向 | 理由 |
|---|---|---|---|
| `ban.admin_roles` / `ban.admin_users` | `config_ban.json` | 保留 YAML | 运维级名单，运行前初始化，变更频率低，手动看文件一目了然。运行时增删 → 走统一 `save_config`。 |
| `tickets_new` 管理员列表（全局 + 按类型） | `config_tickets_new.json` | 保留 YAML | 同上。 |
| `tickets_new.ticket_types` | `config_tickets_new.json` | **迁 DB**（且顺带修 P2-3 里列的两个 AttributeError） | 字典映射 `{type_name: type_data}`，管理员运行时 add/edit/delete，每个类型含 label/description/button_color/admin_roles/admin_users 等。**当前代码 `tickets_new_cog:2418/2504` 已经在调用不存在的 `db_manager.save_config('ticket_types', ...)`**（详见 P2-3 第 6 条），意味着"改 ticket type"的功能现在根本没工作，运行时可变性确凿。迁 DB 同时修掉这个实际故障。 |
| `invitation.ignore_channel_ids` | `config_invitation.json` | **保留 YAML** | 数据性质和 `ban.admin_roles` 同类（低频增删的运维级名单，管理员想手动看文件诊断）；数量有限，不到需要 DB 查询优化的量级；为单一列表新建 `invitation_db.py` 代价不成比例。运行时增删走 `await config.save_config('invitation', ...)`。 |
| `voicechannel.channel_configs` | `config_voicechannel.json` | **迁 DB** | 每次管理员添加一个"自动创建房间"入口都会写回；数据结构为 `{channel_id: config}` 映射，天然像 DB 表。现在写回把整个大字典重写一次，写得越多越慢。 |
| `role.signature.time_requirement` | `config_role.json` | 保留 YAML | 单个阈值标量，运行前确定，偶尔调。 |

**建议做法**

1. **P1-6 之前先定结论**：哪些字段迁 DB、哪些留 YAML，写进本表。避免迁完 YAML 又马上迁 DB 造成重复返工。
2. 判定结论固化到 `tools/field_classification.yaml`（见 P1-6 步骤 5），供迁移脚本读取；迁移脚本据此把"迁 DB"的字段写入 `tools/migration_db_seed.json`、**不写入 YAML**。
3. 迁 DB 的字段：新建或扩展对应 db manager（`voicechannel_db.py` / `tickets_new_db.py` 的 `ticket_types` 表），提供 CRUD 接口；相应的 `save_config` 调用**直接删除**。
4. 导入路径只走**显式手动** `python tools/seed_db.py`（见 P1-6 步骤 0 "老部署升级协议"），**不做 cog 首次启动 bootstrap 自动导入**。避免隐式行为。
5. 留 YAML 的字段：走 P2-3 新统一 `save_config` 接口。

**判定原则**
- **需要在运行前初始化 / 手动看文件诊断** → YAML
- **运行时增删频繁 / 数据规模随使用增长 / 有并发写风险** → DB
- 单个标量、小列表倾向 YAML；字典映射、大列表、关系型结构倾向 DB

---

## P3：工程化与整洁度

### P3-1. 依赖管理统一
- **现状**：`requirements.txt`（无锁版本）+ `requirements.lock` + `pyproject.toml`（dependencies 空）+ `uv.lock` + `.python-version` 并存。
- **建议**：把依赖统一迁到 `pyproject.toml` 的 `[project].dependencies`，用 uv 管理；`requirements.txt` 退役或自动导出。

### P3-2. 硬编码路径梳理
- **例**：`backup_cog.py` 的 `./backup/db_backup`；`ban_cog.py` 的 `./bot/config/config_ban.json`。
- **建议**：基于 `Path(__file__)` 或配置键，避免依赖启动时的 CWD。

### P3-3. 清理根目录空 `bot.db`
- 根目录 `bot.db`（0 字节）疑似误创建，实际 DB 在 `./data/bot.db`，确认后删除。

### P3-4. 补自动化测试
- **现状**：零测试，17k 行代码全靠测试服手点。
- **建议**：优先给 db 管理器（纯函数多、副作用可控）写 `pytest + tmp sqlite` 单元测试；ROI 最高。

### P3-5. 引入 ruff / linter 配置
- `pyproject.toml` 加 `[tool.ruff]`，默认启用 `E`、`F`、`W`、`B`（bugbear），特别是 `E722`（bare-except）锁死 P0-4 成果。

### P3-6. 归档目录清理规划
- **现状**：`old_function/`、`old_test/`、`old_updates.md` 随时间膨胀。
- **建议**：git 本身保留历史，可给每个归档文件标注"到 vX.Y 可真删"时间线，定期清理。

### P3-7. 日志里用户 / 频道的 id ↔ name 双记录

**提出背景**：2026-04-23 测试 P0 系列时，用户反馈日志只记 `User 123456` 很难快速定位是谁；同理看到 `频道A` 也要查 id 才能 grep。希望日志里**凡是记录一个用户或频道**，都同时附带 id + 可读 name。

**现状问题**：
- 绝大多数 cog 里的 `logging.info` / `logging.error` 只记一边。示例：
  - `role_cog.py:186` `User {interaction.user.id} has removed the {star_sign_role.name} role` → 只有 id
  - `voice_channel_cog.py:933` `logging.warning(f"Voice channel {voice_channel_id} not found during restore")` → 只有 id
  - `tickets_new_cog.py` 部分日志只有 `Error creating ticket thread: {e}` → user 信息全无
- 排障时要么到 Discord 里查 id 要么 grep 出一堆记录，效率低。

**建议做法**：
1. 在 `bot/utils/` 新增 `log_helpers.py`，提供：
   ```python
   def fmt_user(user) -> str:
       """'display_name (id)' for Member/User; 'unknown (id)' for raw int."""
   def fmt_channel(channel) -> str:
       """'name (id)' for Channel/Thread; 'unknown (id)' for raw int."""
   def fmt_role(role) -> str:
       """'name (id)' for Role."""
   ```
2. **不强推**立刻全仓替换（17k 行），而是定下**新写代码必须走 `fmt_*` 帮助函数**；老代码在触碰时顺手改。
3. 结构化日志字段（如果未来上 JSON logger）可以一并设计，但本条不强制。

**验收**：
- `bot/utils/log_helpers.py` 存在且导出三个函数。
- `bot/utils/__init__.py` 导出。
- 抽样验证：改过的几个 cog（至少 role_cog、voice_channel_cog、tickets_new_cog）日志里所有 `User {id}` / `Channel {id}` 类记录都至少带一边额外信息。
- 新的 PR 审核时把"是否用了 `fmt_*`"纳入 checklist。

**不要做**：
- 不要写 `logging.info(f"User {id} {name}")` 的裸 f-string —— 容易漏；走帮助函数统一格式。
- 不要为了日志可读性**引入 N+1 Discord API 查询**（例如为记 name 去 `await guild.fetch_member(id)`）。`fmt_user` 接 Member/User 对象就好，Discord gateway 已经提供 cache；当 callsite 只有 raw int 时记为 `"unknown (id)"` 是可接受的。

**与其他项的耦合**：
- 与 P1-5（日志 rotation）可以在同一冲刺做（都是 logging 层改动）。
- 与 P3-5（ruff）可以加 lint 规则禁止 `logging.*(f"... {user_id} ...")` 这种裸 id f-string（高级要求，可选）。

---

## 推进顺序建议

1. **本轮冲刺（P0）**：P0-4（裸 except 治理，范围清晰、改动小、风险低）→ P0-1（giveaway 抽 db）→ P0-2（privateroom 规范化）→ P0-3（其余 cog 补 db manager，内部以 `check_status` 为首）。
2. **下一轮（P1，小步）**：P1-5（日志 rotation）、P1-2（ban_cog 迁 cog_load）、P1-1（命令同步）—— 三个都是改动小、受益长期。
3. **配置系统 2.0（绑定一次冲刺做）**：**P1-6（YAML + i18n）+ P1-4（配置 schema 校验）+ P2-3（save_config 统一）+ P2-5（可变配置 DB 判定）** 高度耦合，一起做。（原 P2-4 已撤销，token 留 `main.yaml`，不纳入本冲刺。）
   - 启动前必须完成：**P2-5 的判定表**（决定哪些字段迁 DB）。
   - 并行或紧接完成：**P1-7（Slash 元数据本地化）**。
4. **大 cog 拆包（P1-3）**：放在配置系统 2.0 之后，或与 P1-6 绑同一 PR（拆包时顺手换 YAML，一次 review 双收益）。不要在 P1-6 之前单独拆。
5. **长期（剩余 P2/P3）**：结合功能迭代穿插。P2-1 之前必须先完成长连接生命周期前置。

---

_最后更新：2026-04-22（第十轮审核修订：拍板**首轮只交付 zh_CN**（当前部署全是 zh_CN 用户，硬抽 en_US 没实际使用者），P1-6 决策表加 B2 条"首轮交付语言 = zh_CN only"；相关措辞同步降调 —— 目标目录结构把 `en_US/` 注释为"预留位，本 PR 不创建"；`t()` fallback 链改为 `lang → zh_CN（基线）→ KeyError`；验收删掉"切 `locale: en_US` 重启"条目，改为抽样核查 zh_CN 下 `t()` 拉起无漏网；P1-7 Translator 映射改为仅 Discord `zh-CN` → 仓库 `zh_CN`，其他 locale 返回 `None` fallback 到默认英文字面量。i18n 框架（目录约定、`t()` 多语言能力、schema 校验、fallback 兜底）仍完整实现，接二语时不改架构。步骤 1 的硬编码文案粗扫方法重写 —— 原 `grep -n '"[A-Z]'` 被证伪（漏掉所有中文字面量，例：`check_status_cog:115`、`role_cog:372`、`ban_cog:1214`），改为三路 grep 互补（CJK 字面量 + 大写英文字面量 + 出口维度反向扫）+ Agent 兜底（处理完每个 cog 用 `general-purpose` / `Explore` agent 列 f-string / 拼接 / 多行 string 等 grep 漏网的用户可见文本）。附：P1-7 验收第 1 条按 B2 条口径拆成两行 —— 简体中文走 Translator + `locales/zh_CN/commands.yaml` 命中、English / 其他 locale 走 decorator 默认英文字面量 fallback（不通过 `locales/en_US/commands.yaml`），顺手验证 Translator 未命中时正确返回 `None` 而不是把 key 当文案展示）_
_上一轮（第九轮）：确认项目不走 env / `.env` 路线 —— P2-4 整条撤销（改为"已撤销"占位条目 + 原因说明），P1-6 设计决策表新增 F 条"敏感信息位置 = `main.yaml`，不引入 env 层"；步骤 2 依赖清单去掉 `python-dotenv` 条件追加，`field_classification.yaml` 示例删除 `main.token: env` 行（main.* 默认 yaml），P1-6 耦合叙述 / 推进顺序 / 验收措辞（改"含 token / 真实 id，属敏感配置"）同步清理；Finding 1 修 `get_config` JSON fallback 保护窗口口径 —— 严格限定"步骤 2 之后、步骤 9 之前"（sync 前启动 bot 因 `ruamel.yaml` 未装会直接 `ImportError`，连 fallback 都进不去，不做代码层 lazy import 兜底，靠升级协议"先 sync 再启动"规避）；Finding 2 修 P1-7 slash 指令第 1 条 —— 明确 `name` 默认保持英文字面量、仅 `description` / `params` 走 `locale_str`（Discord 对 slash `name` 字符集强约束，中文 name 会被 API 拒绝），与第 4 条 YAML 示例后注不再矛盾）_
_上一轮（第八轮）：统一"旧 JSON 保留到步骤 9 清理"口径 —— 步骤 7 原"每迁一 cog 就删 JSON"改成"不删，生产稳定后步骤 9 统一搬 `old_function/`"，并在"不维护双轨"里明确 YAML 为唯一权威源、禁止手工编辑旧 JSON；步骤 0 新增"`old_function/` 归档硬规则"章节并同步写进 `AGENTS.md`（安全与配置提示）—— `old_function/**/*.json|*.yaml` 一律 gitignore，`.example` 脱敏模板不受影响；历史遗留 `old_function/config/config_tickets.json` / `config_rating.json`（已含真实 ID 入 git）走 `git rm --cached` 认账，不做 filter-repo 重写历史；P2-3 `invitation.ignore_channel_ids` 口径对齐 P2-5 拍板（"保留 YAML"）不再留"开发时再评估"悬置）_
_上一轮（第七轮）：P2-5 拍板 `invitation.ignore_channel_ids` 留 YAML，`field_classification.yaml` 可一次定稿；步骤 0 .gitignore 改成**阶段 A/B 分段**；P2-3 `tickets_new_cog:1937` 明确要求 `self.conf` 剔除 `ticket_types` 避免 DB 子树回写 YAML 制造双数据源；第 5 / 6 条补齐 `self.conf` / `self.channel_configs` 与 YAML 隔离的具体处理；P1-6 步骤 5 对迁移脚本的 YAML 输出加"迁 DB 字段必须剔除"约束_
_上一轮：P2-3 建议做法第 2 条收窄到"仅保留 YAML 的写回改 await"，新增逐处对照表防止与 P2-5 迁 DB 指令互斥；P1-6 步骤 3 / 验收同步按 YAML 四处 + DB 两处分流；风险段升级顺序补 `python tools/seed_db.py` 并强调漏这步会丢 `voicechannel.channel_configs` / `ticket_types`_
_上一轮：发现 `tickets_new_cog:2418/2504` 调用不存在的 `db_manager.save_config` 且 `get_config` 不覆盖 ticket_types 的双重 bug —— P2-3 加列、P2-5 判定表加 `ticket_types` 行并判定迁 DB；步骤 0 .gitignore 追加 `migration_db_seed.json` / `migration_report.md` 防 id 泄露；老部署升级协议补 `python tools/seed_db.py` 一步并拍板只走显式手动导入、不做 bootstrap_
_上一轮：升级顺序闭环、lock 文件联动、save_config async 接口 + 调用端必须 await、迁移脚本按 P2-5 判定表分流、P1-7 改为 locale_str + Translator 并标注待验证 API_
_再上一轮：P1-6 重写三层分工 + 决策拍板 + 迁移脚本；新增 P1-7 / P2-5；P2-3 扩大到全部 5 处写回_
_更早：新增 P1-6 配置 YAML 迁移 + i18n；基于外部审核意见修订 P0-1/P0-2/P0-3/P0-4/P1-2/P2-1/P2-3_
