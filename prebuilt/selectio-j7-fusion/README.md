# J7 SelectIO 融合固件

同一份 bit/ELF 同时包含 CMSIS-DAP、100 MHz JTAG/SWD、双协议 RTT 与变量采样、UART/SWO、四线 SPI 和主线并行 ETM。F103ZE 的输入延迟、采样档和空闲周期见 [manifest](manifest.json)。[完整 CLI 与接线](../../docs/selectio/README.md) · [板卡验收](../../docs/validation/selectio-fusion-20261121/README.md)

在本工作树根目录运行。先预览文件身份，再通过 HS3 写入探针易失配置。证据目录使用新名称。

```powershell
python -X utf8 toolbox.py probe-load --selectio --dry-run
python -X utf8 toolbox.py probe-load --selectio --out build/my-selectio-load
python -X utf8 toolbox.py selectio --serial 12345678 info
```

| 文件 | 用途 |
|---|---|
| probe.bit | XC7Z020 PL 配置 |
| application.elf | 探针 Cortex-A9 的 USB、调度和错误恢复固件 |
| ps7_init.tcl | 同一 PL 工程生成的 PS 初始化参数 |
| manifest.json | 源版本、SHA-256、功能字、时钟、板卡档位与验收索引 |
| ps-build.json | PS 构建选项、BSP、链接脚本与各源码哈希 |
| verified_clock.json | Vivado 路由验收数据。SWCLK_max_Hz 字段来自兼容引擎的 FCLK0/2；融合高速引擎使用独立 FCLK1 和 MMCM。 |

重新构建时，PL 指定 `fpga/build_dma.tcl -tclargs --selectio`，PS 指定本目录 manifest 的编译选项。调试时传给 GDB 或 Trace 的 `--elf` 是目标 MCU 的符号文件。
