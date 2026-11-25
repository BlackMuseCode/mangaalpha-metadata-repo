# MangaAlpha Metadata Repository

面向 [MangaAlpha](https://github.com/xJogger/MangaAlpha)（`v3.2+`）的声明式元数据市场仓库（`mangaalpha-repo-v1`）。

## 订阅地址

在 MangaAlpha 管理后台 **「元数据刮削 → 元数据仓库市场」** 中填入以下 JSON 订阅地址：

```text
https://raw.githubusercontent.com/BlackMuseCode/mangaalpha-metadata-repo/main/repo.json
```

## 收录数据源

| ID | 类型 | 说明 | 默认更新策略 |
| :--- | :--- | :--- | :--- |
| `bgm-zh-cn` | `bangumi_archive` | Bangumi 中文简介增强镜像（与官方同构） | 每周 |
| `bgm-official` | `bangumi_archive` | Bangumi 官方原版归档 | 每周 |
| `gallery-nightly` | `offline_sqlite`（`gallery_v1`） | 社区全量离线图库 SQLite 索引（`.db.zstd`，约 1 GB） | 手动（可选定时） |
| `tag-dict-zh-cn` | `tag_dictionary` | 社区中文标签翻译词典（`db.text.json.gz`，约 1.3 MB） | 每周 |
| `community-mappings` | `mapping_pack`（`mangaalpha_mapping_v1`） | 社区脱敏标题映射包（离线库未命中时兜底） | 每周 |

## 贡献社区脱敏映射包（PR 指南）

1. 在 MangaAlpha 后台使用 **「导出社区脱敏映射包」**（仅包含脱敏标题键、可选作者名与目标条目的纯数字/规范 ID，不含任何文件路径、账号或私有信息）。
2. 将新增条目追加至 `mappings/community-bangumi.ndjson`（每行一条标准 JSON，遵循 `mangaalpha_mapping_v1`）。
3. 运行校验与索引更新脚本：
   ```bash
   python3 scripts/validate_mappings.py --rebuild-index
   python3 scripts/validate_mappings.py
   ```
4. 提交 Pull Request；CI 会自动校验 JSON 结构、重复键与隐私红线。
