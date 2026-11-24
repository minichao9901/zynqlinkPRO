# H743 未完成用例复验

2026-11-23，使用 J7 USB 序列号 `12345678`、HS3 `210299008529` 和 CDC OUT 防护融合配对，RAM 加载后物理 OCM 核对 80,260 B。H743 识别为 CPUID `0x411fc271`、DEV/REV `0x20036450`。实读 Flash 两段共 7,740 B，与 `stm32h743_dbgstress/fw.elf` 完全一致。应用以 HSI、标称 CPU/HCLK 64 MHz 运行，初始 PLL 均关闭。用户确认现场只接了标准调试线。 [验收证据](evidence.json)

## 四位 ETM 复测

所有 28 个硬件窗口均为 50 ms，低速 SWD 控制固定请求 10 MHz。PLL 试验以 HSI 为源，PLL1P 保持标称 CPU/HCLK 64 MHz，只用 PLL1R 分频设置 Trace 候选。表内 TRACECLK 是按分频计算的档位，未在探针引脚独立测频。

| 源配置 | GPIO 速度 | 窗口数 | 最少 parser 错误 | 判定 |
|---|---:|---:|---:|---|
| 原 HSI，TRACECLK 未测频 | 1、2、3 | 9 | 6 | 未通过 |
| PLL1R，10 MHz | 2 | 3 | 1,233 | 未通过 |
| PLL1R，13.333 MHz | 2 | 4 | 1,415 | 未通过 |
| PLL1R，20 MHz | 1、2、3 | 9 | 131 | 未通过 |
| PLL1R，24.615 MHz | 3 | 3 | 344 | 未通过 |

均收到实际 formatter 数据，错误出现在探针成帧阶段。FIFO 丢帧、DDR 写入错误、IDELAY ready 丢失均为零。原 HSI、GPIO 3、零 tap 的两次分别为 6 和 8 个 parser 错误。试过的 CLK/D0–D3 tap 对照没有得到零错误窗口，未晋级 3×1 秒。当前配对和目标程序尚未取得严格通过档。历史正式配对的 H743 25 MHz 记录与 F103ZE 融合配对的 36 MHz 各自有效。 [本轮逐点数据](evidence.json) · [历史 H743 25 MHz](https://github.com/minichao9901/zynqlinkPRO/blob/03b6a1dad8ee62aa7902b6bc37d0f0d9c3c3f451/docs/validation/h743-etm-ribbon-20261111/README.md) · [F103ZE 36 MHz](../rx-guard-etm36-long.json)

## 高速源用例

| 用例 | 当前判定 | 所需信号 |
|---|---|---|
| SPI-04，外部主机 100 MHz → J7 CDC | 待接线 | 将 H743 独立 SPI SCK、NSS、MOSI 接到 J7 29、31、25，共地。需预置发送夹具及 60 秒连续已知载荷。 |
| SPI-02，J7 主机 100 MHz 四模式全速回包 | 待独立高速从机 | ST DS12110 的高速输入规格适用于 SPI 从机接收。3.3 V 下表列 SPI 从机发送/全双工上限 31 MHz，H743 不能作为额定 100 MHz 全速回包的验收源。 |
| IO-03，独立连续 100 Mbit/s Manchester | 待合格码源 | J7 L14 需要 200 Mchip/s 的混合码型及源端计数。现场 dbgstress 没有该连续码流，当前 HSI 64 MHz 配置也未提供该速率。 |

[ST DS12110 SPI 动态规格](https://www.st.com/resource/en/datasheet/stm32h743ai.pdf) · [J7 引脚与 SPI CDC 验收口径](../../../selectio/README.md#spi-从机接收并转发到-cdc)

## 现场收尾

第一次 RAM 加载通过 OCM 核对，但探针 USB 未枚举，A9 取样 PC 落在 `_exit`。重新加载同一配对、A9 进入 `chry_dap_handle` 后，J7 USB 和 COM34 恢复。现象已登记到 ZL-060，具体退出路径待定位。H743 回到原 HSI/PLL 配置与运行态，PE2–PE6 和 CoreSight 恢复检查通过。Trace 五路回到禁用且零 tap，J7 的 RTT/HSS、捕获、DDR 和 CDMA 已确认空闲。未写目标 Flash 或探针 QSPI。完整采集文件、测试夹具与日志留在本机 `build/h743-open-cases-20261123/`。
