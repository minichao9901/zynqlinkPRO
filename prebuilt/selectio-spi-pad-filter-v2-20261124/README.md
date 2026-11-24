# J7 SPI 从机输入滤波实验配对

FPGA 按 800 MS/s 接收 SCK 和 MOSI，抑制重复同极性 SCK 边沿。NSS 仍使用 400 MS/s 接收器。去选门限在 50 MHz 及以下为 13 个逻辑槽，在更高档为 5 个逻辑槽。PS ELF 和初始化 Tcl 来自 RAW4 ABI 2 配对。

请经 JTAG/RAM 临时加载。构建选项、时序和 SHA-256 见 [manifest.json](manifest.json)，验证记录见 [实板报告](../../docs/validation/h743-spi2-100mhz-20261124/README.md)。

```powershell
python -X utf8 toolbox.py probe-load --pair prebuilt/selectio-spi-pad-filter-v2-20261124 --dry-run
```

现有杜邦线、H743 SPI2 夹具修订 4 和三线速度 1 已通过 50 MHz 四模式各三轮 60 秒，共 4,499,965,791 B。100 MHz 的跳变数据仍未过逐字节短测。

```powershell
python -X utf8 toolbox.py probe-load --pair prebuilt/selectio-spi-pad-filter-v2-20261124
python -X utf8 tools/h743_spi_accept.py --j7-slave-only --dividers 4 --edge 1 1 1 --seconds 60 --repeats 3 --out build/spi-filter-v2-50mhz
```
