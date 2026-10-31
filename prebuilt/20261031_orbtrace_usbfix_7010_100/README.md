# 7010 / 100MHz，USB Chapter9 修正版

PL显式复用bc9ced6的7010 bit，未修改RTL、未声称重新综合。LUT14618、FF16990、Slice4398/4400，WNS+0.258ns、WHS+0.012ns，TNS/THS零。

配对为zynqlink_probe.bit + zynqlink_probe.elf + ps7_init.tcl；ELF是0ec2e63修复版默认50MHz配置，代码71268字节，OCM跨度120976字节，队列不变。完整SHA-256见manifest.json。共同PS在7020/F103ZE上单独加载完成50MHz峰值/RTT校验；没有物理7010验收，仍仅剩2个Slice。不要把此bit加载到7020。
