# F103ZE 用例清单实板验收

2026-11-24（上海时间），在 `E:\zynqlinkPRO-efficiency` 的 `codex/selectio-efficiency` 执行 [acceptance-cases.json](../../../acceptance-cases.json) 的 F103ZE 条目。初始源码为 `208316672583d8b2ae2986032db996cda592b184`，清单 SHA-256 为 `1f292e665a47c73fb94cba8fdd1fc0ea1f7803fe93720d7f5e78590784c09616`。

HS3 下载线 `210299008529`，J7 USB `12345678`、COM33，目标 CDC `F103CDC0001`、COM34。目标 CPUID `0x411fc231`、DBGMCU ID `0x10036414`。板上 Flash 的 20,168 B 装载段与 CDC48 ELF 一致，目标 RCC_CFGR 为 `0x0051040a`。临时下载探针对应位流和 PS ELF 后，以物理 MEM-AP0 核对其 OCM 执行段。各项的原始窗口与恢复备份保存在本机 `build/runs/<用例 ID>/20261124-case`。

## 本报告的验证范围

这六项是 **J7 探针回归**，使用板上的 CDC48 Golden 和各任务的临时 SRAM 夹具。新交付镜像的实板签收按各自 ELF 与板上装载段单独取证。 [F103ZE 镜像索引](../../../firmware/target/f103ze/README.md)

- 115200 UART 使用 GPIO 回显。100 Mbaud 是 J7 CDC 经 F103 双 TAP BYPASS 的物理回环。ITM 使用临时 SRAM 产数程序。SPI→CDC 的负载由 GPIO 产生，DWT 折算平均 SCK 约 1.35–1.64 MHz。USART 和 SPI1 新镜像的速率另测。
- 独立 J-Scope 在停核时采预置固定值，并发窗口使用 SRAM RTT 生产者和预置采样字。HCLK128 对照使用专用时钟夹具。新 `performance` 镜像的持续产数和动态波形待单独验收。
- 调试和烧录复用了 CDC48。源码步入记录为回退到指令级，源码步入及 GDBStress 的 A/B 映像和 RTT 命令终端待单独验收。ETM 实测绑定本报告记录的 CDC48 Golden ELF。

## 融合功能

以下三项按清单使用 `selectio-spi-cdc-rx-guard-20261123`。实际枚举为 ABI 1，`bcdDevice=0x0201`，原生协议 `ZLK1`。配对哈希、完整 USB 描述符、逐模式数据和恢复结果见[结构化功能证据](functional.json)。

| 用例 | 实板结果 |
|---|---|
| `f103ze-uart-swo` | 物理 UART 在 COM33 双向逐字节匹配，256 次并发 SWD 读取，以及和原生 RTT/J-Scope 并发的路径通过。CDC 旁路计时 60 秒，双向各 264,335,360 B 对拍通过。原生和 CMSIS-DAP 的 ITM/SWO 各四档，每档 500,000 字，全量匹配。五项夹具均恢复。 |
| `f103ze-spi-cdc` | 清单中的历史复测，四模式各 16,384 B 全匹配，零成帧、溢出和尾量，F103 GPIO 源的 DWT 平均 SCK 约 1.35–1.64 MHz。四项夹具均恢复。 |
| `f103ze-etm` | CDC48 ETMv3、TRACECLK 24 MHz，SWD 请求 10 MHz，FCLK 133.333332 MHz 与分频读回折算实际 SWCLK 9.523809 MHz。完整硬件窗 1.000 秒，USB 下载 formatter 15,422,987 B，35.125 MB/s。成帧、FIFO 丢帧、IDELAY ready 丢失及 DDR writer 错误均为 0。严格 `trace verify` 通过，17,270,812 条已执行指令，1 个初始 gap，0 个包错误。RCC、目标及 FPB 已恢复。 |

## HCLK128 性能和调试烧录参考

| 用例 | 实板结果 |
|---|---|
| `f103ze-hclk128-swd50` | `selectio-swd50-standard`，DWT 测得约 128.103 MHz，RCC 核对 HCLK128。FCLK 133.333332 MHz，物理寄存器折算 SWD 49,999,999.5 Hz。2 KiB CMSIS-DAP TransferBlock、队列深度 32、每方向 256 块、三次计时，读／写中位 **3.839／3.872 MB/s**。8 KiB 目标环及 2 KiB 搬运块，RTT→CDC 两轮约 60 秒，探针有效字节中位 **3.812 MB/s**，两轮全程累计 463,980,536 B，全量序号对拍且零传输错误。相对同口径基线，SRAM 读 −0.14%、写 +0.02%、RTT +0.01%。SRAM、RCC、核心及运行状态均已恢复。 [逐轮和恢复](hclk128-swd50.json) · [历史对照](../swd50-standard-20261122/README.md) |
| `f103ze-debug-flash` | 清单指定的 `qspi-reference`，使用正式 QSPI 包的 bit、PS ELF 和初始化脚本经 HS3 临时加载，OCM 核对 85,716 B。源码工作台 v1.3.16，实际 SWD 59,999,999 Hz。原生／Web 烧录、校验分别 1.065／4.290 秒，NRST 和独立心跳确认 0.878 秒。受影响 20 KiB Flash 与原备份一致。连接、暂停、指令单步、变量刷新、硬件断点、源码跳过和跳出、读栈均通过，步入显示回退至指令级。终态为 CDC48 运行、探针引擎空闲。 [逐项及恢复](debug-flash-reference.json) |

## 双链路 100 MHz 长窗

`f103ze-sram-rtt-scope` 使用清单的 ABI 1 配对、目标 CDC48、4,032 B 跨 TAR 页载荷、滑动深度 4、8 KiB RTT 环和 2 KiB 搬运块。物理时钟寄存器折算实际 SWCLK/TCK 均为 99,999,998 Hz。SWD tap8／slot25／idle2，JTAG tap16／slot28／idle33。

| 指标 | SWD | JTAG |
|---|---:|---:|
| SRAM 纯读／纯写／交替，MB/s | 6.664／6.599／6.562 | 4.711／4.565／4.602 |
| 独立 RTT，MB/s | 6.209 | 4.042 |
| J-Scope 单路，组/s | 1,199,845（20 tick） | 299,960（80 tick） |
| J-Scope 八路，组/s | 149,980（160 tick） | 90,897（264 tick） |
| 并发 60 秒 RTT 字节／J-Scope 组数 | 306,075,648／59,994 | 184,250,368／59,994 |

SRAM 各方向及 RTT 取三轮约 60 秒中位。SWD SRAM 中位相对同配对历史读／写／交替分别变化 −0.16%／−0.20%／−0.24%，两条链路的独立 RTT 中位变化在 0.04% 以内。J-Scope 四组实际档位各做 3×60 秒，逐样本和 STOP 总量均通过。SWD 单路历史 16 tick 点首个确认窗跳 486,062 拍，约 0.54013%，超过 0.1% 门槛。20 tick 三轮跳 3／3／4 拍。其余三组各轮跳 1 拍。并发两条链路均零跳拍。SWD、JTAG 的 RTT 上行及下行跨环 257／37 B 均一致。 [逐轮数据](sram-rtt-scope.json) · [同配对历史基线](../spi-cdc-20261123/README.md#cdc-out-防护配对的-usb-与-swd-长窗)

统一入口首轮 13/14 项通过。SWD SRAM 首个交替窗在完成 14,880 个请求后检测到载荷不一致，两级恢复均通过。同一配对、链路及参数复跑的九个窗口全部通过，纯方向和交替方向计数分别独立对账。清单六条均已执行，五条首轮通过，第六条补测后通过。首轮失败保留，起因待定位。 [ZL-340](../../项目问题跟踪列表.md) · [首轮失败](swd-sram-first-failure.json)

### 收尾

- [x] 按用例保存首轮、复跑和历史对照。全部目标夹具回读恢复，ETM 的目标配置和 FPB 独立恢复。
- [x] 独立双读目标 512 KiB Flash，哈希一致且与历史完整镜像读回相同。CDC48 两段装载区一致，RCC_CFGR 为 `0x0051040a`，目标处于运行态，心跳继续前进。
- [x] J7 留在临时 RAM 的 ABI 1 配对。USB 序列号 `12345678`、COM33、ABI 和完整能力描述符正常，目标 CDC 仍为 COM34。USB 状态确认 RTT、J-Scope、ETM DDR 采集及下载均空闲。两次独立工作台和浏览器已退出，令牌已移除，共享 `hw_server` 保留。
- [ ] 实体探针的最终物理 MEM-AP0 复读待验。复跑前已对拍该配对的 80,260 B OCM 执行段并确认 PL、DDR 与 CDMA 空闲。终态复查时，Windows 未枚举 HS3 `210299008529`，重新扫描仍未出现。保留首次物理回读失败。 [ZL-327](../../项目问题跟踪列表.md)

原始长窗及恢复备份保留在本机 `build/runs/f103ze-sram-rtt-scope/20261124-case` 和 `20261124-retry`。交付限本地效率分支的文档和证据。远端 main、固定 EXE、Pages、Release 与 QSPI 固化均未更新，本轮未做实体 QSPI 冷启动。

## 起步对照

开始时误用了通用 Web 全套和 `release-20261106` 的旧 RAM 配对。其结果按实载身份归档为[起步对照](preliminary-reference.json)，对应本机 `build/f103ze-full-20261124-standard`。这轮烧录端的 20 KiB Flash 独立读回与原备份一致，原应用复位心跳前进。最终目标处于运行态，探针采集及 DMA 空闲。旧包的单／八路原生 HSS 固定计数窗报错，网页窗口通过。旧网页 ETM 的严格核验记录 2 个 gap，另有记录 metadata 大小差异。三轮软件跨页各三项通过，实体 USB 项待验。上述数据不计入清单用例。

标准 Web 入口用物理寄存器和固定 bit SHA 核对正式探针配对。ABI 2 RAW4 使用独立的 IF3/EP5–EP10，标准 Web 的 HSS 路径查找旧候选端点，不能作为融合端点的验收入口。F103ZE 的各融合条目以清单指定配对为准。
