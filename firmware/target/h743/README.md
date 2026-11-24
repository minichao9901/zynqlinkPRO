# STM32H743 验收固件

在资源管理器地址栏粘贴以下路径，即可看到编译好的固件。

```text
E:\zynqlinkPRO-efficiency\firmware\target\h743\images
```

[镜像总清单](images/manifest.json)列出本板所有用途。每个子目录有 `fw.elf`、`fw.bin`、`fw.hex` 和 SHA-256 清单。调试和 Trace 使用与已加载映像匹配的 ELF。标为 **RAM 启动**或 **RAM 夹具**的项目按 [三板总表](../README.md) 的 RAM 加载方法使用。

| 目录 | 用途 | 文件 |
|---|---|---|
| `performance-axi` | 480/240 MHz，AXI SRAM 性能测试 | [ELF](images/performance-axi/fw.elf) · [BIN](images/performance-axi/fw.bin) · [HEX](images/performance-axi/fw.hex) · [清单](images/performance-axi/manifest.json) |
| `performance-dtcm` | 480/240 MHz，DTCM 性能测试 | [ELF](images/performance-dtcm/fw.elf) · [BIN](images/performance-dtcm/fw.bin) · [HEX](images/performance-dtcm/fw.hex) · [清单](images/performance-dtcm/manifest.json) |
| `dbg-a` | GDBStress 与 RTT 交互，Flash A | [ELF](images/dbg-a/fw.elf) · [BIN](images/dbg-a/fw.bin) · [HEX](images/dbg-a/fw.hex) · [清单](images/dbg-a/manifest.json) |
| `dbg-b` | 烧录与复位验签，Flash B | [ELF](images/dbg-b/fw.elf) · [BIN](images/dbg-b/fw.bin) · [HEX](images/dbg-b/fw.hex) · [清单](images/dbg-b/manifest.json) |
| `dbg-ram` | GDBStress，RAM 启动 | [ELF](images/dbg-ram/fw.elf) · [BIN](images/dbg-ram/fw.bin) · [HEX](images/dbg-ram/fw.hex) · [清单](images/dbg-ram/manifest.json) |
| `uart` | 物理 UART | [ELF](images/uart/fw.elf) · [BIN](images/uart/fw.bin) · [HEX](images/uart/fw.hex) · [清单](images/uart/manifest.json) |
| `swo` | 真实 SWO/ITM | [ELF](images/swo/fw.elf) · [BIN](images/swo/fw.bin) · [HEX](images/swo/fw.hex) · [清单](images/swo/manifest.json) |
| `swo-source` | SWO 高速合成码源，RAM 启动 | [ELF](images/swo-source/fw.elf) · [BIN](images/swo-source/fw.bin) · [HEX](images/swo-source/fw.hex) · [清单](images/swo-source/manifest.json) |
| `spi` | SPI2 主从收发 | [ELF](images/spi/fw.elf) · [BIN](images/spi/fw.bin) · [HEX](images/spi/fw.hex) · [清单](images/spi/manifest.json) |
| `etm` | 60/60 MHz、TRACECLK 20 MHz | [ELF](images/etm/fw.elf) · [BIN](images/etm/fw.bin) · [HEX](images/etm/fw.hex) · [清单](images/etm/manifest.json) |
