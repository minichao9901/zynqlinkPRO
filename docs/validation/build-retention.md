# efficiency 本地构建输出盘点

范围为 `E:\zynqlinkPRO-efficiency\build`。2026-11-24 的只读快照为 788 个顶层条目、55,901 个文件，逻辑大小约 40.98 GiB。逐目录数据保存在本机 `build/efficiency-retention-20261124.json`。同一次快照只作为盘点，正在写入的数量与大小可能继续变化。

## 复查

```powershell
python -X utf8 toolbox.py project run build.inventory -- --out build/retention-new.json
```

输出包括文件数、逻辑字节数、最后修改时间和跳过数量。盘点限制在本工作树。目录联接、符号链接和不可读条目计入跳过。

## 优先复核的目录

| 顶层输出目录 | GiB | 处理 |
|---|---:|---|
| `spi-cdc-rx-guard-long-hclk` | 5.58 | 含长窗和 guard 结果。先确认每轮的完整报告、失败数据和恢复回执，再核对可重建部分。 |
| `spi-cdc-phase-drift-board-full` | 5.15 | SPI 漂移和全套回归输出。与已提交摘要对账之前整目录保留。 |
| `spi-cdc-rx-guard-board-full` | 5.15 | CDC OUT 防护后的实板回归。保留原始窗口及恢复证据。 |
| `h743-cdc-golden-requal-20261123` | 3.18 | 现行报告直接引用的原始 HSS 窗口和工作产物。保留原路径及哈希。 |
| `spi-cdc-board-full` | 2.97 | 先校对已归档报告和本地恢复资料，再分离编译缓存。 |
| `target-acceptance-e0ae985c` | 1.55 | 三板 ELF/BIN/HEX 与板卡 `images/` 可逐个对拍。HPM 子目录中的 `sdk-build/` 为可重建候选，先保留每个映像的构建日志、清单及已交付映像。 |
| `target-acceptance-hpm-dev2` | 1.41 | 中间开发构建。先核对调试记录引用以及可重建范围，单独决定是否留档。 |
| `target-migration-20261124/local` | — | 原目录迁移时保存的本地文件与 SHA-256 清单，保留。 |

原始板测数据及恢复备份以实际记录为准。进行中的 SPI 工作及对应输出由当前任务继续接管。已知追溯路径见 [SPI 证据](spi-cdc-20261123/README.md)、[H743 RAW4 长窗](h743-cdc-golden-requal-20261123/README.md) 和 [板卡镜像](../../firmware/target/README.md)。

## 新运行的约定

新验收使用独立输出目录，建议置于 `build/runs/<case-id>/<run-id>/`。按脚本要求把报告文件或记录目录传给 `--out`。在已有的 `summary.json` 或 manifest 中记录 Case ID、实际探针配对、目标 ELF、状态和恢复证据。只把后续复现需要的证据纳入现有 `docs/validation/` 归档。

清理前逐项核对当前任务、路径引用和归档完整性。可重建候选只列到具体子目录。清理时以选定的绝对路径核对作用范围。
