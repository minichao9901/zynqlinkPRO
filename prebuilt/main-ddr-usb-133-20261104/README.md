# F103 DDR / USB统一配对

中间统一配对。DDR CLI/Web、RTT/HSS已实测，但保留软件STAT残留缺陷ZL-136；不作为最终交付推荐。

bit逐字节复用fclk133-release-20261101已布线产物，未重跑PL实现；133.333MHz约束、原WNS0.319ns/hold0.033ns。PS实际重新构建，输入SHA、选项和编译器见ps-build.json，实际文件SHA见manifest.json。仅JTAG/RAM加载，无QSPI写入/冷启动验收，也不推广H743/HPM。

[本轮报告](../../docs/validation/main-web-hardware-20261103/README.md)。
