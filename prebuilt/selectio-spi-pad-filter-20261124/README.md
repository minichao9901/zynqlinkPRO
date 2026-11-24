# J7 SPI 从机输入滤波实验配对

FPGA 使用 800 MS/s SCK 和 MOSI 输入，并对 NSS 窄高和重复同极性 SCK 边沿做数字滤波。该工程选项与原版 SelectIO 分开构建。PS ELF 和初始化 Tcl 来自 RAW4 ABI 2 配对。

请经 JTAG/RAM 临时加载。构建选项、时序和 SHA-256 见 [manifest.json](manifest.json)，验证记录见 [实板报告](../../docs/validation/h743-spi2-100mhz-20261124/README.md)。

```powershell
python -X utf8 toolbox.py probe-load --pair prebuilt/selectio-spi-pad-filter-20261124 --dry-run
```
