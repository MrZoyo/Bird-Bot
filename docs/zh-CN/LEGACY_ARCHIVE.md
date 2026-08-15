# 旧实现归档

<p align="center">
  <a href="../../README.zh-CN.md"><img src="https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87%E9%A6%96%E9%A1%B5-2EA44F?style=for-the-badge" alt="返回中文 README"></a>
  <a href="../en/LEGACY_ARCHIVE.md"><img src="https://img.shields.io/badge/READ_IN-ENGLISH-5865F2?style=for-the-badge&amp;logo=googletranslate&amp;logoColor=white" alt="Read in English"></a>
</p>

旧的已脱敏归档内容不再保留在 main 分支。

可以直接在 GitHub 浏览 [`legacy-old-files-archive`](https://github.com/MrZoyo/Bird-Bot/tree/legacy-old-files-archive) 分支，或打开其中的 [`LEGACY_ARCHIVE_INDEX.md`](https://github.com/MrZoyo/Bird-Bot/blob/legacy-old-files-archive/LEGACY_ARCHIVE_INDEX.md)。本地查看方式如下：

```bash
git fetch origin
git switch legacy-old-files-archive
```

该归档是一个不继承旧 Git 历史的单提交脱敏快照。真实配置、日志、运行数据和本地实验文件均不进入归档；归档材料中的 Discord 邀请值统一使用占位符。

需要查看旧实现、拆包前快照、legacy JSON 示例或旧更新记录时使用该分支。索引统计了 32 个旧实现、配置和更新记录文件，共 16,939 行；归档说明文档不计入该数字。

`old_test/` 是本地 ignored 实验目录，不属于已脱敏归档分支内容；可复用测试应放入 main 分支的 `tests/`。
