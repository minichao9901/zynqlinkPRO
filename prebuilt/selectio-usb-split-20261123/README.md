# J7 SelectIO 独立 USB 端点配对

本配对包含融合 PL bitstream、对应 PS ELF 和初始化 Tcl，使用原生 USB ABI 2。PS 将控制、SRAM、RTT、J-Scope、ETM 与 SPI 分在独立的数据端点，SWO 使用标准 CMSIS-DAP Bulk IN。端点数据缓冲和采集队列置于 PS DDR。

| 文件 | 内容 |
|---|---|
| `probe.bit`、`ps7_init.tcl` | 复用已验收的 [融合 PL 配对](../selectio-spi-cdc-rx-guard-20261123/README.md) |
| `application.elf` | 独立端点版 PS 软件 |
| `verified_clock.json`、`ocm-layout.json` | 复用 bit 的实现时序和当前 PS 的 OCM 预算 |
| `manifest.json`、`ps-build.json` | 加载文件 SHA-256、源码及编译选项 |

```powershell
$pair = 'prebuilt/selectio-usb-split-20261123'
python -X utf8 toolbox.py probe-load --pair $pair --dry-run
python -X utf8 toolbox.py probe-load --pair $pair --out build/split-ram-load
python -X utf8 toolbox.py selectio --serial 12345678 info
```

以上为 JTAG/RAM 临时配对。 [接口与协议](../../docs/selectio-native.md) · [H743 定向验收](../../docs/validation/usb-split-20261123/README.md)
