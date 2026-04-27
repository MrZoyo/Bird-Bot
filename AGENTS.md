# Repository Guidelines

## 项目结构与模块组织
- 入口：`run.py` 启动并加载 `bot/` 下的各个 cogs。
- 业务逻辑：`bot/cogs/`（签到/补签、成就、角色、语音、工单等）；公共工具与数据库封装在 `bot/utils/`。
- 配置：`bot/config/*.yaml.example` 为模板，复制去掉 `.example` 生效（config 2.0 起改用 YAML；legacy `config_*.json.example` 已转存到 `legacy-old-files-archive` 分支）。文案资源在 `bot/locales/<lang>/<cog>.yaml`，运行时由 `bot.utils.i18n.t()` 读取。静态资源在 `resources/`、`pics/`。
- 数据：主库默认位于 `data/bot.db`（由 `bot/config/main.yaml` 的 `db_path` 控制，运行时按仓库根目录解析相对路径）；备份在 `backup/`；旧归档内容见 `LEGACY_ARCHIVE.md` 和 `legacy-old-files-archive` 分支。

## 构建、运行与开发命令
- 安装依赖：`uv sync`（建议虚拟环境；依赖源在 `pyproject.toml`，锁定版本在 `uv.lock`）。
- 本地运行：`python run.py`（确保已配置好 token、频道/角色 ID）。
- 可选语法快检：`python -m compileall bot`。
- 自动化单测：`python -m pytest`（需要 `uv sync --extra test`；当前覆盖部分纯 DB manager）。
- 裸 `except:` 回归检查：`python -m ruff check bot tests`（需要 `uv sync --extra lint`；当前只启用 `E722`）。
- 动数据库前先备份：复制 `data/bot.db` 或在运行中的机器人使用 `/backup_now`。

## 代码风格与命名约定
- Python 3 异步优先；遵循 PEP 8，四空格缩进，能加类型注解尽量加。
- Cog 方法保持小而事件驱动；使用 logging 而非 print。
- 日志里记录用户 / 频道 / 角色时优先使用 `bot.utils.fmt_user` / `fmt_channel` / `fmt_role`，保持 `name (id)` 格式；只有 raw id 时允许显示 `unknown (id)`。
- 配置键、JSON、数据库列名用 lower_snake_case；避免硬编码 ID，优先读配置。
- 不要新增裸 `except:`；需要兜底时写 `except Exception` 并记录上下文日志，或优先收窄到具体异常。

## 测试指引
- 已有少量 `pytest` 自动化测试覆盖纯 DB manager；涉及真实 Discord 交互时仍需在测试服逐条验证命令与按钮。
- 影响数据库的改动优先用临时库或备份库验证，防止污染正式数据。
- 涉及连签/余额/补签逻辑时，覆盖重复点击、额度用尽、余额不足等边界场景。

## 提交与 PR 指南
- 提交信息聚焦且用现在时，如：`优化补签窗口`、`增加语音统计日志`。
- 跨多个 cog 或数据库结构改动时，在提交正文写清范围与理由。
- PR 需说明用户可见变化、数据库迁移、手动步骤（新增配置键、需运行的命令），界面/Embed 改动附截图或日志片段更佳。
- 涉及版本号或用户功能变化时，同步更新 `README.md` 中的版本与说明，保持文档一致。

## 安全与配置提示
- Token、Guild/Channel/Role ID 属于机密，不要提交已填充的配置文件；按 `.yaml.example` 模板本地生成。
- 测试尽量使用独立测试服务器；避免让管理员命令指向生产环境。
- 持续开发前确认配置与数据库路径指向非生产副本。
- main 分支不再保留 `old_function/` / `old_updates.md` 这类旧归档文件；要查旧实现、脱敏 JSON example 或旧更新记录，切到 `legacy-old-files-archive` 分支看 `LEGACY_ARCHIVE_INDEX.md`。`old_function/**/*.json` 与 `old_function/**/*.yaml` 仍一律 gitignore，禁止把真实 ID 通过"归档旧配置"带进 git；不要绕过规则去 `git add -f`。`old_test/` 是 ignored 本地实验区，可复用测试必须进入 `tests/`。

## Agent 沟通要求
- 与用户交流时最终请使用中文；展示命令、路径、日志时保持简洁，不泄露敏感信息。
- 除非用户明确要求，否则在用户同意进行任何修改之前，不要直接修改，而是把修改计划给用户二次确认。
