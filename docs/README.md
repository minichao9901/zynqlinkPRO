# 融合工程文档

| 用途 | 入口 |
|---|---|
| 当前固件、SHA-256 与临时加载 | [RAW4 融合 bit/ELF](../prebuilt/selectio-usb-split-raw4-20261123/README.md) |
| J7 接线、USB 端点与主机命令 | [SelectIO CLI](selectio/README.md) · [原生 USB 协议](selectio-native.md) |
| 构建工具、依赖与测试入口 | [CLI 工作台](toolbox-cli-ai.md) · [依赖](dependencies.md) · [仓库规则](../AGENTS.md) |
| Trace 采集、校验、离线查询和导出 | [Trace CLI](Trace-CLI使用说明.md) · [ETM 操作](Zynq-ETM-Trace操作说明.md) · [HTML 导出](flame-html-export.md) |
| 验收用例、实板结果和问题状态 | [融合性能用例](selectio/fusion-performance-cases.md) · [融合证据](validation/README.md) · [问题索引](项目问题跟踪列表.md) |
| 固定 EXE、发布、QSPI 和回退 | [板卡精简验收与交付](板卡精简验收与交付.md) · [发布流程](github-release.md) · [产物索引](../prebuilt/README.md) |
| 可运行的 ETM 离线示例 | [记录清单](retained-records.json) |

融合前的独立验收报告保存在历史提交中，恢复入口见 [验收索引](validation/README.md#融合前档案)。当前配对以板上身份和配对哈希核对为准。
