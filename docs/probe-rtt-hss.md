# Probe RTT→CDC 与 RTL HSS

当前新增的 PL 拼包、RTT 自主读取和 CDMA→DDR 通路见 [PL→DDR 改造](probe-pl-ddr.md)。
下文的数据路径、性能及预编译验收表记录早期版本，不代表新增 RTL 的性能。

本功能在 `main`（`35f7cf6`）上创建的 `codex/probe-rtt-hss` 分支实现。
参考 `E:/superlinkPRO/firmware/application_5301/src/{rtt,scope,usb,api}` 的协议。
原 `prebuilt/zynqlink_packet.*` 保留原版本；本功能的已验收配对为
[`zynqlink_probe.bit`](../prebuilt/zynqlink_probe.bit) 与
[`zynqlink_probe.elf`](../prebuilt/zynqlink_probe.elf)。可直接加载，也可从源码重建。

## 数据路径

- RTT：PS 分段搜索 SEGGER RTT 控制块、读取选定的 up channel，使用现有 RTL
  TransferBlock + CDMA 路径搬运目标数据，经 CDC 输出。支持环形回绕、未对齐字节、
  1 KiB MEM-AP TAR 边界。CDC 队列满或 DTR 关闭时不继续消耗目标缓冲。
- HSS：PL 自主执行 24 MHz 时间轴的定时调度、AP0 内存读计划、WAIT 重试与完整样本
  FIFO。PS 只配置计划、提取变量字节并组装 HSS DEF/DATA/STAT USB 包。
- HSS 支持 1～8 个变量，宽度 1/2/4/8 字节、未对齐地址；按地址排序，最多展开成
  24 个对齐字地址。当前每个字用 TAR → posted DRW → RDBUFF，未做单字跨样本流水优化。
- RTT 和 HSS 互斥。实际 DAP 命令执行前，先等待当前采样完成并暂停采样；恢复主机的
  DP SELECT、AP0 CSW/TAR、FCLK、SWD CFG 和 DAP 软件状态，再执行 DAP。执行后恢复采样。
  批量 DAP_Transfer 中包含 SELECT 写入时走现有 scalar 路径，以跟踪主机的 SELECT。

RTT 数据先进入私有 USB 槽，成功回写 RdOff 后才发布给 USB。RdOff 写失败时保留该槽并
重试同一个偏移，不重读、不重复发布。USB 复位使整个会话失效；复位前已回写 RdOff、
尚未送达主机的数据不能恢复，不能把设备侧搬运计数当成主机无损接收证明。

## USB 布局（HS）

VID/PID 保持 `0D28:0204`，bcdDevice 升至 `1.01`。配置描述符 137 字节，4 个接口。

| 接口 | 用途 | 端点 |
|---|---|---|
| 0 / WinUSB | CMSIS-DAP v2 + HSS | DAP OUT `02`、DAP IN `81`、HSS IN `87`，Bulk，512 B |
| 1 | CDC ACM 控制 | 通知 IN `85`，Interrupt，64 B |
| 2 | CDC ACM 数据 | OUT `04`、IN `83`，Bulk，512 B |
| 3 | 自定义 HID | OUT `06`、IN `86`，Interrupt，64 B |

HSS 挂在已有 WinUSB 接口 0，所以保留原 Microsoft OS 2.0 / BOS 绑定。
HID usage page `FF00`、usage `1`，OUT report ID `1`，IN report ID `2`；含 ID 总长 64 B。
CDC 原端点无需改驱动；HID 使用系统 HID 驱动。

参考工程 HSS 固定使用 `83`，这里 `83` 已属于 CDC，因此 HSS 使用 `87`。
现有上位机若硬编码 `83`，必须调整 HSS 端点选择；随分支提供的工具已使用 `87`。
本分支没有修改 `E:/superlinkPRO` 的网页源码。

## 控制协议

所有 HID 报文：`report_id, length, command, payload...`。
`length` 包含 command，不包含 report ID 和 length 本身。状态响应：
`02, 50, command, signed_rc, 12×u32 little-endian, padding`。

| 命令 | 支持动作 |
|---|---|
| `10/11/13` | 型号、序列号、固件版本 |
| `31` RTT | 0 STOP，1 START(addr4,size4,channel1)，2 STATUS，3 AUTO，7 CONFIG(hz4,chunk2,flags1,delay1)，10 TARGET(0=ARM) |
| `32` HSS | 0 STOP，1 START，2 STATUS，3 CLOCK(hz4)，7 CONFIG_US，10 CONFIG_TICKS，11 METRICS |

HSS 配置 payload（动作之后）：`period:u32, flags:u8, nvars:u8,
n×{addr:u32,size:u8,type:u8}`，与参考工程相同。类型码 0～7 原样进入 DEF。
配置中非法宽度/地址/变量数会整包拒绝，停止状态下清空计划，避免下次 START 使用旧计划。

- v1：周期与 DATA 时间戳单位 µs；最小周期 2 µs，最大 1 s。
- v2：周期与时间戳单位 24 MHz tick；最小 48 tick，最大 24000000 tick；u32 回绕。
- HSS 时间戳表示该样本的名义调度时刻，各变量依次读取。采样来不及时跳过 deadline，
  累加 skipped；不会把间断样本挤成连续时间轴。不同时间段拆成不同 DATA 包。
- FIFO 满时跳过采样并计数；PS/USB 都不覆盖已发布的样本。FIFO 为单写口 LUT RAM，16 个样本，USB 每类
  队列 8 槽，HSS 包长 512 B。稀疏采样的部分 DATA 包约 10 ms flush 一次。
- HSS CLOCK 允许 15～60 MHz，并受固件构建时的已验证时序上限约束；配置时需停止 HSS。
  默认使用本板已验证的 50 MHz。RTT CONFIG 的时钟范围 1～60 MHz、块长上限 1024 B；
  有待回写 RdOff 时拒绝改配置。当前 F103CB 的 10/20 MHz 分频初始化路径存在既有失败，
  main 预编译版本同样如此；本分支的实板验收使用 50 MHz，不宣称全部频点均已验收。
- HSS STOP 为排空当前采样/FIFO 的优雅停止。返回 `-7` 时仍需读取 `87`；主循环继续
  排空并自动完成停止。重新 START 前需读完上一个 HSS 会话的 USB 队列。
- 返回码：0 成功，-1 时钟失败，-2 SWD 初始化失败，-3 无计划/未找到控制块，
  -4 SWD 访问失败，-6 配置非法，-7 忙/需要排空队列，-9 不支持，-10 bitstream 缺少采样器。
- 不支持参考工程的 RISC-V/JTAG、触发、raw DAP、peek 和 benchmark 动作，明确返回错误。
  HSS DISCARD(bit1) 支持；其余已接受的 ARM 提示位不改变 RTL 的调度方式。

STATUS 与 METRICS 保持参考工程的基本字段布局。METRICS word3 是已由 PS 取出并组包的
样本数，word4 是 RTL skipped；word5 为零（USB 背压统一体现在 RTL skipped 中），
word7 是 DAP 让路次数。DAP 暂停造成的时间间隔不算 RTL skipped。
word8 统计 USB DMA 完成，不能证明上位机实际保存了数据。

## RTL 寄存器

SWD 控制器原地址不变，基址 `40010000`；FEATURES(`4C`) 为 `44500003`，bit1 表示采样器。

| 偏移 | 读 | 写（配置须停止且当前样本结束） |
|---|---|---|
| `60` | 高16位 `4853`；低位 enable/count | bit0 enable；bit1 清 FIFO/计数；bits12:8 字地址数1～24 |
| `64` | bit0 enabled；bit1 finishing；bit4 fault；高16位完整样本数 | — |
| `68` | 计划索引 | 0～23 |
| `6C` | 所选对齐字地址 | 对齐字地址 |
| `70` | 周期（24 MHz tick） | 48～24000000 |
| `74` | FIFO：timestamp、随后 count 个数据字；最后一字释放槽 | — |
| `78` | 当前 24 MHz 时间戳 | 实际 FCLK Hz（至少24 MHz） |
| `7C` | skipped 计数 | 设置时间戳；PS 在重新启用前与全局 timer 对时 |

STOP 清 enable 后继续完成当前样本。WAIT 最多重试64次，FAULT/奇偶错误使当前样本作废并
停机；单次 SWD watchdog 超时会置 fault，保留忙状态直到核心退出或 PS 复位执行引擎。
FIFO 只发布完整样本。异步 USB reset 会停止采样、作废队列，并复位执行状态机。

## 构建与使用

直接加载已验收配对（Zynq JTAG RAM 加载，不写目标 Flash）：

```powershell
python tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/zynqlink_probe.elf prebuilt/zynqlink_probe.bit
```

`prebuilt/probe_build_manifest.json` 记录 RTL/固件源文件和 bit/ELF 的 SHA256。
固件限制 SWCLK≤60 MHz。最终 routed FCLK 上限 128571429 Hz，setup +0.227 ns、
hold +0.040 ns；bitgen/DRC 通过。原 packet 配对未改动。

源码构建沿用 README 的 BSP 和 Vivado 流程；增量构建也会添加新 RTL 源文件。

```powershell
python tools/run_vivado.py -mode batch -nojournal -log build/probe_fpga_build.log -source fpga/build_dma.tcl
python tools/build_xusbps_daplink.py --project xusbps_daplink_dma --bsp <BSP目录>
python tools/run_xsct.py tools/download_dap_fpga.tcl build/xusbps_daplink_dma/O3/xusbps_daplink_dma.elf build/fpga_dma_global/system_wrapper.bit

python tools/probe_stream.py info
python tools/probe_stream.py rtt --address 0x20000000 --size 65536 --port COM33 --seconds 3 --output rtt.bin
python tools/probe_stream.py hss --var 0x20000020:4:4 --period 100 --seconds 3 --output capture.hss
python tools/probe_stream.py hss --var 0x20000020:4:4 --ticks --period 240 --seconds 3 --output capture-v2.hss
```

COM 号应使用本机枚举值。HSS 工具保留 DEF/DATA/STAT 原始包，按参考工程 HSS 协议解析即可。
RTT/HSS 的 SWD 初始化不停止目标 CPU；目标固件不需要加入 HSS 代码。

## 验证

```powershell
python tools/test_probe_host.py
python tools/test_probe_rtl.py
python tools/run_vivado.py -mode batch -nojournal -log build/probe_ram_synth.log -source fpga/synth_probe_sample.tcl
python tools/test_packet_engine.py
python tools/test_dap_transport.py --cc clang
python tools/run_cortexm0_sim.py --build --tag probe-sampler +sampler
python tools/test_probe_board.py --services both --seconds 2 --output results/probe_board.json
```

主机测试编译生产 C，覆盖 HID/描述符、8个未对齐宽变量、HSS缺拍分包、RTT回绕与RdOff重试、
USB队列背压/ZLP/reset、AP与时钟上下文恢复。独立 RTL 测试覆盖 posted read、WAIT、
FAULT、parity、watchdog、时间戳回绕、停止和 FIFO 满。

XSim 使用本机已有 ARM DesignStart Cortex-M0 模型，验证真实 MEM-AP 采样、16样本FIFO、
竞争启动屏蔽与停采后的 DAP 读取。ARM 模型不复制进仓库。

实板验收为 F103CB、HCLK 96 MHz、SWCLK 50 MHz。目标原本处于 halt，测试维持该状态，
未复位、未改 RCC、未编程目标 Flash。

| 项目 | 结果 |
|---|---|
| USB/HID | 4 接口、端点布局正确；100次状态查询全部成功，平均约2 ms |
| RTT→CDC | 21轮、19965 B逐字节一致；覆盖回绕、1/511/512/1023/1024/1537/2047 B；读/写错误0 |
| 探针独立初始化 | USB重新配置后让DAP断开，由HID启动RTT；探针自行SWJ激活和搜索控制块，通过 |
| HSS v1 单变量 | 20076个样本，逐字节一致 |
| HSS v2 单变量 | 20062个样本，逐字节一致 |
| HSS v2 8变量 | 20062个样本，30 B/样本逐字节一致；含未对齐8 B及1 KiB边界 |
| DAP/HSS 仲裁 | 每组8次不重写TAR的连续DRW，24次均得到正确相邻字；采样SWD错误0 |
| USB背压 | 每组故意停读50 ms，skipped约489～495；恢复读取及优雅停止通过 |
| 目标SRAM恢复 | 4 KiB临时夹具窗口恢复SHA256完全一致 |
| 普通DAP回归 | 20 KiB线性API、单会话10轮，读3.834 / 写3.777 MB/s；完整20 KiB恢复，RCC不变 |

HSS各组约2秒接收窗口，周期100 µs（v2为2400 ticks）；这是功能与完整性验收，
没有把主机写入RTT夹具的速度当成RTT峰值，也没有据此宣称HSS最高采样率。
采样模块独立综合为1508 LUT（其中352为LUT RAM）、1154 FF；脚本会拒绝FIFO退化为寄存器阵列。

详细帧数、计数器、产物哈希、时序和恢复记录：
[`20261027-probe-rtt-hss.json`](measurements/20261027-probe-rtt-hss.json)。
