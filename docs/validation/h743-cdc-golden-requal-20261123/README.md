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
