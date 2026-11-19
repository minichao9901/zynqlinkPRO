# F103ZE 驻留命令与 SWDIO 换向

2026-11-19。PL/PS 源码 `5dad78ec`。保持纯 SWD。新增 AXI 寄存器 `0x1c`，位 1:0 选择原始、驻留读、驻留写三个命令 bank，位 2 控制图案取反，位 3 启用读回逐字比对，位 6:4 指定读尾换向等待的 CLKDIV 拍数。特征寄存器 `0x20` 读回 `BNK1`。期望数据窗口从 `0x3000` 起，共 256 字。写 bank 对 DRW 写数据取反，读 bank 校验 posted read 结果及最后的 RDBUFF。校验错误置批次失败位并保留结果。

CM3 使用实际 SelectIO 原语，覆盖两个驻留表交替、整块取反、故意损坏最后一个期望字、错误隔离和恢复。160 MHz、20 ns 模拟返程延时、时隙 19、guard 3 通过。XC7Z020-CLG400-2 完成布线，WNS +0.109 ns、WHS +0.069 ns，DRC 零违规。使用 1,288 LUT、1,209 寄存器、5 个 BRAM Tile 和三个 PL 管脚。CDC 握手数据和复位入口仍保留报告项。

实板为 HS3 `210299008529` 和 F103ZE。HCLK 由 SRAM 自循环的 DWT 验证约 128 MHz。每次测量先装入一个 1 KiB 图案，再进行交替反相写入和逐字读回。下表计时为 A9 探针本地每块操作，包含提交、等待和 PL 在线数据核对。另在计时窗外由 A9 完整复读最后一块，每个长窗口后低档复核原 4 KiB SRAM 和哨兵。写入前用 TAR posted read 核对目标地址。一次性装表与 PC 到探针传送新载荷的时间另计。

| SWCLK MHz | 读 / 写 MB/s，A9 本地 | 批提交到完成读 / 写 MB/s |
|---:|---:|---:|
| 66.667 | 5.109 / 5.118 | 5.146 / 5.265 |
| 100 | 7.346 / 7.458 | 7.423 / 7.729 |
| 160 | 9.397 / 11.074 | 9.524 / 11.632 |
| 177.778 | 10.121 / 12.252 | 10.269 / 12.906 |

177.778 MHz，tap 8、ACK/数据时隙 20、idle 1、guard 1，三轮，每轮读与写各 16 MiB。对照旧配对的 100 MHz，A9 本地读写由 3.65 / 4.37 提升至 7.35 / 7.46 MB/s。100 MHz guard 为 0，改善主要来自预装命令与 PL 比对。历史 USB 全局最高为 5.3605 / 5.2527 MB/s，传输路径与新的本地驻留测试不同。未修改目标 Flash 或探针 QSPI，最终由独立 USB 配对核对原 HCLK、运行态、SRAM 和保护字。

[原始窗口](hclk128-windows.txt) · [时钟与恢复](hclk128-target.json) · [同日历史 USB](hclk128-historical.json) · [CM3 对照](sim.json) · [时序](timing.rpt) · [DRC](drc.rpt) · [配对清单](../../../prebuilt/swd-only-200mhz-resident-20261119/manifest.json)

## 100 MHz 后续候选

一拍 SWCLK 对应一个 CLKDIV 字时，在 ACK 与数据落在同组四个时隙的条件下也可提前输出主机高阻首拍。允许批内零 idle，最后一条保留两拍。CM3 100 MHz、idle0 的同一台架实测模型读写 8.245 / 8.405 MB/s，驻留 bank 误码注入通过。160 MHz、20 ns 返程、guard1 的短测也通过。

最终配对 WNS +0.524 ns、WHS +0.066 ns、DRC 零违规。HCLK128 下，100 MHz 使用 tap0、ACK/数据时隙20、批内 idle0，三轮批读写 7.565 / 8.039 MB/s，含 A9 控制的驻留读写 7.485 / 7.759 MB/s。177.778 MHz 使用 tap8、时隙20、guard1、idle1，三轮批读写 10.276 / 12.905 MB/s，本地读写 10.129 / 12.248 MB/s。两档各轮每方向 16 MiB，均逐字校验。177.778 MHz 的 idle0 只通过短窗，长窗使用 idle1。182.857 和 188.235 MHz 虽有 DPIDR 或短窗通过点，未通过本轮三次持续读写。193.939 和 200 MHz 缺少稳定 DPIDR。较早的驻留配对在 HCLK96 也复验了 100 与 177.778 MHz 的三轮读写。

120.755 MHz 档使用 IO PLL 约 1600 MHz、FCLK1 整数除 53（寄存器 0x00103500）、PL MMCM 乘 20 除 5，SWCLK 为 6400/53 MHz，CLKDIV 为其一半。使用已读回的时钟树和实际时隙计算，无外部频率计读数。

收尾以独立 USB 链路读回 4 KiB SRAM 及两侧哨兵，RCC、Flash 等待周期和原运行态一致。探针恢复开测时的 JTAG 启动与 PL 复位隔离寄存器状态，F103 CDC 仍枚举。实验仅交付本地分支，固定 EXE、远端 main、Pages、Release 和 QSPI 冷启动均为范围外。

[最终硬件窗口](zero-refine-windows.txt) · [频率边界](resident-upper-windows.txt) · [96 MHz HCLK](resident-96-confirm-windows.txt) · [最终恢复](final.json) · [最终配对](../../../prebuilt/swd-only-200mhz-resident-zero-20261119/manifest.json)
