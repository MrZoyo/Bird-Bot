# Bird-Bot 旧文件归档

[English](./README.md) | [简体中文](./README.zh-CN.md)

本分支保存从 `main` 移出的已脱敏历史参考材料，包括已退役实现、重构前快照、旧 JSON 示例和旧更新记录。

文件清单和恢复示例见 [`LEGACY_ARCHIVE_INDEX.md`](./LEGACY_ARCHIVE_INDEX.md)。

## 安全边界

- 本分支只有一个根提交，不继承任何旧 Git 历史。
- 真实配置、日志、本地实验文件和运行数据均不进入归档。
- 归档材料中的 Discord 邀请链接统一使用占位符。
- `old_function/` 仅供历史参考，不属于受支持的运行时代码。

本地查看归档：

```bash
git fetch origin
git switch legacy-old-files-archive
```
