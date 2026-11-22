# SelectIO 融合版 CDC 接收防护配对

FPGA bit 和初始化 Tcl 的 SHA-256 沿用已布线的 SPI 双边沿版本。SDK 2018.3 重建的 PS ELF 增加 CDC OUT 缓冲区返回值检查。生产回调的空描述符、接收长度边界和 IN 完成分流模型通过。定向实板 11 项通过，包括物理 MEM-AP0 读回 80,260 B OCM；完整套件正在复验。 [清单](manifest.json) · [生产回调模型](../../docs/validation/spi-cdc-20261123/cdc-rx-receive-error-model.txt) · [定向实板](../../docs/validation/spi-cdc-20261123/rx-guard-board-smoke.json)

```powershell
$pair = 'prebuilt/selectio-spi-cdc-rx-guard-20261123'
python -X utf8 toolbox.py probe-load --pair $pair --dry-run
python -X utf8 toolbox.py project run board.accept -- --selectio --board f103ze --pair $pair --clock 100000000 --seconds 60 --rounds 3 --rtt-ring-bytes 8192 --rtt-chunk 2048
```
