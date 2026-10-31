# 7010 / 100MHz 静态实现配对

器件 `xc7z010clg400-2`，已完成实际目标器件布局布线、STA与bitgen：
LUT14,618、FF16,990、Slice4,398/4,400、BRAM36等效10.5；
WNS +0.258ns、WHS +0.012ns。仅剩2个Slice，按用户指示不再追求7010/120MHz。

配对为本目录 `zynqlink_probe.bit`、`zynqlink_probe.elf`、`ps7_init.tcl`。
RTL/实现源码 `bc9ced6`；最终通用固件源码 `cbedca2`，上限50MHz，包含SWJ与HSS STOP修复。
PS代码71,300B，OCM跨度120,976B，原USB/DAP队列和DDR缓冲保留。

**没有物理7010板验收。** 同一个ELF在7020上的通过不代表7010平台/DDR/USB已验证。
不得向当前7020板加载此7010 bit。PS初始化/BSP沿用现有平台，7010实板仍须核对板级配置。

[完整记录](../../docs/validation/orbtrace-hardware-20261031/README.md)；精确SHA、选项与来源见
`manifest.json` / `SHA256SUMS`。另一worktree后续ETM改动未合入，合并后须重新检查资源与时序。
