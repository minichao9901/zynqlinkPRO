# STM32H743 验收固件

在资源管理器地址栏粘贴以下路径，即可看到编译好的固件。

```text
E:\zynqlinkPRO-efficiency\prebuilt\targets\efficiency-acceptance-20261124\h743
```

每个子目录有 `fw.elf`、`fw.bin`、`fw.hex` 和 SHA-256 清单。调试和 Trace 使用与已加载映像匹配的 ELF。标为 **RAM 启动**或 **RAM 夹具**的项目按 [三板总表](../README.md) 的 RAM 加载方法使用。

| 目录 | 用途 | 文件 |
|---|---|---|
| `performance-axi` | 480/240 MHz，AXI SRAM 性能测试 | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/performance-axi/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/performance-axi/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/performance-axi/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/performance-axi/manifest.json) |
| `performance-dtcm` | 480/240 MHz，DTCM 性能测试 | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/performance-dtcm/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/performance-dtcm/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/performance-dtcm/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/performance-dtcm/manifest.json) |
| `dbg-a` | GDBStress 与 RTT 交互，Flash A | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/dbg-a/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/dbg-a/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/dbg-a/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/dbg-a/manifest.json) |
| `dbg-b` | 烧录与复位验签，Flash B | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/dbg-b/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/dbg-b/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/dbg-b/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/dbg-b/manifest.json) |
| `dbg-ram` | GDBStress，RAM 启动 | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/dbg-ram/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/dbg-ram/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/dbg-ram/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/dbg-ram/manifest.json) |
| `uart` | 物理 UART | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/uart/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/uart/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/uart/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/uart/manifest.json) |
| `swo` | 真实 SWO/ITM | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/swo/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/swo/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/swo/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/swo/manifest.json) |
| `swo-source` | SWO 高速合成码源，RAM 启动 | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/swo-source/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/swo-source/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/swo-source/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/swo-source/manifest.json) |
| `spi` | SPI2 主从收发 | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/spi/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/spi/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/spi/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/spi/manifest.json) |
| `etm` | 60/60 MHz、TRACECLK 20 MHz | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/etm/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/etm/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/etm/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/h743/etm/manifest.json) |
