# J7 efficiency 三板目标固件

用于 [RAW4 ABI 2 融合探针](../../prebuilt/selectio-usb-split-raw4-20261123/README.md)。
这里收录 MCU 目标源码和各板编译产物。J7 bit/PS ELF、目标 MCU ELF 和上位机版本各有独立身份。
各板已编译的固件在自己的 `images/` 目录。每个用途子目录包含 ELF、BIN、HEX 和 SHA-256 清单，清单同时记录装载地址、工具链和验证范围。

[HPM6800EVK 固件索引](hpm6800evk/README.md) · [F103ZE 固件索引](f103ze/README.md) · [H743 固件索引](h743/README.md)。

## 固件清单

表中频率为 CPU/HCLK，单位 MHz。HPM 单列 hart0 和计时器时钟。

| 用途 | HPM6800EVK | STM32F103ZE | STM32H743 |
|---|---|---|---|
| SRAM、RTT、J-Scope 和并发 | `performance-axi`、`performance-ahb`，hart0 600，MCHTMR 24 | `performance`，128/128，SRAM 装载 | `performance-axi`、`performance-dtcm`，480/240 |
| GDBStress、RTT 交互与烧录复位验签 | `dbg-a`、`dbg-b`、`dbg-ram`，hart0 600 | 同名，HSE 72/72 | 同名，HSE 480/240，含浮点 IRQ 栈 |
| 物理 UART | `uart`，hart0 600，UART3 PE15 TX / PE14 RX | `uart`，72/72，USART1 PA9 TX / PA10 RX | `uart`，480/240，USART1 PA9 TX / PA10 RX |
| SWO / ITM | 不适用 | `swo`，48/48，PB3 | `swo`，60/60，PB3。`swo-source`，480/240，TIM2/DMA 合成码源，SRAM 装载 |
| SPI 主从 | 不适用 | `spi`，128/128，SPI1 PA4–PA7，SRAM 装载 | `spi`，480/240，SPI2 PI0–PI3，沿用现行修订 3 |
| ETM 与测速 | 不适用 | `etm`，48/48，TRACECLK 24。另有 `etm-ram`、`etm-loop`、`etm-fault` | `etm`，60/60，TRACECLK 20 |

旧工程仍可定向复测。[F103 CDC](f103ze/etm/cdc/README.md) · [F103 HAL 存储器负载](f103ze/etm/hal-storage/README.md)
· [H743 CDC](h743/etm/cdc/README.md) · [HPM6800 参考工程](hpm6800evk/reference/README.md)。
Golden 和历史验收继续使用原 ELF，例如
[F103 CDC48](../../prebuilt/golden/f103ze-cdc48.elf) 和 [H743 CDC60](../../prebuilt/targets/stm32h743-cdc-trace-20261101/README.md)。
同一例程重新构建得到的新 ELF 应和新板上镜像配对使用。

## 构建、加载与符号

在仓库根目录运行。构建只产生文件，输出必须是新目录。ARM GCC 可通过 `--gcc` 指定。HPM SDK 和配套 GCC 通过 `--sdk-env` 指定，默认使用 `HPM_SDK_ENV_DIR` 或 `E:/sdk_env_v1.11.0`。

```powershell
python -X utf8 toolbox.py project run target.acceptance-build -- --list
python -X utf8 toolbox.py project run target.acceptance-build -- --board all --out build/target-acceptance-new
python -X utf8 toolbox.py project run target.acceptance-build -- --board h743 --image performance-dtcm --out build/h743-dtcm-new
```

目标 Flash 映像从对应板型的烧录器入口加载。Cortex-M RAM 映像使用 ELF 的装载地址和向量表启动，HPM RAM 映像按 ELF 入口启动。Flash A/B 的 `g_boot_id` 分别为 `0x44424741` 和 `0x44424742`，RAM 为 `0x44424752`。核对 `g_boot_data_verified=1`、`g_ticks` 递增及 RTT `version`。RAM 版核对 `.data`、`.bss` 和 `main`。板卡原 Flash 与工作区的备份和恢复按 [验收规范](../../docs/板卡精简验收与交付.md) 执行。

先查镜像的 `manifest.json` 或使用对应工具链的 `nm -n fw.elf` 获取符号。SRAM 临时加载前保存所触及的代码、数据、栈、核心和时钟。F103ZE 的 128 MHz 超出额定规格，`performance` 和 `spi` 的代码、数据和栈均在 SRAM，采用 HSE 8 MHz ×16。H743 夹具按阿波罗 HSE 25 MHz、现有 LDO 供电配置构建。时钟失败时看 `g_clock_error` 和 `g_fixture_ready`，开测前用 RCC/DWT 核对时钟。

## 性能、调试和双向 RTT

- `g_mode` 为 0/1/2/3 时，分别对应 SRAM 空闲、RTT 洪流、Scope、两者并发。SRAM 数组位于 `g_perf_sram + 32` 或 HPM AHB 的 `g_perf_sram_address`。数组前后各有 32 B 保护字，测试区 16 KiB。先做跨 1 KiB、非对齐及 8/16/32 位读写，再以 **4032 B、depth 4** 测独立读、写和交替，复核保护字与末块。HPM AHB 映像还会初始化 `0xf0401000–0xf040503f`，装载前备份该区。
- RTT 默认发布连续小端 u32。置 `g_rtt_use_pattern=1` 可选用 `g_rtt_pattern`，该模式保留环背压。STM32 用 8 KiB 上行环，HPM 用 16 KiB，上行名为 Terminal，下行通道 0 为 256 B。记录 `g_rtt_published`、RdOff、主机实际字节和 STOP 尾量。GDBStress 接收 `help`、`version`、`echo <text>`，置 `g_rtt_binary_echo=1` 做原样二进制回显。
- Scope 以 10 kHz 更新 `g_scope[8]` 和 `g_scope_mixed`。单路用 `g_scope[0]`，八路用连续的 8 个 u32。第 0/7 项为同一更新序号，第 1 项为反码，异步读取跨过更新边界时可识别。先独立采样，再跑 RTT＋Scope 并发。H743 从八路 **250 组/s** 起，再试 1 k组/s。验证实际组速、序号、读错、跳拍 **<0.1%** 和 STOP 对账。
- STM32 高速性能从 **SWD 50/100 MHz**、**ARM JTAG 50/72.727/100 MHz** 取证。HPM 从标准 DAP 的 **JTAG 25 MHz** 起，50/100 MHz 为待验。ABI 2 原生 ARM SRAM 地址范围和实际 JTAG 窗口以 [实现](../../tools/selectio_native.py) 和所用 bit/ELF 为准。H743 AXI、DTCM 分别记录，JTAG 优先用已验证的 DTCM 地址段。稳定点做 **3×60 秒**。
- GDBStress 保持低速调试基线。STM32 先用 SWD 10 MHz，HPM 先用 JTAG 25 MHz。观察点可监视 `g_watch_byte`、`g_watch_half`、`g_watch_word`。写 `g_watch_request` 触发目标读写。验证断点、步入/步过/步出、调用栈、复位和 RTT 自动接入。Flash A/B 同时产出 ELF/BIN/HEX。

## UART、SWO、SPI 和 ETM

- **物理 UART。** J7-25 TX 接目标 RX、J7-27 RX 接目标 TX，共地。先用 **115200、8N1**。待空闲时写 `g_uart_baud_request`，核对 `g_uart_baud` 和错误计数。模式 0 逐字节回传异或 `0xa5`，模式 1 发连续序列并独立接收，模式 2 只接收。模式 1 第 n 字节为 `((n//4) >> (8*(n%4))) & 255`。用 `g_uart_rx_hash` 的 FNV-1a 校验目标收到的载荷。分别升档测 TX、RX 和同时收发，覆盖 4095/4096/4097 B 和 DTR 重开。J7 **100 Mbaud** 用独立对端或物理回环复测。
- **SWO/ITM。** PB3 接 J7-27。真实 ITM 版由探针控制 ITM/TPIU 编码与分频，再写 `g_itm_port`、`g_itm_request`。第 n 个 u32 为 `(n*0x9e3779b9)^0xa55aa55a`，n 从 0 开始。F103ZE 对照 NRZ **3/48 Mbaud**、Manchester **1.5/24 Mbit/s**。H743 从 NRZ **250 kbaud**、Manchester **500 kbit/s** 验真实源。合成源在暂停且未启动时配置 `g_source_mode`（0 NRZ、1 Manchester）、`g_source_ticks`（默认 16，目标 15 Msymbol/s）、`g_source_repeats` 与 `g_source_request`（1–256 B）。探针 **100 Mbit/s Manchester** 独立码源须提供 **200 Msymbol/s**、混合数据和可核对时序。
- **SPI。** J7-31/29/25/27 对应 NSS/SCK/MOSI/MISO。F103ZE 的 PA4/5/7/6 接对应引脚。写 `g_spi_role`（0 从机，1 主机）、Mode 0–3、`g_spi_div`（BR 0–7）、`g_spi_length`（1–4096 B）、seed 和超时后，写 `g_spi_arm=1`。主机默认预留 1 秒让夹具接管。`g_spi_stream_ms` 可启用主机连续重复缓冲。有限事务读取 `g_spi_rx` 对拍，连续模式重点校验 J7 实收序列和目标计数。主机 APB2 为 64 MHz，SCK 按 **1/4/8/16/32 MHz** 分档。**36 MHz** 用独立时钟验证且单列。H743 见 [SPI2 控制协议及接线](../../prebuilt/targets/stm32h743-spi2-cdc-r3-20261124/README.md)，内核 200 MHz。四模式下分开签收 **H743 发→J7 收**、**J7 发→H743 只收**和**双向**。100 MHz 为单向目标，四模式全双工先在 ≤25 MHz 复验。高速档先短筛，再做 **3×60 秒**逐字节对拍并保留首个失败档。
- **ETM。** 两块 STM32 的 PE2 为 TRACECLK，PE3–PE6 为 D0–D3。匹配目标 ELF，从 **SWD 10 MHz** 控制采集。F103ZE Golden 测 1 秒及现有 SRAM/Fault 变体，H743 Golden 测 **10/200/500/1000 ms**。分别记录硬件窗、EP9 下载、解码/索引和首屏。核对有效指令流、包错误、gap 和目标恢复。[Trace CLI](../../docs/Trace-CLI使用说明.md)

## 当前验证范围

新版包的每个 ELF 当场检查了机器架构、可执行入口和关键符号。产物状态为 **离线构建，硬件待验**。
H743 SPI2 修订 3 已有独立实板证据，其 50 MHz Mode 1/2 短窗对拍和源端计数通过。新包的重建 SPI ELF 保留自己的哈希和待验状态。
[融合版 J7 物理接线与 CLI](../../docs/selectio/README.md) · [独立端点定义](../../docs/selectio-native.md) ·
[性能判据](../../docs/selectio/fusion-performance-cases.md) · [H743 SPI 修订记录](../../docs/validation/h743-spi2-cdc-20261124/README.md)。
