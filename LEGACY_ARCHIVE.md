# Legacy Archive

旧的已脱敏归档内容不再保留在 main 分支。

需要查看旧实现、拆包前快照、legacy JSON example 或旧更新记录时，切到：

```bash
git switch legacy-old-files-archive
```

归档分支内的 `LEGACY_ARCHIVE_INDEX.md` 记录了完整统计和说明。当前归档范围包括原 main 上已追踪的 `old_function/` 与 `old_updates.md`：共 32 个旧文件，16939 行。

`old_test/` 是本地 ignored 实验目录，不属于已脱敏归档分支内容；可复用测试应放入 main 分支的 `tests/`。
