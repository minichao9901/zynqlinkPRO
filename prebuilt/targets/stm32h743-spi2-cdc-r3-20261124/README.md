# H743 SPI2 USB CDC 夹具修订 3

修正连续发包时的 TX DMA 计数。SPI 停钟后先读取实际回卷和 NDTR，再停 DMA，避免把停通道产生的 TCIF 计作额外 16 KiB。

`SPI DRIVE 0|1|2|3` 在空闲时设置 H743 未来传输的 GPIO 输出驱动速度，默认 3。`SPI INFO` 报 `revision=3` 和 `drive`。测试命令及接线沿用 [修订 2](../stm32h743-spi2-cdc-r2-20261124/README.md)。构建哈希见 [manifest.json](manifest.json)，实板状态见 [验收记录](../../../docs/validation/h743-spi2-cdc-20261124/README.md)。
