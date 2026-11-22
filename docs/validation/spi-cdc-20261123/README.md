# SelectIO SPI 从机接收与 CDC 验收

本轮在融合分支上增加 SPI MOSI → 原有 CDC COM 的接收转发。USB 接口、端点地址和 VID/PID 沿用现有融合版。SPI 主机、SWD/JTAG、RTT、HSS、UART/SWO 与 ETM 依然使用这一个融合镜像。

| 验证 | 范围 | 结果 |
|---|---|---|
| SPI 接收原语仿真 | 50、72.727、100 MHz，CPOL/CPHA 四模式，每档每模式八个输入初相，带 pad 偏斜模型 | 9,424 字节逐字通过，四次不足八位的片选中断正确报错并恢复，监听期间 SCK、CS、MOSI 高阻 |
| 共享 SelectIO 回归 | 真实 Cortex-M3 模型和 UNISIM，100 MHz JTAG/SWD 整页分方向校验 | 两条链路各 256 字读写通过，保持原有共享 PHY |
| 物理 CDC 数据通路 | F103ZE SRAM-only GPIO 源，四模式，原 J7 接线 | 每模式 16,384 B，合计 65,536 B 全匹配，零溢出、帧错、尾差。DWT 窗口平均 SCK 为 mode 0/2 约 1.35 MHz，mode 1/3 约 1.64 MHz |
| 100 MHz 实体线速 | 独立、可持续发送精确数据的 SPI 主机，三轮 60 秒 | 待独立源实测。100 MHz 满载目标为 12.5 MB/s 有效字节 |

[SPI 接收 XSim 完整结果](spi-slave-xsim.txt)。离线 DAP/IF4 回归覆盖 SPI 绑定、错误模式、短配置帧。描述符回归分别核对 legacy 与融合的端点地址、类型、包长和版本值。F103 GPIO 测试源的指令模型复核了四模式位序和 GPIO、AFIO、APB2 恢复。

首轮布局走线的同步 setup 为 +0.165 ns。旧输出用的 `pad_swclk` 时钟同时约束到新增外部 SCK 首级 ISERDES，报告一个 −1.073 ns 的 hold 违例。SPI 从机采用异步过采样，约束只豁免 L15 外部输入至该 ISERDES DDLY 的路径。原 SWCLK 输出和采样器之后的同步路径继续检查。同一路由检查点按 `--selectio --selectio-variable --etm400` 的环境重验，133.333 MHz setup/hold 裕量为 **+0.165/+0.051 ns**，DRC 与 bitgen 通过。 [首轮失败路径](first-sck-sta-failure.txt) · [归档配对](../../../prebuilt/selectio-spi-cdc-20261123/manifest.json)

首轮实板的 mode 0/1 在 Windows WinUSB 占用期间重新枚举 CMSIS-DAP 失败，尚未启动目标源。夹具将 DAP 的准备和恢复置于 WinUSB/COM 采集期之外。复验四模式全部通过，COM34 释放，原目标 SRAM、核心、GPIO、AFIO、APB2 和运行态恢复。新配对由 HS3 临时加载，物理 MEM-AP0 核对 80,228 B OCM 执行段。实机枚举的 VID/PID、接口和端点与原融合版一致。 [首次失败](first-dap-open-failure.txt) · [首次汇总](first-board-attempt.json) · [四模式结果](spi-cdc-four-modes.json) · [恢复与通过汇总](spi-cdc-board-summary.json) · [OCM 核对](probe-ocm.json) · [USB 枚举](usb-info.json)

SPI 同步引脚经 SelectIO 在 100 MHz 并行域得到每拍四个样本。接收器使用外部 SCK 的指定边沿，依 CS 边界重新对齐 MSB-first 字节。AUX 板载 64 KiB 环在数据复制到 PS DDR 后释放，DDR 消费指针在 USB IN 完成后确认。SPI CDC 短包在有待发数据约 0.5 ms 后提交，连续流优先聚合到 4 KiB。DTR、引脚所有权和 CDC 的实际排空分别核对。

## SWD 与 JTAG HSS 长窗

同一融合配对，F103ZE CDC48，实际 SWCLK/TCK 均为 99,999,998 Hz。SWD 用 tap8/slot25/idle2，JTAG 用 tap16/slot28/idle33。修复 CLI 会话入口后，两条链路的 RTT UP/DOWN 环尾各 257/37 B 全匹配。HSS 每种宽度三轮 60 秒，全部样值、帧序号和 STOP 计数通过，目标已恢复。

| 链路 | 变量 | 周期 | PC 实收中位组/s | 三轮跳拍 |
|---|---|---:|---:|---|
| SWD | 单 u32 | 16 tick | 1,499,801.76 | 5 / 4 / 4 |
| SWD | 八个连续 u32 | 160 tick | 149,980.20 | 1 / 1 / 1 |
| JTAG | 单 u32 | 80 tick | 299,960.12 | 1 / 1 / 1 |
| JTAG | 八个连续 u32 | 264 tick | 90,897.30 | 1 / 1 / 1 |

[SWD 逐轮数据](swd-hss-100.json) · [JTAG 逐轮数据](jtag-hss-100.json) · [首轮 CLI 会话错误](first-cli-context-failure.txt)

## 原有 USB 和物理线回归

| 项目 | 当前配对实板结果 |
|---|---|
| IF4 USB 回环 | 三轮各 60 秒，每轮双向逐字节校验，合计速率 21.398 / 21.483 / 21.585 MB/s |
| 100 MHz SPI 主机 | 双 TAP 的 mode 0 传输 1,128,448 B；MOSI 实际 pad 的 CPOL/CPHA 四模式各 1,128,448 B |
| 物理 UART 突发 | 按 100 Mbaud 发送/接收，各 52,896 B 逐字通过 |
| Manchester 源与接收 | 50 Mbit/s 外返、100 Mbit/s 带负载的 TDI pad 各 17,632 B 匹配。按位率记录物理突发，连续主机速率另计 |

SPI 主机的 mode 0/2 的通过 slot 为 16，mode 1/3 为 18。其他短测采样设置的失败保留。每项的发送源、tap/slot、结果和持续窗由独立夹具记录，目标恢复通过。 [物理线原始数据](wire.json) · [USB 三轮数据](usb-echo.json)

实物 CDC 100 Mbaud 回环 60 秒，每个方向 **268,017,664 B** 全匹配，约 4.467 MB/s/方向。物理 CDC 与 IF4 RTT/HSS 并行时收到 96 B RTT、111 组 HSS，跳拍 0。原生 IF4 和标准 IF0 的真实 ITM 各跑了 NRZ 3/48 Mbaud、Manchester 1.5/24 Mbit/s 四档，每个档位每接口均为 2,500,000 B，全匹配并排空。另用 F103 TIM2_CH2 12 MHz 在四模式下验证外部 MISO，SPI 主机 SCK 为 100 MHz；Manchester 100 Mbit/s 的带载突发累计 3,675,952 B。 [CDC 回环](uart-cdc-100m.json) · [并发](cdc-rtt-hss.json) · [ITM IF4](itm-if4.json) · [ITM IF0](itm-if0.json) · [外部 MISO](spi-master-external-miso.json) · [Manchester](manchester-hardware-bursts.json)

CDC48 的 24 MHz TRACECLK 运行态 ETM，完整 1.000 秒窗口、19,389,488 B formatter、0 个硬件丢帧/解析错/写错，严格解码核验和现场恢复通过。报告保留 301,602 个条件执行未知，全部按函数统计集中在 `usb_device_is_configured`，数量等于调用次数。事件样本 PC 0x0800226E 对应 `IT NE` 下的 `MOVNE`，TraceStore 给出的未知原因是 trace 没记录该非分支条件结果。 [采集](etm-cdc48-capture.json) · [严格核验](etm-cdc48-verify.json) · [谓词事件](etm-predicated-example.json)

首轮统一入口共 36 项，22 项通过。前部 14 项中的错误来自本分支旧 CLI 会话入口，夹具恢复均通过；后部使用修正的 CLI。首轮原样归档，SWD/JTAG 切换、丢失主机句柄、调试、SRAM、运行 RTT 和并发单独补跑，使用相同哈希的配对。 [首轮统一报告](first-full-board-summary.json)

补跑已通过 128 次 SWD/JTAG 切换、SPI/HSS 主机退出与重新接管、SWD 单步与断点。SWD SRAM 同一 100 MHz/slot25/idle2 配置，4,032 B 跨页、深度 4，读、写、交替各 3×60 秒。PC 读/写/交替的中位数为 **6.673/6.610/6.575 MB/s**，全部载荷或末块与保护字校验通过，目标恢复。 [SWD 长窗](swd-sram-100.json)

定向补跑的 14 个功能项均通过并核对恢复，与首轮合并后覆盖统一入口的 **36 项**。两轮的 bit、PS ELF 及初始化 Tcl 哈希一致。F103ZE 为原 CDC48 目标，SWCLK/TCK 读回均为 99,999,998 Hz。JTAG SRAM 的相同跨页条件读／写／交替中位数为 **4.716/4.566/4.603 MB/s**。IF4 RTT 使用运行态 8 KiB 环、2 KiB 请求，每条链路三轮各 60 秒并逐字核对。SWD／JTAG 的 CLI 全程中位数分别为 **6.156/3.997 MB/s**，传输窗口中位数与逐轮字节数见原始记录。这个套件覆盖 CDC48 统一入口，96/128 MHz 筛选及独立高速源用例另有各自的计时与硬件条件。 [合并判定](board-acceptance-union.json) · [复跑原始汇总](cli-retest-board-summary.json) · [JTAG SRAM](jtag-sram-100.json) · [RTT 逐轮数据](rtt-if4-100.json)

复现入口见 [CLI](../../selectio/README.md#spi-从机接收转发到-com) 与 [Case 表](../../selectio/fusion-performance-cases.md)。

## 100 MHz 异步参考漂移复测

上面的实板记录属于 `d7c58324…` 配对。后续在数字台架用精确 100 MHz SCK 和 2.502 ns 采样间隔复现错误。相位漂移使同一个四点采样字偶尔包含两个有效边沿，旧接收器会报帧错并丢弃它们。接收器改为按顺序处理两个边沿，保留字内的 CS 间隙。四种模式连续 8,192 B 匹配，观察到 53 个双边沿字，另核对同字 CS 间隙跨过两帧。新配对需要重新构建与板测，100 MHz 独立源长窗仍待验证。 [旧 RTL 失败](spi-slave-offset-before.txt) · [修正后结果](spi-slave-offset-after.txt)

数字链路补跑将 100 MHz 波形从 SelectIO 采样字接口送进生产 AUX RTL。同时经 133.333 MHz AXI-Lite 读取和确认接收环，73,727 B 逐字节匹配，覆盖 64 KiB 回卷与 3 B 尾。暂停消费时多送 7 个字节和 3 个尾位，计数正好为 7 个丢失字节和 1 个帧错误。清空并重新配置后再次收齐。这一用例验证到 FPGA 接收环，CDC 的持续实收由独立线路用例确认。 [Icarus 原始结果](spi-slave-ring-iverilog.txt)

## HCLK128 的 JTAG 采样终帧

旧配对在 JTAG 100 MHz、tap16/slot28/idle29 的单变量请求 24 tick 超额采样时，主机收齐了 118,459 组、29,172 帧数据，最后缺少 STAT。原 STOP 仍返回成功。该轮已核对目标恢复。生产 C 模型填满发送队列，分别验证 PS 与 PL 路径。旧版提前报告成功，修正版保持所有权，返回忙，等主机消费一帧后只发布一次最终 STAT 再释放。CLI 也核对终帧类型、计数与读错。修正后的 PS ELF 和同条件实板复验待完成。 [失败现场与前后对照](hss-stop-full-queue.txt)

## 首版配对的 96/128 MHz 稀疏初筛

采用 Case 表八个 DBG 点、每点保护与恢复目标时钟和 SRAM。线频按 PS/PL 寄存器回读，HCLK 用 RCC 配置和 DWT 对照。写入使用 4,032 B、深度 4；RTT→CDC 使用 8 KiB 目标环与 2 KiB 搬运。以下均为短窗候选，最终选择须复核三轮长窗。

| Case | 实际链路 / HCLK MHz | 较快 SRAM 读／写 MB/s | RTT→CDC MB/s | 单／八变量组/s |
|---|---:|---:|---:|---:|
| DBG-01 SWD | 50 / 96 | 3.828 / 3.801，idle1/0 | 3.733 | 856,737 / 90,863 |
| DBG-02 SWD | 72.727 / 128 | 5.154 / 5.220，idle0 | 5.021 | 1,199,529 / 99,956 |
| DBG-03 SWD | 100 / 96 | 6.685 / 6.601，idle2 | 6.5060 | 1,499,367 / 149,946 |
| DBG-04 SWD | 100 / 128 | 6.692 / 6.705，idle1 | 6.5058 | 1,499,356 / 149,931 |
| DBG-05 JTAG | 50 / 96 | 3.267 / 3.204，idle13 | 2.751 | 187,408 / 62,477 |
| DBG-06 JTAG | 72.727 / 128 | 4.088 / 3.975，idle21 | 3.144 | 187,430 / 62,473 |
| DBG-07 JTAG | 100 / 96 | 4.720 / 4.557，idle33 | 4.039 | 299,881 / 90,872 |
| DBG-08 JTAG | 100 / 128 | 4.959 / 4.779，idle29 | 4.213 | 超额试点缺 STOP 终帧，待新配对复验 |

DBG-06 原清单 slot22 邻域没有通过点。按 Case 表修正到 slot28 后，tap14/16/18 均通过回读；idle21/25/29 的跨页 SRAM 校验通过，idle21 的 3 秒 RTT 和单变量及八变量确认通过。归档清单的 73 MHz JTAG 预设改为 slot28，保留较稳健的 idle25。数据、所有通过点的跳拍和第一次失败保留在同一份报告。 [逐点记录](sparse-debug-screen-v1.json)

## 首版配对的 ETM 实板边界

与同一份 F103ZE SRAM 循环 ELF 配对，固定低频 SWD 配置。按目标 HCLK 得出 TRACECLK，HCLK 用 RCC 和 DWT 对照。**36 MHz TRACECLK** 的三轮 1 秒严格验收通过，formatter 字节为 33,235,768 / 32,788,138 / 33,235,774，零 FPGA parser 错误，已知两支交替执行序列通过。24 和 32 MHz 各通过一轮 1 秒。36 MHz 是本组实板严格通过的最高档。

40 MHz 的短窗 FPGA parser 错误为零，严格核验发现 638 个解码缺口。44 MHz 和四路数据 tap12 的 48 MHz 窗口也无 FPGA parser 错误，原生 OpenCSD 在窗口前段退出。默认 tap 的 48 / 64 MHz 各记录 192,594 / 86,124 个 FPGA parser 错误。48 MHz 两个其他设置也保留原始失败。所有点核对了采集和夹具恢复。 [逐窗计数与质量](etm-physical-boundary-v1.json)

## 修正配对首次实板

新版的 bit 为 `f3c4ccfd…`，PS ELF 为 `32f75ae7…`。Vivado 按 133.333 MHz 约束完成布线，setup/hold 为 +0.012/+0.021 ns。真实 JTAG/RAM 加载后，MEM-AP0 核对了 80,268 B OCM 执行段，USB 描述符与首版完全相同。F103 GPIO 四模式各 16,384 B 全匹配，零溢出、帧错及尾差，夹具恢复。全套与最高物理速率分别跟踪。 [新配对](../../../prebuilt/selectio-spi-cdc-phase-drift-20261123/manifest.json) · [首轮硬件证据](phase-drift-smoke.json)
