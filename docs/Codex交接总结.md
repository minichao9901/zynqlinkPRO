# Zynq DAPLink 交接总结（给 Codex）

> 更新（2026-10-25）：以下保留 Deepseek 交接时的历史基线。当前已完成 AXI4-Full + CDMA、RTL 连续传输与 LA 分析：50 MHz 下读 3.052 MB/s、写 3.367 MB/s。请优先阅读 [优化记录](RTL批量与DMA优化.md)、[LA 微时序](LA微时序分析.md) 和 [已验证下载包](../releases/dma50_20261025/README.md)。

日期：2026-10-25。工作区 `E:\zynqlinkPRO`。板子：Zynq-7020（xc7z020clg400-2）+ F103CB 目标 + Digilent JTAG-HS3 + Kingst LA。

## 一、现在是什么状态

**能用的：**

- XUsbPs 复合设备：接口 0 = CMSIS-DAP v2（WinUSB bulk，VID/PID `0D28:0204`），接口 1/2 = CDC ACM（COM33）。
- FPGA 里跑旧工程的 SWD RTL（`swd_core` + `swd_batch_engine` + `swd_controller`，AXI-Lite，基址 `0x40010000`；AXI GPIO `0x40000000`）。
- OpenOCD nightly `0.12.0+dev-gcb0c224`（`E:\Share\env-windows\openocd-nightly\bin\openocd.exe`）能连上、reset/halt/单步/硬件断点/读写 SRAM/flash probe 全部正常。
- 20 KiB SRAM：读 16.2 ms（1.27 MB/s），写 13.9 ms（1.47 MB/s）；128 KiB flash 读 98–99 ms（1.32 MB/s）。
- 固件：`firmware/xusbps_daplink`，`DAP_PACKET_SIZE=4096`、`DAP_PACKET_COUNT=16`，O3 构建。

**不能用的/待办：**

- `adapter speed` 无效，SWCLK 固定 50 MHz（详见瓶颈分析）。
- LA 目前采不到任何跳变（见第七节）。
- CDC 通道没有接 DAP 协议（DAPLink 标准里 CDC 只做串口，不影响调试）。

## 二、必须知道的三个坑

### 1. 上电后必须先用 JTAG 配 bitstream

板子启动时 PL 是空的，只下 ELF 会让 `DAP_Setup()` 写不存在的寄存器，OpenOCD 连不上（`Cannot access FPGA: Bitstream is not programmed`）。

```powershell
python tools\run_xsct.py tools\download_dap_fpga.tcl `
  build\xusbps_daplink\O3\xusbps_daplink.elf build\bitstream\system_wrapper.bit
```

顺序：`rst -system → ps7_init → ps7_post_config → fpga -f *.bit → rst -processor → dow → con`。
bitstream 来源：`E:\Share\github\ZYNQ7020_YuanZi\ZYNQ_DAPLINK_RTL_100TO50MHz\...\impl_1\system_wrapper.bit`，已复制到 `build/bitstream/`（SHA-256 `C0438D83…E521`）。本次没有改 RTL、没有重新综合。

### 2. 4096B 包只配 OpenOCD master

- OpenOCD ≤ v0.12 用 `DAP_Transfer`（8 位 count），4096B 包时 `N=(4096-4)/5=818` 溢出成 50，报 `transfer count mismatch`。老 OpenOCD 必须用 `DAP_PACKET_SIZE=1024`。
- nightly/master 用 `DAP_TransferBlock`（16 位 count）+ 异步 bulk，4096 正常。日志：`Packet Size = 4096`、`Packet Count = 16`。

### 3. `verify_image` 会占用 0x20000000

`stm32f1x.cfg` 默认 `-work-area-phys 0x20000000 -work-area-size 0x1000`，`verify_image` 的 CRC 算法会下载到那里执行，把该区域改掉，校验必挂。验证 SRAM 用 `dump_image` + 主机比较，别用 `verify_image`。

## 三、固件结构与改动

`firmware/xusbps_daplink/`

| 文件 | 作用 |
|---|---|
| `xusbps_intr_example.c` | main、USB 端点配置、EP0/EP1-2(DAP)/EP3-4(CDC) 回调 |
| `dap_main.c` | DAP 请求/响应队列、`DAP_ExecuteCommand` 主循环、响应发送（含 ZLP） |
| `DAP/Source/DAP.c` | CMSIS-DAP 命令分发、SWD 传输、batch 块传输 |
| `DAP/Include/DAP_config.h` | 包大小、引脚、`SWD_CFG` 配置 |
| `lscript.ld` | OCM 代码/栈，DDR 放 bss、`.dap_debug`、`.dap_trace` |

本次为了打通和测速做的固件改动（都在源码里）：

1. **`DAP_PACKET_SIZE` 4096**（`DAP_config.h`）。
2. **块传输内部分段**（`DAP.c` `DAP_SWD_TransferBlock`）：读 1000 字/段、写 500 字/段，不再因为 `rsp_words > 1024` 回退到逐 word 的 legacy 路径。统计计数 `xfer_block_legacy_depth` 现在恒为 0。
3. **整 512 倍数响应加 ZLP**（`dap_main.c` `dap_start_response`）：否则 255 字块读（响应 1024B）会卡 3 秒超时。
4. **时序 trace**（`dap_main.c`，测量用，建议保留到优化结束）：事件写 `0x3F000000` 的非缓存区，格式见第六节。

## 四、工具清单

| 工具 | 用途 |
|---|---|
| `tools/build_xusbps_daplink.py --opt 3` | 构建，产物 `build/xusbps_daplink/O3/xusbps_daplink.elf` |
| `tools/download_dap_fpga.tcl` | 配 bitstream + 下 ELF（必须用这个） |
| `tools/openocd_dap.cfg` | `adapter driver cmsis-dap` + SWD + `stm32f1x.cfg` |
| `tools/dap_sram_bench20.tcl` | 20 KiB dump/load 计时（OpenOCD 内） |
| `tools/dap_block_1023.py` | 裸块读 1023 字验证（含分段边界） |
| `tools/dap_block_timing.py` | 裸块读 255/500/1000 字计时 |
| `tools/dap_trace_analyze.py` / `dap_trace_blocks.py` | 解析固件时序 trace |
| `tools/read_dap_stats.tcl` | 读 `DAP_SWD_Stats`（batch/legacy 计数） |
| `tools/la/kingst_la.py` | LA 采集/解码（见第七节） |

OpenOCD 命令模板：

```powershell
& 'E:\Share\env-windows\openocd-nightly\bin\openocd.exe' `
  -s 'E:\Share\env-windows\openocd-nightly\share\openocd\scripts' `
  -f tools\openocd_dap.cfg -c "init" -c "reset halt" -c "reg pc" -c "exit"
```

（旧版 OpenOCD 的 scripts 在 `E:\Share\env-windows\rtt-debugger-support-package-0.4.0\bin\scripts`。）

## 五、性能瓶颈分析（本次实测）

### 5.1 总体

| 项目 | 数值 |
|---|---:|
| 20 KiB SRAM 读 | 16.2 ms，1.27 MB/s |
| 20 KiB SRAM 写 | 13.9 ms，1.47 MB/s |
| 128 KiB flash 读 | 98–99 ms，1.32 MB/s |
| 1024B 包 + 老 OpenOCD 对照 | 读/写均约 1.14 MB/s |

4096 + 异步 + 块传输只比老组合快 11%（读）/29%（写）。

### 5.2 固件 trace 数据（3 次 20 KiB dump，612 条事件）

每个 `DAP_TransferBlock`（0x06，OpenOCD 发 770 字/包，响应 3084B）：

| 阶段 | 时间 |
|---|---:|
| OUT 完成 → 主循环开始 EXEC（队列等待，多数与上一条命令重叠） | ~570 µs |
| EXEC（batch 引擎跑 SWD） | **2103 µs** |
| DONE → 提交 IN 响应 | 1.7 µs |
| 3084B 响应在 USB 线上的时间（提交→完成） | **88 µs（≈35 MB/s）** |
| IN 完成 → 主机发下一条 OUT | ~327 µs（被 OpenOCD 的 4 笔流水重叠） |
| 单包 OUT→IN 提交合计 | **2676 µs** |

- SWD batch：770 字 / 2103 µs = **2.73 µs/字** ≈ 1.47 MB/s。50 MHz SWCLK、每字约 45 bit 的理论值是 0.9 µs/字，实际慢 3 倍。
- 同一次 trace 里 `DAP_Transfer`（0x05）共 118 条，合计 11.16 ms，占 EXEC 总时间 26%；这些是 OpenOCD 的寄存器/小批量访问，无法完全避免。
- 按 3 次 dump 的墙钟 48.6 ms 算：0x06 EXEC 31.5 ms + 0x05 EXEC 11.2 ms = 42.7 ms，**SWD 执行占 88%**；USB 线上传输 + 主机调度只占约 12%。

### 5.3 LA 实测（2026-10-25 手工接线后）

Kingst MIPI16，500 MHz 采样，1 ms 窗口（`results/daplink/la/manual_1ms.csv`），SWD 解码结果：

- **SWCLK = 54 MHz**（周期中位数 18.5 ns，min 14 / max 26 ns）。
- 每读一个 AP word 实际要 **3 笔事务**：`WAIT → WAIT → OK`。
  - WAIT 事务 13 个时钟（≈240 ns），OK 事务 47 个时钟（≈870 ns，含 32 位数据）。
  - 1 ms 窗口内解码 40 笔：13 笔 OK、26 笔 WAIT、1 笔 FAULT，**WAIT:OK = 2:1**。
- 每字周期约 **2.45 µs**：时钟时间约 1.35 µs + **事务间空隙约 1.1 µs（45%）**。
- 空隙主要来自 RTL 每笔事务之间的 turnaround/idle 和 WAIT 重试间隔，不是 USB。

### 5.4 结论（更新）

1. **SWD 协议本身正确**，数据校验全对；但目标 F103 在 54 MHz 下每字要回 2 个 WAIT，等于每字多花 2 笔事务。
2. **RTL 事务间空隙占了 45%**：每字 2.45 µs 里只有 1.35 µs 在打时钟。优化空间在这：
   - 减少 WAIT 重试之间的 idle/turnaround；
   - 修慢时钟路径，找“WAIT 更少、周期更短”的最优频点（F103 的 SWD 上限通常 10–18 MHz，但 54 MHz+2 WAIT 目前仍比 12 MHz+0 WAIT 快）；
   - 换更快目标才能看出 DAP 的真实上限。
3. **USB 不是瓶颈**：3084B 响应线上 88 µs（35 MB/s），主机周转 ~330 µs，且被 4 笔流水重叠；墙钟里 SWD 执行占 88%。

### 5.5 `adapter speed` 试验（已回退）

在 `DAP_SWJ_Clock()` 里按 `delay_fast = 50MHz/clock - 1` 写 `SWD_CFG`：

- 20–50 MHz：能连、能读写；
- ≤15 MHz：`Error connecting DP: cannot read IDR`，运行中降速也会立刻失联。

说明 RTL 慢时钟路径（turnaround/idle 计数或 SWDIO 采样）有问题，已回退成固定 50 MHz。要修得先看 `swd_core.v` 的 `step_tick`/`idle_cnt` 时序。

## 六、固件 trace 格式（优化时继续用）

- 区域：`0x3F000000`（1 MiB，`Xil_SetTlbAttributes(..., NORM_NONCACHE)`）。
- `0x3F000000`：`dap_trace_count`；`0x3F000004`：`dap_trace_hz`（实测 333,333,436 ≈ 333.33 MHz，3 ns/tick）；`0x3F000040` 起是条目。
- 每条 4 字：`lo, hi, ev, arg`，时间 = `((hi<<32)|lo) / hz` 秒。
- 事件：`1=USB OUT(arg=长度)`、`2=EXEC 开始(arg=命令)`、`3=EXEC 结束(arg=响应长度)`、`4=提交 IN(arg=长度)`。
- 读取：`tools/dump_dap_trace.tcl` 把 16388 字 dump 到 `results/daplink/dap_trace.bin`，再跑 `tools/dap_trace_analyze.py` / `dap_trace_blocks.py`。

## 七、LA 使用现状（已可用）

完整操作流程见 [LA使用说明.md](LA使用说明.md)（接线、GUI 设置、socket 采集、窗口导出、分析脚本、常见问题）。

- 当前 LA 是 **Kingst MIPI16**（`KingstVIS` 标题栏：`MIPI16 已连接`），socket 在 23367。
- 注意：`vis.config` 里 MIPI16 的 `<chnEnable>` 初始是空的，需要手动打开通道（本次已备份并改成 16 通道全开：`vis.config.bak_dsh`）。
- 手工接好 SWCLK→CH0、SWDIO→CH1 后，500 MHz 采样、1 ms 窗口即可稳定抓到：
  - `results/daplink/la/manual_1ms.csv`（95655 行，5.8 MB）
  - 分析脚本：
    - `tools/la/la_activity.py`：找有跳变的通道、统计边沿密度
    - `tools/la/la_swd_timing.py`：SWCLK 周期、frame/burst 划分
    - `tools/la/la_swd_burst.py`：最大 burst 的每字间隔
    - `tools/la/la_swd_frames.py`：逐 frame 的 bit 流
    - `python tools/la/kingst_la.py decode <csv> --ch-clk 0 --ch-dio 1 --gap 0.2e-6`：正式 SWD 解码（ACK/数据/校验）
- 采集命令（需要 SWD 持续跑时配合 `tools/ocd_live_traffic.tcl`）：
  `python tools/la/la_capture_export.py --rate 500000000 --time 0.001 --out results/daplink/la/xxx.csv`
  大窗口导出容易 `save file failed`，用 `--time 0.5`～`1 ms` 的小窗口最稳。

## 八、下一步建议（按优先级）

1. **降低每字的事务开销**：现在每字 WAIT+WAIT+OK 三笔，事务间空隙约 1.1 µs（占每字 2.45 µs 的 45%）。先看 `swd_batch_engine.v`：
   - WAIT 重试之间能不能不插入额外 idle/turnaround；
   - `idle_cycles`/turnaround 能否在 batch 模式下压到最小。
2. **修慢时钟路径**，让 `adapter speed` 生效并扫频：F103 在 54 MHz 下要 2 个 WAIT，可能存在“27 MHz + 1 WAIT”或“18 MHz + 0 WAIT”的更快点；当前 ≤15 MHz 会失联，是 RTL 慢时钟时序问题。
3. 复核 0x05 小命令占比（118 条/3 次 dump），必要时把连续小传输也走 batch。
4. 换更快目标（F4/H7）复测，区分“DAP 上限”和“F103 上限”。
5. 可选：CDC 接成 DAPLink 串口透传，补齐标准 DAPLink 功能。

## 九、关键数字速查

```
bitstream sha256   C0438D83B0DA1F7A2AB267C886E1B81884479F2F4FFD1CA8D2934B611689E521
DAP_PACKET_SIZE    4096
DAP_PACKET_COUNT   16
SWD_CFG            0xA11 (turnaround=1, idle=1, clock_delay=5, delay_fast=0)
SWCLK              54 MHz 实测（周期 18.5 ns 中位数）
SWD 每字            WAIT + WAIT + OK = 13+13+47 时钟；周期约 2.45 us，其中时钟 1.35 us、空隙 1.1 us
SWD 批量            firmware EXEC 2.73 us/word（770 字块 2103 us）
USB 单包            3084B 响应线上 88 us（35 MB/s）；OUT->EXEC ~570 us（流水重叠）
block 包           770 words / 3084 B response (OpenOCD master)
```

更细的过程记录见 [纯DAPLink移植进度.md](<docs/纯DAPLink移植进度.md>) 和 [results/daplink/dap_bringup_summary.json](<results/daplink/dap_bringup_summary.json>)。
