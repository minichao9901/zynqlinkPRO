# H743 ETM 成帧错误来源对照

2026-11-23。探针 J7 `12345678`、HS3 `210299008529`。H743 运行当前 Flash 的 `stm32h743_dbgstress/fw.elf`，实读核对两段 Flash 装载区共 7,740 B。目标保持 HSI64、既有 PLL/AHB/APB 设置和原排线。SWD 请求固定 10 MHz。探针采集参考约 200 MHz，实际目标引脚 TRACECLK 未独立测量。各配对均经 JTAG/RAM 临时加载，OCM 经物理 MEM-AP0 核对。 [逐窗与恢复](summary.json)

## 同板对照

| 配对或变量 | 其他条件 | 成帧错误 |
|---|---|---:|
| `main` 正式 RAM 配对，旧 RAW4 | GPIO 3，50 ms × 3 | 237 / 251 / 246 |
| 拆端点前融合版 ABI 1 | GPIO 3，50 ms × 3 | 15 / 476 / 15 |
| 独立端点 ABI 2 | 与 ABI 1 相同 FPGA bit。GPIO 3，50 ms | 7 |
| 冻结 `main 03b6a1da` 自己的 CLI | GPIO 2，50 ms × 3 | 231 / 197 / 215 |
| 冻结 `main` 自己的 CLI | GPIO 1，50 ms × 3 | 125 / 184 / 158 |
| 冻结 `main`，窗口对照 | GPIO 2，5 ms × 2 | 14 / 20 |
| 冻结 `main`，窗口对照 | GPIO 2，200 ms × 2 | 789 / 969 |
| 冻结 `main`，仅改变 TRACECLK 抽头 | GPIO 1，50 ms，D0–D3 固定 0，CLK tap 8 / 16 / 24 | 134 / 112 / 198 |

20 个窗口里，USB 下载文件与物理 MEM-AP0 DDR 回读的 SHA-256 全部相同。FIFO 丢帧、DDR writer 错误、IDELAY ready 丢失及 USB 提交错误均为零。异常在 PL 将 formatter 帧交给 DDR writer 之前出现。`orbtrace_tpiu_stream` 在已经同步后，遇到不完整的全同步序列或帧中途出现全同步标记时产生 `malformed_event`，由 `orbtrace_ddr_capture` 记为 `parserErrors`。错误随采集窗口长度增多。离线解码及拆 USB 端点均发生在该计数产生之后。 [TPIU 检查](../../../fpga/rtl/orbtrace_tpiu_stream.v#L33) · [捕获计数](../../../fpga/rtl/orbtrace_ddr_capture.v#L91)

## 历史通过记录与归因

同一 `main` 正式 RAM bit/ELF 在历史 H743 **CPU/HCLK200、TRACECLK25 MHz、GPIO 2、临时分支负载**下，曾三轮各 1 秒通过。历史 **CPU/HCLK60、TRACECLK20 MHz** 的 H743 CDC 目标也有通过记录。本次用当前解码器从这份 1 秒归档的 2,176,688 B 原始数据重建解码与索引，严格校验通过，解析 18,373,686 条指令、0 个 ETM packet issue。 [25 MHz 实板](../h743-etm-ribbon-20261111/README.md) · [20 MHz 原始记录](../h743-comprehensive-20261101/raw/etm20-4ms-matrix/1000ms-1/session.json) · [本次离线复验](summary.json)

当前能确认的是这套 H743 工况的 **TRACECLK/TRACED 接收及 formatter 成帧阶段**持续失步，连历史通过的 bit/ELF 和冻结的主线 CLI 也能复现。GPIO 驱动档和有限的 CLK tap 试验都未得到零错误窗口。当前 HSI64 dbgstress 与历史已通过的 Trace 源时钟、目标负载不同。要判定具体是源端时钟/数据、线路电气还是探针输入采样裕量，需要在同一排线上复现已核对的 20 MHz Trace 源，并同时核对 J7 的 TRACECLK 与四条数据线。本次保留现有目标时钟，精确物理根因仍待定位。

20 次采集均恢复 H743 时钟、CoreSight、GPIO 和运行态。探针 tap 恢复后重新载入 ABI 2 配对，物理 OCM 再次核对 80,620 B。最后 H743 SWD 识别和探针空闲检查通过。 [已装回的配对](../../../prebuilt/selectio-usb-split-20261123/README.md)
