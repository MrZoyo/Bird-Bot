# Repository Guidelines

## 项目结构与模块组织
- 入口：`run.py` 启动并加载 `bot/` 下的各个 cogs。
- 业务逻辑：`bot/cogs/`（签到/补签、成就、角色、语音、工单等）；公共工具与数据库封装在 `bot/utils/`。
- 配置：`bot/config/*.yaml.example` 为模板，复制去掉 `.example` 生效（config 2.0 起改用 YAML；legacy `config_*.json.example` 归档在 `old_function/config/`）。文案资源在 `bot/locales/<lang>/<cog>.yaml`，运行时由 `bot.utils.i18n.t()` 读取。静态资源在 `resources/`、`pics/`。
- 数据：主库 `bot.db` 位于仓库根目录；备份在 `backup/`；旧实验代码在 `old_function/` 和 `old_test/`。

## 构建、运行与开发命令
- 安装依赖：`uv sync`（建议虚拟环境；依赖源在 `pyproject.toml`，锁定版本在 `uv.lock`）。
- 本地运行：`python run.py`（确保已配置好 token、频道/角色 ID）。
- 可选语法快检：`python -m compileall bot`。
- 动数据库前先备份：复制 `bot.db` 或在运行中的机器人使用 `/backup_now`。

## 代码风格与命名约定
- Python 3 异步优先；遵循 PEP 8，四空格缩进，能加类型注解尽量加。
- Cog 方法保持小而事件驱动；使用 logging 而非 print。
- 配置键、JSON、数据库列名用 lower_snake_case；避免硬编码 ID，优先读配置。

## 测试指引
- 无现成自动化测试；在测试服实际跑机器人，逐条验证涉及的命令与按钮。
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
- `old_function/` 仅承载已废弃的代码（cogs、工具脚本、旧 db 管理器等）；`old_function/**/*.json` 与 `old_function/**/*.yaml` **一律 gitignore**，禁止把真实 ID 通过"归档旧配置"这个动作带进 git。`.json.example` / `.yaml.example` 脱敏模板不在忽略名单里，可以入 git 供查阅历史结构。config 2.0 收官时已把 `bot/config/config_*.json`（含真 ID）与 `config_*.json.example` 模板一并 `git mv` 到 `old_function/config/`，真 `.json` 被 gitignore 自动挡下。若将来仍需归档新产物，照此直接 `mv` 即可；不要绕过规则去 `git add -f`。

## Agent 沟通要求
- 与用户交流时最终请使用中文；展示命令、路径、日志时保持简洁，不泄露敏感信息。
- 除非用户明确要求，否则在用户同意进行任何修改之前，不要直接修改，而是把修改计划给用户二次确认。
