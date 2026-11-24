# J7 SPI 从机输入滤波实验配对

FPGA 按 800 MS/s 接收 SCK 和 MOSI，抑制重复同极性 SCK 边沿。NSS 仍使用 400 MS/s 接收器。去选门限在 50 MHz 及以下为 13 个逻辑槽，在更高档为 5 个逻辑槽。PS ELF 和初始化 Tcl 来自 RAW4 ABI 2 配对。

请经 JTAG/RAM 临时加载。构建选项、时序和 SHA-256 见 [manifest.json](manifest.json)，验证记录见 [实板报告](../../docs/validation/h743-spi2-100mhz-20261124/README.md)。

```powershell
python -X utf8 toolbox.py probe-load --pair prebuilt/selectio-spi-pad-filter-v2-20261124 --dry-run
```
