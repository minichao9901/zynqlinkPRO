# SelectIO 融合版 CDC 接收防护配对

FPGA bit 和初始化 Tcl 的 SHA-256 沿用已布线的 SPI 双边沿版本。SDK 2018.3 重建的 PS ELF 增加 CDC OUT 缓冲区返回值检查。生产回调的空描述符、接收长度边界和 IN 完成分流模型通过。定向实板 11 项和随后全功能套件 36 项全部通过。物理 MEM-AP0 核对 80,260 B OCM，USB 描述符逐项一致。 [清单](manifest.json) · [生产回调模型](../../docs/validation/spi-cdc-20261123/cdc-rx-receive-error-model.txt) · [定向实板](../../docs/validation/spi-cdc-20261123/rx-guard-board-smoke.json) · [完整实板](../../docs/validation/spi-cdc-20261123/rx-guard-full-board.json)

```powershell
$pair = 'prebuilt/selectio-spi-cdc-rx-guard-20261123'
python -X utf8 toolbox.py probe-load --pair $pair --dry-run
python -X utf8 toolbox.py project run board.accept -- --selectio --board f103ze --pair $pair --clock 100000000 --seconds 60 --rounds 3 --rtt-ring-bytes 8192 --rtt-chunk 2048
```

持续 100 MHz 的 SPI 从机接收转发仍待独立物理源实测。CAL-01 和 HCLK96/128 的性能结果按独立报告记录。
