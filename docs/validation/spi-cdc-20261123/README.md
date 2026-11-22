# SelectIO SPI 从机接收与 CDC 验收

本轮在融合分支上增加 SPI MOSI → 原有 CDC COM 的接收转发。USB 接口、端点地址和 VID/PID 沿用现有融合版。SPI 主机、SWD/JTAG、RTT、HSS、UART/SWO 与 ETM 依然使用这一个融合镜像。

| 验证 | 范围 | 结果 |
|---|---|---|
| SPI 接收原语仿真 | 50、72.727、100 MHz，CPOL/CPHA 四模式，每档每模式八个输入初相，带 pad 偏斜模型 | 9,424 字节逐字通过，四次不足八位的片选中断正确报错并恢复，监听期间 SCK、CS、MOSI 高阻 |
| 共享 SelectIO 回归 | 真实 Cortex-M3 模型和 UNISIM，100 MHz JTAG/SWD 整页分方向校验 | 两条链路各 256 字读写通过，保持原有共享 PHY |
| 物理 CDC 数据通路 | F103ZE SRAM-only GPIO 源，四模式，原 J7 接线 | 构建并核对新配对后执行。源 SCK 报告以 DWT 配合字节数估算 |
| 100 MHz 实体线速 | 独立、可持续发送精确数据的 SPI 主机，三轮 60 秒 | 待独立源实测。100 MHz 满载目标为 12.5 MB/s 有效字节 |

[SPI 接收 XSim 完整结果](spi-slave-xsim.txt)。离线 DAP/IF4 回归覆盖 SPI 绑定、错误模式、短配置帧。描述符回归分别核对 legacy 与融合的端点地址、类型、包长和版本值。F103 GPIO 测试源的指令模型复核了四模式位序和 GPIO、AFIO、APB2 恢复。

首轮布局走线的同步 setup 为 +0.165 ns。旧输出用的 `pad_swclk` 时钟同时约束到新增外部 SCK 首级 ISERDES，报告一个 −1.073 ns 的 hold 违例。SPI 从机采用异步过采样，约束只豁免 L15 外部输入至该 ISERDES DDLY 的路径。原 SWCLK 输出和采样器之后的同步路径继续检查。最终版在同一路由检查点重做完整时序、DRC 和 bitgen。 [首轮失败路径](first-sck-sta-failure.txt)

SPI 同步引脚经 SelectIO 在 100 MHz 并行域得到每拍四个样本。接收器使用外部 SCK 的指定边沿，依 CS 边界重新对齐 MSB-first 字节。AUX 板载 64 KiB 环在数据复制到 PS DDR 后释放，DDR 消费指针在 USB IN 完成后确认。SPI CDC 短包在有待发数据约 0.5 ms 后提交，连续流优先聚合到 4 KiB。DTR、引脚所有权和 CDC 的实际排空分别核对。

复现入口见 [CLI](../../selectio/README.md#spi-从机接收转发到-com) 与 [Case 表](../../selectio/fusion-performance-cases.md)。时序收敛、目标和探针恢复以及全部功能用例以同一份 bit/ELF 的后续实测记录为准。
