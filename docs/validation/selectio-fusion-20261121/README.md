# F103ZE 多协议融合探针实板验收

探针为 J7（USB 序列号 12345678），由 HS3 210299008529 临时加载。目标是 STM32F103ZE CDC48，HCLK 为 48 MHz。测试沿用目标原有 Flash、PLL、AHB/APB 配置。SRAM 测试区域为 0x20008000 起的 4 KiB，并检查两侧哨兵与初始运行状态。源版本、bit/ELF 和初始化 Tcl 的 SHA-256 见[配对清单](../../../prebuilt/selectio-j7-fusion/manifest.json)。[加载记录](load.json) · [枚举描述符](interfaces.json) · [CLI 手册](../../selectio/README.md)

## 时钟与时序

FCLK0 按 7.5 ns 实现；高速路径使用 ARM PLL /10，寄存器读回约 133.333 MHz。读回的 FCLK1 为 199,999,998 Hz，MMCM 产生 200 MHz 输出串行时钟、100 MHz 四时隙时钟、50 MHz 八时隙时钟及 400 MHz 输入串行时钟。TDO 和 TDI 的 ISERDESE2 为 8 位 DDR，Manchester 100 Mbit/s 使用每个信息位的八个采样。SWDIO 使用四采样。由时钟树推算的 100 MHz 档为 99,999,999 Hz。没有外接示波器或频率计。[布线时序](timing.rpt) · [时钟间约束](clock-interaction.rpt) · [资源占用](utilization.rpt) · [综合输入哈希](rtl-inputs.json)

融合配置的 setup 余量为 +0.177 ns、hold 余量为 +0.027 ns。整机占用 26,527 个 LUT（49.86%）、28,875 个寄存器（27.14%）、67.5 个 BRAM tile（48.21%）和 1 个 DSP。静态时序、Cortex-M3/UNISIM 仿真、真实探针 I/O、真实目标外设和 PC 文件吞吐分别取证。

## USB 与模式切换

IF4 的 0–4,079 B 边界载荷回环，以及 3 × 60 秒全载荷回环均逐字节正确。双向合计 21.48–21.64 MB/s。该数字对应主机发送、接收和验证相同字节的总量。IF0 保留标准 CMSIS-DAP 和 SWO_Data；Windows CDC 由实际物理串口单独占用。[USB 实测](usb.json)

在刻意保留相反采集端口偏好的条件下，128 次交替 SWD/JTAG 接管及跨页读取均正确。分别在 SPI 与 HSS 过程中释放 WinUSB 句柄、留下未读回复后，新主机能重新取得引脚并读回原 SRAM，详情见[交替切换](switch.json)和[主机异常退出](host-loss.json)。

## 100 MHz SRAM

Windows、PyUSB/WinUSB、深度 4，每请求 4,032 B，访问 0x20008020，跨四个 1 KiB TAR 页。每个方向及交替读写各跑 3 × 60 秒。下表为计入主机准备和收发时间的有效载荷 MB/s。混合项按每个字节实际占用的完整窗口计算。

| 链路 | 读 | 写 | 交替读写 | F103 参数 |
|---|---:|---:|---:|---|
| SWD | 6.157–6.183 | 6.165–6.170 | 5.951–5.960 | tap 8、slot 24、idle 2 |
| JTAG | 4.676–4.677 | 4.551–4.568 | 4.495–4.506 | tap 16、slot 28、idle 29 |

在相同窗口中，PS 硬件计时器测得队列从提交到完成的读/写载荷吞吐，SWD 为 7.274/7.547 MB/s，JTAG 为 5.313/5.311 MB/s。主机端到端速率约为相应队列速率的 82%–88%。队列计时包含目标应答和寄存器握手。

每种模式的读返回逐字节对照，单向写窗口结束后独立低速读回末次图案及哨兵，交替窗口验证每一对写读。较短 JTAG idle 9、17、25 的短测遇到 WAIT，保留失败点。普通调试与运行态采集采用 idle 33。[SWD 原始窗口](memory-swd.json) · [JTAG 原始窗口](memory-jtag.json) · [idle 对照](../selectio-integration/idle-study.json)

J-Trace PRO 公布的 RAM 下载上限为 4.0 MB/s。这块 F103 上两种传输的实测写入都超过该数值。目标硬件、协议、块大小与主机不同，本次没有同板同负载的商用探针对测。[SEGGER 官方规格](https://www.segger.com/products/debug-probes/j-trace/)

## 上板窗口

完整接线、使用命令和离线 CSV 导出见 [CLI 手册](../../selectio/README.md)。原始 RTT 与 HSS 文件保留在验收运行目录，版本库保存每轮计数、哈希、窗口参数及恢复结果。

### 运行中的 RTT 与变量

目标在 SRAM 中连续产生递增 u32。每轮 60 秒，PC 对收到的全部序号逐一验证，并与固件写指针及目标计数核对。独立 RTT 的 MB/s 计时包含 CLI 启动及链路接管；并发项按采集开始至 STOP 和尾部排空计时。

| 协议 | 独立 RTT | RTT 与双变量 1 kHz 并发 | 并发采样组 | 跳拍 |
|---|---:|---:|---:|---:|
| SWD 100 MHz | 5.413 MB/s | 4.614 MB/s | 59,995 | 0 |
| JTAG 100 MHz | 3.485 MB/s | 3.062 MB/s | 59,995 | 0 |

双向 RTT 单独检查了 UP 257 B 和 DOWN 37 B，两种链路均跨环尾逐字节匹配。原生终端写入 DOWN 环前检查空闲空间，发布写指针前读回目标数据。运行态测试恢复所保存的核心寄存器并读回 SRAM。SEGGER 对背景 RTT 给出的公开参照约为 3.5 MB/s。[SWD RTT](rtt-swd.json) · [JTAG RTT](rtt-jtag.json) · [SWD 并发](combo-swd.json) · [JTAG 并发](combo-jtag.json) · [SEGGER RTT](https://kb.segger.com/General_information_about_RTT)

### 独立 J-Scope

每个变量为 32 位；八变量测试使用连续地址。每个数据帧检查序号，每组检查变量值，最终 STAT 的采样数与主机文件一致。全部确认窗口为 60 秒，无变量读取错误。[全部档位、失败对照和 STOP 计数](services.json)

| 链路 | 变量数 | 周期（24 MHz tick） | 实收组 | 探针报告跳拍 |
|---|---:|---:|---:|---:|
| SWD | 1 | 24 | 59,993,244 | 3 |
| SWD | 8 | 192 | 7,499,160 | 0 |
| JTAG | 1 | 96 | 14,998,395 | 1 |
| JTAG | 8 | 416 | 3,461,163 | 0 |

### COM、SWO 与 SPI

Windows 实际打开 COM43，提交 100,000,000 baud、8N1，通过 F103 双 BYPASS 将探针 UART TX 在物理 TDO/SWO 引脚送回 RX。连续 60 秒共发送和接收 **261,959,680 B/方向**，每个 4,096 B 载荷逐字节匹配，硬件溢出和帧错均为零。窗口包含主机请求与等待，每方向约 4.37 MB/s。另用 F103 GPIO 软件串口在 115200 baud 回送每字节异或 0xA5，同时执行 256 次 100 MHz SWD SRAM 读取。[高速物理 CDC](cdc-100m.json) · [独立 GPIO 回送及并发 SWD](cdc.json)

真实 F103 ITM 端口分别发出 500,000 个递增 32 位字。UART 3/48 Mbaud、Manchester 1.5/24 Mbit/s，在原生 IF4 和标准 IF0 各四轮，分别得到 2,500,000 B，全部与预期端口号、宽度、载荷、尾部计数相符。该目标的 48 MHz HCLK 限定了原生目标可产生的码率。[IF4](itm-native.json) · [CMSIS-DAP SWO_Data](itm-cmsis-dap.json)

100 Mbit/s Manchester 的信息位宽为 10 ns。M15 的真实带负载引脚回读进入 8 倍采样解码器。在一次持续开启的 60 秒接收会话中，发送 31,143 个不同的 112 B 载荷，3,488,016 B 全部一致，零帧错、零溢出。每次原始发生器的 RAM 重新装载产生间隔；这些数据验证 100 Mbit/s 的物理突发，不代表整分钟的连续线速流量。[混合数据长窗](manchester-bursts.json)

L14 的外部证据分列。F103 TDO 作为码源时，50 Mbit/s 任意字节返回正确；100 Mbit/s 的交替数据通过独立 60 秒窗口。一次完整套件中，相同交替夹具没有收到字节，该次失败保留。其后 3 次独立 RAM 加载及 128 次在 M15 和 L14 间切换均成功。任意 100 Mbit/s Manchester 码流的部分相邻边沿间距为 5 ns，在 F103 的 TAP 上生成这些边沿需要局部 200 MHz 移位。首个混合图案应有 382 个跳变，L14 的原始抽样仅观察到 190–198 个；扩展到 128 个源端驱动边沿和采样组合后，观察范围为 73–233 个。设置 PB3 为高速复用输出也没有恢复正确波形。独立外部 200 Msymbol/s 混合码源的完整验证留待具备该信号源的现场。[完整套件首次记录](wire-first-attempt.json) · [独立 L14 长窗](external-sparse-retest.json) · [重载与切换](restarts-and-switches.json) · [混合源原始跳变](external-mixed-source.json) · [PB3 对照](external-mixed-gpio-fast.json)

SPI 100 MHz 的模式 0 通过真实两级 TAP 的 TDI→TDO 数据返回。模式 0–3 分别验证了带负载 MOSI 引脚的已知载荷，同时另用与探针异步的 F103 TIM2_CH2 在 PB3 输出 12 MHz，逐事务检查物理 MISO 位流的每个边沿间隔、频率和数据量，每种模式各 60 秒。数字仿真中的四模式 SPI 从机覆盖单个 CS 下 1、5、4,096 B 双向数据。此处的外部器件是 TAP 和目标定时器，未接专用高速 SPI Flash。[独立物理 MISO](spi-target.json) · [ST RM0008 引脚复用](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-arm-based-32-bit-mcus-stmicroelectronics.pdf)

### ETM 硬件与解码

使用主线四线并行接收、DDR 及 USB 下载。目标 TRACECLK 24 MHz，SWD 配置上限 10 MHz，实际寄存器分频 9.524 MHz。默认调试恢复起点的 1 秒窗口已完成，解码 17,231,642 条已执行指令，packet issue 为 0；初始未同步与调试恢复各记一个边界 gap。[默认起点](etm-startup.json)

运行态窗口先让目标的 ETM 输出启动，再由硬件计完整 1.000 秒，获取 15,415,504 B formatter 数据。硬件 loss 为假、frameDrops/parserErrors/readyLosses/writerError 均为 0。解码 17,271,819 条已执行指令，1 个初始 gap、1 个条件执行未知、0 个 packet issue，原生严格 verify 通过。RCC、FPB 和运行态恢复。报告同时保留 tailAmbiguous=true 与尾长 0，未据此宣称每条指令条件均已观测。[运行态采集](etm-running.json) · [严格核验](etm-running-verify.json) · [采集和恢复判据](etm-acceptance.json)

8 MiB 循环飞行记录使用主机定时触发，触发后硬件窗口 50 ms。总采集约 1.461 秒，保留 8,388,593 B，解码 9,392,313 条已执行指令，1 个初始 gap、0 个 packet issue，严格 verify 通过。[飞行记录](flight.json) · [严格核验](flight-verify.json)

### 交付范围

本轮交付本地源码、固定 bit/PS ELF、PS 初始化 Tcl、CLI 与 README。探针用 HS3 JTAG/RAM 临时加载，目标 Flash 和探针 QSPI 保持原内容。远端 main、固定 Windows EXE、Web、Pages、公开 Release 与 QSPI 冷启动不在本轮交付范围。实板验收范围为 F103ZE CDC48；其他目标的可用档位须按各自的时钟、TAP 和布线取证。[逐项目标恢复](target-restore.json)


## 最终逐项判定

同一 bit、ELF 与 PS 初始化 Tcl 上，首次整套实板验收、增加在独立 SWJ 夹具中检查外部码源后的完整串行/SPI 复验，以及运行态 ETM 严格复验，逐项列在[判定表](qualification.json)。首次外部交替码未取得数据的失败记录保留。串行与 SPI 对照在同一配对完成。外部源单独保存和恢复目标状态；在同一次引脚所有权内，每次先用 25 MHz 参考扫描检查 F103 两级 BYPASS，再发送 100 Mbit/s 波形。参考检查共 34,038 位、零差异；60 秒外部交替码共 17,568 B 匹配。独立带负载混合源复验共 3,462,032 B、零差异。[全部回送点](wire-qualified.json) · [复验清单](wire-acceptance.json) · [混合源](manchester-bursts-qualified.json)

实际同时使用三个通道时，物理 Windows CDC 完成 256 B 变换回送，原生 RTT 精确取得预置的 96 B，原生变量采样取得 102 组、零跳拍，观测到目标 UART 计数从 0 增至 255。实板结束后确认 F103ZE 运行、RCC_CFGR=0x0051040a，原 ELF 的 20,168 B 全匹配；COM33 对应目标 F103CDC0001，COM43 对应探针 12345678。HS3 通过物理 MEM-AP0 再次核对 115,300 B 探针 OCM 可执行内容，探针保持本次 JTAG/RAM 配对，独占引擎已释放。[三通道并发](cdc-rtt-scope.json) · [目标现场](final-target.json) · [探针状态](final-probe-state.json) · [最终 OCM](final-ocm.json) · [ETM 恢复](etm-restore.json)
