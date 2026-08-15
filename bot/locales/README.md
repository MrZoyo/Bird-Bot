# Locales

<p align="center">
  <a href="../../README.md"><img src="https://img.shields.io/badge/README-HOME-2EA44F?style=for-the-badge" alt="Back to the English README"></a>
  <a href="README.zh-CN.md"><img src="https://img.shields.io/badge/READ_IN-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-5865F2?style=for-the-badge&amp;logo=googletranslate&amp;logoColor=white" alt="Read in Simplified Chinese"></a>
</p>

`bot/locales/<lang>/<cog>.yaml` contains generic default copy. The repository ships `zh_CN` as its complete sample and fallback locale; deployments may add another complete language directory and select it through `main.locale`. Slash-command descriptions for a new Discord language also need a mapping in `bot/utils/slash_translator.py`.

Production deployments may edit tracked locale files directly to customize a server. Those differences from the repository are expected deployment overrides, not drift that needs to be fixed.

Rules:

- Preserve server-local changes during upgrades with `git stash && git pull && git stash pop`. Never run `git checkout -- .` or `git reset --hard` on a production checkout.
- Submit generally useful copy improvements upstream. Keep server-specific branding in the deployment.
- Do not hardcode host facts such as the timezone, server name, or entry invite code. Supply them at runtime—for example, the bot fills `{tz_label}` in `shop.checkin_embed_footer` from the deployment host timezone—or keep them in server-owned ignored config.
- After adding or moving locale keys, run `./.venv/Scripts/python.exe -X utf8 tools/check_locales.py`.
