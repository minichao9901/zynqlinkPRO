# F103ZE 的 JTAG 100 MHz 同条件复测

2026-11-23，F103ZE CDC48 与 J7（USB 序列号 `12345678`，HS3 `210299008529`）。两套配对都经 JTAG/RAM 临时加载并核对物理 OCM。开工确认探针处于 JTAG 启动且 PL 隔离，收尾核对采集与调试队列空闲。F103ZE 只在带保护字和恢复夹具的 SRAM 窗口使用 HCLK128。TCK 由实际寄存器回读换算。原始数值、配对哈希、首错及恢复状态见 [evidence.json](evidence.json)。

## 对拍结果

| 配对与负载 | tap / slot / idle | 计时及窗口 | 读 / 写 MB/s |
|---|---:|---|---:|
| jtag200，1 KiB 驻留图案 | 16 / 36 / 11 | A9 分方向计时，3×10 秒交替 | 6.949 / 6.949 |
| 同一 jtag200 测试 | 16 / 36 / 11 | GO 至 DONE 的扫描计时 | 7.049 / 7.049 |
| 融合，1 KiB 对齐页 | 16 / 28 / 11 | PL 队列，1 秒交替的分方向计时 | 7.046 / 7.047 |
| 融合，4,032 B 跨页 | 16 / 28 / 11 | PL 队列，读写各 3×60 秒 | 7.043 / 7.043 |
| 同一融合长窗 | 16 / 28 / 11 | PS 内存服务 | 6.682 / 6.655 |
| 同一融合长窗 | 16 / 28 / 11 | PC 墙钟 | **6.406 / 6.162** |
| 此前同配对、同跨页负载 | 16 / 28 / 25 | PC 墙钟，读写各 3×60 秒 | 5.213 / 5.036 |

融合版实际 TCK 99,999,998 Hz。目标 DWT 核对约 128.076 MHz。原生长窗从 `0x20008020` 开始，4,032 B 被分成 992、1,024、1,024、992 B，USB 在途深度为 4。每轮读写分别对账，写及交替发送不同载荷，末块及保护字经低速回读。交替三轮的 PC 合计吞吐中位 **6.214 MB/s**，九轮有效 idle 均为 11，未触发自动退避。本次分方向 PC 吞吐比同配对的 idle25 档分别提高约 **22.9% / 22.4%**。

## 差距发生在哪一层

- **扫描帧与 idle。** 两版在 100 MHz 每个逻辑发射字均承载两个 TCK，稳态 DRW 帧均为 **43 + idle**。在同一个融合 bit 和 ELF 上，idle25 → 11 让 4,032 B 的 PL 队列每请求缩短约 144 µs。1,008 个数据字每字省 14 个 TCK，本身就解释约 141 µs。队列速度随 idle 改变与帧预算吻合。 [JTAG 帧预算](../../../../fpga/rtl/jtag200_arm_stream.v#L23) · [原 idle25 长窗](../rx-guard-jtag-idle25-long.json)
- **SelectIO 相位。** 独立版用 200 MHz DDR、8 位直收至 50 MHz CLKDIV。融合版的 TX 用 4 位字分两次送出。TDO 对 AUX/SWO 以 400 MHz DDR 取样，再取偶数样本并拼接两组形成 JTAG 的 8 位接收字。融合版固件还使用 TMS/TDI 预移。两套 slot 包含各自的发射和接收流水，不能按相同编号移植。融合版原样使用 slot36 在第一笔传输失败，slot26/27 失败，slot28/29/30 在 idle11 的 1 KiB 短窗均通过。对齐各自相位后，两套 1 KiB 的扫描时间折算都约为 **7.05 MB/s**。 [融合 PHY](../../../../fpga/rtl/selectio_debug_phy.v#L21) · [短筛原始状态](evidence.json)
- **PS 和主机搬运。** 独立 runner 预装图案，在 PL 逐字比较。融合版为每个 TAR 段搬运实际载荷，写侧先 CDMA 再发队列，读侧完成后搬出，页面之间逐段等待。PS 时间含这些操作。PC 墙钟再覆盖 USB 往返、帧处理和主机准备、收包及校验。同一批跨页数据由队列到 PC 的差额是读 **0.637**、写 **0.882 MB/s**，多个环节有重叠。 [融合 PS 块循环](../../../../firmware/xusbps_daplink_dma/DAP/Source/selectio_block.c#L376) · [主机计时](../../../../tools/selectio_pipeline_bench.py#L15)

当前证据将旧成绩差距定位到保守 idle 与端到端搬运。融合 SelectIO 的相位窗口需要独立校准，在本次共同 100 MHz 档未观察到扫描吞吐损失。结论限于本板与原生 SRAM 的已测组合。RTT、J-Scope 和默认档位沿用原验收。

## 复测与收尾

- 融合配对 `prebuilt/selectio-spi-cdc-rx-guard-20261123`。使用 `tools/selectio_f103_clock_accept.py --hclk-mhz 128 --enable-jtag` 包住 `tools/selectio_pipeline_bench.py --transport jtag --clock 100000000 --tap 16 --slot 28 --idle 11 --bytes 4032 --address 0x20008020 --depth 4 --rounds 3 --seconds 60`。两个入口均显式带 `--execute` 和各自的新输出目录。
- 独立配对 `E:/zynqlinkPRO-jtag200` 的 `prebuilt/jtag-only-f103ze-quad-20261119`。用 `jtag200_f103_fixture.py --hclk 128` 包住 `jtag200_f103_sweep.py --rates 100 --quad --idles 11 --seconds 10 --confirm-inline`。种子使用独立分支 `docs/validation/f103ze-jtag200-20261119/f103-128-quad-pilot-windows.json.gz`（解压为 `windows.json`，同目录放该次原始 `state.json`）。选择的历史点是 tap16/slot36。
- 独立 runner 三轮均通过扫描校验。旧夹具载回历史 USB 配对后，两次各等 12 秒仍找不到 J7，自动末页回读和恢复中止。随后 HS3 临时加载回融合配对，物理 OCM 核对 80,260 B。通过低速 DAP 独立核对末轮 1 KiB 载荷的 SHA-256、其余 3 KiB 和两侧保护字，再用原夹具独立恢复入口恢复。F103ZE 返回 CDC48 原时钟和原运行态，J7 的 RTT、HSS、DDR、CDMA 及两条调试队列空闲。原失败及恢复保留为 ZL-311。
- 本轮交付为融合分支的验收证据、问题表和地图。固定 EXE、Pages、Release 与冷启动验收均不适用。

[验收地图](../fusion-acceptance-map.svg) · [问题表 ZL-310](../../../项目问题跟踪列表.md) · [上轮的 100 MHz 分层对照](../../selectio-fusion-20261121/compare100/README.md#2026-11-23-的-jtag-100-mhz-原始数据复核)
