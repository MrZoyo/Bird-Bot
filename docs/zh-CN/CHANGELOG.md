# 更新日志

<p align="center">
  <a href="../../README.zh-CN.md"><img src="https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87%E9%A6%96%E9%A1%B5-2EA44F?style=for-the-badge" alt="返回中文 README"></a>
  <a href="../en/CHANGELOG.md"><img src="https://img.shields.io/badge/FULL_HISTORY-ENGLISH-5865F2?style=for-the-badge&amp;logo=googletranslate&amp;logoColor=white" alt="查看英文完整更新历史"></a>
</p>

本文只提供当前版本的中文摘要。所有历史版本及其原始发布说明请查看[英文完整更新日志](../en/CHANGELOG.md)。当前运行行为以[中文功能参考](FEATURES.md)为准。

## 2.0.5 — 2026-09-12

- 邀请排行榜排除机器人账号，已有历史邀请计数的机器人也不再上榜；真人按原有邀请总数和用户 ID 顺序补足名次。
- 未缓存的账号通过 Discord 查询，已退服的真人仍可参与排名；查询失败的账号仅在本次刷新跳过，下次重试。
- 同一面板上方显示总榜，下方显示当月前10名，以分割线区分；更新时间旁显示上月已结算冠军。
- 每月1日 `Europe/Berlin` 当地00:00结算上月，自动处理夏令时并在离线重启后补结算。冠军额外200积分、亚军150积分、季军100积分，第4–10名各60积分。
- 首次启用时，现有累计邀请数一次性计入启用月份；以后各月只统计新的有效归因。保留原有总榜计数及Shop余额。
- 新增月榜计数、结算、通知记录表，以及Shop唯一奖励流水键，防止重复到账。启动时自动执行增量迁移，并新增 `tzdata` 时区依赖。
- 月榜奖励私信显示结算时的真实名次和额外积分，按冠亚季军及第4–10名使用四档图片。私信失败或发送中断不会回滚积分。
- 补充月界、池化计数、首次导入、并发变化、账号查询失败、奖励恢复、图片选择和合并面板的回归测试。

## 历史版本

英文长版记录了 `2.0.4` 及更早版本。旧条目中的 `Tickets_New_Cog`、`Rating_Cog` 和 JSON 配置文件名只描述当时的版本，不代表当前运行结构。
