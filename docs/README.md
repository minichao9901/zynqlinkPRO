# 工程文档

日常入口是固定程序 `dist/zynq-etm-bridge/zynq-etm-bridge.exe`。开发前先读[仓库规则](../AGENTS.md)与[问题索引](项目问题跟踪列表.md)。

| 用途 | 文档 |
|---|---|
| 当前bit/ELF、WebUSB、EXE与在线发布 | [正式交付](validation/release-20261106/README.md)、[GitHub发布](github-release.md) |
| J7 QSPI固化、整片验证和实体冷启动 | [QSPI交付验收](validation/qspi-release-20261106/README.md)、[启动链构建](../firmware/boot/README.md) |
| CLI发现、Web工作台、构建交付 | [CLI工作台](toolbox-cli-ai.md) |
| 采集、飞行记录、离线查询与导出 | [Trace CLI](Trace-CLI使用说明.md) |
| 连接、接线和操作 | [ETM操作说明](Zynq-ETM-Trace操作说明.md) |
| 工具链、SDK、仿真模型 | [依赖与构建](dependencies.md) |
| 精选业务trace与逐文件SHA | [记录清单](retained-records.json) |
| 当前能力、限制和主要成果 | [项目能力评估](validation/project-assessment-20261104/README.md) |
| 历史验收、失败证据与恢复方法 | [验收索引](validation/README.md) |
| 本轮精简范围与验证 | [工程整理](validation/cleanup-20261105/README.md) |

当前功能验收优先阅读[统一控制与飞行记录](validation/session-flight-recorder-20261105/README.md)、[报告与固件查看器](validation/report-firmware-inspector-20261105/README.md)、[探针安全](validation/probe-safety-111-112-115-20261104/README.md)、[主线实板](validation/main-web-hardware-20261103/README.md)、[H743](validation/h743-comprehensive-20261101/README.md)与[HPM USB修复](validation/hpm6800-def-cdc-fix-20261102/README.md)。

历史报告按当时日期和配对解读，当前状态以问题索引及较新证据为准；Git工作区路径不能证明板上版本。
