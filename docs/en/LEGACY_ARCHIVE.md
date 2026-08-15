# Legacy archive

<p align="center">
  <a href="../../README.md"><img src="https://img.shields.io/badge/README-HOME-2EA44F?style=for-the-badge" alt="Back to the English README"></a>
  <a href="../zh-CN/LEGACY_ARCHIVE.md"><img src="https://img.shields.io/badge/READ_IN-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-5865F2?style=for-the-badge&amp;logo=googletranslate&amp;logoColor=white" alt="Read in Simplified Chinese"></a>
</p>

Sanitized legacy content is no longer stored on the `main` branch.

Browse the [`legacy-old-files-archive`](https://github.com/MrZoyo/Bird-Bot/tree/legacy-old-files-archive) branch or open its [`LEGACY_ARCHIVE_INDEX.md`](https://github.com/MrZoyo/Bird-Bot/blob/legacy-old-files-archive/LEGACY_ARCHIVE_INDEX.md) directly. To inspect it locally:

```bash
git fetch origin
git switch legacy-old-files-archive
```

The archive is a single sanitized root commit with no inherited Git history. It excludes real configuration files, logs, runtime data, and local experiments; Discord invite values in archived material use placeholders.

Use the archive to inspect old implementations, pre-package snapshots, legacy JSON examples, and old update notes. The index covers 32 legacy implementation, configuration, and update-note files totaling 16,939 lines; supporting archive documentation is excluded from that count.

`old_test/` is an ignored local experiment directory and is not part of the sanitized archive branch. Reusable tests belong in `tests/` on `main`.
