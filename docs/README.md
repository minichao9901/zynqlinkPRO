# 融合工程文档

## 从任务找入口

先核对当前 Git worktree 和分支。用根目录 [acceptance-cases.json](../acceptance-cases.json) 的 Case ID 找入口、参数、配对、目标 ELF 和证据。用例库涵盖优先复用的工作路径、常用诊断和明确保留的历史对照，更细的测试组合见对应验收报告。

`validationScope: "probe-regression"` 标出这六个 F103ZE 探针回归用例。三板新目标镜像的实板签收应明确融合 bit/PS ELF，按 [板卡镜像索引](../firmware/target/README.md) 选目标 ELF，核对装载段，再测镜像本身的功能与速率。QSPI 正式配对用于旧工作台对照。 [F103ZE 回归范围](validation/f103ze-cases-20261124/README.md#本报告的验证范围)

| 任务 | 从这里开始 | 配对与证据 |
|---|---|---|
| SRAM、RTT、J-Scope | F103ZE CDC48 功能回归用 `f103ze-sram-rtt-scope`，HCLK128 的 50 MHz SWD 性能用 `f103ze-hclk128-swd50`。另有 `h743-sram-rtt-scope`、`hpm6800evk-rtt`、`hpm6800evk-scope`。 | [融合板测索引](validation/README.md)。F103ZE 功能与性能、H743 RAW4 ABI 2、HPM QSPI 历史对照各有独立条件。 |
| 调试、烧录和复位 | 三板的 `*-debug-flash` | [统一入口与验收判据](板卡精简验收与交付.md) · [目标固件](../firmware/target/README.md)。实板启动前以实际读回绑定目标 ELF。 |
| 物理 UART、SWO | `f103ze-uart-swo`、`h743-uart-swo`（历史证据） | [接线与控制](selectio/README.md#物理串口swo-和-spi) · [ABI 2 端点证据](validation/usb-split-20261123/README.md)。 |
| SPI | 滤波 v2 的四模式长窗用 `h743-spi-j7-rx-filter-v2-50`。原配对用 `h743-spi-j7-rx`、`h743-spi-j7-tx`、`h743-spi-full-duplex`，诊断用 `h743-spi-pad-diagnostic`，F103ZE 对照用 `f103ze-spi-cdc`。 | [滤波 v2 长窗](validation/h743-spi2-100mhz-20261124/README.md#50-mhz-持续验收) · [原配对结果](validation/h743-spi2-cdc-20261124/README.md#实板验收结果与收尾)。 |
| ETM | `f103ze-etm`、`h743-etm` | [Trace CLI](Trace-CLI使用说明.md) · [H743 RAW4 严格复验](validation/h743-cdc-golden-requal-20261123/README.md#etm-对照)。目标 ELF 与探针 PS ELF 分开核对。 |
| 构建、探针加载和发布 | `target-acceptance-build`、`probe-raw4-load`、`probe-qspi-release` | [目标构建](../firmware/target/README.md) · [探针配对索引](../prebuilt/README.md) · [发布流程](github-release.md)。 |

用例角色为 `regular`（常用入口）、`diagnostic`（定向诊断）、`historical`（历史条件或复现）。下列命令只查询数据。有独立入口的用例会给出脚本及含 `--dry-run` 的参数数组。`entry: null` 的条目只用于查历史证据。

```powershell
python -X utf8 toolbox.py project cases --board h743 --feature spi
python -X utf8 toolbox.py project case h743-spi-j7-rx
python -X utf8 toolbox.py project case f103ze-etm
python -X utf8 toolbox.py project case hpm6800evk-rtt
```

知道工具名时用 `project describe <入口>`。具体参数以原脚本的 `--help` 为准。增加或变更用例时维护入口、参数和证据引用。文件 SHA-256 由产物 manifest 维护，问题状态由问题表维护。`targetElf` 缺省表示要从实际读回核对。固定历史资料写为 `提交号:路径`，可用 `git show` 查看。

标准 Web 板测先用 `toolbox.py --runtime <目录> serve --native-probe --bit <探针bit> --zynq-elf <探针PS ELF>` 启动匹配的本机工作台，再把同一个 `--runtime` 传给验收脚本。共用 SPI 脚本的用例按 `resultRows` 读对应报告行。

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

融合通用参考为 [RAW4 ABI 2](../prebuilt/selectio-usb-split-raw4-20261123/README.md)。`board.accept --selectio` 当前只支持 F103ZE，省略 `--pair` 时会选旧融合配对。按 Case 显式声明。对 AXI/DTCM、JTAG/SWD、J7 RAM/正式 QSPI 分别引用实测。

融合前的独立验收报告保存在历史提交中，恢复入口见 [验收索引](validation/README.md#融合前档案)。当前配对以板上身份和配对哈希核对为准。
