# HS3 驱动与 J7 临时加载复验

2026-11-20。Windows 最初仅识别目标 CDC；同时出现端口重置失败的未知设备，其身份无法确认。SetupAPI 记录 23:44:13 的 RemoveGhostDev64 清理了 HS3 的非在线实例。无法据此判定线缆消失的根因。

签名有效的 Vivado 2018.3 Digilent 安装程序返回 0，安装日志提示组件已是当前版本。随后用 PnPUtil 实际导出、移除并重新添加 Digilent 随附的 FTDI 总线包 2.12.28.0。重新插入后，Windows 选择 FTDI 2.12.36.20。对准确实例 `USB\VID_0403&PID_6014\210299008529` 再执行实例移除及实际绑定包的导出、移除、重新添加与设备扫描，设备状态 Started，实际绑定 oem7.inf。

XSCT 扫链读到 Digilent JTAG-HS3 210299008529、ARM DAP 4ba00477 和 XC7Z020 23727093。初始 BOOT_MODE=0、LEVEL_SHIFTERS=0、FPGA_RESET=0x01f33f0f。统一 probe-load 入口随后临时加载正式 USB 基线，物理 MEM-AP0 核对 OCM 的 85,844 字节通过，CMSIS-DAP 12345678 重新枚举。此处仅记录基线配对。目标 CDC 序列号为 F103CDC0001，重新枚举期间 COM 号发生变化。

[基线加载结果](baseline-load.json)
