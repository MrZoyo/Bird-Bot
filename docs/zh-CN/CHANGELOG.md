# 更新日志

<p align="center">
  <a href="../../README.zh-CN.md"><img src="https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87%E9%A6%96%E9%A1%B5-2EA44F?style=for-the-badge" alt="返回中文 README"></a>
  <a href="../en/CHANGELOG.md"><img src="https://img.shields.io/badge/FULL_HISTORY-ENGLISH-5865F2?style=for-the-badge&amp;logo=googletranslate&amp;logoColor=white" alt="查看英文完整更新历史"></a>
</p>

本文只提供当前版本的中文摘要。所有历史版本及其原始发布说明请查看[英文完整更新日志](../en/CHANGELOG.md)。当前运行行为以[中文功能参考](FEATURES.md)为准。

## 2.0.3 — 2026-08-15

- 新增可选的 `@everyone` 垃圾消息防护：非管理员发送真实 `@everyone` mention 时，Bot 自动执行一天临时封禁。
- 服务器所有者、Discord 管理员、Ban 配置中的管理员用户和身份组，以及可在管理员频道发言的成员不受此规则影响。
- 默认删除过去一小时的消息记录，同时兼容旧版 `delete_message_days` 配置。
- 复用临时封禁的私信、持久化、通知、定时和自动解封流程；数据库写入失败时会立即撤销 Discord 封禁。
- 临时封禁私信新增账号安全提醒，并补充权限豁免、误报、权限失败、持久化回滚和重复临时封禁的回归测试。

## 历史版本

英文长版记录了 `2.0.2` 及更早版本。旧条目中的 `Tickets_New_Cog`、`Rating_Cog` 和 JSON 配置文件名只描述当时的版本，不代表当前运行结构。
