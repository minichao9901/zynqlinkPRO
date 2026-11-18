# J7 纯 SWD SelectIO 实验

2026-11-18，分支 `codex/swd-only-200mhz`，基线 `03b6a1da`。本轮验收范围为 Cortex-M3 模型、综合与布线。

## 设计

PL 源清单只有 SWD PHY、事务引擎、批处理、寄存器和 PS7 GP0 控制通路。PS 裸机 ELF 在 OCM 中控制 FCLK1、采样设置和时钟档位，只在收到邮箱请求后改档。J7 只使用 SWCLK（29/L15）、SWDIO（31/L16）和保持高电平的 nSRST（23/M14）。该配对没有目标 JTAG、HSS、RTT 或 ETM 模块。

两颗 4:1 DDR OSERDESE2 输出 SWCLK 和 SWDIO。SWDIO 的 TQ 同步串行化四个三态控制位，IOBUF 的输入经 IDELAYE2 回到 ISERDESE2。最高档为 200 MHz 串行 CLK、100 MHz CLKDIV，每个并行字发送两个 SWCLK 周期，周期 5 ns。160 MHz 档将 FCLK1 从 50 MHz 换到 40 MHz。50 和 100 MHz 档延长高、低半周期。ACK 和读数据分别选择接收时隙，IDELAY tap 单独可调。

事务按 ADIv5 单目标 SWD 执行。请求、ACK、数据按段送至 PHY，ACK 决策时 SWCLK 停在低电平，逻辑保持 SWDIO 当前归属。标准换向周期为一拍，WAIT/FAULT 无数据阶段。批处理只重试 WAIT，遇到 FAULT、无效 ACK 或读奇偶错误停止，且不执行后续描述符。一个批次最多 512 条命令。测试中的 MEM-AP 按 1 KiB 地址边界分块，并通过 RDBUFF 刷新写入及最后一个 posted read。

## 复现

```powershell
python -X utf8 toolbox.py project run swd200 -- sim --mhz 200
python -X utf8 toolbox.py project run swd200 -- matrix
python -X utf8 toolbox.py project run swd200 -- build
```

XSim 2018.3 使用仓库中的 Cortex-M3 DesignStart 模型和 Vivado 自带的 MMCM、SelectIO 原语库。测试通过 AXI-Lite 写命令并读取结果，从 AXI 提交到完成计算读写吞吐，命令预填和结果搬运在计时窗外。台架中 SWCLK 与主机驱动的 SWDIO 直接接入模型，配置的延时施加于目标返回的数据和驱动使能。每次检查 DPIDR、DP 上电握手、AP、实际模型 SRAM、posted read、脉宽、SWDIO 换向及奇偶故障后的批处理隔离和 DPIDR 恢复。

## CM3 仿真

HCLK 100 MHz，返程附加延时 0.8 ns，ACK/数据采样时隙 12，tap 0，idle 两拍。每档三轮，每轮完整写入及回读 1 KiB。WAIT 计数包含初始化及吞吐测试，批处理重试后完成全部命令。

| SWCLK MHz | 读 MB/s | 写 MB/s | WAIT 重试 | 结果 |
|---:|---:|---:|---:|---|
| 50 | 3.5054 | 3.5053 | 6 | 通过 |
| 100 | 6.0904 | 6.0901 | 6 | 通过 |
| 160 | 7.7185 | 7.7075 | 8 | 通过 |
| 200 | 9.6470 | 9.6261 | 9 | 通过 |

200 MHz 通过该测试矩阵的最高设定频率。接收相位失配最初在时隙 16 上复现，已记录 [ZL-265](../../项目问题跟踪列表.md)。

[四档及首次失败的仿真摘录](nominal-sim.txt)

## AXI-Lite 与 PS 邮箱

地址基准为 `0x40000000`。寄存器和缓冲区按 32 位对齐。写命令、切换档位和改采样前等待状态位 5。启动前还需状态位 0 为 1。批次结束后等待状态位 2、5 同时为 1，再读摘要和结果。

| 偏移 | 用途 |
|---|---|
| `0x0000` | ID `0x53323030` |
| `0x0004` | 状态位 0 就绪、1 运行、2 有结果、3 延时校准、4 时钟保持、5 可接收下一批 |
| `0x0008` | 位 0 保持 PHY 复位 |
| `0x000c` | 位 17:14 idle（1–15 拍），13:8 读数据采样时隙，7:2 ACK 采样时隙，1:0 档位（0 为 50 MHz，1 为 100 MHz，2 为全速） |
| `0x0010` | 写 1–512 启动对应条数的命令 |
| `0x0014` | 位 31:16 WAIT 重试数、15 时钟失锁、14 批次失败、13 奇偶错误、12:10 ACK、9:0 已完成条数 |
| `0x0018` | IDELAY tap（0–31） |
| `0x1000 + 8*i` | 第 i 条命令。位 4 为 1 时发送 SWD 切换及复位序列。其余命令位 3:0 是 A[3:2]、RnW、APnDP |
| `0x1004 + 8*i` | 第 i 条命令的写数据 |
| `0x2000 + 4*i` | 第 i 条已完成命令的读数据 |

PS 邮箱从低 OCM `0x2ff00` 开始，依次各占一字。字段为签名、请求序号、档位索引（50/100/160/200 MHz 对应 0/1/2/3）、采样设置（低两位由固件填写，调用者置零）、tap、响应序号、错误码、FCLK1 寄存器读回值和 SWCLK 计算值。默认进 50 MHz 档。写入参数后更新请求序号，等响应序号匹配，并检查错误码为零。
