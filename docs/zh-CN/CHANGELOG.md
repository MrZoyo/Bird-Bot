# 更新日志

<p align="center">
  <a href="../../README.zh-CN.md"><img src="https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87%E9%A6%96%E9%A1%B5-2EA44F?style=for-the-badge" alt="返回中文 README"></a>
  <a href="../en/CHANGELOG.md"><img src="https://img.shields.io/badge/FULL_HISTORY-ENGLISH-5865F2?style=for-the-badge&amp;logo=googletranslate&amp;logoColor=white" alt="查看英文完整更新历史"></a>
</p>

本文只提供当前版本的中文摘要。所有历史版本及其原始发布说明请查看[英文完整更新日志](../en/CHANGELOG.md)。当前运行行为以[中文功能参考](FEATURES.md)为准。

## 2.0.5 — 2026-09-12

- 邀请排行榜排除机器人账号，已有历史邀请计数的机器人也不再上榜；真人按原有邀请总数和用户 ID 顺序补足名次。
- 未缓存的账号通过 Discord 查询，已退服的真人仍可参与排名；查询失败的账号仅在本次刷新跳过，下次重试。
- 保留数据库中的邀请归因、计数和奖励记录，无需数据库迁移。
- 新增历史机器人过滤、真人补位、并发计数变化、池化计数、账号查询失败、空榜单和面板刷新的回归测试。

## 历史版本

英文长版记录了 `2.0.4` 及更早版本。旧条目中的 `Tickets_New_Cog`、`Rating_Cog` 和 JSON 配置文件名只描述当时的版本，不代表当前运行结构。
