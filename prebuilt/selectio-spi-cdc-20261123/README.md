# SelectIO 融合探针与 SPI 从机 CDC

该目录包含完成 133.333 MHz 时序复核的融合 bit、匹配 PS ELF 和 PS 初始化脚本。探针 12345678 经 JTAG/RAM 加载后，物理 MEM-AP0 核对 80,228 B OCM 执行段并确认 USB 描述符。F103ZE GPIO 源四个 SPI 模式各转发 16,384 B 到 COM34，线频为 DWT 窗口平均约 1.35–1.64 MHz。100 MHz 接收已通过 UNISIM 仿真，独立 SPI 主机的 100 MHz 持续实板验收待完成。

```powershell
$pair = 'prebuilt/selectio-spi-cdc-20261123'
python -X utf8 toolbox.py probe-load --dry-run --bit "$pair/probe.bit" --zynq-elf "$pair/application.elf"
python -X utf8 toolbox.py project run board.accept -- --selectio --board f103ze --pair $pair --only spi-cdc
```

实际执行用单独的 `--execute` 板测入口。另见 [CLI 和接线](../../docs/selectio/README.md#spi-从机接收转发到-com) · [验收记录](../../docs/validation/spi-cdc-20261123/README.md) · [哈希和构建选项](manifest.json)。
