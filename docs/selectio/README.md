# J7 SelectIO 多协议探针 CLI

这套固件在同一块 Zynq-7020 上提供 CMSIS-DAP、RTT、变量采样、四线 SPI、串口、SWO 和四位并行 ETM。命令从本工作树根目录执行，输出使用新路径。融合通用参考为 [RAW4 ABI 2](../../prebuilt/selectio-usb-split-raw4-20261123/README.md)。F103ZE CDC48 的融合回归使用[已验收 ABI 1 配对](../../prebuilt/selectio-spi-cdc-rx-guard-20261123/README.md)。按[用例清单](../../acceptance-cases.json)选择配对及目标 ELF，并以各自清单核对 bit、PS ELF、初始化脚本和验证范围。Windows 主机依赖、Vivado/SDK 和 OpenOCD 的安装位置见[依赖说明](../dependencies.md)。标准串口示例需要 pyserial，验收脚本另用 NumPy 校验连续样本。

## 架构和引脚

PS 负责 USB、会话、DMA、错误恢复和 RTT/变量并发调度。PL 的固定事务引擎负责 TAP 状态转换、APACC、SWD 换向、ACK、批量传输、串行编解码和采样。主机可以提交有限长度的事务描述符，PS 可以重用并修补描述符。逐边沿时序由 SelectIO 产生。这个实现不需要通用微码解释器。ETM 延用主线的独立采集时钟、DDR 窗口、USB 下载及离线解码。

```mermaid
flowchart LR
    Host[PC CLI / CMSIS-DAP / CDC] <--> USB[Zynq PS USB 2.0 HS]
    USB <--> PS[PS 会话、错误恢复和 DDR 队列]
    PS <--> DMA[CDMA 与分组 BRAM]
    DMA <--> AP[JTAG / SWD 批量事务]
    PS <--> Live[CMSIS-DAP / RTT / HSS 引擎]
    AP <--> PHY[共享 SelectIO 引脚]
    Live <--> PHY
    PS <--> AUX[SPI / UART / Manchester]
    PHY <--> AUX
    ETM[四位 ETM 输入] --> DDR[主线 ETM DDR 采集窗口]
    DDR --> USB
```

高速内存路径在 GP1 配置队列，CDMA 对每种协议的四个 TX/RX bank 搬运数据。标准 DAP、独立 RTT 和独立变量采样复用实时 AP 事务通道；并发采集由 PS 在单次 AP 会话内安排采样和有界的 RTT 读取。串口接收的 FPGA 环有 64 KiB，PS 在前台转入 2 MiB DDR。完整 SWO 缓冲容量以 IF0 的 DAP_Info 或 IF4 的 info 为准。

| J7 针号 | Zynq 球位 | 调试 | SPI 主机 | 串行 |
|---|---|---|---|---|
| 29 | L15 | TCK / SWCLK | SCK | — |
| 31 | L16 | TMS / SWDIO | CS，低有效 | — |
| 25 | M15 | TDI | MOSI | 探针 TX，接目标 RX |
| 27 | L14 | TDO | MISO | 探针 RX，接目标 UART TX / CoreSight SWO |
| 41、39、37、35、33 | J16、K16、M18、M17、L17 | TRACECLK、TRACED[0..3] | — | ETM |

J7 信号使用 LVCMOS33，探针与目标共地。nSRST 在 J7-23，nTRST 在 J7-19。SWD 的时钟和数据只需 L15、L16，可与使用 L14 的被动监听共存。[J7 转接板引脚](https://github.com/minichao9901/zynqlinkPRO/blob/03b6a1dad8ee62aa7902b6bc37d0f0d9c3c3f451/docs/validation/j7-adapter-20261106/README.md)

JTAG 占用 TDI/TDO，SPI 切换时取得四根线的独占权。F103 的 PB3 可切换 JTDO 与 TRACESWO，PA15 用作 JTDI 或测试目标的串口接收。目标串口、ITM 和四位 ETM 各自需要正确的目标引脚配置。

## USB 接口分配

独立端点版保留标准 CMSIS-DAP、标准 SWO Bulk IN 和物理 CDC COM。原生 WinUSB 使用 IF3。控制、SRAM、RTT、J-Scope、ETM 和 SPI 分别使用 EP5–10。RTT 和 J-Scope 的 IN 队列独立，组合采集在同一个目标 AP 会话中调度。完整地址与 ABI 见 [原生 USB 协议](../selectio-native.md)。

`selectio info` 输出实际枚举和 `dedicated_pipes`。新配对的 SWO 命令默认使用标准 CMSIS-DAP，物理 UART 通过 `selectio com bind` 和系统串口读写。旧报告中的 MI_04、HID、RTT→CDC 和 EP87 上的 HSS 属于各自历史配对。

## 识别、临时加载及调试

独立端点版配对及 H743 验收入口见 [RAW4 配对说明](../../prebuilt/selectio-usb-split-raw4-20261123/README.md)。临时加载后，以 `selectio info` 中的 ABI 和枚举为准。

按本分支验收记录选择配对目录。`probe-load --pair` 按清单逐一核对 bit、Zynq ELF 和 PS 初始化 Tcl 的 SHA-256，在写入探针易失配置前检查占用，加载后核对 OCM。目标 MCU ELF 与探针 ELF 分开传入。

```powershell
$pair = 'prebuilt/selectio-usb-split-raw4-20261123'
python -X utf8 toolbox.py probe-load --pair $pair --dry-run
python -X utf8 toolbox.py probe-load --pair $pair --out build/my-load
python -X utf8 toolbox.py selectio --serial 12345678 info
python -X utf8 toolbox.py selectio usb-test --seconds 60
python -X utf8 toolbox.py selectio --help
```

info 同时显示实枚举接口、各端点、PS 固件 ABI、队列深度、原生块头大小和 PL 特性字。link_hz 是由真实参考寄存器换算的高速模式线速。兼容 DAP 使用不超过 10 MHz 的初始化档，显式请求 100 MHz 切换到专用 PHY。

下例的时隙值用于通过验证的特定版次。更换 bit 后按对应 manifest 选择 tap/slot。tap 是 SWDIO 或 TDO 的输入 IDELAY 档位，slot 选择反串化后的采样位置，idle 设置事务所用的额外空闲钟数。变频融合版的 SWD/JTAG slot 在 50 和 100 MHz 档间隔约 2.5 ns，在 72.727 MHz 档间隔约 3.4375 ns。下表列出当前配对的起始配置。换档时同时更新时钟、tap、slot 和 idle。校准顺序见 [精简性能用例](fusion-performance-cases.md#case-表)。

| 请求 MHz | 预计实际 MHz | SWD tap / slot / idle | JTAG tap / slot / idle |
|---:|---:|---|---|
| 50 | 50 | 8 / 24 / 0 | 16 / 28 / 17 |
| 73 | 72.727 | 8 / 22 / 0 | 16 / 28 / 25 |
| 100 | 100 | 8 / 25 / 2 | 16 / 28 / 33 |

F103 上电后的应用可能关闭完整 JTAG，使用 JTAG 前须确认目标的 AFIO 配置。示例先在 1 MHz 识别，再切到 `$clock` 指定的高速档。在一个终端启动 OpenOCD，在第二个终端运行 GDB。退出 GDB 可用 `detach`。

```powershell
$transport = 'swd'
$clock = 100000000
$adapterKHz = [int]($clock / 1000)
$tap = 8
$slot = 25
$idle = 2
# JTAG 对应参数
# $transport = 'jtag'; $tap = 16; $slot = 28; $idle = 33
python -X utf8 toolbox.py selectio profile --transport $transport --tap $tap --slot $slot --idle $idle
python -X utf8 toolbox.py selectio identify --transport $transport --clock 1000000
openocd -f interface/cmsis-dap.cfg -c "adapter serial 12345678" -c "transport select $transport" -f target/stm32f1x.cfg -c "adapter speed 1000" -c "init" -c "adapter speed $adapterKHz"
arm-none-eabi-gdb prebuilt/golden/f103ze-cdc48.elf -ex "target extended-remote localhost:3333"
```

CDC48 应用在启动时设置 SWJ_NOJTAG。可以在已核对该目标映像后，用仓库的 F103 JTAG 夹具临时开启完整 TAP，命令结束后恢复原应用的 SWJ 设置。数字 2 来自该固件源码。

```powershell
python -X utf8 tools/run_f103_jtag_fixture.py --serial 12345678 --swd-khz 1000 --run-during-child --restore-swj 2 --output build/jtag-identify-state.json -- python -X utf8 toolbox.py selectio identify --transport jtag --clock 100000000
```

运行独占的原生会话前退出占用接口的调试服务器。以下用 PowerShell 数组传递吞吐参数。读写地址和长度按 4 B 对齐，原生优化窗口为 F103 的 64 KiB SRAM。写示例把刚读出的文件写回，执行前确认区域由调用方独占。主机深度和 1 KiB TAR 分割由 CLI 管理。

```powershell
$link = @('--transport', $transport, '--clock', $clock, '--tap', $tap, '--slot', $slot, '--idle', $idle)
python -X utf8 toolbox.py selectio read @link --address 0x20008020 --bytes 4032 --out page.bin --queue-depth 4
python -X utf8 toolbox.py selectio write @link --address 0x20008020 --file page.bin --queue-depth 4
```

## RTT 和 J-Scope

变频融合配对在高速内存、RTT 和变量采样入口接受 50–100 MHz 的时钟请求。下列 A/B 命令使用候选 bit/ELF，F103ZE 保持 CDC48。50 MHz 示例的采样相位以实际配对为准。每次测试使用新的输出目录。

```powershell
# 以同一 SRAM 帧格式读写探针私有 DDR，逐项测纯 USB、队列深度和传输方向
python -X utf8 tools/selectio_transport_bench.py --serial 12345678 --seconds 10 --schedule sliding --out build/usb-sliding
python -X utf8 tools/selectio_transport_bench.py --serial 12345678 --seconds 10 --schedule grouped --out build/usb-grouped

# 真实目标 SRAM，先备份 16 KiB，分别计读、写、混合，最后恢复目标
python -X utf8 tools/selectio_f103_fixture.py --serial 12345678 --size 16384 --out build/swd50-state --execute -- python -X utf8 tools/selectio_pipeline_bench.py --transport swd --clock 50000000 --tap 8 --slot 24 --idle 0 --frame 16384 --bytes 16320 --depth 4 --seconds 60 --rounds 3 --out build/swd50-pc --execute
```

F103ZE 统一融合验收入口支持按所选配对的 50 / 73 / 100 MHz 参数串行运行调试、内存、RTT、变量采样及 USB 对照。下例以 CDC48 目标和带 50 MHz 采样配置的已验收 ABI 1 配对打印计划。添加 `--execute` 后，经 HS3 临时加载对应 bit/ELF、检查身份、备份目标 SRAM，逐项测试并复核恢复。每个 SRAM 窗口的复算例见效率报告。

```powershell
$f103Pair = 'prebuilt/selectio-spi-cdc-rx-guard-20261123'
python -X utf8 toolbox.py project run board.accept -- --selectio --board f103ze --pair $f103Pair --clock 50000000 --frame 16384 --only switch --only debug --only memory --only rtt --only scope --only combo --only usb-ddr
```

运行态 RTT 默认使用与 100 MHz 历史成绩相同的 1,024 B 目标环。给同一入口加 `--rtt-ring-bytes 8192` 可测大环并减少环尾截断。两种容量使用同一个 Cortex-M3 生产者，每次运行都从真实 RTT 描述符取环地址和大小。大环占用的区域由 16 KiB SRAM 夹具备份和复原。请分别保存两次的报告，以便区分环长和 USB 帧长带来的变化。

F103ZE HCLK128 的 50 MHz SWD 优化包见 [候选配对](../../prebuilt/selectio-swd50/README.md)。在已经加载该配对、目标 RTT 控制块和上行环均位于 SRAM 的条件下，可使用 `rtt-queue` 启动专用队列路径。它连续读完整 TAR 页，每次最多 4 KiB，并在落入探针 DDR 后检查 RdOff 写入的 SWD 应答和 DP 状态。以下地址是本仓库 SRAM 夹具的示例。

标准 CMSIS-DAP 与 RTT→CDC 共用 50 MHz SWD 批次队列的验证配对是 [selectio-swd50-standard](../../prebuilt/selectio-swd50-standard/README.md)。CMSIS-DAP 使用现有 TransferBlock 命令。CDC 转发继续使用 J7 串口，启动后借用同一队列，并在 STOP 或调试器接管时交还 AP。[实测与复测入口](../validation/swd50-standard-20261122/README.md)

```powershell
python -X utf8 toolbox.py selectio --serial 12345678 rtt-queue --tap 8 --slot 22 --idle 0 --address 0x20008200 --seconds 60 --out build/rtt-queue.bin
python -X utf8 tools/selectio_f103_clock_accept.py --pair prebuilt/selectio-swd50 --hclk-mhz 128 --only memory --only rtt --rtt-queue --memory-page-aligned --seconds 60 --rounds 3 --out build/swd50-accept --execute
```

独立 RTT 的 `--chunk 1024` 或 `--chunk 2048` 控制每次确认目标 RdOff 之前最多搬运多少字节。CLI 默认在协商到 16 KiB 的 IF4 上使用 2,048 B，旧接口沿用 1,024 B。STOP 返回的状态字给出实际设置。统一验收入口的对应参数是 `--rtt-chunk`，例如固定 `--only rtt --clock 50000000 --rtt-ring-bytes 8192`，分别用两个块长运行。报告中的 `stream_MBps` 使用从服务启动确认到 STOP 尾部排空的窗口，`cli_process_MBps` 包含启动 CLI、连接与退出耗时，二者均使用已验证的主机有效字节。

在相同线速做小帧对照时，用 `--frame 4096 --bytes 4032`；比较队列策略用相同帧长、字节数和深度，仅调整 `--schedule`。报告中的 `clock` 给出时钟树、队列分频及采样 tap 的来源。`wall_MBps` 包含主机载荷生成和校验，`probe` 中的计时覆盖队列与 PS 块函数。[分层基线和数字模型](../validation/efficiency-20261122/README.md)

以下地址仅作 CDC48 示例；其他固件从目标 ELF 符号表取得 RTT 控制块或变量地址。RTT 下行需要目标定义 DOWN 通道。本项目的 J-Scope 指主线 HSS 硬件变量采样，CLI 可导出 CSV。独立采样支持 1–8 个变量。周期单位为 24 MHz tick，`24000` 表示 1 ms。`--var` 的格式为地址、字节宽度、类型码，用冒号分隔。类型码 0–7 依次对应 u8、i8、u16、i16、u32、i32、f32、f64。

```powershell
python -X utf8 toolbox.py selectio rtt @link --address 0x2000b000 --size 256 --channel 0 --seconds 10 --out log.rtt
python -X utf8 toolbox.py selectio rtt-send @link --address 0x2000b000 --channel 0 --text "help`n"
python -X utf8 toolbox.py selectio rtt-terminal @link --address 0x2000b000 --channel 0 --up-channel 0
python -X utf8 toolbox.py selectio scope @link --var 0x2000c000:4:4 --var 0x2000c004:4:4 --period 24000 --seconds 10 --out scope.hss
python -X utf8 toolbox.py selectio scope-export --in scope.hss --csv scope.csv
python -X utf8 toolbox.py selectio combo @link --rtt-address 0x2000b000 --channel 0 --var 0x2000c000 --var 0x2000c004 --ticks 24000 --seconds 60 --rtt-out combined.rtt --scope-out combined.csv
```

`combo` 在一个 AP 会话内同时取得 RTT UP 字节及 1–8 个对齐的 u32 变量，分别输出原始字节与带时间戳的 CSV。终端支持双向输入输出。`scope` 收尾时校验最终统计帧。用 `scope-export` 可继续核对定义、帧序号、样本数、跳拍数并导出 CSV。100 MHz 是 SWCLK/TCK 线速；采样率取决于变量数量、地址布局和目标响应。

## 物理串口、SWO 和 SPI

`com bind` 将 CDC 分配给物理 UART，打开 Windows 串口并置 DTR 后开始工作。配置为 8N1，波特率由 CDC SET_LINE_CODING 提交。串口号可以用 `python -m serial.tools.list_ports -v` 按 USB 序列号查找。单独运行 `uart` 可以用文件或十六进制载荷发送并保存收到的原始字节。

```powershell
python -X utf8 toolbox.py selectio com bind
python -X utf8 toolbox.py selectio com status
python -m serial.tools.miniterm COM43 115200
python -X utf8 toolbox.py selectio com release
python -X utf8 toolbox.py selectio swo --encoding uart --rate 48000000 --configure-f103 --itm-mask 1 --seconds 2 --out itm-uart.bin
python -X utf8 toolbox.py selectio swo --encoding manchester --rate 24000000 --configure-f103 --seconds 2 --out itm-manchester.bin
python -X utf8 toolbox.py selectio swo --encoding manchester --rate 100000000 --seconds 2 --out external-manchester.bin
python -X utf8 toolbox.py selectio spi --mode 0 --slot 22 --tap 0 --hex 9f000000 --out spi-rx.bin
```

关闭串口终端后执行 release。F103 配置选项会保存并恢复 TPIU、ITM 和相关 GPIO 配置，要求该目标的实际 HCLK 和 TPIU 分频可产生请求码率。目标需要主动写 ITM 激励端口才会产生有效包。已配置的外部源可直接被动接收。Manchester 的 rate 表示信息位率，100 Mbit/s 对应 200 Msymbol/s。标准 SWO 使用固件默认采样设置。SPI 固定 100 MHz、MSB first、模式 0–3，由一次命令在同一次 CS 低电平下交换 1–4,079 B，文件发送可用 `--file`。

### ABI 2 的 SPI 从机接收

ABI 2 用 IF3 的 EP10 接收 SPI 数据。H743 的四模式 50 MHz 持续复验使用滤波 v2 和 H743 修订 4，查看 `python -X utf8 toolbox.py project case h743-spi-j7-rx-filter-v2-50` 获取配对和参数。 [实测](../validation/h743-spi2-100mhz-20261124/README.md#50-mhz-持续验收)

### 历史 ABI 1 的 SPI 从机接收转发

以下从机转发用例对应 [历史 CDC 配对](../../prebuilt/selectio-spi-cdc-rx-guard-20261123/README.md)。外部 SPI 主机驱动 J7-29 SCK、J7-31 低有效 CS 和 J7-25 MOSI，并与探针共地。探针在监听时释放这三根线，按选择的 CPOL/CPHA 接收 MSB-first 字节。CDC 返回连续原始字节，片选结束时丢弃不足八位的尾字节并累计帧错误。桥接方向为 MOSI → COM，J7-27 保持输入，COM 写入不驱动 MISO。

先让主机保持 CS 为高，并在探针完成占用前保持三根信号高阻。执行绑定并打开同一探针的 COM，让终端置 DTR，然后用 `com status` 确认 `binding=spi-slave`、`claimed=1` 后开始打钟。测试结束先停外部主机，让三根信号进入高阻，确认 COM 收齐、`rx_available=0` 后关闭终端并释放。CDC 波特率参数只用于打开串口，实际 SCK 由外部主机给出。SPI 绑定独占复用引脚，与物理串口、RTT→CDC 和使用同一引脚的调试会话分时使用。

```powershell
python -X utf8 toolbox.py selectio com bind-spi --mode 0 --tap 0
python -X utf8 toolbox.py selectio com status
python -m serial.tools.list_ports -v
python -X utf8 toolbox.py selectio com release
```

100 MHz 是接收设计目标，连续满载对应 12.5 MB/s MOSI 有效载荷。`--tap` 调 MOSI，外部 SCK 与 CS 共用最近一次载入的 SWDIO 延迟值。确认最高档时应使用独立 SPI 主机和已知数据，逐字节对拍，并保留 SCK 实测值、COM 实收速率、溢出和帧错误。已有 F103 夹具用于较低速度的实际引脚和 CDC 端到端测试。两种物理测试和原语仿真的判定分别记录。 [Case 表](fusion-performance-cases.md#case-表)

独立 SPI 主机应在测试工具显示 `ARMED` 后发送 `--expected` 指定的二进制载荷。工具按探针序列号定位 COM，逐块比对，核对尾包后释放：

```powershell
python -X utf8 tools/selectio_spi_cdc_test.py --serial 12345678 --mode 0 --tap 0 --expected build/known-mosi.bin --seconds 65 --out build/spi-slave-wire.json --execute
```

持续 100 MHz 满载对应每轮 60 秒 **750,000,000 B**，确认三轮。报告中的 `pc_receive_MBps` 以 MB/s 计，取 COM 首字节至收齐的主机计时。SCK 频率、源发送窗与帧间间隙由独立主机记录，与 COM 字节数及 SHA-256 对拍。Windows 采集端建议驱动使用 1 MiB 接收缓冲，并按块读取。

## 频率与参数速查

| 功能 | CLI 与主要配置 |
|---|---|
| USB 枚举、时钟核对 | `info`，`usb-test --seconds`。按 USB 序列号选设备 |
| SWD / JTAG 识别和标准命令 | `identify --transport --clock`，`profile --transport --tap --slot --idle`。先低速识别，空闲再换到高速 |
| SRAM 原生块 | `read/write --address --clock --tap --slot --idle --queue-depth`。地址与载荷按 4 B 对齐，硬件按 1 KiB TAR 页拆分 |
| RTT 转发与交互 | `rtt --address --size --channel --chunk --clock`，`rtt-send`，`rtt-terminal --up-channel --timeout`。独立端点版使用 EP7 |
| J-Scope / HSS | `scope --clock --period --var --seconds`，`scope-export`。周期为 24 MHz ticks，分别回读实际周期、实收组数、跳拍和 STOP 尾部 |
| RTT＋HSS 同时运行 | `combo --clock --tap --slot --idle --rtt-address --var --ticks`。新固件支持 50–100 MHz 请求，包括 73 MHz |
| 50 MHz SWD RTT 批队列 | `rtt-queue --tap --slot --idle --address --channel --seconds`，使用独立的 50 MHz 路径 |
| COM / 物理 UART | `com bind/status/release`，模式随 Windows COM 的 DTR 和 SET_LINE_CODING |
| SWO | `swo --encoding --rate --seconds`，编码选 `uart` 或 `manchester`，独立端点版走标准 EP2 IN。F103 ITM 夹具支持 `--configure-f103 --itm-mask` |
| SPI 主机 | `spi --mode --slot --tap`，用 `--hex` 或 `--file` 提交载荷，固定 100 MHz |
| ETM | `trace capture --swd-khz --seconds --elf --bit --zynq-elf`，以及 `trace verify/query/export`。TRACECLK 由目标配置提供 |

高速请求使用 Hz，例如 `--clock 50000000`、`73000000`、`100000000`，73 MHz 在当前时钟树上约为 **72.727 MHz**。以结果中的实际频率和时钟树为准。tap 范围 0–31，slot 范围 0–63。SWD idle 为 0–15，JTAG 的 slot 范围是 16–63。原生块、RTT 下行与并发读数要求 JTAG idle 为奇数。JTAG 实时路径的 idle 范围为 0–255。独立 `rtt` 和 `scope` 可以一起传入 `--tap --slot --idle`，省略时使用既有 profile。 [精简性能用例与校准](fusion-performance-cases.md)

统一实板入口支持 50/73/100 MHz，需要配对清单提供相应采样档。HCLK96/128 的定向压测使用 `selectio_f103_clock_accept.py --pair ... --hclk-mhz ... --out ... --execute --command <子命令>`，由外层夹具核对时钟、暂停并备份 SRAM，子命令退出后恢复。需要完整 JTAG 时加 `--enable-jtag`。这些 HCLK 是 F103 实验档。

F103ZE 候选性能用例可从同一个入口复跑，以下使用已完成相应实测的 ABI 1 配对。用 `--only` 选择本轮授权范围，先预览，再临时加载并验证指定配对。默认计划还包含 36 MHz TRACECLK 历史诊断，按暂停范围保留。每个测试点有单独的恢复记录。DBG-04 和 DBG-08 同时保存标准 CMSIS-DAP 的 2 KiB／深度 32 对照和原生 SRAM、RTT→CDC、J-Scope 长窗。`--only DBG-08-STREAMS` 可单独复验同条件的 RTT→CDC 和 J-Scope。RTT 停止时主机保持 COM 接收并限时处理忙状态，失败报告保存 STOP 与接收线程现场。

```powershell
$f103Pair = 'prebuilt/selectio-spi-cdc-rx-guard-20261123'
python -X utf8 toolbox.py project run board.selectio-performance -- --pair $f103Pair --out build/perf-preview --only CAL-01 --only DBG-04 --only DBG-08
python -X utf8 toolbox.py project run board.selectio-performance -- --pair $f103Pair --out build/calibration --only CAL-01 --execute
python -X utf8 toolbox.py project run board.selectio-performance -- --pair $f103Pair --out build/perf-128 --only DBG-04 --only DBG-08 --execute
```

## ETM

以下 F103ZE CDC48 采集示例声明已临时加载的 ABI 1 配对。H743 RAW4 采集见 `project case h743-etm`。

```powershell
$f103Pair = 'prebuilt/selectio-spi-cdc-rx-guard-20261123'
python -X utf8 toolbox.py trace doctor --offline
python -X utf8 toolbox.py trace capture --elf prebuilt/golden/f103ze-cdc48.elf --bit "$f103Pair/probe.bit" --zynq-elf "$f103Pair/application.elf" --swd-khz 10000 --seconds 1 --out build/my-etm --json-out build/my-etm.json
python -X utf8 toolbox.py trace query --record build/my-etm --view summary
python -X utf8 toolbox.py trace capture --running-window --elf prebuilt/golden/f103ze-cdc48.elf --bit "$f103Pair/probe.bit" --zynq-elf "$f103Pair/application.elf" --swd-khz 10000 --seconds 1 --out build/my-etm-running
python -X utf8 toolbox.py trace verify --record build/my-etm-running --require-decoded
```

F103 保持 CDC48 时 TRACECLK 为 24 MHz。默认窗口从目标恢复执行开始，记录起点可同时出现初始化未同步和调试重启标记。需要观察已经运行的程序时，加 `--running-window`，在 ETM 源恢复输出后再启动完整的硬件计时窗口。入口断点模式用 `--entry` 另行选择。按采集 JSON 核对实际 SWD 配置频率、窗口长度、frameDrops、parserErrors、USB 完成状态、解码 gap 与目标恢复。进一步的导出及符号查询见 [Trace CLI](../Trace-CLI使用说明.md)。

空闲原生 SRAM 会话的释放时限为 2 秒；主机没有继续取流时，原生 AUX、RTT 和 HSS 经过 5 秒释放其私有资源。新主机的 HELLO 按序号识别并排空旧回复。标准 DAP SWO 由 SWO_Control 与 DAP_Disconnect 控制，CDC 由串口 DTR 控制。

## 构建与复测

融合版三档调试时钟、SRAM、采集和物理接口的定向性能验收见 [精简性能用例](fusion-performance-cases.md) 与 [已确认结果](fusion-performance-cases.md#已确认结果)。

```powershell
$env:ZYNQLINK_FPGA_OUT = Join-Path $PWD 'build/fusion-pl-new'
python -X utf8 tools/run_vivado.py -mode batch -nojournal -source fpga/build_dma.tcl -tclargs --selectio --selectio-variable
python -X utf8 tools/build_xusbps_daplink.py --selectio --selectio-variable --j7-adapter --compact-code --opt s --experimental-zero-idle --timing build/fusion-pl-new/verified_clock.json --out build/fusion-ps-new
python -X utf8 tools/selectio_cm3.py
python -X utf8 tools/selectio_cm3.py --services --sample-ticks 64 --out build/cm3-jtag-services
python -X utf8 tools/selectio_cm3.py --services --swd-only --sample-ticks 32 --out build/cm3-swd-services
python -X utf8 tools/selectio_spi_slave_sim.py --out build/spi-cdc-xsim
python -X utf8 tools/selectio_spi_slave_sim.py --ring-only --out build/spi-cdc-ring
python -X utf8 tools/selectio_spi_slave_sim.py --pump-only --out build/spi-cdc-pump
```

以上构建使用已复验的 RAW4 ETM 接收路径。`--etm400` 属于独立的双沿采样实验，在相同 H743 历史 CDC 工况复现了 TPIU 成帧错误。[H743 同板对照](../validation/h743-cdc-golden-requal-20261123/README.md)

F103ZE CDC48 的整套融合回归使用归档 ABI 1 配对。以下依次为离线预览、经授权实际执行和报告复核。

```powershell
$f103Pair = 'prebuilt/selectio-spi-cdc-rx-guard-20261123'
python -X utf8 toolbox.py project run board.accept -- --selectio --board f103ze --pair $f103Pair --clock 100000000 --seconds 60 --rounds 3 --rtt-ring-bytes 8192 --rtt-chunk 2048
python -X utf8 toolbox.py project run board.accept -- --selectio --board f103ze --pair $f103Pair --clock 100000000 --seconds 60 --rounds 3 --rtt-ring-bytes 8192 --rtt-chunk 2048 --out build/accept-new --execute
python -X utf8 toolbox.py project run board.accept -- --selectio --review build/accept-new/summary.json
```

自建配对按用例选相应验收入口，并核对 bit、PS ELF、PS 初始化 Tcl、采样配置和清单。高速模式使用独立的 SelectIO 参考时钟。对有写入的实板压力测试，`selectio_f103_fixture.py` 会核对目标映像、保存 4 KiB SRAM、两侧哨兵及初始运行状态，并在独立进程中读回恢复结果。下列示例仅用于该 F103 实验夹具。

```powershell
python -X utf8 tools/selectio_f103_fixture.py --out build/my-guard --execute -- python -X utf8 tools/selectio_pipeline_bench.py @link --bytes 4032 --depth 4 --seconds 60 --rounds 3 --out build/my-pipeline --execute
```

各配对的时序、真实目标读写、序列校验和恢复数据分别归档在[板测报告](../validation/selectio-integration/README.md)。与商用探针对照时，分别比较目标 RAM 写入 MB/s、目标运行时 RTT MB/s、变量采样组/s 和物理 SWO 信息位率。公开参照值包括 J-Trace PRO 的 4.0 MB/s RAM 下载、SEGGER 所列约 3.5 MB/s RTT 背景传输，以及 ULINKpro 的 100 Mbit/s Manchester。测试目标与传输方式会影响结果。[SEGGER J-Trace](https://www.segger.com/products/debug-probes/j-trace/) · [SEGGER RTT](https://kb.segger.com/General_information_about_RTT) · [Arm ULINKpro](https://support.arm.com/tools-and-software/ulinkpro)
