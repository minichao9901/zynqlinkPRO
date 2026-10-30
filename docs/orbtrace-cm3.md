# ORBTrace 并行 ETM 接收移植：20261029 初始 CM3 仿真阶段

> 本文保留最初的仿真阶段结果。后续板级、PS USB、Web 和新 CM3 AXI 验证见
> [集成工作记录](orbtrace-integration-progress.md) 与 [USB/PL 接口](orbtrace-usb.md)。

本轮按“先用 CM3 model 仿真”实施，工作分支 `codex/orbtrace-cm3` 从本地 main
`dc95b99` 创建，未带入主目录的未提交改动。本轮不是硬件发布或合并验收；尚未接入
BD、物理 trace 引脚、PS 搬运和 USB，也没有生成/验收本次 bit/ELF 配对。
已有 `prebuilt/` 未作为本次构建产物使用。

## 实现

- `fpga/rtl/orbtrace_traceif.v`：移植 ORBTrace 的并行 DDR 接收、双边沿同步、
  full/short sync 和 16 字节 TPIU 帧组装。补齐复位，禁止同步前输出未初始化帧。
- `orbtrace_parallel.v`：Zynq-7 `IDDR(OPPOSITE_EDGE)` 采样，接收域与系统域各自
  同步释放复位，帧 FIFO 跨时钟传递，输出 `data[7:0]`、`channel[6:0]`、ready/valid。
- `orbtrace_frame_fifo.v`：8 帧异步 FIFO，Gray 指针与两级同步。TRACE 无法被
  接收端反压；满时置 sticky `overflow`，该次捕获必须判无效并复位后重采。
- `orbtrace_tpiu_demux.v`：恢复 auxiliary byte 中的 LSB、剥离 ID、处理即时和延迟
  source ID 切换、过滤 channel 0；输出停顿时保持数据稳定。
- `cm3_target.sv`：引出真实 DesignStart 的 TRACECLK/TRACEDATA/TRCENA；默认
  `TRACE_LEVEL=0`，`tb_cm3_etm` 显式选 `TRACE_LVL=2`，启用 ITM/DWT/ETM。
- `tb_cm3_etm.sv`：复用现有 PL SWD controller，通过真实 SWD / MEM-AP 配置
  CoreSight；没有 force ETM 输出或用软件波形替代 CM3 trace。

ORBTrace 固定上游提交 `e416cd5b074fc725a04cf6b877d458e2074467ae`，来源及 BSD
许可证保留于 `third_party/orbtrace/`。上游 Python 解帧模块原样保留，作为独立 golden
reference，未放入 Vivado 构建。

## CM3 用例

CODE AXI SRAM 提供复位向量和以下实际 Thumb 指令，CM3 持续执行：

```asm
0x100: movs r0, #0
0x102: adds r0, #1
0x104: cmp  r0, #7
0x106: bne  0x102
0x108: b    0x100
```

ETM 配置参考只读的 `E:/superlinkPRO/etm/tools/f103ze_etm.py`，参考仓库 HEAD
`be75311236da2665a2edc54b9b4d4561f0219456`：DEMCR.TRCENA、ETM 编程态握手、
TEEVR=0x6f、TECR1=0、FFLR=0、TRACEIDR=2、TPIU SPPR=0、CSPSR=8、FFCR=2。
STM32 DBGMCU 的引脚路由寄存器不存在于 DesignStart 中，因此没有照搬该寄存器。
接收器保持复位直到 TPIU 配置完成。

真实模型读回 ETMIDR=`0x4114f253`、ETMCCER=`0x18541800`、运行时 ETMCR=`0x810`，
不是直接套用 F103ZE 的解码配置。具体值同时记录在每次捕获的 JSON 中。

## 复现

需要 Vivado/XSim 2018.3、Icarus Verilog、Python 和 `amaranth==0.5.8`。
DesignStart 加密 RTL 不随本仓库分发，需合法取得，传入现有本机路径：

```powershell
python -m pip install amaranth==0.5.8
python tools/run_orbtrace_sim.py `
  --rtl E:/zynqlinkPRO/reference/cortex_m3_on_xc7a100t/cm3_core/Arm_ipi_repository/CM3DbgAXI/rtl `
  --decoder E:/superlinkPRO/etm/build-native/etm_decode.exe
```

`--decoder` 可选；不传时只检查引脚测试与上游逐字节一致，不宣称指令解码验收。
该可执行文件是 superlinkPRO 已有的 OpenCSD 1.8.3 解码器，只读调用，未改动参考仓库。
脚本不连接探针、板卡或 USB。单独调试 CM3：

```powershell
python tools/run_cm3_sim.py --top tb_cm3_etm --rtl <CM3DbgAXI/rtl>
```

默认输出 `build/orbtrace_sim/`，包含 XSim 日志、原始 TPIU 帧、ETM 字节、解码 JSONL、
解码配置和 `acceptance.json`。runner 按源文件与加密模型指纹复用成功的 snapshot，
源码变化或上次编译失败后自动重编译。精简证据归档在 `docs/validation/orbtrace-cm3-20261029/`。

## 仿真结果

两档 CM3 仿真的 FCLK 都为 120 MHz，SWD TCK 为 60 MHz，返回路径延迟为 16 ns。
这些是仿真时钟参数，不是实板测量。两档都是 4 位 DDR 接收。

| CM3 HCLK | 接收端 | TPIU 帧 | ETM 字节 | OpenCSD 指令范围 |
|---|---|---:|---:|---:|
| 100 MHz | 连续 ready | 277 | 1955 | 22101 |
| 160 MHz | 每 11 个系统周期停顿 3 周期 | 442 | 3120 | 35292 |

两档均无 FIFO 溢出、无未知字节、source ID 全为 2；与原版 ORBTrace 解帧逐字节一致。
OpenCSD `lastErrorCode=0`，检查恢复的每条指令与下一条 PC 是否符合上述循环，包含
条件分支执行/不执行两条路径，覆盖全部五条指令。

ETM 字节流 SHA-256：

- 100 MHz：`7fe223bdbbb828e649f822f63e431aaa351f08cfa0b78c973c47df5fcd461594`
- 160 MHz + stalls：`588a7014c3fc0ce36032f4193508f86bdccbcfb553aa1f01d4597ce4c4fcbd62`

独立物理引脚测试覆盖 1/2/4 位 × 两种 DDR 对齐共 6 档，逐字节记分检查同步前噪声、
帧内 short sync、full sync 丢弃残帧、auxiliary LSB、即时/延迟 source ID、channel 0、
ready 停顿、FIFO 溢出显式上报以及复位恢复。原有 CM3 SWD SRAM 读写另作回归。

## 边界和后续硬件工作

本轮 CM3 通过项仅为 4 位 DDR。探索 CSPSR=2 的窄位宽模型用例出现 source ID 127，
尚未定位模型引脚映射/采样关系；不将其算作通过。RTL 的 1/2 位通过项仅来自独立物理
刺激测试，不能替代真实 CM3 或目标板验收。当前没有 SWO、ORBFlow/COBS 或 ORBTrace
USB 兼容性声明。

硬件集成前需确定 TRACECLK 与四根 TRACEDATA 的 Zynq 引脚、输入约束、时钟布线和
采样裕量；补 PS 可读缓冲/传输接口与主机捕获路径。`width` 必须在同一次捕获期间固定；
切换宽度、复位或发生 overflow 后须丢弃此前半帧并重新同步。当前 FIFO 状态跨域信号
仅供捕获状态判断，不能当作逐帧有效性标志；捕获结束仍需检查 overflow。

按根目录 AGENTS.md，硬件交付/合并前还须从本次源码构建 bit/ELF，记录源码提交、构建
选项、两文件 SHA-256、实现时序、实际 FCLK/TCK 和 F103ZE 上板验收，并把实际加载验收
的配对纳入 Git。本轮没有这些产物或结果，不把仿真通过等同于硬件交付完成。
