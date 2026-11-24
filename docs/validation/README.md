# SelectIO 融合验收

## 当前 RAW4 + ABI 2

| 验收 | 证据 |
|---|---|
| F103ZE 新清单的同配对实板复验 | [RAW4 ABI 2 新批次](f103ze-raw4-v2-20261124/README.md) |
| H743 历史 CDC Golden，ETM、SWD/JTAG、COM/SWO/SPI 功能与持续窗口 | [功能及持续验收](h743-cdc-golden-requal-20261123/README.md) |
| 同板 MEM-AP WAIT、SRAM 区及 USB 端点拆分对照 | [吞吐分析](h743-throughput-audit-20261123/README.md) |
| HCLK60/240 相同负载对照、JTAG SRAM 与独立 RTT 长窗 | [时钟及 JTAG 档位](h743-hclk-ab-20261123/README.md) |
| USB ABI 2 拆分、并发与读尾部 | [USB 拆分验证](usb-split-20261123/README.md) |
| ETM400 的成帧故障与 RAW4 复验 | [同板诊断](h743-etm-source-audit-20261123/README.md) |
| H743 → J7 EP10 从机持续接收 | [修订 3 长窗](h743-spi2-cdc-20261124/README.md#实板验收结果与收尾)。50 MHz 按 Mode 1/2，12.5 MHz 按 Mode 0/3。 |
| J7 原生主机 → H743 只收 | [100 MHz Mode 3 三轮记录](h743-spi2-cdc-20261124/native-master-100-mode3.json)。目标修订 2，单帧 4,096 B。 |
| J7 ↔ H743 全双工 | [四模式对拍](h743-spi2-cdc-20261124/README.md#实板验收结果与收尾)。原始波形路径约 25 MHz。 |

## SPI 定向诊断

[三线采样、固定码型与速度对照](h743-spi2-100mhz-20261124/README.md)使用诊断配对和 H743 修订 4。固定码型的 100 MHz 通过点与任意数据的失败边界单独记录。用例的脚本和镜像见[根目录清单](../../acceptance-cases.json)，最新状态查问题表。

[滤波 v2 专用配对](../../prebuilt/selectio-spi-pad-filter-v2-20261124/README.md)与 H743 修订 4 的 **50 MHz 四模式各 3×60 秒**均通过。源端三线速度全 1，SCK/NSS 与 MOSI tap 为 0。按 `h743-spi-j7-rx-filter-v2-50` 复查 12 个长窗。100 MHz 任意载荷仍未通过短测。 [持续验收](h743-spi2-100mhz-20261124/README.md#50-mhz-持续验收)

## 融合方案历次实测

- [F103ZE 用例清单实板验收](f103ze-cases-20261124/README.md)，含 ABI 1 功能及旧正式 RAM 对照。

- [首轮双协议集成](selectio-integration/README.md)与[F103ZE 整体回归](selectio-fusion-20261121/README.md)
- [融合队列与吞吐](efficiency-20261122/README.md)、[变频实现](selectio-variable-20261122/README.md)与[变频实板](selectio-variable-board-20261122/README.md)
- [SWD50 标准路径](swd50-standard-20261122/README.md)与[四时钟 DMA 对照](swd50-quad-dma-20261122/README.md)
- [SPI CDC 原配对与分档](spi-cdc-20261123/README.md)及 [H743 目标高速工况](h743-perf-20261123/README.md)

## 融合前档案

`bf53619c` 是共享 SelectIO 融合的起点。融合前的验收报告和过时文档可以从冻结的 `main` 提交 `03b6a1da` 或清理前融合分支提交 `9b5faece` 读取。例如：

```powershell
git show 9b5faece:docs/validation/README.md
git show 03b6a1da:docs/validation/h743-comprehensive-20261101/README.md
```

离线示例、测试依赖及配对身份清单随当前工程提供。历史条件和问题状态可在原提交追溯。
