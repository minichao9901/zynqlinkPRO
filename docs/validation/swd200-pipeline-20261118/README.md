# 200 MHz 纯 SWD 流水优化

2026-11-18，`codex/swd-only-200mhz`，基线 `3b4e2e0d`。继续使用 J7 的 SWCLK、双向 SWDIO 和保持高电平的 nSRST。验收范围为 Cortex-M3 仿真、XC7Z020 综合布线及 bit/ELF 配对，实板待验。

## 同口径吞吐

Vivado XSim 2018.3、Cortex-M3 DesignStart、SWCLK 200 MHz、HCLK 100 MHz。返程附加延时 0.8 ns，ACK 和数据采样时隙 12，IDELAY tap 0，idle 两拍。每次三轮 1 KiB SRAM 写入并完整回读，检查 SRAM 内容、posted read、换向、WAIT 重试、奇偶错误隔离和恢复。计时从 AXI 提交到读取批完成摘要，命令填表和结果搬运在计时窗外。MB/s 按十进制计。

| 方案 | 读 MB/s | 写 MB/s | 成功事务 ACK 后停钟 | 成功事务笔间停钟 |
|---|---:|---:|---:|---:|
| 原配对 `3b4e2e0d` | 9.6470 | 9.6261 | 约 60 ns | 读写约 110 ns |
| 独立预取 `05d039bd` | 10.6842 | 10.6592 | 约 60 ns | 读写约 70 ns |
| 直接段交接 | 14.6448 | 15.1754 | 约 20 ns | 读约 10 ns，写连续 |
| 提前首拍及预计算奇偶校验 | 15.2025 | 15.1788 | 约 15 ns | 读写约 5 ns |

最后一版读写比原配对分别高约 57.6%、57.7%，约为 16 MB/s 目标的 95%。主对照的总 SWCLK 边数 74,975 和 WAIT 重试 9 次与原版一致。停钟列描述成功事务的波形，WAIT 的短段可能因链路状态已切换而在计数器中归入笔间停钟。JSON 中保留边数和端到端时间。

[原配对](../swd200-20261118/README.md) · [预取证据](prefetch.txt) · [直接交接证据](direct-handoff.txt) · [最终矩阵](matrix.json)

## 最终版本回归

| SWCLK MHz | 读 MB/s | 写 MB/s | WAIT 重试 |
|---:|---:|---:|---:|
| 50 | 4.0422 | 4.0420 | 6 |
| 100 | 7.7615 | 7.7607 | 6 |
| 160 | 12.1640 | 12.1467 | 9 |
| 200 | 15.2025 | 15.1788 | 9 |

四档均完成三轮 1 KiB。200 MHz、时隙 13 在 0、0.8、1.6、2.0、2.4、2.8、3.2、4.0 ns 八个模拟返程延时点通过，4.0 ns 下另通过三轮 1 KiB，速度与主测试一致。两拍 idle 为主测试设置，另复核了 1、3、15 拍的读写。错误对照保留时隙 12 在 2.0 ns 及以后返回无效 ACK，以及时隙 14 在 0–1.6 ns 触发换向争用的记录。

SWCLK 200 MHz 下，CM3 HCLK 125、100、80、50 MHz 均完成完整读写。HCLK 80 MHz 的读速降到 14.1120 MB/s，HCLK 50 MHz 的读写降到 8.6299 / 9.6702 MB/s，WAIT 重试升至 2,701 次。该低 HCLK 条件下，目标 AP 响应等待占用更多链路时间。

## 交接和错误处理

批引擎在当前事务期间读取下一条 BRAM 命令，并预先计算头部和写数据奇偶。成功完成时可直接发出已预取命令。WAIT 重发当前命令，预取项留在队列。FAULT、无效 ACK 或读奇偶错误停止批次，并使未完成项不可读。

段结束以最后一个发送字及所需的最后一个采样为准。高速档可同拍把下一段的首字送给 OSERDES。累计奇偶随 ISERDES 采样位推进，事务完成只处理最后一组采样。全速档在 ACK 和数据采样时隙为 12 或 13 时提前送出一拍主机高阻的 SWCLK。对成功读事务，这一拍接收 D0。对写事务和 WAIT/FAULT，它是换向周期。写数据驱动仍等三个 ACK 位全部确认。无效 ACK 最多已发出这一拍主机高阻时钟，随后保持高阻并结束批次。

其他采样设置沿用等待完整 ACK 的直接交接。前一版的相位风险仍适用，失配可以把 ACK 误判成另一种有效 ACK 并引起方向冲突。

首轮优化版实现仍报结果 BRAM 写使能的 REQP-1840。结果提交改为单独的 CLKDIV 寄存器级，结果可与下一条命令并行提交，最后一次写入先于 AXI 获得批完成标志。加寄存器后，主测试的吞吐、引脚计时和 WAIT 重试次数保持一致。见[首轮 DRC](first-route-drc.rpt)。

## 最终综合布线

XC7Z020-CLG400-2，Vivado 2018.3。AXI 目标 133.333333 MHz，最高档串行时钟 200 MHz，CLKDIV 100 MHz。布线 WNS **+0.997 ns**、WHS **+0.082 ns**，全部 2,188 条可布线网络完成，DRC 零违规。使用 1,010 LUT、1,122 寄存器和 1.5 个 BRAM Tile。构建核对两颗 OSERDESE2、一颗 ISERDESE2、一颗 IOBUF 及 L15、L16、M14 三个 PL 外部管脚。

CDC 报告仍标记同步完成握手下的失败位、复位异步断言的组合入口以及 58 个握手使能控制项。外部 SWDIO/SWCLK 时序和信号完整性待实板签核。本轮交付限实验分支的源码与 bit/ELF 配对。远端 main、固定 EXE、Pages、Release 下载和 QSPI 冷启动均为范围外。

[时序](timing.rpt) · [时钟](clocks.rpt) · [资源](utilization.rpt) · [管脚](io.rpt) · [CDC](cdc.rpt) · [DRC](drc.rpt) · [配对及 SHA-256](../../../prebuilt/swd-only-200mhz-pipeline-20261118/manifest.json)

## 复现

```powershell
python -X utf8 toolbox.py project run swd200 -- sim --mhz 200 --words 256 --rounds 3 --trace
python -X utf8 toolbox.py project run swd200 -- matrix
python -X utf8 toolbox.py project run swd200 -- build
```
