# J7 原始 SWD 序列路由修复

修复 ZL-158。旧 `0x1D` 的软件管脚函数访问 AXI GPIO bit1，而该位已接 J7 的 L14/TDO。修复后输入读取、输出数据和方向控制均经 `JTAG_PINS` 连接真实 L16/SWDIO。手动控制寄存器 bit9 表示输入，bit8 表示手动模式。bit9 同时读回，确保切换 SWCLK 电平的读改写保留输入方向。新 FPGA 能力位 bit6 用于协商。 [CMSIS-DAP SWD_Sequence](https://arm-software.github.io/CMSIS_5/DAP/html/group__DAP__SWD__Sequence.html)

RTL 将 L14/TDO 在 SWD 和 JTAG 模式下均设为输入，阻止旧 GPIO TRI bit1 使其输出。新 PS 配旧 bit 或请求处于非 SWD 模式时，原始序列返回 `DAP_ERROR`，按命令约定消费请求长度并清零输入响应区域。普通 `0x12` 和标量/块读写继续走原硬件移位引擎。

原生 C 测试提取生产函数，覆盖 1～64 位混合输入/输出、LSB 位序、非整字节尾部、方向往返、旧 bit 拒绝和非 SWD 拒绝，模型禁止访问旧 GPIO。最初本机 GCC 无有效诊断退出，按仓库既有主机测试方式使用 Clang/MinGW 后通过。RTL 仿真通过实际 AXI 写读，检查手动 SWDIO 的 0/1 输出、输入释放和 TDO 隔离，已接入 `tools/test_packet_engine.py`。生产 DAP 预检、50000 组边界输入和有界等待回归通过。

新实现保留 ELD1 五路延时单元，按 J7 球号和 133.333333 MHz 约束布局布线。第一次后置检查预期 TDO 必须优化为 IBUF，而 Vivado 保留 T 端恒为 VCC 的 IOBUF，导致检查主动拒绝。随后检查同时支持 IBUF 和输出禁止端固定为高的 IOBUF，并检查不存在可控的输出使能。基于同一个已布线 DCP 重新执行完整时序和 bitgen 验证，原拒绝日志保留。

Vivado 的展开网表同时列出 IOBUF 宏及内部 IBUF/OBUFT，首次修订仍被子 OBUFT 拒绝。最终验证逐项核对宏和 OBUFT 的 T 为固定高电平，且恰有一条输入路径，记录 `TDO_INPUT_ISOLATION_VERIFIED`。133.333333 MHz 下最终 setup/hold 余量为 0.067/0.044 ns，五路 ELD1 的 DATAOUT 均到达独立采样端点。 [实现摘要](raw/implementation-summary.txt) · [时序](raw/timing.rpt)

最终配对是本轮新生成并实际装载的 bit `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6` 和 PS ELF `3cef987ab54e784a2103d9d0e88d5ecc42caf207b99ecf6d13795cd47994496b`。物理 MEM-AP0 的 85636 B PS 执行段完全一致。构建基线 `0be2aff3` 加实际工作区输入，源码 SHA 和换行差异单独绑定。 交付配对（历史归档 `archive/main-before-formal-release-20261106:prebuilt/j7-eld1-sequence-fixed-20261106/README.md`）

| 实板检查 | 结果 |
|---|---|
| 新 PS + 旧 bit | 输出请求 `1D FF`，输入请求 `1D FF 00`；GPIO TRI 与手动控制寄存器前后相同 |
| 完整新配对原始 `0x1D` | 16 次 DP 读返回 `0x1BA01477`，ACK=1、数据奇偶校验一致；每次包含输出、输入、turnaround 与 idle |
| 非整字节输出 | 1/7/8/9/31/32/33/63/64 位均按正常命令返回成功 |
| 常规 JTAG | 1/10 MHz IDCODE、CPUID 和 Flash 页读回通过 |
| 常规 SWD60 SRAM | 2 KiB 块/depth32 三轮读/写 4.817/4.733 MB/s，10 秒校验通过 |
| 常规 JTAG60 SRAM | 同口径三轮读/写 2.418/2.395 MB/s，10 秒校验通过 |
| 新配对 ELD1 零 tap ETM | 24 MHz 三轮 100 ms、32 MHz 三轮 1 s，完整窗口和原生解码均通过，包错误与 parser 错误为 0 |

当前吞吐较历史同频最好值差约 0.1%～0.4%，与前次 J7 同口径数据接近。三轮 32 MHz 的约 2740 万条指令及两个目标函数均完整展开，指令数和同负载基线相符。新配对从零 tap 启动。前一实验配对的 36 MHz 候选按原 bit 身份归档，裕量结论保持候选。 [原始序列](raw/raw-sequence.json) · [旧 bit 拒绝](raw/old-bit-guard.json) · [ETM](raw/final-etm.json)

验收器首轮持有父进程锁时启动 JTAG 子进程，被 OS 锁拒绝并恢复原生产配对。随后子进程的 JTAG 已通过，但外层将成功的 `SystemExit(0)` 误当失败，再次恢复原配对。调整测试器的锁交接与成功退出处理后，独立新输出完成剩余检查。两次测试器失败及已通过的硬件结果分别保留。生产控制路径未放宽所有权规则。

收尾 64 KiB SRAM、核心寄存器、FPB、VTOR、DWT、RCC 与目标运行状态均恢复，CDC48 Flash 装载段匹配。目标 DHCSR `0x01010001`，探针采集、DMA、RTT 和 HSS 空闲。板上保留本次修复后的 ELD1 bit/ELF 配对，默认零 tap。目标 Flash 和探针 QSPI 无写入，所有本任务测试进程已退出，`hw_server` PID 3904 保留。 [最终 OCM](raw/final-ocm.json) · [目标复核](raw/target-final.json) · [收尾](raw/board-summary.json)

本轮限定关闭 ZL-158。TCK 断开后仍驱动的 ZL-159 和外部 IO/CDC 签核缺口 ZL-007 继续保留。RTCK 为只读输入预留。 [完整改脚复核](../j7-eld1-20261106/j7-production-audit.md)
