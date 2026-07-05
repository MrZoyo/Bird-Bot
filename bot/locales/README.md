# Locales

`bot/locales/<lang>/<cog>.yaml` 是**通用默认文案（样本）**。生产部署可以直接在服务器上修改这些文件做本服定制，这类与仓库的差异是**预期行为**，不是需要"修复"的漂移。

约定：

- 升级部署时用 `git stash && git pull && git stash pop` 保留服务器本地修改；**不要**在生产机上执行 `git checkout -- .` 或 `git reset --hard`。
- 通用性的文案改进请提交回仓库；仅属于某个服务器的品牌化文案留在该服务器本地。
- 不要把主机环境事实（时区、服务器名、入口邀请码等）写死进文案：用运行时参数（例如 `shop.checkin_embed_footer` 的 `{tz_label}` 由 bot 按部署主机时区自动填充），或放进各服务器自己的 gitignored 配置。
- 新增或移动 locale 键后运行 `./.venv/Scripts/python.exe -X utf8 tools/check_locales.py`。
