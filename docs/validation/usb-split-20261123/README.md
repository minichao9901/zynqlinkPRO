# SelectIO 独立端点与 H743 定向验收

2026-11-23。J7 USB 序列号 `12345678`，HS3 `210299008529`，H743 使用原 HSI64 和原调试排线。探针以 JTAG/RAM 临时加载，复用已布线的融合 PL。物理 MEM-AP0 核对 PS OCM 执行段 80,620 B。目标 SRAM、两侧保护字、核心上下文、时钟、运行态及试验用外设均复核恢复。收尾 SWD 识别通过，探针各采集引擎和 CDMA 空闲。 [加载配对及哈希](load.json) · [最后 SWD](h743-swd.json) · [探针空闲](probe-final-idle.json)

Windows 枚举 IF0 CMSIS-DAP、IF1/2 CDC ACM、IF3 WinUSB。ABI 2 独立队列和端点与 [协议表](../../selectio-native.md) 一致。帧、DMA 和队列缓冲使用 PS DDR。EP11 预留。H743 内存夹具由低速独立读回和临时 AXI SRAM 范围保护。

| 验收项 | 实测结果 | 证据 |
|---|---|---|
| DAP | SWD 1 MHz 的 DPIDR `0x6ba02477`，JTAG 1 MHz CPU TAP `0x6ba00477`，CPUID 一致 | [SWD](h743-swd.json) · [JTAG](h743-jtag.json) |
| EP6 SRAM/私有 DDR | H743 AXI SRAM 4,032 B 跨 TAR 页读写与独立低速读回匹配。探针私有 DDR 的 16 KiB 帧、depth4、单方向短窗 PC 读/写 **28.02 / 24.48 MB/s** | [H743](h743-long.json) · [DDR](usb-ddr.json) |
| EP7 RTT DOWN | 14 B 跨目标环尾，写入字节和偏移通过回读 | [H743](h743-long.json) |
| EP8 独立 HSS | SWD 50 MHz、八变量 1 kHz、约 60 秒，**59,994 组，零跳拍、零读错**，样值、帧序号和 STOP 对账通过 | [H743](h743-long.json) |
| EP7 + EP8 并发 | 同一 SWD 会话约 60 秒，RTT **46,515,200 B**（约 **0.775 MB/s**），八变量 **250 Hz，15,000 组、零跳拍**。故意保留 EP8 待取帧时，EP5 状态和 EP7 RTT 仍可先完成。所有 RTT 字序、变量值和 STOP 计数一致 | [60 秒](h743-long.json) · [重开会话](h743-reopen.json) |
| EP2 标准 SWO | 使用 `SWO_Transport=2`；H743 经 PB3 → J7 L14，NRZ **250 kbaud**、Manchester **500 kbit/s** 各 **73,728 B** 完全匹配，尾部和索引一致 | [物理源](h743-swo.json) |
| EP4 物理 COM | COM34 上，H743 NRZ **250 kbaud**，Windows 实收 **73,728 B** 完全匹配，零溢出、帧错和尾差 | [物理 COM RX](h743-com.json) |
| EP10 SPI 主机 | J7 SCK 100 MHz、H743 异步约 32 MHz PWM MISO，四模式分别约 3.34–3.41 MB 实收，无溢出/帧错，边沿频率和间隔通过。完整独立 100 MHz 双向从机载荷待合格夹具 | [四模式及对照](h743-spi.json) |
| EP9 ETM 下载 | 在 50 ms 窗内收齐 **132,924 B** formatter，USB SHA-256 与物理 MEM-AP0 DDR 回读一致。**7 个采集成帧错误**，FIFO、IDELAY ready、writer 和 USB 提交错误均为零。严格采集/解码待源端条件改善 | [DDR 对拍](h743-etm-ddr.json) · [目标恢复](h743-etm-restore.json) |

保留边界。重开早期候选时 EP6 读到上一会话的完成帧，随后可超时。最终 HELLO 保留 USB DMA 和数据 toggle，只重建应用序号并取消旧流消费计数。主机在各 IN 的首次读确认本会话序号。Windows 重开和连续定向验收通过。H743 1 kHz 并发短窗有 1,268 次跳拍，250 Hz 长窗通过，前者保留为调度性能边界。H743 HSI 下的高速 DMA 码源 8 Mbaud/4 Mbit/s 在源端提前结束。16 MHz PWM 对照的三个 SPI mode 偶见短边沿间隔，USB 回复长度和错误计数正常。 [旧会话失败](reopen-before-fix.json) · [1 kHz 高载](one-khz-combo.json) · [高速码源](h743-swo-dma-source-limit.json) · [SPI 对照](h743-spi.json)

离线检查通过 11 项原生 USB 专项测试、118 项 CLI 测试、207 项 Web 测试和 177 个 Web 模块的语法检查。新旧两种 PS 配置均构建通过，共享驱动一致性通过。固定 EXE、公开 Pages/Release 和 QSPI 冷启动沿用原正式交付。本轮设备处于已经核对的新融合临时配对。

## 复测

```powershell
$pair = 'prebuilt/selectio-usb-split-20261123'
python -X utf8 toolbox.py probe-load --pair $pair --dry-run
python -X utf8 toolbox.py selectio --serial 12345678 info
python -X utf8 tools/verify_selectio_usb_split_h743.py --out build/h743-split-new
# 已核对配对、目标空闲及写入范围后执行
python -X utf8 tools/verify_selectio_usb_split_h743.py --out build/h743-split-new --seconds 60 --execute
```
