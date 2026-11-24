# F103ZE 50 MHz SWD 复盘

本轮整理实板证据并运行诊断仿真。实板数字为 PC 有效载荷，单位 MB/s。历史标准路径、现版标准路径和现版原生路径分别列出，探针内部计时另列。

## 历史基线与优化过程

2026-10-31 的项目最佳为标准 CMSIS-DAP SRAM **4.047 / 3.983 MB/s**，RTT→CDC **3.995 MB/s**。目标 HCLK96，探针 FCLK0 约 100 MHz，实际 SWCLK 49,999,999.5 Hz，配置 0xa11 为约 10 ns 高电平、1 拍 idle。标准 SRAM 使用 512 字、2 KiB、USB 深度 32，每方向 256 块、三轮取中位。RTT 使用 SRAM 生产者、8 KiB 环和 2 KiB 块，两个 3 秒窗，探针计数约 4.007 MB/s。原始记录位于归档 archive/main-before-cleanup-20261105 的 docs/validation/combined-20261031/sota_peak_rtt/peak_swd_50000.json 和 rtt_swd_50000000.json。历史 RTL 为 954de8fd。[历史报告](https://github.com/minichao9901/zynqlinkPRO/blob/03b6a1dad8ee62aa7902b6bc37d0f0d9c3c3f451/docs/validation/combined-20261031/README.md#最终真机验收)

| 阶段 | 目标 HCLK | 主机接口 | SRAM 读 / 写 | RTT |
|---|---:|---|---:|---:|
| 历史最佳 | 96 MHz | CMSIS-DAP / CDC | 4.047 / 3.983 | 3.995 |
| 融合版同条件重放，slot 24 | 96 MHz | CMSIS-DAP / CDC | 3.649 / 3.695 | 3.645 |
| 融合版提高 HCLK，slot 24 | 128 MHz | CMSIS-DAP / CDC | 3.649 / 3.696 | 3.602 |
| 融合版切到 slot 22，原固件路径 | 96 MHz | CMSIS-DAP / CDC | 3.748 / 3.747 | 3.711 |
| 标准和 CDC 复用 SWD 队列 | 128 MHz | CMSIS-DAP / CDC | 3.844 / 3.871 | 3.811 |
| 同一 ELF 的 A/B 基准，FCLK0 约 133 MHz | 128 MHz | CMSIS-DAP / CDC | 3.846 / 3.873 | 3.810 |
| CDMA、GP1、HP0、载荷 BRAM 全部迁到 quad | 128 MHz | CMSIS-DAP / CDC | 3.827 / 3.853 | 3.788 |
| 切回 A，保留逐笔队列执行 | 128 MHz | CMSIS-DAP / CDC | 3.840 / 3.869 | 3.810 |
| 原生大帧、页间 DMA 重叠、RTT 4 KiB 批次 | 128 MHz | IF4 WinUSB | 4.016 / 3.972 | 3.915 |

原生 SRAM 使用 15 KiB 页对齐块和深度 4。原生 RTT 使用同一类 SRAM 生产者，每次可搬运 4 KiB。标准路径 A/B 的 SRAM 使用历史 2 KiB、深度 32，RTT 继续走 CDC 和 2 KiB，窗口为 2 × 60 秒。[相位、原生和历史重放](../swd50-recovery-20261122/README.md) · [标准共用队列](../swd50-standard-20261122/README.md) · [DMA 同域 A/B/A](../swd50-quad-dma-20261122/README.md)

- **slot 24→22**。提前回采相位在实板改善标准和原生吞吐。同一原生 15 KiB 配对短窗里，队列读从 4.020 提到 4.104 MB/s。slot 20 实测读回失败。
- **原生页间重叠和 RTT 大块**。固定 slot 24 时，重叠 CDMA 和引脚传输后，原生 PC 读 / 写从 3.852 / 3.840 提到 3.934 / 3.935。独立 RTT 复用 SRAM 队列和 4 KiB 搬运，最终 3 × 60 秒中位数 3.915 MB/s。
- **标准协议复用队列**。实时路径每笔 AP 操作都经 FCLK0 → quad → FCLK0。标准块改为描述符批次后，每笔连续 DRW 留在 quad 域。RTT 单换读路径、反复切回实时路径写 TAR 时一度降至 3.51 MB/s。持续持有队列并完成描述符、负载与 RdOff 后恢复到约 3.81。
- **统一 DMA/AXI**。A 的 CDMA 与 BRAM 主机端已经在同一 FCLK0。B 省下的是 SWD 逐批交接。1 KiB 上／下行，A133 为 6.870 / 6.046 µs，A100 为 7.913 / 7.117 µs，B100 为 7.928 / 7.105 µs。现有 50 MHz 工况以 A 性能更好。

## 余差按每 2 KiB 折算

| 标准路径 | 历史 | 现用 A | 额外时间 |
|---|---:|---:|---:|
| SRAM 读 | 506.09 µs | 532.51 µs | **26.42 µs** |
| SRAM 写 | 514.15 µs | 528.85 µs | **14.70 µs** |
| RTT→CDC | 512.66 µs | 537.58 µs | **24.92 µs** |

用 2,048 除以 MB/s 得到 µs。HCLK96→128 的融合版对照基本重合，目标升频无法解释这轮差距。历史与现版 RTT 的探针计数分别约为 4.007、3.810 MB/s，和各自 PC 收速相近，差距主要发生在数据进入 CDC 之前。原生私有 DDR 的 16 KiB 帧实测约 29.0 / 25.9 MB/s，USB 总带宽有余量。标准接口的块间等待仍需单独计时。

历史 swd_core 与包调度器同在 FCLK0，成功完成时可同拍接受下一笔。旧 RTT 的描述符、数据窗口及 RdOff 确认由 PL 自治执行。现版标准读写共用队列后，2 KiB 块仍按两个 256 字载荷 bank 提交。每批有首部和尾部 DP 事务，并付两次提交、DMA 接续和 USB 块处理。现版 CDC 使用同一物理队列，描述符读取、数据读取、RdOff 的批次提交由 PS 调度。这些成本需要按相同负载分别计时。

## 逐边沿仿真

三个模型均以相同 Cortex-M3、HCLK96、50 MHz SWCLK、16 ns SWDIO 回传延迟运行。16 ns 是一致的仿真假设。历史按实板配置使用 idle 1，现版使用 slot 22、idle 0。历史和实时均计 256 字标准包窗口。队列用 256 字原生页，含 TAR、RDBUFF、CTRL/STAT。所有 SRAM 载荷读回或逐字比对。计时从启动到结果可见，包含台架 AXI 轮询，覆盖的证据为数字链路。

| 模型 | SRAM 写 1 KiB | SRAM 读 1 KiB | RTT 第一个 1 KiB 就绪 |
|---|---:|---:|---:|
| 历史 RTL | **242.020 µs** | **242.020 µs** | **253.130 µs** |
| 现版实时逐笔 | 257.520 µs | 262.605 µs | 274.605 µs |
| 现版 SelectIO 队列 | 246.630 µs | 249.180 µs | — |

同一 SWCLK 窗口里，按每两个相邻上升沿的间距扣除 20 ns 周期。历史 SRAM 各打 12,092 个上升沿，累计额外停钟 **0.030 µs**。现版队列各打 11,929 个，写／读额外停钟 **7.820 / 10.380 µs**。现版实时路径两方向各 11,835 个沿，写／读额外停钟 **20.620 / 25.730 µs**。队列同域后，SelectIO 的停顿仍让一页比历史慢 **4.610 / 7.160 µs**。一页数字模型差额和整块 PC 差额各有计时边界。

RTT 表计到第一包就绪，DDR 复制、最终 RdOff、PC 消费在其后。历史和现版实时模型第一个 1 KiB 窗口均观察到 4 次 WAIT。现用 CDC 的 PS 借队列路径需要单独建立与历史等价的多包仿真。

把同一模型的目标 HCLK 从 96 改为 128 MHz 后，历史三个窗口及现版队列两个 SRAM 窗口的边沿计数、额外停钟和总时长均相同。这一控制组支持先定位探针侧时序。[六组计数](wire-budget.txt)

### 停钟发生在哪里

在 100 MHz quad 时钟域同时观测 SWD 分段引擎。发送段已经结束但等待最后回采的周期标为 DRAIN。内部分段计数与外部引脚停钟有重叠，下列数字用于定位阶段。

| 现版模型，HCLK96 | ACK 段等待回采的 quad 周期，写 / 读 | 读数据段等待回采的 quad 周期，读 | 段完成至下一笔启动，写 / 读 |
|---|---:|---:|---:|
| 队列 slot 22 | 1040 / 1040 | 514 | 259 次衔接同拍 / 同拍 |
| 队列 slot 24 | 1300 / 1300 | 771 | 259 次衔接同拍 / 同拍 |
| 实时 slot 22 | 1032 / 1032 | 514 | 257 次，平均 60.08 / 60.04 ns |

队列内部已经连续接下一笔。主要停钟落在 50 MHz 分段发送等 ACK 回采的阶段，读方向还要等末尾数据和奇偶校验。slot 24 比 slot 22 在每个 ACK 回采段多 1 个 quad 周期，读尾也多 1 个。引脚累计停钟随之增加约 **2.61 µs 写、5.17 µs 读**，与实板提前 slot 后读提升更明显的方向一致。实时路径逐笔约 60 ns 的额外交接，和这两种回采等待同时存在。

历史基线在模拟延时 16 ns、idle 1 下，上一笔后立刻发出的优势仍然可见。现版 50 MHz 半速分支在 ACK 确认后启动下一段，而 swd200_link 已在部分 100/200 MHz 分支提前排入下一个合法边沿。若继续改逻辑，50 MHz 可先在台架试验等 ACK 时能否安全保留这个边沿，并同时覆盖 OK、WAIT、FAULT、奇偶校验错与换向。读末尾须以校验通过作为发布条件。

## 下一轮仿真的测量边界

1. 把 512 字标准路径按实际提交方式建模。历史是一笔 512 字 TransferBlock，现版是两批 256 字及各自的首尾 DP 操作。把引脚活动、ACK/读尾停钟和批次之间的间隙逐项记账。
2. 以相同 8 KiB RTT 环和 2 KiB 搬运做持续多包模型。分别记录描述符轮询、数据、DDR 提交、RdOff 写入与确认。这能区分历史 PL 自治路径和现版 CDC 的 PS 批次调度。
3. 在同一实板窗口补 PS 层时间戳时，分别测提交、DMA、块尾处理和主机收包。将每项结果与 26.42 / 14.70 / 24.92 µs 的端到端余差对齐。

## 复现

```powershell
git archive -o build/swd50-history-rtl.zip 954de8fd fpga/rtl
Expand-Archive -LiteralPath build/swd50-history-rtl.zip -DestinationPath build/swd50-history-rtl
python -X utf8 tools/run_cm3_sim.py --top tb_cm3_swd --dut-rtl build/swd50-history-rtl/fpga/rtl --work-dir build/swd50-budget-history benchmark wire_budget half_ns=5 target_clk_ns=10.4166667 idle=1 return_ns=16
python -X utf8 tools/selectio_cm3.py --swd-only --half-rate --wire-budget --idle 0 --target-clk-ns 10.4166667 --return-ns 16 --swd-slot 22 --out build/swd50-stage-queue-22
python -X utf8 tools/selectio_cm3.py --swd-only --half-rate --wire-budget --idle 0 --target-clk-ns 10.4166667 --return-ns 16 --swd-slot 24 --out build/swd50-stage-queue-24
python -X utf8 tools/selectio_cm3.py --services --swd-only --half-rate --wire-budget --idle 0 --target-clk-ns 10.4166667 --return-ns 16 --swd-slot 22 --out build/swd50-stage-live-22
```

HCLK128 控制组将历史命令的目标周期参数和队列命令的 --target-clk-ns 改为 7.8125，分别使用证据文件所列的新目录。Vivado 2018.3 的 XSim 曾在诊断 task 传入字符串时退出，改用整数阶段编号后运行完成。已保存版本和失败阶段。[台架修正记录](wire-budget.txt)
