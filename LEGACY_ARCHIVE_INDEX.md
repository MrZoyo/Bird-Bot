# Legacy Old Files Archive

> 本分支专门保存 main 分支不再需要随运行时代码携带的旧实现、脱敏 legacy 配置模板和旧更新记录。
> main 分支如需查找这些历史材料，请切到 `legacy-old-files-archive`。

本分支是无父提交的单提交脱敏快照，不继承旧仓库历史。归档材料中的 Discord 邀请链接统一替换为占位符。

## 范围统计

统计时间：2026-04-27  
统计范围：已被 git 跟踪、且确认适合放入归档分支的 old/legacy 内容。

| 分类 | 文件数 | 行数 | 说明 |
|---|---:|---:|---|
| `old_function/cogs/` | 13 | 14257 | 已废弃 cog、拆包前快照、P3-8 移除的 NotebookCog |
| `old_function/config/*.json.example` | 16 | 1668 | config 2.0 前的 JSON 脱敏模板，仅供迁移结构参考 |
| `old_function/*_db.py` | 2 | 598 | legacy DB manager / Notebook DB manager 参考 |
| `old_updates.md` | 1 | 416 | 旧更新记录 |
| **合计** | **32** | **16939** | 不含本索引文档 |

`old_test/` 没有进入本分支索引：该目录是 gitignored 的本地实验区，包含旧日志、API scratch 和可能带有个人环境痕迹的数据文件，不按“已脱敏归档内容”处理。可复用测试必须进入 main 分支的 `tests/`。

## 文件清单

### Deprecated Cogs And Snapshots

| 路径 | 行数 | 说明 |
|---|---:|---|
| `old_function/cogs/ban_cog_pre_split.py` | 1430 | ban cog 拆包前快照 |
| `old_function/cogs/illegal_team_act_cog.py` | 404 | 已废弃功能 |
| `old_function/cogs/notebook/__init__.py` | 3 | P3-8 移除的 NotebookCog 包入口 |
| `old_function/cogs/notebook/cog.py` | 178 | P3-8 移除的 NotebookCog 主逻辑 |
| `old_function/cogs/notebook/views.py` | 136 | P3-8 移除的 NotebookCog view |
| `old_function/cogs/privateroom_cog_pre_split.py` | 1993 | privateroom cog 拆包前快照 |
| `old_function/cogs/rating_cog.py` | 560 | legacy rating cog |
| `old_function/cogs/role_cog_pre_split.py` | 1151 | role cog 拆包前快照 |
| `old_function/cogs/shop_cog_pre_split.py` | 1101 | shop cog 拆包前快照 |
| `old_function/cogs/tickets_cog.old` | 2349 | legacy tickets 历史版本 |
| `old_function/cogs/tickets_cog.py` | 1977 | legacy tickets cog |
| `old_function/cogs/tickets_cog_current.py` | 309 | tickets 历史对照文件 |
| `old_function/cogs/tickets_new_cog_pre_split.py` | 2666 | tickets_new 拆包/改名前快照 |

### Legacy Config Templates

这些文件是 `.json.example` 脱敏模板，用来查看 config 2.0 迁移前的旧 JSON 结构。真实 `.json` / `.yaml` 配置仍由 `.gitignore` 拦截，不能强行加入 git。

| 路径 | 行数 |
|---|---:|
| `old_function/config/config_achievements.json.example` | 301 |
| `old_function/config/config_ban.json.example` | 79 |
| `old_function/config/config_checkstatus.json.example` | 8 |
| `old_function/config/config_giveaway.json.example` | 32 |
| `old_function/config/config_invitation.json.example` | 26 |
| `old_function/config/config_main.json.example` | 35 |
| `old_function/config/config_privateroom.json.example` | 150 |
| `old_function/config/config_rating.json.example` | 4 |
| `old_function/config/config_role.json.example` | 277 |
| `old_function/config/config_shop.json.example` | 79 |
| `old_function/config/config_spymode.json.example` | 26 |
| `old_function/config/config_teamup_display.json.example` | 50 |
| `old_function/config/config_tickets.json.example` | 264 |
| `old_function/config/config_tickets_new.json.example` | 241 |
| `old_function/config/config_voicechannel.json.example` | 58 |
| `old_function/config/config_welcome.json.example` | 38 |

### Legacy DB Managers And Notes

| 路径 | 行数 | 说明 |
|---|---:|---|
| `old_function/notebook_db.py` | 130 | P3-8 移除的 Notebook DB manager |
| `old_function/tickets_db.py` | 468 | legacy tickets DB manager |
| `old_updates.md` | 416 | 旧更新记录 |

## 使用方式

查看旧文件：

```bash
git fetch origin
git switch legacy-old-files-archive
```

从归档分支拿回单个文件到当前分支：

```bash
git restore --source legacy-old-files-archive -- old_function/path/to/file.py
```

建议只把确实需要继续维护的内容恢复到 runtime 目录或正式文档；不要把整个 `old_function/` 再搬回 main。

## 敏感信息规则

- 本分支只保存已追踪且可公开归档的旧内容。
- 本分支不继承旧提交历史；真实 Discord ID、邀请值、token、日志和真实配置不得进入快照。
- `old_function/**/*.json` 和 `old_function/**/*.yaml` 仍视为可能包含真实 ID / token，不能 `git add -f`。
- `old_test/` 不进入归档分支，除非先人工确认没有真实日志、个人数据、token、guild/channel/role/user ID。
