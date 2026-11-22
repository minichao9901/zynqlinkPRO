# F103ZE SelectIO 变频实板复验

使用 HS3 210299008529 临时加载 Zynq 探针，USB 识别为 12345678。目标 DEV/REV 0x10036414，CPUID 0x411FC231。目标通过 SRAM-only 夹具进入 HCLK128，每个窗口独立由 RCC 读回与 DWT 验证。阶段间检查原始 SRAM、核心寄存器、时钟和运行态恢复。探针固化与 Web 不在验收范围。

初始加载的融合版 OCM 核对 79,692 B。50 MHz SRAM 读/写 3.832/3.863 MB/s，逐字校验通过。RTT 首次在取到控制块前返回 -4，AP 诊断首次恢复失败为阶段 6（恢复 SELECT），DAP 请求进入隔离。J7 定向 USB 重枚举后从备份恢复目标。干净临时加载后改用 slot24 仍能复现这一接管失败。独立物理 MEM-AP0 检查采集、队列与 CDMA 空闲后才临时重载 probe。目标 Flash 和探针 QSPI 无写入动作。

验证 ELF 复用主机已经选好的同频 SelectIO 档位，直接接管并保存 AP 上下文。对比时采用相同的 bit 和 PS 初始化脚本。50 MHz、slot22、idle0 的第一个 8 秒窗为 3.808 MB/s，确认收到发布的全部 33,433,596 B，设备错误为零。随后更长窗口继续测试稳定性。

[首轮 RTT 失败](full-first-rtt-failure.json) · [AP 上下文诊断](ap-context-restore.txt) · [修正后首个窗口](full-50-rtt-first-fix.json)
