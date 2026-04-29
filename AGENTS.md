# Repository Agent Entry

本文件是给自动化 coding agent 的入口说明。详细项目结构、开发约定、测试命令、迁移规则和日志规范都维护在 `CLAUDE.md`；开始工作前先读 `CLAUDE.md`，本文件只保留必须马上知道的约束。

## 必读顺序
- 先读 `CLAUDE.md`，再读当前任务相关代码。
- 涉及功能测试流程时同步查看 `REFACTORING_TEST_CHECKLIST.md`。
- 涉及重构历史、已完成/未完成状态时同步查看 `REFACTORING_PROGRESS.md` 和 `REFACTORING_PLAN.md`。

## 当前项目事实
- 入口是 `run.py`，实际 bot 构造、cog 加载和 command sync 在 `bot/main.py`。
- 运行时配置是 `bot/config/*.yaml`；旧 `config_*.json` 只用于一次性迁移或历史归档。
- 文案资源在 `bot/locales/<lang>/<cog>.yaml`，运行时通过 `bot.utils.i18n.t()` 读取。
- 主库默认是 `data/bot.db`；动数据库前先备份。
- 旧实现、脱敏旧模板和旧更新记录在 `legacy-old-files-archive` 分支；main 分支不保留 `old_function/` / `old_updates.md`。

## 开发硬规则
- 不提交真实 token、Guild/Channel/Role/User ID、真实 YAML 配置、数据库、日志或 migration seed/report。
- 日志中出现 Discord 用户、频道、线程或身份组时，用 `bot.utils.fmt_user` / `fmt_channel` / `fmt_role`，格式保持 `name (id)`；只有 raw id 时允许 `unknown (id)`。
- 不要新增裸 `except:`；需要兜底时用 `except Exception` 并记录上下文。
- 用户明确要求继续、修复、重构或测试时直接执行；如果只是方案讨论或需求不清，再先确认。
- 环境验证按用户要求在沙箱外运行，优先使用 `./.venv/Scripts/python.exe`；缺包时同步补齐依赖。

## 常用验证
- `./.venv/Scripts/python.exe -m pytest -q`
- `./.venv/Scripts/python.exe -m ruff check bot tests tools`
- `./.venv/Scripts/python.exe -m compileall bot tests tools`
- `./.venv/Scripts/python.exe -X utf8 tools/check_locales.py`
- `./.venv/Scripts/python.exe -m pip check`
- `uv lock --check`
- `uv sync --frozen --dry-run --extra test --extra lint --python 3.12.3`

## 沟通
- 与用户交流使用中文。
- 展示命令、路径、日志时保持简洁，不泄露敏感信息。
