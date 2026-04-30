# 测试服全量验证 Checklist

> 目标：先用自动化 smoke test 排除“不需要真实 Discord”的回归，再按模块在测试服验证命令、按钮、权限、后台任务和日志。
> 当前清单按 2026-04-30 main 分支现状编写；NotebookCog、RatingCog 和旧 channel-based TicketsCog 已移除，不再作为现役功能测试项。

标记规则：
- `[ ]` 未测
- `[x]` 通过
- `[!]` 异常；在该项下面补一行“现象 / 日志 / 复现步骤”
- 手工测试只用测试服和测试库；不要直接指向生产 `data/bot.db`

---

## 0. 自动化 Gate

这些测试都使用临时 sqlite DB 或静态导入，不联网、不触碰真实 `data/bot.db`。

自动覆盖：
- `tests/test_runtime_metadata.py`：YAML 模板可解析、`main.features` 与 `COG_SPECS` 对齐、所有注册 cog 可 import、runtime 不再注册 notebook / tickets_new。
- `tests/test_check_status_db.py`：在线人数采样写入和按日期查询。
- `tests/test_tickets_db.py`：ticket type CRUD、配置读写、工单创建 / 成员 / 接单 / 关闭 / 统计 / 历史。
- `tests/test_voice_channel_db.py`：创建频道配置、临时房间状态、控制面板恢复字段。
- `tests/test_privateroom_db.py`：私人房间配置、店铺消息、房间生命周期、续费提醒标记。
- `tests/test_ban_db.py`：临时封禁、活跃查询、统计、手动解除、旧记录清理。
- `tests/test_role_db.py`：身份组面板记录、签名次数 / 禁用 / 清空。
- `tests/test_giveaway_db.py`：抽奖记录、参与者、获奖者、持久 View 清理。
- `tests/test_shop_db.py`：余额、流水、签到、补签、签到面板统计。
- `tests/test_achievement_db.py`：成就计数、排行榜、语音 session、手动操作、签到联查。
- `tests/test_log_helpers.py`：日志 helper；用户 `昵称 / 用户名 (id)`，频道/身份组 `name (id)`，id 使用英文括号。
- `tests/test_invitation_full_message.py`：关键词检测日志 `昵称 / 用户名 (id)` 格式，组队消息 / 房间面板满员样式共享。
- `tests/test_shop_ui_metadata.py`：Shop 补签 / 余额修改 modal 与交易历史翻页按钮文案来自 locale，不再要求 `shop.yaml` 提供 UI 文案键。
- `tests/test_ui_locale_metadata.py`：PrivateRoom 购买 / 续费 modal、Welcome DM 成员数按钮、Achievement rank 按钮文案来自 locale。
- `tests/test_migrate_config_to_yaml_temp.py`：临时升级 smoke，验证旧 JSON config 可转换为新 YAML / locale / DB seed，并跳过旧 rating / 旧 ticket。
- `tests/test_task_helpers.py`：离线 cog-load smoke 时后台 loop 不再因未登录客户端抛未取回异常。

必须先过：
- [x] `./.venv/Scripts/python.exe -m pytest -q`
  - 预期：全部通过；当前基线是 `31 passed`，允许出现 discord.py 的 `audioop` / `TextInput.label` deprecation warning。
- [x] `./.venv/Scripts/python.exe -m ruff check bot tests tools`
  - 预期：0 error；当前只启用 `E722`，用于防裸 `except:` 回归。
- [x] `./.venv/Scripts/python.exe -m compileall bot tests tools`
  - 预期：无语法错误。
- [x] `./.venv/Scripts/python.exe -X utf8 tools/check_locales.py`
  - 预期：locale key 全 resolve。
- [x] `./.venv/Scripts/python.exe -m pip check`
  - 预期：依赖一致。
- [x] `uv lock --check`
  - 预期：lock 与 `pyproject.toml` 对齐。

---

## 1. 启动 / 全局状态

自动覆盖：`test_runtime_metadata.py` 已验证 runtime 注册清单、配置模板和 import smoke。

- [x] 使用测试服 `main.yaml` 启动 `python run.py`
  - 预期：所有启用且配置完整的 cog 被加载；缺配置或 disabled feature 只打印 skip，不抛异常。
- [ ] 启动日志无 `ImportError` / `ModuleNotFoundError` / `no such table` / `OperationalError`
- [x] Slash command 同步完成；必要时手动跑 `!synccommands`
- [x] Discord command picker 不显示 `/notebook_*`
- [x] `bot/cogs/` 顶层只作为包入口；不依赖旧平面 `*_cog.py`
- [ ] `data/bot.db`、日志、备份路径都解析到仓库根目录下的预期位置
- [ ] 抽查日志中用户显示为 `昵称 / 用户名 (id)`，频道 / 角色显示为 `name (id)`，raw id 为 `unknown (id)`；id 使用英文括号。

---

## 2. Voice Channel

自动覆盖：`test_voice_channel_db.py` 覆盖 `channel_configs` 与 `temp_channels` 状态读写。

- [ ] `/vc_add` 添加一个创建入口频道
- [ ] `/vc_list` 能看到刚添加的入口频道和前缀 / 类型
- [ ] 用户进入入口频道后自动创建临时语音房，并被移动进去
- [ ] 房间控制面板出现；Unlock / Lock / Soundboard 按钮可用
- [ ] 点击 Lock 后频道权限变私有；点击 Unlock 后恢复公开
- [ ] Soundboard 状态能切换，按钮 / embed 状态一致
- [ ] 点击 Full 后如果存在 teamup 展示消息，能标记为满或触发预期提示
- [ ] 房间无人后自动删除；`/check_temp_channel_records` 不再列出已删除房间
- [ ] Bot 重启后，有控制面板记录的房间 View 能恢复，按钮仍可点击
- [ ] `/vc_remove` 能用频道选择或 channel_id 删除入口配置

---

## 3. Invitation / Teamup Display

自动覆盖：配置写回、locale、runtime import 已由全局 gate 覆盖；Discord 交互需手工。

- [ ] 用户不在语音频道时跑 `/invt`，得到“请先进入语音频道”的提示
- [ ] 用户在语音频道时跑 `/invt`，生成可点击邀请消息
- [ ] 在普通频道发送配置的组队关键词，bot 自动回复语音频道邀请
- [ ] `/invt_addignorelist` 添加忽略频道 / 用户后，关键词不再触发
- [ ] `/invt_checkignorelist` 显示忽略列表
- [ ] `/invt_removeignorelist` 移除后，关键词恢复触发
- [ ] `/teamup_init` 初始化展示频道
- [ ] `/teamup_type_add` / `/teamup_type_list` / `/teamup_type_delete` 管理展示类型
- [ ] 临时房间删除或标满后，对应 teamup 展示能被清理或更新

---

## 4. Shop / Checkin

自动覆盖：`test_shop_db.py` 覆盖余额、流水、签到、补签、签到面板 DB 状态。

- [ ] `/create_checkin_embed` 创建签到面板，图片和按钮显示正常
- [ ] 普通用户点击每日签到，余额增加、连签显示更新
- [ ] 同一用户重复点击每日签到，得到已签到提示，不重复加钱
- [ ] 补签按钮在有可补日期 / 额度时成功；额度用完后失败提示清楚
  - 自动补充：补签 modal 的 title / label / placeholder 已由 `tests/test_shop_ui_metadata.py` 覆盖，手工只需验证真实余额扣减、补签记录和 Discord 交互响应。
- [ ] `/balance_change` 给测试用户加分和扣分，余额正确
- [ ] `/balance_history` 显示流水，能区分签到和管理员调整
- [ ] `/checkin_history` 显示签到日历 / 历史
- [ ] Bot 重启后，签到面板 persistent view 仍可点击

---

## 5. Private Room

自动覆盖：`test_privateroom_db.py` 覆盖配置、店铺消息、房间生命周期和续费提醒 DB 状态。

- [ ] `/privateroom_init` 创建或刷新私人房间商店面板
- [ ] `/privateroom_setup` 设置 category / 价格 / 时长等关键配置
- [ ] 用户余额足够时购买私人房间成功，频道权限正确
- [ ] 用户余额不足时购买失败，不创建房间、不扣余额
- [ ] 到期前续费成功，余额扣除、到期时间延长
  - 自动补充：购买 / 续费 modal 文案已由 `tests/test_ui_locale_metadata.py` 覆盖，手工只需验证扣款、频道权限和到期时间。
- [ ] 已删除但未过期的房间能通过恢复路径重新绑定新频道
- [ ] `/privateroom_list` 能列出活跃房间
- [ ] `/privateroom_ban` 能限制指定用户进入私人房间
- [ ] `/privateroom_fix` 对异常状态给出可读结果
- [ ] `/privateroom_reset` 只在测试库上执行；执行后店铺消息 / 房间状态清空

---

## 6. Achievements / Ranking

自动覆盖：`test_achievement_db.py` 覆盖计数、月度计数、排行榜、语音 session、手动操作和 shop 签到联查。

- [ ] 普通用户查看 `/achievements`，各项计数显示合理
- [ ] 管理员用 `/increase_achievement` 增加 message / reaction / time / giveaway
- [ ] 管理员用 `/decrease_achievement` 减少对应计数
- [ ] `/achievement_ranking` 显示全服排行榜
- [ ] `/rank` 显示个人名次和总参与人数
  - 自动补充：`/rank` 交互按钮文案已由 `tests/test_ui_locale_metadata.py` 覆盖，手工只需验证真实排行榜数据和按钮切页。
- [ ] `/check_ach_ops` 显示手动操作日志
- [ ] 用户进出语音频道后，语音时长最终写入成就
- [ ] 签到后，`checkin_sum` / `checkin_combo` 排行榜读到 shop 数据

---

## 7. Role / Signature

自动覆盖：`test_role_db.py` 覆盖面板消息记录和签名状态；`test_log_helpers.py` 覆盖日志格式。

- [ ] `/create_role_pickup` 创建普通身份组领取面板
- [ ] `/create_starsign_pickup`、`/create_mbti_pickup`、`/create_gender_pickup` 创建对应面板
- [ ] 普通用户点击领取 / 移除，角色变化正确
- [ ] Bot 角色层级低于目标角色时，用户得到可读错误，不出现裸 traceback
- [ ] `/create_signature_pickup` 创建签名面板
- [ ] 有资格用户设置签名成功，重复设置受次数限制
- [ ] `/signature_check` 能查看无签名 / 有签名 / 已禁用三种状态
- [ ] `/signature_permission_toggle` 禁用后，用户签名不可展示或不可设置
- [ ] `/signature_clear` 清空签名和修改记录
- [ ] `/signature_set_requirement` 写回 YAML 后重启仍生效

---

## 8. Tickets

自动覆盖：`test_tickets_db.py` 覆盖 ticket types、config、工单生命周期、成员、统计和历史。

- [ ] `/tickets_init` 初始化主面板和日志频道
- [ ] `/tickets_add_type` 新增测试类型；主面板出现按钮
- [ ] `/tickets_edit_type` 修改描述 / guide / button color / 管理员列表，重启后仍保留
- [ ] `/tickets_delete_type` 删除测试类型；主面板刷新后按钮消失
- [ ] 普通用户点类型按钮创建 thread 工单，创建者自动成为成员
- [ ] 管理员 `/tickets_add_user` 添加协作者；重复添加有明确提示
- [ ] 管理员点击 Accept 或跑 `/tickets_accept`，工单状态变 accepted
- [ ] `/tickets_close` 关闭工单，记录 close reason
- [ ] 关闭后不能继续添加成员或重复接单
- [ ] `/tickets_stats` 统计 total / active / closed / by type 正确
- [ ] `/tickets_refresh_buttons`、`/tickets_refresh_main` 能恢复 persistent buttons
- [ ] 用户关闭 DM 时，创建 / 关闭流程不因 DM 失败中断

---

## 9. Giveaway

自动覆盖：`test_giveaway_db.py` 覆盖抽奖记录、参与者、获奖者和持久 View 清理。

- [ ] `/ga_create` 打开表单并创建测试抽奖
- [ ] 普通用户点击参与，参与者列表增加
- [ ] 同一用户重复参与有明确提示
- [ ] 用户退出参与后，参与者列表减少
- [ ] `/check_giveaway` 导出或显示当前抽奖状态
- [ ] `/ga_description` 修改描述后消息刷新，重启后仍保留
- [ ] `/ga_time_extend` 延长时长后到期时间正确
- [ ] `/ga_participant` 能查看参与者
- [ ] `/ga_end` 手动开奖，winner 写入，View 清理
- [ ] `/ga_cancel` 取消抽奖后不可继续参与
- [ ] `/ga_sendtowinner` 能给中奖者发送消息；DM 失败不阻断整体流程
- [ ] Bot 重启后，未结束抽奖按钮可恢复

---

## 10. Ban / Moderation

自动覆盖：`test_ban_db.py` 覆盖临时封禁生命周期、统计和旧记录清理。

- [ ] `/ban_admin_add_role` / `/ban_admin_add_user` 添加管理员
- [ ] `/ban_admin_list` 显示 role / user 管理员
- [ ] `/ban_set_notification_channel` 设置通知频道
- [ ] `/ban_set_invite_link` 设置合法邀请链接；非法链接给出错误
- [ ] `/tempban` 封禁测试用户，通知频道记录、DB active 记录存在
- [ ] Bot 重启后 recover tempbans，不丢失未到期任务
- [ ] 到期后自动 unban 并 deactivate 记录
- [ ] `/ban_list_tempbans` 显示活跃临时封禁
- [ ] `/mute` 路径按预期执行或提示权限不足
- [ ] `/ban` 永久封禁路径只在测试账号上验证
- [ ] 删除通知频道 / invite link 后，相关命令回到未配置提示

---

## 11. Check Status / Logs / Backup

自动覆盖：`test_check_status_db.py` 覆盖 status DB；lint 和 locale gate 覆盖日志 / 文案基础一致性。

- [ ] `/check_voice_status` 返回当前语音人数 / 房间统计
- [ ] `/print_voice_status` 能生成统计图或文件
- [ ] `/check_log` 能读取 bot / keyword / room activity 日志
- [ ] 右键菜单 `Where Is` 能查到测试用户所在语音频道
- [ ] 全新测试 DB 启动时不会出现 `no such table: status`
- [ ] `/backup_now` 生成手动备份
- [ ] 自动 / 手动备份目录不误删 `.gitkeep`
- [ ] 日志轮转路径使用 `main.yaml` 中的 repo-root 相对路径

---

## 12. Welcome / Games

自动覆盖：runtime import 和 locale gate 覆盖基础加载；真实 Discord 事件需手工。

- [ ] `/testwelcome` 能发送欢迎图和按钮
- [ ] 新成员加入测试服时，欢迎频道消息和 DM 行为符合配置
  - 自动补充：Welcome DM 成员数按钮已由 `tests/test_ui_locale_metadata.py` 覆盖，手工只需验证 DM 能发出、图片/规则频道链接正确。
- [ ] DM 失败时不影响欢迎频道消息
- [ ] `/dnd_roll` 掷骰结果格式正常
- [ ] `/spymode` 创建游戏 View，加入 / 开始 / 退出流程可用

---

## 13. Legacy / Removed

- [ ] main 分支没有 `old_function/` / `old_updates.md` 的 tracked 文件
- [ ] `LEGACY_ARCHIVE.md` 指向 `legacy-old-files-archive` 分支
- [ ] 如需旧代码或脱敏旧模板，切到 `legacy-old-files-archive` 查看 `LEGACY_ARCHIVE_INDEX.md`
- [ ] Discord command picker 不再显示 notebook 命令
- [ ] 不测试 `event_logs` / `admins` 清表；Notebook 历史 DB 表默认保留

---

## 14. 最终回归

- [ ] 全部手工异常项 `[!]` 已复测或记录为后续 bug
- [ ] 再跑一次 `./.venv/Scripts/python.exe -m pytest -q`
- [ ] 再跑一次 `./.venv/Scripts/python.exe -m ruff check bot tests`
- [ ] 再跑一次 `./.venv/Scripts/python.exe -X utf8 tools/check_locales.py`
- [ ] 备份测试库和日志
- [ ] 在 `REFACTORING_PROGRESS.md` 追加测试服通过日期、测试人、遗留问题
