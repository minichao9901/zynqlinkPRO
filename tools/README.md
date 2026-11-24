# 工程工具

从仓库根目录使用 `python -X utf8 toolbox.py project list`，再用 `project describe <ID>` 或 `project run <ID> --dry-run -- <参数>` 查看入口。真实执行仍遵守底层工具的硬件和Flash边界。

| 类别 | 常用入口 |
|---|---|
| 构建、交付 | `bridge.build`、`bridge.verify`、`fpga.build`、`fpga.verify`、`firmware.build` |
| GitHub页面与下载、WebUSB描述符 | `web.publish`、`usb.landing-check`；发布步骤见[说明](../docs/github-release.md) |
| 依赖、离线检查 | `deps.check`、`etm.records-check`、`web.check`、`test.web`、`test.cli` |
| 仿真、探针回归 | `sim.cm3`、`sim.matrix`、`probe.regression` |
| Trace | `toolbox.py trace --help`、`etm.bench`、`etm.equivalence` |
| 板卡加载与身份 | `probe.load`、`probe.ocm-verify`；`probe.flash`会写QSPI |
| QSPI启动包 | `boot.bsp`、`boot.build`、`boot.package`；[构建与固化](../firmware/boot/README.md) |

当前融合版的验收入口和配对见 [SelectIO CLI](../docs/selectio/README.md)。融合前的专用脚本及报告从 [历史提交](../docs/validation/README.md#融合前档案) 取回。

后续验收优先复用现有入口；一次性脚本随报告归档，不继续堆入活跃工具目录。详细边界见[CLI工作台](../docs/toolbox-cli-ai.md)。
