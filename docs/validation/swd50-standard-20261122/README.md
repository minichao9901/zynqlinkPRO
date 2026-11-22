# 50 MHz 标准 CMSIS-DAP 与 RTT→CDC 共用 SWD 批次队列

F103ZE CDC48 经临时 SRAM 夹具运行 HCLK128。实际 SWCLK 由 PS 时钟树和 SelectIO 分频寄存器折算为 49,999,999.5 Hz。两端使用同一 tap 8、slot 22、idle 0。基准是 `prebuilt/selectio-swd50`，由 HS3 临时加载并核对 OCM。标准 SRAM 使用 2 KiB `TransferBlock`、PC 深度 32、每方向 256 块、三次中位数。RTT 走 J7 CDC 串口，目标 8 KiB 环、每次最多搬运 2 KiB。

## 实现

- 标准 CMSIS-DAP 的适用 DRW 块使用现有 SelectIO 队列，逐笔请求、ACK、WAIT、奇偶校验和结果缓存均在 100 MHz `quad_clk` 域执行。块中保留主机 AP/TAR 状态。读端先处理 posted pipeline，再通过 RDBUFF 取最后一字。每至多 256 字完成一次，DMA 与相邻块的引脚事务重叠。没有重放已经提交的 AP 写入。
- RTT→CDC 先用原所有权逻辑保存调试 AP 上下文，再借用同一队列。描述符、负载与 RdOff 均经过批次执行器。数据已进入 CDC 队列的 DDR 槽且 RdOff 写入确认后才发布。STOP 或 DAP 接管时，先让队列空闲、切回实时路径，再恢复 AP 上下文。正在转发时，其他原生内存请求返回忙。
- 使用现有 bitstream 的队列和引脚复用。FCLK0 继续驱动 PS/PL AXI 与 ETM DDR 入口。调试命令和结果按批跨域，SelectIO 内每笔 AP 可在前一笔确认后直接接续。

## 实板迭代

第一版将 RTT 的读操作逐段接到批次执行器，仍在每页之间切回实时路径写 TAR。SRAM 已提升，RTT 到 PC 约 3.51 MB/s。改为持续借用同一队列后的初版触发 CDC STOP 仲裁错误。经 Windows 重新枚举 J7 后已按备份恢复目标 SRAM、RCC 和核心状态。之后修正了 STOP、调试器接管和 IF4 的队列所有权检查。数字台架用 Cortex-M3 模型和 SelectIO 原语验证了实时访问与队列访问之间的切换、RAM 数据、TAR 与 posted read，模型单次 WAIT 按正常重试处理。

## 实板结果

| 50 MHz SWD 到 PC | 同板 HCLK128 原配对 | 同板 HCLK128 共用队列 | 历史 HCLK96，2026-10-31 |
|---|---:|---:|---:|
| CMSIS-DAP SRAM 读，MB/s | 3.741 | **3.844** | 4.047 |
| CMSIS-DAP SRAM 写，MB/s | 3.744 | **3.871** | 3.983 |
| RTT→CDC，MB/s | 3.722 | **3.811** | 3.995 |

RTT 基准用历史两个 3 秒窗口，最终配对用两个 60 秒窗口，表中分别取中位值。最终两轮总计逐字核对 463,390,712 B，包含窗口两端的预热和尾部排空，探针传输错误为零。RTT 运行中物理读回 SWD 队列 timing `0x1658`。CMSIS-DAP 运行后读回队列完成状态 `0x103`，即 259 条描述符，其中 256 个 DRW 加首尾三条；基准同寄存器为零。另做了一轮 RTT 持续运行中的标准 DAP CPUID 读取，得到 `0x411fc231`，CDC 后续序列完整。两种性能窗口的目标 SRAM、时钟与运行状态均通过恢复复核。[基准 SRAM](baseline-cmsis.json) · [基准 RTT](baseline-rtt.json) · [最终 SRAM](shared-cmsis.json) · [最终 RTT](shared-rtt.json) · [并行接管](handoff-rtt.json) · [最终 OCM](shared-load.json)

原生路径附加回归的首次尝试在启动 HCLK128 夹具时进入异常，性能窗口尚未开始，目标现场恢复成功。同配对重试通过原生读、写和 RTT 队列。该故障证据单列，原因待定位。[启动异常](native-preflight-target.json) · [原生内存回归](native-regression-memory.json) · [原生 RTT 回归](native-regression-rtt.json)

## 复测入口

```powershell
$pair = 'prebuilt/selectio-swd50-standard'
python -X utf8 toolbox.py probe-load --bit "$pair/probe.bit" --zynq-elf "$pair/application.elf" --ps-init "$pair/ps7_init.tcl" --out build/swd50-standard-load
python -X utf8 tools/selectio_f103_clock_accept.py --pair $pair --hclk-mhz 128 --only historical --swd-slot 22 --rtt-cdc-seconds 60 --rtt-cdc-rounds 2 --out build/swd50-standard-check --execute
```

## 时钟统一边界

CDMA、载荷 BRAM 和与之相连的 GP/HP 接口可以作为单独的调试子系统接到 100 MHz `quad_clk`。32 位每拍理论数据量为 400 MB/s，仍需测实际突发延迟。PS 端与 DDR 控制器内部的时钟域、ETM 输入时钟域仍有独立边界。若进一步迁移整个 AXI 体系，需要为 `quad_clk` 建立可从 PS 启动的时钟和复位链，并重新核对兼容低速配置、计时器和 ETM 写入。两阶段对应不同的 A/B，本文只验收逐笔调度迁移。
