# J7 ELD1 与原始 SWD 序列修复配对

2026-11-06。当前实板配对，限定通过 F103ZE 原始 `0x1D`、普通 SWD/JTAG 读写、60 MHz SRAM 三轮及 10 秒校验、零 tap 的 24/32 MHz ETMv3。五路 ELD1 已实现，启动加载零 tap。133.333333 MHz 约束下 setup/hold 余量为 0.067/0.044 ns。

新 PS 的原始 SWD 序列使用 L16/SWDIO，新 bit 将 L14/TDO 永久设为输入。`SWD_FEATURES` bit6 声明手动 SWDIO 方向控制，`JTAG_PINS` bit9 控制输入模式。新 PS 在旧 bit 上收到 `0x1D` 时返回错误。文件 SHA、实际源码输入和本轮验收范围见[manifest](manifest.json)与[完整报告](../../docs/validation/j7-sequence-fix-20261106/README.md)。

```powershell
python -X utf8 tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/j7-eld1-sequence-fixed-20261106/application.elf prebuilt/j7-eld1-sequence-fixed-20261106/probe.bit prebuilt/j7-eld1-sequence-fixed-20261106/ps7_init.tcl
```

使用前核对探针空闲，装载后物理读回核对 OCM。旧校准实验的 36 MHz tap 仅按其原 bit 归档，新配对的默认设置为全部零 tap。TCK 断开高阻和 RTCK 自适应范围见[改脚复核](../../docs/validation/j7-eld1-20261106/j7-production-audit.md)。
