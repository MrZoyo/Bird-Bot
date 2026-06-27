# 测试服真实 Discord 验证 Checklist

> 目标：自动化先排除本地可验证的业务逻辑、DB、locale、handler 顺序和失败分支；手工测试只保留真实 Discord 环境才能验证的路径。
> 当前清单按 2026-05-03 状态重写；NotebookCog、RatingCog 和旧 channel-based TicketsCog 已移除，不再作为现役功能测试项。

标记规则：
- `[ ]` 未测
- `[x]` 通过
- `[!]` 异常；在该项下面补一行“现象 / 日志 / 复现步骤”
- 手工测试只用测试服和测试库；不要直接指向生产 `data/bot.db`

---

## 0. 自动化 Gate

这些测试使用临时 sqlite DB、静态导入或 fake Discord interaction，不联网、不触碰真实 `data/bot.db`。

当前自动覆盖：
- Runtime / config / locale / command metadata / log helper / logging callsite scan。
- 所有保留 DB manager 的离线 smoke。
- JSON config 临时迁移到 YAML / locale / DB seed。
- PrivateRoom 续费日期、持久化回读、扣款顺序和失败不扣款。
- Shop、Tickets、Ban、VoiceChannel、Giveaway、Role / Signature、Achievement / Rank、Welcome / Games、CheckStatus / Backup 的 fake interaction flow。
- 组队消息和房间面板“满员”共享样式。
- 后台 loop 未登录离线 guard。

最后一次通过基线：
- [x] `./.venv/Scripts/python.exe -m pytest -q`
  - 当前：`78 passed, 8 warnings`
- [x] `./.venv/Scripts/python.exe -m ruff check bot tests tools`
- [x] `./.venv/Scripts/python.exe -m compileall bot tests tools`
- [x] `./.venv/Scripts/python.exe -X utf8 tools/check_locales.py`
- [x] `./.venv/Scripts/python.exe -m pip check`
- [x] `uv lock --check`
- [x] `uv sync --frozen --dry-run --extra test --extra lint --python 3.12.3`
  - 注意：WSL 下会提示替换 Windows `.venv`，当前只 dry-run，不实际同步。
- [x] `git diff --check`

手工测试不再重复验证：
- DB CRUD 是否正确。
- modal / button handler 的基本调用顺序。
- 本地可构造的失败分支是否写 DB / 扣款 / 发 followup。
- locale key 是否缺失。
- embed/view 的基本字段结构。

---

## 1. 启动 / 全局状态

真实 Discord 必测点：真实配置、登录、command sync、路径、removed commands、日志输出。

- [x] 使用测试服 `main.yaml` 启动 `python run.py`
  - 预期：所有启用且配置完整的 cog 被加载；缺配置或 disabled feature 只打印 skip，不抛异常。
- [x] 启动日志无 `ImportError` / `ModuleNotFoundError` / `no such table` / `OperationalError` / background task 未取回异常。
- [x] Slash command 同步完成；必要时手动跑 `!synccommands`。
- [x] Discord command picker 不显示 `/notebook_*`。
- [x] `data/bot.db`、日志、备份路径都解析到仓库根目录下的预期位置。
- [x] 抽查运行日志：用户为 `昵称 / 用户名 (id)`，频道 / 角色 / 服务器为 `name (id)`，raw id 为 `unknown (id)`，id 使用英文括号。

---

## 2. Voice / Teamup

真实 Discord 必测点：语音移动、频道权限、soundboard 权限、persistent view、真实展示消息。

- [x] `/vc_add` 添加入口频道，用户进入后自动创建临时语音房，并被移动进去。
- [x] 房间控制面板出现；Lock / Unlock 实际改变频道连接权限。
- [x] Soundboard 按钮实际切换权限，embed 状态一致。
- [x] 发送组队邀请后，从房间面板点击 Full；组队消息样式变满员，展示板移除或更新正确。
- [x] 房间无人后自动删除；`/check_temp_channel_records` 不再列出已删除房间。
- [x] Bot 重启后，有控制面板记录的房间 View 能恢复，按钮仍可点击。

---

## 3. Shop / Private Room

真实 Discord 必测点：持久按钮、余额实际变化、频道权限、真实购买 / 续费用户体验。

- [x] `/create_checkin_embed` 创建签到面板，图片和按钮显示正常；重启后按钮仍可点击。
- [x] 普通用户每日签到一次，余额增加、连签显示更新；重复点击不重复加钱。
- [x] 补签一次，余额扣减、补签记录和 Discord 响应正确。
- [x] `/privateroom_setup` 配置测试 category / 价格 / 时长；`/privateroom_init` 创建或刷新商店面板。
- [x] 用户余额足够时购买私人房间成功，频道权限正确；余额不足时不创建房间、不扣余额。
- [x] 到期前续费成功，余额扣除、到期时间从原到期日延长。
- [x] 已过期但频道/DB 记录滞留时续费成功，余额扣除、到期时间从当前时间延长。
- [x] `/privateroom_ban` 实际限制指定用户进入私人房间；`/privateroom_fix` 对异常状态给出可读结果。

---

## 4. Tickets / Giveaway

真实 Discord 必测点：真实 thread、persistent buttons、DM 失败、抽奖消息恢复。

- [x] `/tickets_init` 初始化主面板和日志频道。
- [x] 新增一个测试 ticket type，普通用户点按钮创建 thread，创建者自动成为成员。
- [x] 管理员接单、添加协作者、关闭工单；thread 状态、日志频道和统计正确。
- [x] Bot 重启后，Tickets 主面板和已存在工单按钮可恢复。
- [x] 用户关闭 DM 时，Tickets 创建 / 关闭流程不因 DM 失败中断。
- [x] `/ga_create` 创建测试抽奖，普通用户参与 / 退出后消息人数显示正确。
- [x] `/ga_end` 手动开奖或 `/ga_cancel` 取消后，View 清理且不能继续参与。
- [x] Bot 重启后，未结束抽奖按钮可恢复；`/ga_sendtowinner` 遇到 DM 失败不阻断整体流程。

---

## 5. Role / Achievement / Signature

真实 Discord 必测点：role hierarchy、真实角色增删、真实语音时长、排行榜可见性。

- [x] 创建一个身份组领取面板，普通用户点击后实际获得 / 移除角色。
- [x] Bot 角色层级低于目标角色时，用户得到可读错误，不出现裸 traceback。
- [ ] 创建签名面板；有资格用户设置签名成功，重复设置受次数限制。
- [ ] `/signature_permission_toggle` 禁用后，用户不可设置或展示签名；`/signature_clear` 清空记录。
- [ ] 管理员执行一次 `/increase_achievement` 或 `/decrease_achievement`，确认 `/check_ach_ops` 有记录。
- [ ] 普通用户查看 `/achievements`、`/achievement_ranking`、`/rank`，真实排行榜数据和按钮切换可用。
- [ ] 用户进出语音频道后，语音时长最终写入成就。

---

## 6. Ban / Moderation

真实 Discord 必测点：真实封禁 / 解封、role 权限、通知频道、重启恢复任务。

- [ ] 配置 Ban 管理员和通知频道；`/ban_admin_list` 显示正确。
- [ ] `/ban_set_invite_link` 接受合法邀请链接，非法链接给出错误。
- [ ] `/tempban` 封禁测试账号，通知频道记录、DB active 记录存在。
- [ ] Bot 重启后 recover tempbans，不丢失未到期任务。
- [ ] 到期后自动 unban 并 deactivate 记录。
- [ ] `/ban_list_tempbans` 显示活跃临时封禁。
- [ ] `/mute` 路径按预期执行或提示权限不足；`/ban` 永久封禁只在测试账号上验证。

---

## 7. Check Status / Backup / Welcome / Games

真实 Discord 必测点：图表文件、日志文件、备份文件、欢迎图片、DM、游戏真实交互。

- [x] `/check_voice_status` 返回当前语音人数 / 房间统计。
- [x] `/print_voice_status` 能生成统计图文件。
- [x] `/check_log` 能读取 bot / keyword / room activity 日志。
- [x] 右键菜单 `Where Is` 能查到测试用户所在语音频道，并给出可点击跳转按钮。
- [x] `/backup_now` 生成手动备份；自动 / 手动备份目录不误删 `.gitkeep`。
- [x] `/testwelcome` 能发送欢迎图和 DM；新成员加入测试服时欢迎频道消息和 DM 行为符合配置。
- [x] DM 关闭时不影响欢迎频道消息。
- [x] `/dnd_roll` 掷骰结果在客户端显示正常。
- [x] `/spymode` 创建游戏 View，加入队伍、开始、查看结果流程可用，身份 DM 正确。

---

## 8. Legacy / Removed

- [ ] main 分支没有 `old_function/` / `old_updates.md` 的 tracked 文件。
- [ ] `LEGACY_ARCHIVE.md` 指向 `legacy-old-files-archive` 分支。
- [ ] 如需旧代码或脱敏旧模板，切到 `legacy-old-files-archive` 查看 `LEGACY_ARCHIVE_INDEX.md`。
- [ ] Discord command picker 不再显示 notebook / rating / old tickets 命令。
- [ ] 不测试 `event_logs` / `admins` 清表；Notebook 历史 DB 表默认保留。

---

## 9. 最终回归

- [ ] 全部手工异常项 `[!]` 已复测或记录为后续 bug。
- [ ] 再跑一次 `./.venv/Scripts/python.exe -m pytest -q`。
- [ ] 再跑一次 `./.venv/Scripts/python.exe -m ruff check bot tests tools`。
- [ ] 再跑一次 `./.venv/Scripts/python.exe -X utf8 tools/check_locales.py`。
- [ ] 备份测试库和日志。
- [ ] 在 `REFACTORING_PROGRESS.md` 追加测试服通过日期、测试人、遗留问题。
