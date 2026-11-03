# F103 DDR / USB统一配对

本轮最终实测候选配对。PS增加STAT payload初始化，最终冻结EXE及DDR/OCM收尾完成，仍有HSS标定、热状态RTT启动和Web控制/烧录性能限制；accepted=false，不替代Golden。

bit逐字节复用fclk133-release-20261101已布线产物，未重跑PL实现；133.333MHz约束、原WNS0.319ns/hold0.033ns。PS实际重新构建，输入SHA、选项和编译器见ps-build.json，实际文件SHA见manifest.json。仅JTAG/RAM加载，无QSPI写入/冷启动验收，也不推广H743/HPM。

[本轮报告](../../docs/validation/main-web-hardware-20261103/README.md)。
