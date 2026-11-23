# J7 SelectIO 独立端点配对（RAW4 ETM）

同一个融合 bitstream 提供 SWD、JTAG、SPI、串口、SWO 和 ETM。使用原生 USB ABI 2，控制、SRAM、RTT、J-Scope、ETM 和 SPI 保持独立端点。ETM 采用主线验证过的 RAW4 单沿 200 MHz 接收路径，采集窗口连续存入 PS DDR，经 EP9 下载。

| 项目 | 本配对 |
|---|---|
| FPGA | Vivado 2018.3，`--selectio --selectio-variable`，FCLK0 133.333 MHz，建立 +0.057 ns，保持 +0.039 ns |
| Zynq PS | XUsbPs DMA，J7 引脚，DDR 数据队列，JTAG 队列地址窗口检查 |
| 实板 ETM | H743 历史 CDC，CPU/HCLK 60 MHz、TRACECLK 20 MHz、SWD 10 MHz，10/200/500/1000 ms 各三轮 |
| 文件身份 | `manifest.json` 记录 bit、ELF 和 PS 初始化 Tcl 的 SHA-256，加载后核对物理 OCM |

```powershell
$pair = 'prebuilt/selectio-usb-split-raw4-20261123'
python -X utf8 toolbox.py probe-load --pair $pair --dry-run
python -X utf8 toolbox.py probe-load --pair $pair --out build/selectio-raw4-ram-load
python -X utf8 toolbox.py selectio --serial 12345678 info
```

此配对用于 HS3 JTAG/RAM 临时加载。H743 历史 CDC 验收配对、数据、工况和范围见[实板报告](../../docs/validation/h743-cdc-golden-requal-20261123/README.md)。
