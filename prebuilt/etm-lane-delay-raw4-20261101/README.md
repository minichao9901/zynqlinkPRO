# ELD1实际输入延迟研究配对（非Golden）

当前研究配对已通过JTAG加载，仅在FPGA配置和PS RAM运行；没有写目标Flash或Zynq QSPI。源码、构建/修复/验证提交、SHA及各项验收状态见manifest.json。

- probe.bit：eac5a263c4966e664370a78f299600c47d034b905b897a083cdf154ee01264ae。
- application.elf：1d55b321f95e15d43afb719380c7cefb4f05955c89f018e49c38bb3fb38ef559。PS源码未改，但本次从源码重新编译；与旧配对字节相同，完整新编译命令日志已归档。
- 实现：RAW4、DDR、5个独立VAR_LOAD输入延迟；默认明确加载零tap，不等于直接旁路。120MHz setup +0.013ns / hold +0.010ns，bitgen DRC 0错误。5条DATAOUT分别实际连接到5个采样FF/D端点。
- 上板：OCM代码逐字节匹配，2轮1MiB DDR模式/保护字通过；D0/D1/D2/D3/CLK=0/8/16/24/31实际装载和读回通过，再归零。实际FCLK119,999,998Hz、SWCLK999,999.9833Hz。
- 零tap、原Golden F103ZE CPU48MHz/TRACECLK24MHz：100ms、1s采集和原生解码通过，1s硬件窗口内63次完整精确CDC echo。
- SRAM CPU72MHz/TRACECLK36MHz：110个已完成扫描点均未通过；第111点在DAP清理时失败，未重试。原始坏点保留，未完成五条lane的全部扫描，更未证明36MHz可用或自动校准成功。

扫描结束时外层恢复验证原Flash字节不变、RCC回到原48MHz固件，tap归零，候选未保留。已知工作配对prebuilt/etm-ddr-usb-raw4-20261101及Golden未覆盖。暂停后续自动推进时，本研究FPGA/PS配对仍在线，Web服务已关闭。重启/断电会丢失本次JTAG/RAM加载；本目录不是QSPI启动镜像。

详细原始证据：docs/validation/etm-lane-delay-20261101。主结论保存在docs/F103ZE-Web-CLI-ETM统一验收-20261031.md；ELD1寄存器及AI CLI说明见docs/ETM逐线输入延迟-ELD1.md。
