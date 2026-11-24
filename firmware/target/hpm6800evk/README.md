# HPM6800EVK 验收固件

在资源管理器地址栏粘贴以下路径，即可看到编译好的固件。

```text
E:\zynqlinkPRO-efficiency\prebuilt\targets\efficiency-acceptance-20261124\hpm6800evk
```

每个子目录有 `fw.elf`、`fw.bin`、`fw.hex` 和 SHA-256 清单。调试和 Trace 使用与已加载映像匹配的 ELF。标为 **RAM 启动**或 **RAM 夹具**的项目按 [三板总表](../README.md) 的 RAM 加载方法使用。

| 目录 | 用途 | 文件 |
|---|---|---|
| `performance-axi` | 600 MHz，AXI SRAM 性能测试 | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/performance-axi/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/performance-axi/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/performance-axi/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/performance-axi/manifest.json) |
| `performance-ahb` | 600 MHz，AHB SRAM 性能测试 | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/performance-ahb/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/performance-ahb/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/performance-ahb/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/performance-ahb/manifest.json) |
| `dbg-a` | GDBStress 与 RTT 交互，Flash A | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/dbg-a/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/dbg-a/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/dbg-a/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/dbg-a/manifest.json) |
| `dbg-b` | 烧录与复位验签，Flash B | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/dbg-b/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/dbg-b/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/dbg-b/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/dbg-b/manifest.json) |
| `dbg-ram` | GDBStress，RAM 启动 | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/dbg-ram/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/dbg-ram/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/dbg-ram/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/dbg-ram/manifest.json) |
| `uart` | 物理 UART | [ELF](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/uart/fw.elf) · [BIN](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/uart/fw.bin) · [HEX](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/uart/fw.hex) · [清单](../../../prebuilt/targets/efficiency-acceptance-20261124/hpm6800evk/uart/manifest.json) |
