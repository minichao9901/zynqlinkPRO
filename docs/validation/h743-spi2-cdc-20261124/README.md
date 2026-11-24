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
