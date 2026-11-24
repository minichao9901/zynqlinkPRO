# H743 历史 CDC ELF 与融合版同板复验

2026-11-23，J7 USB 序列号 `12345678`，HS3 `210299008529`。H743 CDC `COM43`，USB `F055:7431`，序列号 `H743CDC0001`。探针采用 HS3 JTAG/RAM 临时加载。

## 目标和对照条件

[CDC Golden ELF](../../../prebuilt/targets/stm32h743-cdc-trace-20261101/cpu60-trace20/fw.elf) 的 SHA-256 为 `246640bf79c8b1e568441a286812326dfb0ae68a0df061a0c023262c07cf221b`，与历史 1 秒通过记录保存的 ELF 一致。经授权写入 H743 Bank 1 首扇区，整片 2 MiB Flash 读回与预期镜像逐字节相同。扇区内 ELF 占 31,752 B，其余字节保留。测前原件只存在本机私有备份中，验收现场保留 CDC 固件。

PLL 和总线寄存器读值与同一历史工况一致，目标诊断读出 CPU/HCLK 60 MHz，按这套配置为 TRACECLK 20 MHz。SWD 控制 10 MHz，GPIO 速度档 2。每窗由目标物理 CDC 执行带 CRC 的回显，周期约 4 ms。

## ETM 对照

| 探针 RAM 配对 | 完整采集窗口 | 结果 |
|---|---|---|
| 冻结 main 正式配对，当前 CLI | 10、200、500 ms 各三轮；严格判据下 1 s 三轮 | 每轮硬件窗口完整，成帧错误 0。1 s 三轮硬件窗口内精确回显 214、214、216 次。 |
| 融合 ETM400 接收器、旧 ABI 1 | 10 ms 两轮，1 s 两轮 | 10 ms 成帧错误 24、1；1 s 成帧错误 2,140、2,094。丢帧、IDELAY ready 丢失为 0。 |
| 同一融合 ETM400 bit、独立端点 ABI 2 | 10 ms 一轮 | 成帧错误 1，丢帧与 IDELAY ready 丢失为 0。 |
| 融合 RAW4 接收器、独立端点 ABI 2 | 10、200、500、1000 ms 各三轮 | **12/12 严格通过**。所有窗口 TPIU 成帧、FIFO 丢帧、DDR 写入和 IDELAY ready 错误为 0。 |

固定 CDC ELF 和接线后，冻结 main 与早于 USB 拆分的融合版已经能够区分通过和失败。回归在 TPIU 接收/成帧路径，早于 USB 拆分；本组数据不足以识别具体的采样相位或电气根因。

融合候选仅切回主线 RAW4 单沿 200 MHz 接收路径，保留可变 SelectIO 时钟、同一个融合 bitstream 和 ABI 2 独立端点。三轮 1 s 硬件窗分别有 221、222、222 次正确的物理 CDC 回显，主机解码约 1,835 万条指令，EP9 下载 34.79–35.02 MB/s。最后一轮保留 1 字节采集边界 `I_INCOMPLETE_EOT`，统一严格校验确认中途异常为 0。完整计数和哈希见[RAW4 ETM 证据](raw4-etm-evidence.json)。

实际加载配对见 [RAW4 配对](../../../prebuilt/selectio-usb-split-raw4-20261123/README.md)。Vivado 2018.3 在 133.333 MHz 通过时序，setup/hold 余量 +0.057 / +0.039 ns。上板物理 MEM-AP0 核对 80,668 B OCM，FCLK0 读回 133,333,332 Hz。

早期矩阵另有一轮 1 s 在输入末端被旧规则误拒。该原始记录经 `trace verify --require-decoded` 通过，终止诊断保留。专用 H743 矩阵脚本改用同一判据，在恢复已确认时继续下一轮。

## JTAG 原生 SRAM 回归

PS 曾允许整个 H743 AXI SRAM，PL JTAG 队列的 AXI SRAM 窗口为 `0x24050000–0x240503ff`。向越界页发起 GO 后，物理 MEM-AP 查到 Zynq PC 停在 `Xil_DataAbortHandler`，CPSR 为 Abort 模式，USB 命令超时。核对 CDMA 空闲、解除已停住的队列后重载探针。已独立恢复并验证目标 SRAM 前后保护字、核心寄存器、时钟及运行状态。

修正后，越界页请求在启动队列前返回 ZLK 参数错误。JTAG 50 MHz、tap16/slot28/idle33、目标 HCLK60 的 DTCM 双向 4,032 B 独立读回通过，RTT UP 257 B、DOWN 14 B 环绕通过。按公开 CLI 重新连接后，独立单变量和八变量采样各 3,001 组，均为零跳拍和零读错误。RTT/HSS 并发短窗中收到 1,757,184 B 和 751 组，载荷序列正确、零跳拍，夹具恢复通过。

[结构化证据](baseline-evidence.json)

## 最终 RAW4 配对功能清单

| 功能 | 同一配对的实板结果 |
|---|---|
| SWD/JTAG SRAM | 实际连线时钟 49,999,999 Hz；SWD AXI SRAM、JTAG DTCM 各 4,032 B 双向通过，低速 DAP 独立核对。JTAG 越界返回参数错误，随后传输正常。 |
| SWD/JTAG RTT | 两条链路 UP 257 B、DOWN 14 B 跨环，逐字节通过。 |
| SWD/JTAG J-Scope | 1 k 组/s 一变量／八变量，SWD 为 3,001／3,001 组，JTAG 为 3,021／3,001 组。值、序号与 STOP 计数一致，零跳拍。 |
| SWD/JTAG 并发 | 250 组/s 八变量，SWD 752 组、RTT 2,121,728 B；JTAG 751 组、RTT 1,775,616 B。均零跳拍，取流尾部和原始序列一致，EP8 未读时 EP5 仍有响应。 |
| COM 双向 | COM34 TX 115,200 baud，H743 PA15 独立接收 256 B。RX 250,000 baud，H743 PB3 独立发送 73,728 B。全量一致，零帧错误。 |
| SWO | 标准 IF0 EP2，NRZ 250 kbaud 和 Manchester 500 kbit/s，两档分别逐字节匹配 73,728 B，无待收数据和诊断错误。 |
| SPI 主机 | 配置 SCK 100 MHz，四模式各通过独立 15 MHz 和 30 MHz MISO PWM 的边沿间隔与样本长度检查。100 MHz 四模式全双工 1/5/4,096 B 通过 RTL 模型。四模式双向独立实板对拍尚需高速 SPI 从机夹具。 |
| ETM | H743 20 MHz TRACECLK，EP9 连续采集和严格解码 12/12。 |

在旧 ETM400 加地址保护的配对上，如果沿用同一个已执行原生内存和 RTT 的低速 JTAG DAP 会话，HSS 首次启动返回 `-7`。按独立 CLI 的连接流程重新连接后复验通过。最终配对的功能验收也使用该流程，直接跨服务的长寿命 DAP 会话继续跟踪。

临时 SRAM、GPIO、定时器、目标时钟和核心状态均有恢复回执。JTAG 验收可用 `python -X utf8 tools/verify_selectio_usb_split_h743.py --transport jtag --execute --seconds 3 --out build/h743-raw4-jtag-new` 复测，SWD 将 transport 改为 `swd`。 [功能计数与哈希](raw4-functional-evidence.json)

## H743 HCLK60 短窗性能

后续同板对照已补测停核／运行、AXI SRAM／DTCM、旧版／独立端点、USB/DDR 回环和目标 WAIT。本文数字用于记录原工况，JTAG idle65 的写入重复性和 RTT 运行态瓶颈见 [吞吐差异定位](../h743-throughput-audit-20261123/README.md)。

SRAM 使用 4,032 B 跨 1 KiB 页、WinUSB 队列深度 4，每方向约 2 秒，回读最终数据和前后保护字。RTT 是运行态序号源、8 KiB 环和 EP7 独立转发，逐字校验，主机吞吐不含 STOP 尾部。吞吐以十进制 MB/s 计。J-Scope 的速率按 24 MHz 计时和通过的请求周期列出。以下均为单点短筛，链路用寄存器实际读回。

| 调试链路实速 | tap / slot / idle | SRAM 读／写 MB/s | RTT MB/s | J-Scope 单／八变量合格短窗 |
|---|---|---:|---:|---:|
| SWD 49.999999 MHz | 8 / 24 / 4 | 3.606 / 3.518 | 0.734 | 750 / 83.33 k 组/s |
| SWD 72.727272 MHz | 8 / 22 / 6 | 4.860 / 4.428 | 0.714 | 750 / 83.33 k 组/s |
| SWD 99.999998 MHz | 8 / 25 / 4 | **4.927 / 4.726** | **0.755** | 1,000 / 107.14 k 组/s |
| JTAG 49.999999 MHz | 16 / 28 / 33 | 2.443 / 2.409 | 0.567 | 125 / 37.50 k 组/s |
| JTAG 72.727272 MHz | 16 / 26 / 65 | 2.502 / 2.462 | 0.575 | 150 / 41.67 k 组/s |
| JTAG 99.999998 MHz | 16 / 28 / 65 | **3.391 / 3.323** | **0.624** | 187.50 / 50.00 k 组/s |

SWD 测 AXI SRAM，JTAG 测 DTCM。所列 RTT 上限为单请求主机拉取的实测值，50 MHz 及 SWD 72.727 MHz 用 1,024 B chunk，JTAG 72.727 MHz 及两路 100 MHz 用 2,048 B chunk。首轮 SWD 72.727 MHz 的 RTT UP 扫描报错，保持 slot22/idle6、分别建立采样与 RTT 的 DAP 会话后通过。slot24 的 SRAM 首次写失败。JTAG 72.727 MHz 的 slot28/idle33 和 100 MHz 的 slot28/idle37、idle53 均发生首笔 WAIT。SWD 100 MHz 下，20 tick 的单变量和 192 tick 的八变量短筛的跳拍率分别约 95.4% 与 56.4%。

原定 HCLK96/128 档位与使用 CDC Golden 的 HCLK60 工况分开记。SWO 最高速任意码序列和 SPI 100 MHz 四模式双向实板仍需独立夹具。 [全部通过和失败短窗](raw4-performance-screen.json) · [原定性能用例表](../../selectio/fusion-performance-cases.md)

## J-Scope 100 MHz 长窗

HCLK60、SWD tap8/slot25/idle4、JTAG tap16/slot28/idle65。各宽度独立跑 3×60 秒，按样值、时间网格、序号、尾帧和读错误核对。12 个窗口全过，目标在每轮后恢复。

| 链路 | 变量数 | 周期（24 MHz tick） | 实收组/s（样本时间网格） | 三轮跳拍 | 最差跳拍率 |
|---|---:|---:|---:|---:|---:|
| SWD | 1 | 24 | 999,999.95 | 3 / 3 / 3 | 0.00000501% |
| SWD | 8 | 208 | 115,384.60 | 1 / 1 / 1 | 0.00001445% |
| JTAG | 1 | 112 | 214,285.70 | 1 / 1 / 1 | 0.00000778% |
| JTAG | 8 | 416 | 57,692.31 | 0 / 0 / 0 | 0% |

最差跳拍率小于验收上限 0.1%。原始 `.hss` 保存于本机 `build/h743-cdc-golden-requal-20261123/scope-raw4-confirm`，每窗 SHA-256、实际组数和计时见 [长窗证据](raw4-hss-60s.json)。

## SRAM、RTT 及串行接口持续结果

SRAM 每方向和 RTT 各一轮 60 秒，调试线实速 99,999,998 Hz，目标 HCLK60。方法与短筛相同，RTT chunk 为 2,048 B。下表载荷时间排除 STOP 尾部，尾部另作总量和序列核对。

| 路径 | 60 秒 SRAM 读／写 MB/s | 60 秒独立 RTT MB/s | SRAM 读／写载荷 B | RTT 窗口载荷 B |
|---|---:|---:|---:|---:|
| SWD AXI SRAM，tap8/slot25/idle4 | **4.927 / 4.732** | **0.755** | 295,658,496 / 283,917,312 | 45,289,472 |
| JTAG DTCM，tap16/slot28/idle65 | **3.392 / 3.320** | **0.624** | 203,535,360 / 199,213,056 | 37,462,016 |

| 串行接口 | 本夹具逐字节通过的最高试档 | 边界 |
|---|---|---|
| COM34 接收 | 1 Mbaud，73,728 B | 请求 1.5 Mbaud 时实际平均频率匹配，载荷不完整。具体波形误差待独立码源对照。 |
| COM34 发送 | 500 kbaud，256 B | H743 的软件接收在 750 kbaud 和 1 Mbaud 出现帧错误，需独立接收夹具划出探针上限。 |
| SWO NRZ | 1 Mbaud，73,728 B | 1.5 Mbaud 载荷不完整；2 Mbaud 时 H743 源平均仅约 1.75 Msymbol/s。 |
| SWO Manchester | 750 kbit/s，协商 750,002 bit/s，73,728 B | 1 Mbit/s 要求 2 Msymbol/s，本夹具实测约 1.75 Msymbol/s。 |
| SPI 四模式 | Probe 100 MHz 配置下，15/30 MHz PWM 各通过；四模式 100 MHz 全双工模型通过 | 全速双向实板对拍待独立高速从机；SPI 从机到 CDC 的 100 MHz 物理验收也需独立高速主机。 |
| ETM | 20 MHz TRACECLK，12 窗严格通过 | 同配对最高频率待独立匹配工况。历史不同目标配置曾连续通过 25 MHz。[历史灰排线证据](https://github.com/minichao9901/zynqlinkPRO/blob/03b6a1dad8ee62aa7902b6bc37d0f0d9c3c3f451/docs/validation/h743-etm-ribbon-20261111/README.md) |

以上为本次 H743 工况。原定 HCLK96/128、标准 CMSIS-DAP 和旧 RTT→CDC 的历史成绩按各自负载与入口留档。 [持续吞吐、接口及最终现场证据](raw4-sustained-evidence.json) · [历史参考和用例](../../selectio/fusion-performance-cases.md#已确认结果)

## 交接

- [x] 保存 ETM 12 窗、功能对拍、SWD/JTAG 三档通过和失败短筛、J-Scope 12 个长窗、SRAM/RTT 60 秒结果。完成 TPIU 回放、DDR RTL 回归、SPI 四模式仿真和 118 项 CLI 测试。原始 ETM 记录与目标 ELF 在本机 `build/h743-cdc-golden-requal-20261123`。
- [x] H743 保留用户指定的历史 CDC Flash 镜像。收尾逐字节核对 31,752 B ELF 装载段，原 HCLK60 时钟、心跳和 COM43 回显正常。所有 SRAM、核心及外设夹具恢复。物理 MEM-AP0 复核探针 OCM 的 80,668 B，采集、RTT/HSS、DDR/CDMA 空闲。
- [x] 问题表同步 ZL-063、ZL-242、ZL-316、ZL-318–322。配对的 bit、PS ELF、初始化 Tcl、构建时序与 SHA-256 均纳入 Git。命令与配对可通过 [SelectIO CLI](../../selectio/README.md) 和 `probe-load --pair ... --dry-run` 核对。
- [x] 本轮交付到本地 `codex/selectio-efficiency`。本地与远端 `main` 均冻结在 `03b6a1da`。固定 EXE、Pages、Release 和探针 QSPI 冷启动为本轮不适用，探针保留 JTAG/RAM 临时配对。保留共享 `hw_server`、失败证据及私有 Flash 备份。
