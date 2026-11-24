# H743 SPI2 USB CDC 夹具修订 2

SPI2 主机先置内部 SSI，再配置 MASTER 与软件 NSS。发送 DMA 使用 FIFO 缓冲。`SPI READ` 查询最后一次接收的前 24 B，`SPI PINS` 查询空闲时 GPIOI 低四位的输入电平，`SPI INFO` 报 `revision=2`。USB 身份、排针和传输命令同 [修订 1](../stm32h743-spi2-cdc-20261124/README.md)。

本次仍使用 480 MHz CPU 构建档和 200 MHz SPI2 内核时钟配置。文件哈希见 [manifest.json](manifest.json)。实板状态见 [验收记录](../../../docs/validation/h743-spi2-cdc-20261124/README.md)。
