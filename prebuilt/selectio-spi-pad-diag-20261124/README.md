# J7 SPI 从机输入采样诊断配对

FPGA 从现有 SCK、NSS、MOSI 的 SelectIO 输入并行旁路记录 1,024 组、每组各四点。解码路径继续使用本分支原有逻辑。PS ELF 和初始化 Tcl 取自已验收的 RAW4 ABI 2 配对。

此配对用于 HS3 JTAG/RAM 诊断，时序和文件哈希见 [manifest.json](manifest.json)。采样格式、掉线现场和离线验证见 [报告](../../docs/validation/h743-spi2-100mhz-20261124/README.md)。

```powershell
python -X utf8 toolbox.py probe-load --pair prebuilt/selectio-spi-pad-diag-20261124 --dry-run
python -X utf8 tools/spi_slave_pad_snapshot.py --cable-serial 210299008529 --mode 0 --out build/spi-pad-mode0
```

诊断工具要求此配对已加载。保持 H743 修订 3、SPI 接线和两端 USB 在线。工具在 AUX 释放后经物理 MEM-AP0 保存 `samples.bin` 和逐线统计，并回读核对暂用的 delay tap 已恢复。
