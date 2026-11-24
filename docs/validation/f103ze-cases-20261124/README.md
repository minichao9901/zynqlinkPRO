# F103ZE 用例清单实板验收

2026-11-24（上海时间），在 `E:\zynqlinkPRO-efficiency` 的 `codex/selectio-efficiency` 执行 [acceptance-cases.json](../../../acceptance-cases.json) 的 F103ZE 条目。初始源码为 `208316672583d8b2ae2986032db996cda592b184`，清单 SHA-256 为 `1f292e665a47c73fb94cba8fdd1fc0ea1f7803fe93720d7f5e78590784c09616`。

HS3 下载线 `210299008529`，J7 USB `12345678`、COM33，目标 CDC `F103CDC0001`、COM34。目标 CPUID `0x411fc231`、DBGMCU ID `0x10036414`。板上 Flash 的 20,168 B 装载段与 CDC48 ELF 一致，目标 RCC_CFGR 为 `0x0051040a`。临时下载探针对应位流和 PS ELF 后，以物理 MEM-AP0 核对其 OCM 执行段。各项的原始窗口与恢复备份保存在本机 `build/runs/<用例 ID>/20261124-case`。

## 融合功能

以下三项按清单使用 `selectio-spi-cdc-rx-guard-20261123`。实际枚举为 ABI 1，`bcdDevice=0x0201`，原生协议 `ZLK1`。配对哈希、完整 USB 描述符、逐模式数据和恢复结果见[结构化功能证据](functional.json)。

| 用例 | 实板结果 |
|---|---|
| `f103ze-uart-swo` | 物理 UART 在 COM33 双向逐字节匹配，256 次并发 SWD 读取，以及和原生 RTT/J-Scope 并发的路径通过。CDC 旁路计时 60 秒，双向各 264,335,360 B 对拍通过。原生和 CMSIS-DAP 的 ITM/SWO 各四档，每档 500,000 字，全量匹配。五项夹具均恢复。 |
| `f103ze-spi-cdc` | 清单中的历史复测，四模式各 16,384 B 全匹配，零成帧、溢出和尾量，F103 GPIO 源的 DWT 平均 SCK 约 1.35–1.64 MHz。四项夹具均恢复。 |
| `f103ze-etm` | CDC48 ETMv3、TRACECLK 24 MHz，SWD 请求 10 MHz，FCLK 133.333332 MHz 与分频读回折算实际 SWCLK 9.523809 MHz。完整硬件窗 1.000 秒，USB 下载 formatter 15,422,987 B，35.125 MB/s。成帧、FIFO 丢帧、IDELAY ready 丢失及 DDR writer 错误均为 0。严格 `trace verify` 通过，17,270,812 条已执行指令，1 个初始 gap，0 个包错误。RCC、目标及 FPB 已恢复。 |

## 起步对照

开始时误用了通用 Web 全套和 `release-20261106` 的旧 RAM 配对。其结果按实载身份归档为[起步对照](preliminary-reference.json)，对应本机 `build/f103ze-full-20261124-standard`。这轮烧录端的 20 KiB Flash 独立读回与原备份一致，原应用复位心跳前进。最终目标处于运行态，探针采集及 DMA 空闲。旧包的单／八路原生 HSS 固定计数窗报错，网页窗口通过。旧网页 ETM 的严格核验记录 2 个 gap，另有记录 metadata 大小差异。三轮软件跨页各三项通过，实体 USB 项待验。上述数据不计入清单用例。

标准 Web 入口用物理寄存器和固定 bit SHA 核对正式探针配对。ABI 2 RAW4 使用独立的 IF3/EP5–EP10，标准 Web 的 HSS 路径查找旧候选端点，不能作为融合端点的验收入口。F103ZE 的各融合条目以清单指定配对为准。
