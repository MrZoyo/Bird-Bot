# 更新日志

<p align="center">
  <a href="../../README.zh-CN.md"><img src="https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87%E9%A6%96%E9%A1%B5-2EA44F?style=for-the-badge" alt="返回中文 README"></a>
  <a href="../en/CHANGELOG.md"><img src="https://img.shields.io/badge/FULL_HISTORY-ENGLISH-5865F2?style=for-the-badge&amp;logo=googletranslate&amp;logoColor=white" alt="查看英文完整更新历史"></a>
</p>

本文只提供当前版本的中文摘要。所有历史版本及其原始发布说明请查看[英文完整更新日志](../en/CHANGELOG.md)。当前运行行为以[中文功能参考](FEATURES.md)为准。

## 2.0.4 — 2026-08-16

- 组队自动检测继续以“标记 + 人数”为必需条件，只在命中后检查标记前是否写了单人数量。`1q4`、`一等全世界` 会使用柔和提示，`稍微一等`、`1等`、`一q` 不会误触发。
- 普通提示改为“本频道不允许私拉，先创个房间吧~”，单人状态改为“不如你先来发车~”。
- 保留 6 字符邀请的静默忽略规则，并将不区分大小写的 `hks` 加入 `flex`、`rank`、`aram` 例外。
- 当前 `/achievements` 列表迁移到 Components v2，以原生分割线区分成就分类并显示右上角大头像。头像依次降级为用户自定义头像、Bot 自定义头像、用户默认头像。
- 新增组队检测、6 字符处理、成就面板结构和头像降级顺序的回归测试。

## 历史版本

英文长版记录了 `2.0.3` 及更早版本。旧条目中的 `Tickets_New_Cog`、`Rating_Cog` 和 JSON 配置文件名只描述当时的版本，不代表当前运行结构。
