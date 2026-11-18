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

## 交接和错误处理

批引擎在当前事务期间读取下一条 BRAM 命令，并预先计算头部和写数据奇偶。成功完成时可直接发出已预取命令。WAIT 重发当前命令，预取项留在队列。FAULT、无效 ACK 或读奇偶错误停止批次，并使未完成项不可读。

段结束以最后一个发送字及所需的最后一个采样为准。高速档可同拍把下一段的首字送给 OSERDES。累计奇偶随 ISERDES 采样位推进，事务完成只处理最后一组采样。全速档在 ACK 和数据采样时隙为 12 或 13 时提前送出一拍主机高阻的 SWCLK。对成功读事务，这一拍接收 D0。对写事务和 WAIT/FAULT，它是换向周期。写数据驱动仍等三个 ACK 位全部确认。无效 ACK 最多已发出这一拍主机高阻时钟，随后保持高阻并结束批次。

其他采样设置沿用等待完整 ACK 的直接交接。前一版的相位风险仍适用，失配可以把 ACK 误判成另一种有效 ACK 并引起方向冲突。

## 复现

```powershell
python -X utf8 toolbox.py project run swd200 -- sim --mhz 200 --words 256 --rounds 3 --trace
python -X utf8 toolbox.py project run swd200 -- matrix
python -X utf8 toolbox.py project run swd200 -- build
```
