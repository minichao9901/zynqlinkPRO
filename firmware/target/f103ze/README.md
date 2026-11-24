# STM32F103ZE 验收固件

在资源管理器地址栏粘贴以下路径，即可看到编译好的固件。

```text
E:\zynqlinkPRO-efficiency\firmware\target\f103ze\images
```

[镜像总清单](images/manifest.json)列出本板所有用途。每个子目录有 `fw.elf`、`fw.bin`、`fw.hex` 和 SHA-256 清单。调试和 Trace 使用与已加载映像匹配的 ELF。标为 **RAM 启动**或 **RAM 夹具**的项目按 [三板总表](../README.md) 的 RAM 加载方法使用。

本目录的交付镜像已核对离线构建，实板按实际加载的 ELF 单独签收。现有 F103ZE 实板报告使用 CDC48 Golden 和临时 SRAM 夹具，适用范围为 J7 探针回归。 [实板报告的验证范围](../../../docs/validation/f103ze-cases-20261124/README.md#本报告的验证范围)

| 目录 | 用途 | 文件 |
|---|---|---|
| `performance` | 128/128 MHz，SRAM 性能测试，RAM 启动 | [ELF](images/performance/fw.elf) · [BIN](images/performance/fw.bin) · [HEX](images/performance/fw.hex) · [清单](images/performance/manifest.json) |
| `dbg-a` | GDBStress 与 RTT 交互，Flash A | [ELF](images/dbg-a/fw.elf) · [BIN](images/dbg-a/fw.bin) · [HEX](images/dbg-a/fw.hex) · [清单](images/dbg-a/manifest.json) |
| `dbg-b` | 烧录与复位验签，Flash B | [ELF](images/dbg-b/fw.elf) · [BIN](images/dbg-b/fw.bin) · [HEX](images/dbg-b/fw.hex) · [清单](images/dbg-b/manifest.json) |
| `dbg-ram` | GDBStress，RAM 启动 | [ELF](images/dbg-ram/fw.elf) · [BIN](images/dbg-ram/fw.bin) · [HEX](images/dbg-ram/fw.hex) · [清单](images/dbg-ram/manifest.json) |
| `uart` | 物理 UART | [ELF](images/uart/fw.elf) · [BIN](images/uart/fw.bin) · [HEX](images/uart/fw.hex) · [清单](images/uart/manifest.json) |
| `swo` | 真实 SWO/ITM | [ELF](images/swo/fw.elf) · [BIN](images/swo/fw.bin) · [HEX](images/swo/fw.hex) · [清单](images/swo/manifest.json) |
| `spi` | SPI1 主从收发，RAM 启动 | [ELF](images/spi/fw.elf) · [BIN](images/spi/fw.bin) · [HEX](images/spi/fw.hex) · [清单](images/spi/manifest.json) |
| `etm` | 48/48 MHz、TRACECLK 24 MHz | [ELF](images/etm/fw.elf) · [BIN](images/etm/fw.bin) · [HEX](images/etm/fw.hex) · [清单](images/etm/manifest.json) |
| `etm-ram` | ETM SRAM 负载，RAM 启动 | [ELF](images/etm-ram/fw.elf) · [BIN](images/etm-ram/fw.bin) · [HEX](images/etm-ram/fw.hex) · [清单](images/etm-ram/manifest.json) |
| `etm-loop` | ETM SRAM 循环夹具 | [ELF](images/etm-loop/fw.elf) · [BIN](images/etm-loop/fw.bin) · [HEX](images/etm-loop/fw.hex) · [清单](images/etm-loop/manifest.json) |
| `etm-fault` | ETM RAM Fault 触发夹具 | [ELF](images/etm-fault/fw.elf) · [BIN](images/etm-fault/fw.bin) · [HEX](images/etm-fault/fw.hex) · [清单](images/etm-fault/manifest.json) |
