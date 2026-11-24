# H743 SPI2 USB CDC 夹具验收

2026-11-24，`codex/selectio-efficiency`。目标为阿波罗 H743，测试接线为 P3-25/32/33/34 接 J7。用户授权将独立测试固件写入 H743 Flash，免备份，并要求 Zynq 加载支持 SPI 的 bit/ELF。H743 夹具采用 USB CDC 控制。拟使用 [RAW4 ABI 2 配对](../../../prebuilt/selectio-usb-split-raw4-20261123/README.md)，源端发送与 J7 EP10 接收由两条独立 USB 会话控制。

| 项目 | 结果 |
|---|---|
| H743 夹具构建 | ARM GCC 链接通过，39,064 B Flash 映像，DMA 缓冲区位于 AXI SRAM。原 CDC Golden 模式也通过构建。 |
| SPI 主机数字模型 | 100 MHz，四个 Mode，各对拍 1、5、4,096 B 双向数据。 |
| SPI 从机 AUX 数字模型 | 100 MHz，连续 73,727 B、环回卷、尾包、溢出、帧错注入及重新启动通过。 |
| SPI CDC 泵及端点事件模型 | 4,194,341 B，10 次提交重试、短包、重新启用、计数回卷、错误注入通过。见 ZL-326。 |
| 主机辅助工具 | Python 编译、四模式波形编码、三个采样宽度和八档 SPI2 分频验证通过。 |
| Zynq 加载与 H743 Flash | 等待 HS3 或 J7 USB 恢复。只读检查看到过 BOOT_MODE=0，DDR AP 事务出错。重新接线后 XSCT 无目标，Windows 也无 J7/HS3 地址。端口和集线器复位后原 H743 COM43 正常，J7/HS3 未恢复。 |
| 新接线实板与最高稳定速度 | 待测。未写目标 Flash，未下载 Zynq bit/ELF，未改动 QSPI。 |

[构建配对和复测入口](../../../prebuilt/targets/stm32h743-spi2-cdc-20261124/README.md) · [端口及离线证据](evidence.txt)

## HS3 驱动复装

2026-11-24，按用户要求只恢复 HS3 驱动，SPI 验收暂缓。使用 Xilinx SDK 2018.3 随附的 Digilent 签名安装程序。Windows 驱动库已导入同包的 Microsoft 签名 FTDI `ftdibus.inf` 2.12.28.0，发布名 `oem6.inf`，并确认为 `0403:6014`、序列号 `210299008529` 的最佳匹配。复查时该设备实例仍显示 `Disconnected`，XSCT 未列出 JTAG 目标。H743 原固件仍枚举为 `COM33`，Zynq 装载、目标 Flash 和 SPI 实板验收留待恢复后继续。

同日，更换 USB 端口后，Windows 已将 `oem6.inf` / `FTDIBUS` 绑定到 HS3，状态正常。XSCT 枚举到 `Digilent JTAG-HS3 210299008529`、`arm_dap` 和 `xc7z020`，两颗 Cortex-A9 显示 Running。此次只核对 JTAG 枚举，J7 探针 USB 仍未出现。

## H743 Flash 与 USB CDC 验证

按用户要求先完成烧录，再交由用户切换实体接线。HS3 临时加载 RAW4 ABI 2 的 bit/ELF，物理 MEM-AP0 对拍 OCM 执行段 80,668 B。读回 FCLK0 为 133,333,332 Hz，J7 USB 序列号 `12345678` 与 EP10 双向端点均已枚举。探针 QSPI 未写入。

通过 J7 SWD 1 MHz 确认 Cortex-M7 和 STM32H74x/75x，经 OpenOCD 写入 H743 Bank 1 首扇区。镜像从 `0x08000000` 起共 39,064 B，编程校验和独立读回 SHA-256 均通过。软件复位后 H743 以 `F055:7432`、`H743SPI0001` 枚举为 `COM52`。`PING`、`SPI INFO` 和 `SPI STOP` 响应通过，SPI2 内核时钟报告 200 MHz，总线处于空闲。此时仍是 SWD 接线，SPI 实际收发及限速待切线后验收。 [实板证据](flash-and-cdc.json)

## SPI 首轮定位与修订 2

用户换到 SPI 接线后，H743 的 COM52 正常。Zynq ARM DAP 报 `0x30000021`，降低 JTAG 频率和 SRST 后仍无法访问 APU。用户将 Zynq 断电重上后，JTAG 恢复，确认 BOOT_MODE=0、PL 电平转换关闭并处于复位。重新临时加载 RAW4 ABI 2，物理 OCM 匹配 80,668 B，使用同一 USB 序列号接着验收。

修订 1 的首轮 Mode 0 表现如下。

- H743 主机八档均在送出首字节前报 `MODF=0x200`，J7 收到 0 B。固件将 MASTER 和 SSM 写入时内部 SSI 仍为低。修订 2 提前置 SSI。
- J7 100 MHz 原生主机的 1、5、4,096 B 均有正确的 H743 RX 计数，数据不匹配。进一步对 Mode 0/3 和 1.5625/25/100 MHz 用 `00`、`FF`、`96` 做单字节对照，H743 全部收到 `FF`。根因待定位。
- 25 MHz 原始波形全双工在发钟前触发 DMA1 TX Stream 1 的 FEIF。当时 TX 已提交 16 B，RX 为 0。修订 2 为 TX 启用 DMA FIFO，并保留错误检查。

修订 2 已编译，新增 `SPI READ` 和 `SPI PINS`。修订 1 的失败证据保留。修订 2 的实板结论待重烧、接线和对拍。 [首轮数值](first-spi-attempt.json) · [修订 2 产物](../../../prebuilt/targets/stm32h743-spi2-cdc-r2-20261124/README.md)

## 修订 2 USB DFU 烧录

保留 SPI 接线，通过 H743 原生 USB 烧录。板载 CH340 控制线尝试未引起 CDC 断开，用户手动设置 BOOT0 并复位。Windows 枚举 ROM DFU `0483:df11`、序列号 `200364500000`，DFU alt 0 为 `0x08000000` 内部 Flash。烧前读取前 1,024 B 核对旧夹具身份。dfu-util 0.11 写入修订 2，共 39,392 B，全量独立读回一致。Option Bytes 未写入。

自动退出 DFU 时 dfu-util 返回 74，ROM DFU 仍枚举。待 BOOT0 回到 0 并复位后确认修订号、CDC 与 SPI 实测。 [烧录证据](revision2-usb-dfu.json) · [ST AN2606](https://www.st.com/resource/en/application_note/an2606-stm32-microcontroller-system-memory-boot-mode-stmicroelectronics.pdf)
