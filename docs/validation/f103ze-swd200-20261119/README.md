# F103ZE 实板 SWD 扫频与历史性能对照

2026-11-19，J7 HS3 `210299008529`，目标 CDC `F103CDC0001`。SWD 读回 DPIDR `0x1ba01477`、CPUID `0x411fc231`、DEV/REV `0x10036414`、Flash 容量字 512 KiB，对应高密度 64 KiB SRAM。起始 HCLK 48 MHz，RCC_CFGR `0x51040a`，应用运行。使用与仿真候选相同的 bit，实板计时 ELF 经物理 MEM-AP0 校验 2,756 B 执行段。

96、128 MHz 为临时超频。USB 外设门钟，APB1 /4、APB2 /2。目标核在 SRAM 测速时暂停，仅在 DWT 独立验频期间运行 SRAM 自循环。DWT 分别测得约 96.03、128.06 MHz，检查 SRAM 夹具与核心寄存器恢复。8 MHz HSE ×16 为当前标准 PLL 配置上限。48 MHz 对照保持运行态。SWCLK 由探针 IO PLL、FCLK 分频和串行时隙推算，未经示波器测量。

## 基线配对

每轮在 `0x20008000` 交替写入原数据与逐位反相图案并回读，每字比对。100 MHz 使用 tap8、ACK 和数据时隙 20、idle 2。三个目标时钟下，该档均完成三轮各 16 MiB 写入及 16 MiB 读回。128 MHz HCLK 的分频测试覆盖 50、66.667、100、120.755 至 200 MHz 的可选档，稳定窗最高通过 100 MHz。160 MHz 部分相位可识别 DPIDR，200 MHz 同相位初筛无法稳定识别。各点的身份检查、失败摘要和持续窗口见原始记录。

| 目标 HCLK | SWCLK | 批提交到完成，读 / 写 MB/s | A9 含准备和校验，读 / 写 MB/s | 同日历史配对 USB 66.667 MHz，读 / 写 MB/s |
|---|---:|---:|---:|---:|
| 48 MHz | 100 MHz | 7.14 / 7.43 | 3.65 / 4.37 左右 | 5.185 / 4.680 |
| 96 MHz | 100 MHz | 7.15 / 7.45 | 3.65 / 4.37 | 5.244 / 4.974 |
| 128 MHz | 100 MHz | 7.15 / 7.45 | 3.65 / 4.37 | 5.070 / 4.827 |

历史最高记录为 66.667 MHz 下读 5.3605、写 5.2527 MB/s。J7 归档配对在 48 MHz HCLK 原测为 5.333 / 5.239。上表同日 USB 复测采用 2 KiB、队列 32、每方向 256 块、三次中位，另有 3 秒交替窗口。新配对经 A9/GP0，1 KiB/块、单批次，没有 PC USB 数据路径。[历史全局最佳](../performance-limits-20261101/README.md) · [历史 J7 配对](../j7-swd66666-20261106/README.md)

128 MHz HCLK、100 MHz SWCLK 下，每 KiB 批读时间 143.21 µs，A9 全流程 280.21 µs，逐字 MMIO 读回比对 53.90 µs，余约 83.10 µs 为排命令和控制。写分别为 137.55 与 234.31 µs，TAR 保护约 4.20 µs，余约 92.56 µs 主要来自写命令和载荷填表。同频 66.667 MHz 的批读写为 4.952 / 5.067 MB/s，低于历史全局记录。每块重复发送 TAR、RDBUFF、状态检查，保留 2 拍 idle，并有段间停钟。100 MHz 的批速度超过历史记录，端到端差额主要在 A9/GP0 搬运。计时器为 Zynq 全局定时器，按 PS ARM PLL 与分频的半 CPU 时钟约 333.333 MHz 换算。[AMD UG585](https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/Introduction?contentId=2Ilh3ZGEcOptlhwX4Eqrhw)

三种 HCLK 均由独立历史 USB 配对最终复核 4 KiB SRAM、两端哨兵、RCC、Flash 等待周期及原运行态。目标 Flash 和探针 QSPI 写入均为零。首轮 96 MHz 在写探针邮箱时遇到 HS3 FT_Write 错误，重连 USB 后独立恢复，重跑通过。交付限本地分支，固定 EXE、远端 main、Pages、Release 与 QSPI 冷启动为范围外。

[128 MHz 逐项数据](hclk128-timing.json) · [128 MHz 全部频点](hclk128-windows.txt) · [128 MHz 恢复](hclk128-target.json) · [实板配对](../../../prebuilt/swd-only-200mhz-f103-bench-20261119/manifest.json)
