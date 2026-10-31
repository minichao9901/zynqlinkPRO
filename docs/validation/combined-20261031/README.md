# 两条工作流合并后的统一构建与验收

本目录保留合并后新构建的原始证据，包括失败与复测。产品输入快照为 `954de8fd09f4a97aafb7dc42fa5e4a9a019c3f19`；之后主分支的 `cff18fa`、`24e36ef` 只补齐目标/主机端源码及离线证据，未改变此次 PL/PS 输入。`9561082` 刷新相应硬件 HDF 并加入显式配对回归入口。

**本轮仅 JTAG 配置 PL、下载 ELF 到 RAM；没有擦写 QSPI，也没有把新 BOOT 的文件生成等同于冷启动验收。** 旧已验收 Flash 配对保留。单板先由优化线程独占，再显式交给 ETM/Web 线程；共享协调文件是协作约定，不是驱动锁。

## 最终静态结果（含新增输出预算）

| 方案 | LUT | FF | Slice | BRAM36 当量 | WNS / WHS |
|---|---:|---:|---:|---:|---:|
| 7020 / 120MHz / RAW4 FIFO16 | 14779 | 17051 | 6367/13300 | 38.5/140 | +0.167 / +0.024ns |
| 7010 / 100MHz / RAW4 FIFO16 | 14625 | 17051 | 4399/4400 | 38.5/60 | +0.164 / +0.065ns |

两者 setup/hold 的 TNS/THS 均为 0，完成实际目标器件的布局布线和 bitgen。7010 仅剩 1 个 Slice，**没有 7010 真机验收**。没有用禁用 ETM 的 RAW0 结果冒充完整 RAW4 结果。原始时序、资源报告在 `static/`。

PS 代码 71268 字节；代码、只读/必要静态数据、MMU 表、堆栈所在 OCM 地址跨度 120976 字节，低 OCM 余量 75632 字节，扣除 512 字节保留区后全部 256KiB OCM 合计余量 140656 字节。运行缓冲在 DDR；DAP 16×4096、USB 512KiB 保持原值。完整 ELF 布局见对应 prebuilt 的 `ocm_layout*.json`。

最终交付配对是 `prebuilt/20261031_combined_raw4_io_7020_120/`，静态通过但没有实物板的 7010 配对是 `prebuilt/20261031_combined_raw4_io_7010_100/`。所有哈希见各自 `manifest.json`。

首次构建配对（后续真机失败，仅用于复现）：`prebuilt/20261031_combined_raw4_7020_120/probe.bit` SHA-256 `76a8deefb1b879c7ac253a205cabd6fde53674f6454c1c2c5a88fd4f54e65f1f`，`application.elf` SHA-256 `e977914c2924ab4cac13f4075de0a5108d1e2e8cf48966fb8fbdea3a358e0b2c`。不能仅靠切换 worktree 判断板上版本；每次实际 JTAG 加载保留 `load.log`。

## 真机进度与已知异常

`full_60/` 首轮 SRAM 14 个频点有 13 个通过。JTAG 30MHz、自动采样模式 0 在流水读取开始时返回 `06000003`（0 个成功传输，状态 3）；该次已停止后续批次，RAM 和目标状态恢复通过。不得删除该失败或改写为全通过。

`jtag30_qualification/` 为新 PL 的 6 轮独立专项：自动模式 0 三轮、显式诊断模式 17 三轮，每轮顺序读/流水读/流水写各 5×1 秒，均通过且恢复通过。`old_pl_jtag30_control/` 为旧已验收 PL `f02a15db…` 加同一新 ELF 的三轮对照，均通过。该混合配对只作诊断，不是交付组合。历史 `docs/F103ZE测速-20261029.md` 也记录过 30MHz 单次异常后 3/3 复测通过；目前没有证据把本次异常归因于新 ETM 或某个确定采样问题。没有为此修改固件校准或降低队列。

`full_60_repeat/` 在明确重新 JTAG 加载新配对后，SRAM 14/14 全过；RTT SWD1/10MHz 通过，25MHz 出现可重复传输错误并停止。目标保持其原始 HCLK48MHz。`rtt25_qualification/` 中，新 PL 三轮均失败，旧 PL 加相同新 ELF 三轮各三次均无错，所有目标状态恢复通过。直接切换采样相位的实验在 `phase25_experiment/` 中 IDCODE 失败，该固件修改已撤回。

## SWCLK 输出路径修正

新旧 routed DCP 的慢角分析显示：短脉冲 SWCLK 寄存器到引脚延迟从 7.417ns 增至 8.400ns。原约束没有该输出路径的专门预算。`9bfd403` 加入更严格的 7ns `set_max_delay -datapath_only`，并接入正常实现及 7010 入口；没有放宽内部时序，也没有改动 RTL、固件、队列、采样配置或链路速率。基于原始新构建 DCP 重新进行 phys_opt/route/bitgen 后，SWCLK 路径为 6.833ns，7020/120MHz 内部 setup/hold 为 +0.259/+0.024ns，包含新增 I/O 路径的总 WNS 为 +0.167ns、WHS +0.024ns、TNS/THS 0。

修正配对 `prebuilt/20261031_combined_raw4_io_7020_120/probe.bit` SHA-256 `1da17cb60175bbc2b7abd647770c7053bd7b7097e0d38aa819fb89678d564473`，ELF 仍为 `e977914c…`。LUT14779、FF17051、Slice6367、BRAM36当量38.5。`io25_qualification.json` 在原 HCLK48MHz、原 cfg `0xc2a11`、原25MHz链路下连续9次 RTT 全部0错，数据序列完整并恢复通过。这支持输出延迟是关键因素，但不能代替其余频点回归。`io_ocm_verify/` 为修正配对运行时5次代码回读（含4次USB重新配置），均与 ELF 一致。

首版 `76a8…` 配对及其 BOOT 仅保留作失败复现，不能作为已验收合并版或用于固化。

## 最终真机验收

最终 `1da17c… / e97791…` 的 `io_full_60/` **25/25 全通过**：SRAM14频点、RTT14频点、HSS矩阵/动态生产者/8变量、功能、JTAG非对齐、CMSIS深度16多会话及OpenOCD多会话。这里目标保持原 HCLK48MHz。RAM、寄存器、RCC、AFIO及原运行/暂停状态恢复证据随各测试保存。

按 `F103ZE测速-20261029.md` 相同参数复测 SOTA：临时 HCLK96MHz（DWT实测约96.03MHz，仅运行RAM生产者，结束恢复48MHz）；512字/2KiB块、深度32、256循环、3次中位。没有降低速率或队列。实际FCLK约100/120MHz，实际链路约49,999,999.5/59,999,999Hz。

| 链路 | SWD读/写 MB/s | JTAG读/写 MB/s | SWD RTT主机 MB/s | JTAG RTT主机 MB/s |
|---|---:|---:|---:|---:|
| 50MHz | 4.047 / 3.983 | 2.023 / 2.005 | 3.995 | 1.999 |
| 60MHz | 4.836 / 4.755 | 2.420 / 2.396 | 4.803 | 2.394 |

RTT为8KiB环、chunk2048、3秒×2次，全部发布字节收到、序列连续、0错；SWD60额外30.059秒读写soak，137轮、0错。`sota_peak_rtt/` 8项均通过。

`sota_hss/` 原参数42行全部逐帧验证及计数一致，传输错误为0。SWD单变量50/60MHz均约1MHz，三轮0跳点；8变量分别101.695/121.827kHz，在原period236/197下三轮0跳点。JTAG单变量零跳点约269.663/324.324kHz；8变量约45.369/54.299kHz，原period529/442下三轮0跳点。超容量点仍保留原来的周期跳点行为（例如JTAG period527/411约6.25%），不能把所有42行说成全部零跳点。详见 `acceptance_summary.json` 及原始JSON。

`profile50/` 另检查50MHz上限ELF：12个SRAM频点、SWD/JTAG各25/50MHz RTT、60MHz请求被拒绝，全部通过；该ELF仅在7020板上验证，不能代替7010实物验收。

结束时通过JTAG重新加载最终60MHz配对，`final_handoff_ocm_verify/` 5次代码回读均匹配，物理BOOT_MODE仍为QSPI但本轮执行来自JTAG/RAM；本轮未写Flash，重新上电仍是旧固化版本。最终FCLK0约100MHz、FCLK1约200MHz；`handoff_state/` 保存时钟寄存器及最终加载记录。目标CDC为COM34（源码VID/PID F055:1031），PING/INFO正常，返回 `sysclk=48000000Hz clk_err=0`，没有为交接复位目标或改写其Flash。

我方验收范围是PL静态签核、PS/OCM、传输和SOTA。**ETM/Web实际采集验收由另一线程在明确交板后完成，此处尚不声明ETM端到端通过。** 默认QSPI固化包保留旧已验收版本，新I/O约束配对未生成或固化BOOT。

复测加载命令（在仓库根目录执行；仅JTAG/RAM）：

```powershell
python tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/20261031_combined_raw4_io_7020_120/application.elf prebuilt/20261031_combined_raw4_io_7020_120/probe.bit prebuilt/20261031_combined_raw4_io_7020_120/ps7_init.tcl
```

完整回归：`tools/run_probe_regression.py` 显式给出上述bit/ELF/ps-init、全新 `--out` 和 `--execute`；默认仅输出计划。必须先取得单板协作占用权。SOTA则用 `run_f103_clock_fixture.py`、`run_f103_jtag_fixture.py` 包裹 `run_sota_regression.py`，原样命令见归档helper和JSON，输出目录必须新建。

`static/native_tests/results.json` 为九组实际执行的 RTL/主机仿真结果。传输相关九个 RTL 模块及 PS 应用源码与此前已验收版本一致，Git blob/tree 比较在 `static/component_equivalence.json`；旧的加密 CM3 矩阵只作为未改变组件的既有证据，不冒充本轮新执行。

私有 RAM 备份、运行时代码快照不纳入 Git；对应公共 JSON 保存恢复一致性/哈希和命令。现场诊断脚本原样存于 `as_run_helpers/`，通用入口为 `tools/run_probe_regression.py`、`tools/run_sota_regression.py`，测试不写目标 MCU Flash。
