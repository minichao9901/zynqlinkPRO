# SelectIO 融合版 SPI 异步采样修正配对

这个 bit/PS ELF 同时包含 SPI 从机双边沿接收与 HSS STOP 终帧修正。J7 使用 HS3 进行 JTAG/RAM 临时加载。133.333 MHz 的布线 setup/hold 分别为 +0.012/+0.021 ns。探针 12345678 的物理 MEM-AP0 OCM 执行段读回校验 80,268 B，USB 描述符与首版一致。

F103ZE 的 GPIO 源四模式各 16,384 B 到 COM34，字节匹配，零溢出、帧错或尾差，目标已恢复。该源的 DWT 窗口平均 SCK 约 1.35–1.64 MHz。F103ZE CDC48 全功能套件 36 项通过，独立 SPI 主机 100 MHz 连续线速仍待验证。 [清单](manifest.json) · [真实 SPI CDC 与 OCM 证据](../../docs/validation/spi-cdc-20261123/phase-drift-smoke.json) · [全功能套件](../../docs/validation/spi-cdc-20261123/phase-drift-full-board.json)

```powershell
$pair = 'prebuilt/selectio-spi-cdc-phase-drift-20261123'
python -X utf8 toolbox.py probe-load --pair $pair --dry-run
python -X utf8 toolbox.py project run board.accept -- --selectio --board f103ze --pair $pair --only spi-cdc
```

验收预览加 `--execute` 才会加载和运行。 [融合 CLI](../../docs/selectio/README.md) · [用例与判据](../../docs/selectio/fusion-performance-cases.md)
