# STM32F103ZE 验收固件

在资源管理器地址栏粘贴以下路径，即可看到编译好的固件。

```text
E:\zynqlinkPRO-efficiency\prebuilt\targets\efficiency-acceptance-20261124\f103ze
```

每个子目录有 `fw.elf`、`fw.bin`、`fw.hex` 和 SHA-256 清单。调试和 Trace 使用与已加载映像匹配的 ELF。标为 **RAM 启动**或 **RAM 夹具**的项目按 [三板总表](../README.md) 的 RAM 加载方法使用。

| 目录 | 用途 | 文件 |
|---|---|---|
| `performance` | 128/128 MHz，SRAM 性能测试，RAM 启动 | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/performance/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/performance/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/performance/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/performance/manifest.json) |
| `dbg-a` | GDBStress 与 RTT 交互，Flash A | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/dbg-a/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/dbg-a/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/dbg-a/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/dbg-a/manifest.json) |
| `dbg-b` | 烧录与复位验签，Flash B | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/dbg-b/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/dbg-b/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/dbg-b/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/dbg-b/manifest.json) |
| `dbg-ram` | GDBStress，RAM 启动 | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/dbg-ram/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/dbg-ram/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/dbg-ram/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/dbg-ram/manifest.json) |
| `uart` | 物理 UART | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/uart/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/uart/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/uart/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/uart/manifest.json) |
| `swo` | 真实 SWO/ITM | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/swo/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/swo/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/swo/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/swo/manifest.json) |
| `spi` | SPI1 主从收发，RAM 启动 | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/spi/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/spi/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/spi/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/spi/manifest.json) |
| `etm` | 48/48 MHz、TRACECLK 24 MHz | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm/manifest.json) |
| `etm-ram` | ETM SRAM 负载，RAM 启动 | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm-ram/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm-ram/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm-ram/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm-ram/manifest.json) |
| `etm-loop` | ETM SRAM 循环夹具 | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm-loop/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm-loop/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm-loop/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm-loop/manifest.json) |
| `etm-fault` | ETM RAM Fault 触发夹具 | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm-fault/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm-fault/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm-fault/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/f103ze/etm-fault/manifest.json) |
