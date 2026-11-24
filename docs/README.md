# 融合工程文档

## 从任务找入口

先核对当前 Git worktree 和分支。三板功能、性能和极限验收使用 `fusionAcceptance.cases`，固定使用 RAW4 ABI 2。用 `project run fusion.accept -- list` 查必验矩阵，用 `describe <用例ID>` 查目标镜像、档位、脚本与判据。 [融合验收手册](selectio/fusion-acceptance.md) · [验收清单](../acceptance-cases.json)

下表检索归档记录。用 `project case <用例ID>` 查询历史配对和实际取证范围。目标镜像按各板索引选择。[板卡镜像索引](../firmware/target/README.md) · [F103ZE 回归范围](validation/f103ze-cases-20261124/README.md#本报告的验证范围)

| 任务 | 从这里开始 | 配对与证据 |
|---|---|---|
| SRAM、RTT、J-Scope | F103ZE CDC48 功能回归用 `f103ze-sram-rtt-scope`，HCLK128 的 50 MHz SWD 性能用 `f103ze-hclk128-swd50`。另有 `h743-sram-rtt-scope`、`hpm6800evk-rtt`、`hpm6800evk-scope`。 | [融合板测索引](validation/README.md)。F103ZE 功能与性能、H743 RAW4 ABI 2、HPM QSPI 历史对照各有独立条件。 |
| 调试、烧录和复位 | 三板的 `*-debug-flash` | [统一入口与验收判据](板卡精简验收与交付.md) · [目标固件](../firmware/target/README.md)。实板启动前以实际读回绑定目标 ELF。 |
| 物理 UART、SWO | `f103ze-uart-swo`、`h743-uart-swo`（历史证据） | [接线与控制](selectio/README.md#物理串口swo-和-spi) · [ABI 2 端点证据](validation/usb-split-20261123/README.md)。 |
| SPI | 滤波 v2 的四模式长窗用 `h743-spi-j7-rx-filter-v2-50`。原配对用 `h743-spi-j7-rx`、`h743-spi-j7-tx`、`h743-spi-full-duplex`，诊断用 `h743-spi-pad-diagnostic`，F103ZE 对照用 `f103ze-spi-cdc`。 | [滤波 v2 长窗](validation/h743-spi2-100mhz-20261124/README.md#50-mhz-持续验收) · [原配对结果](validation/h743-spi2-cdc-20261124/README.md#实板验收结果与收尾)。 |
| ETM | `f103ze-etm`、`h743-etm` | [Trace CLI](Trace-CLI使用说明.md) · [H743 RAW4 严格复验](validation/h743-cdc-golden-requal-20261123/README.md#etm-对照)。目标 ELF 与探针 PS ELF 分开核对。 |
| 构建、探针加载和发布 | `target-acceptance-build` 和 `probe-raw4-load` 提供当前入口。 `probe-qspi-release` 为归档索引。 | [目标构建](../firmware/target/README.md) · [探针配对索引](../prebuilt/README.md) · [发布流程](github-release.md)。 |

归档用例带 `role: "historical"` 和 `entry: null`，查询结果仅提供依赖和历史证据。下列命令只查询数据。

```powershell
python -X utf8 toolbox.py project cases --board h743 --feature spi
python -X utf8 toolbox.py project case h743-spi-j7-rx
python -X utf8 toolbox.py project case f103ze-etm
python -X utf8 toolbox.py project case hpm6800evk-rtt
```

知道工具名时用 `project describe <入口>`。具体参数以原脚本的 `--help` 为准。增加或变更用例时维护入口、参数和证据引用。文件 SHA-256 由产物 manifest 维护，问题状态由问题表维护。`targetElf` 缺省表示要从实际读回核对。固定历史资料写为 `提交号:路径`，可用 `git show` 查看。

本轮若需要工作台取证，启动 `serve --native-probe` 时显式传入同一 RAW4 ABI 2 配对的 `--bit` 和 `--zynq-elf`，并记录 `--runtime`。归档的 SPI 脚本结果通过 `resultRows` 定位。

## 配对与手册

| 用途 | 入口 |
|---|---|
| 当前固件、SHA-256 与临时加载 | [RAW4 融合 bit/ELF](../prebuilt/selectio-usb-split-raw4-20261123/README.md) |
| J7 接线、USB 端点与主机命令 | [SelectIO CLI](selectio/README.md) · [原生 USB 协议](selectio-native.md) |
| 构建工具、依赖与测试入口 | [CLI 工作台](toolbox-cli-ai.md) · [依赖](dependencies.md) · [仓库规则](../AGENTS.md) |
| Trace 采集、校验、离线查询和导出 | [Trace CLI](Trace-CLI使用说明.md) · [ETM 操作](Zynq-ETM-Trace操作说明.md) · [HTML 导出](flame-html-export.md) |
| 验收用例、实板结果和问题状态 | [融合性能用例](selectio/fusion-performance-cases.md) · [融合证据](validation/README.md) · [问题索引](项目问题跟踪列表.md) |
| 固定 EXE、发布、QSPI 和回退 | [板卡精简验收与交付](板卡精简验收与交付.md) · [发布流程](github-release.md) · [产物索引](../prebuilt/README.md) |
| 可运行的 ETM 离线示例 | [记录清单](retained-records.json) |
| 本地构建输出、原始证据和清理候选 | [build/ 盘点与保留](validation/build-retention.md) |

当前验收配对由 `probePairs.raw4` 指定。用 `probe-load --selectio` 临时加载，并用 `fusion.accept` 核对加载回执。 [RAW4 ABI 2](../prebuilt/selectio-usb-split-raw4-20261123/README.md)

融合前的独立验收报告保存在历史提交中，恢复入口见 [验收索引](validation/README.md#融合前档案)。当前配对以板上身份和配对哈希核对为准。
