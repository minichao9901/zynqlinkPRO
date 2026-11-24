# SelectIO 融合验收

## 当前 RAW4 + ABI 2

| 验收 | 证据 |
|---|---|
| H743 历史 CDC Golden，ETM、SWD/JTAG、COM/SWO/SPI 功能与持续窗口 | [功能及持续验收](h743-cdc-golden-requal-20261123/README.md) |
| 同板 MEM-AP WAIT、SRAM 区及 USB 端点拆分对照 | [吞吐分析](h743-throughput-audit-20261123/README.md) |
| HCLK60/240 相同负载对照、JTAG SRAM 与独立 RTT 长窗 | [时钟及 JTAG 档位](h743-hclk-ab-20261123/README.md) |
| USB ABI 2 拆分、并发与读尾部 | [USB 拆分验证](usb-split-20261123/README.md) |
| ETM400 的成帧故障与 RAW4 复验 | [同板诊断](h743-etm-source-audit-20261123/README.md) |

## 融合方案历次实测

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
