# 工程工具

从仓库根目录使用 `python -X utf8 toolbox.py project list`，再用 `project describe <ID>` 或 `project run <ID> --dry-run -- <参数>` 查看入口。真实执行仍遵守底层工具的硬件和Flash边界。

| 类别 | 常用入口 |
|---|---|
| 构建、交付 | `bridge.build`、`bridge.verify`、`fpga.build`、`fpga.verify`、`firmware.build` |
| 依赖、离线检查 | `deps.check`、`etm.records-check`、`web.check`、`test.web`、`test.cli` |
| 仿真、探针回归 | `sim.cm3`、`sim.matrix`、`probe.regression` |
| Trace | `toolbox.py trace --help`、`etm.bench`、`etm.equivalence` |
| 板卡加载与身份 | `probe.load`、`probe.ocm-verify`；`probe.flash`会写QSPI |

保留构建/运行依赖、测试、可复用诊断和当前验收工具；Python Golden参考不属于冗余代码。2026-11-05退出活跃树的8个一次性旧测速、改频和打包脚本，以及历史报告内的驱动副本，见[归档清单](../docs/validation/cleanup-20261105/archived-files.json)。其原始字节保存在tag `archive/main-before-cleanup-20261105`。

后续验收优先复用现有入口；一次性脚本随报告归档，不继续堆入活跃工具目录。详细边界见[CLI工作台](../docs/toolbox-cli-ai.md)。
