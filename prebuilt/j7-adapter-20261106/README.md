# J7 转接板 JTAG / ETM 配对

2026-11-06，`accepted=true`，适用范围为 XC7Z020 CLG400-2 和用户提供的 Bank 35 转接板。133.333333 MHz 布线约束，setup 余量 0.074 ns，hold 余量 0.054 ns。F103ZE CDC48 实板完成约 1 MHz / 10 MHz JTAG 内存读和 100 ms ETMv3 DDR/USB 捕获。

使用同目录的 `probe.bit`、`application.elf` 和 `ps7_init.tcl`。`application.elf` 是转接板专用 PS 构建，保持 nSRST 在 JTAG Connect 时释放。RTCK 为输入，JTAG 使用固定 TCK。实际通过 JTAG 下载到 PL / PS OCM。

```powershell
python -X utf8 tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/j7-adapter-20261106/application.elf prebuilt/j7-adapter-20261106/probe.bit prebuilt/j7-adapter-20261106/ps7_init.tcl
```

上板前按仓库规则核对占用，下载后用物理 MEM-AP0 独立核对 ELF。文件 SHA、构建选项和验收见[配对清单](manifest.json)与[转接板报告](../../docs/validation/j7-adapter-20261106/README.md)。
