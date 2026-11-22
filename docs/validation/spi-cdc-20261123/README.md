# SelectIO SPI 从机接收与 CDC 验收

本轮在融合分支上增加 SPI MOSI → 原有 CDC COM 的接收转发。USB 接口、端点地址和 VID/PID 沿用现有融合版。SPI 主机、SWD/JTAG、RTT、HSS、UART/SWO 与 ETM 依然使用这一个融合镜像。

| 验证 | 范围 | 结果 |
|---|---|---|
| SPI 接收原语仿真 | 50、72.727、100 MHz，CPOL/CPHA 四模式，每档每模式八个输入初相，带 pad 偏斜模型 | 9,424 字节逐字通过，四次不足八位的片选中断正确报错并恢复，监听期间 SCK、CS、MOSI 高阻 |
| 共享 SelectIO 回归 | 真实 Cortex-M3 模型和 UNISIM，100 MHz JTAG/SWD 整页分方向校验 | 两条链路各 256 字读写通过，保持原有共享 PHY |
| 物理 CDC 数据通路 | F103ZE SRAM-only GPIO 源，四模式，原 J7 接线 | 每模式 16,384 B，合计 65,536 B 全匹配，零溢出、帧错、尾差。DWT 窗口平均 SCK 为 mode 0/2 约 1.35 MHz，mode 1/3 约 1.64 MHz |
| 100 MHz 实体线速 | 独立、可持续发送精确数据的 SPI 主机，三轮 60 秒 | 待独立源实测。100 MHz 满载目标为 12.5 MB/s 有效字节 |

[SPI 接收 XSim 完整结果](spi-slave-xsim.txt)。离线 DAP/IF4 回归覆盖 SPI 绑定、错误模式、短配置帧。描述符回归分别核对 legacy 与融合的端点地址、类型、包长和版本值。F103 GPIO 测试源的指令模型复核了四模式位序和 GPIO、AFIO、APB2 恢复。

首轮布局走线的同步 setup 为 +0.165 ns。旧输出用的 `pad_swclk` 时钟同时约束到新增外部 SCK 首级 ISERDES，报告一个 −1.073 ns 的 hold 违例。SPI 从机采用异步过采样，约束只豁免 L15 外部输入至该 ISERDES DDLY 的路径。原 SWCLK 输出和采样器之后的同步路径继续检查。同一路由检查点按 `--selectio --selectio-variable --etm400` 的环境重验，133.333 MHz setup/hold 裕量为 **+0.165/+0.051 ns**，DRC 与 bitgen 通过。 [首轮失败路径](first-sck-sta-failure.txt) · [归档配对](../../../prebuilt/selectio-spi-cdc-20261123/manifest.json)

首轮实板的 mode 0/1 在 Windows WinUSB 占用期间重新枚举 CMSIS-DAP 失败，尚未启动目标源。夹具将 DAP 的准备和恢复置于 WinUSB/COM 采集期之外。复验四模式全部通过，COM34 释放，原目标 SRAM、核心、GPIO、AFIO、APB2 和运行态恢复。新配对由 HS3 临时加载，物理 MEM-AP0 核对 80,228 B OCM 执行段。实机枚举的 VID/PID、接口和端点与原融合版一致。 [首次失败](first-dap-open-failure.txt) · [首次汇总](first-board-attempt.json) · [四模式结果](spi-cdc-four-modes.json) · [恢复与通过汇总](spi-cdc-board-summary.json) · [OCM 核对](probe-ocm.json) · [USB 枚举](usb-info.json)

SPI 同步引脚经 SelectIO 在 100 MHz 并行域得到每拍四个样本。接收器使用外部 SCK 的指定边沿，依 CS 边界重新对齐 MSB-first 字节。AUX 板载 64 KiB 环在数据复制到 PS DDR 后释放，DDR 消费指针在 USB IN 完成后确认。SPI CDC 短包在有待发数据约 0.5 ms 后提交，连续流优先聚合到 4 KiB。DTR、引脚所有权和 CDC 的实际排空分别核对。

复现入口见 [CLI](../../selectio/README.md#spi-从机接收转发到-com) 与 [Case 表](../../selectio/fusion-performance-cases.md)。时序收敛、目标和探针恢复以及全部功能用例以同一份 bit/ELF 的后续实测记录为准。
