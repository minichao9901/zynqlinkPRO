# H743 原排线 SWO 与 SPI 定向验收

2026-11-23，J7 USB `12345678`、HS3 `210299008529`、融合 CDC OUT 防护配对。物理 MEM-AP0 对拍 PS OCM 80,260 B，H743 使用 `stm32h743_dbgstress/fw.elf`，原程序 7,740 B Flash 装载段与 ELF 相符。目标 HSI 标称 CPU/HCLK 64 MHz。全过程沿用标准排线。 [逐轮证据](evidence.json)

| 路径 | 条件 | 本轮实板结果 |
|---|---|---|
| J7 SPI 主机 MOSI | 100 MHz 档，四模式各 60 秒，取样 slot 16/18/16/18 | 69,400,576 / 72,781,824 / 72,374,272 / 70,686,720 B，实体 M15 回采全匹配 |
| J7 SPI 主机 MISO | 100 MHz 档，H743 PB3 经 L14 分别固定为低、高，四模式 | 每种电平每模式 16,384 B，全部匹配。同步变化的独立全速数据待测 |
| H743 GPIO SPI 主机 → J7 CDC | PA13/14/15 分时借用为 CS/SCK/MOSI，四种 CPOL/CPHA | 每模式 65,536 B 全匹配，DWT 算得平均 SCK 约 3.483 MHz，PC 约 0.438 MB/s，零溢出、帧错及尾差 |
| H743 GPIO SWO → J7 L14 | NRZ 0.25/0.5 Mbaud，Manchester 0.5 Mbit/s。IF0 和 IF4 分别接收 | 六组各 73,728 B，源端完成计数、实收 SHA-256 和 STOP 排空一致 |
| J7 本端串行实体回采 | M15 接原 H743 排线负载，100 Mbaud NRZ 突发，60 秒会话 | 3,171,000 B 全匹配。100 Mbit/s Manchester 首块在 slot21 只收 104/112 B，slot20/22 未收齐 |

SWO 把 PB3 预置到各编码的空闲电平后再开启接收。Manchester 1 Mbit/s 的软件发送档平均仅到约 1.796 Msymbol/s，接收出现帧错。NRZ 1 Mbaud 的首次软件单点也存在错字。上述两点保留源端和接收端证据。H743 的 SWO 送样为 GPIO 定时发生器，CoreSight ITM/SWO 硬件码源仍待验证。J7 M15 是本端带载突发对照，L14 高速连续外部信号仍待测。

SPI 接收端另重跑 100 MHz AUX 数字接收环仿真，73,727 字节匹配，检查回卷、尾包、溢出、帧错及重新启用。生产 CDC pump 的缓冲、短包、提交重试、计数器回卷和 CDC 描述符事件模型通过。实际 100 MHz 连续 SPI→CDC 与独立从机全速动态回包仍各自待验证。

## 调试访问与恢复

初始 SWO 配置尝试后，目标 AP0/AP2 内存访问失败，保留 DPIDR、FAULT/WAIT、OpenOCD AP2 和双 TAP 参考失败。按用户授权由现有 J7 NRST 排线复位一次，恢复 CPUID、常规 SRAM 和 Flash 访问，并恢复初始 DEMCR 与 AHB4 时钟门。之后 `DBGMCU_CR` 系统别名读零且开钟写入未读回，CPU 执行 RAM 诊断也只读到零，AP2 仍返回 FAULT。见 ZL-199。

早期 4 Mbaud SWO 尝试在接收报错后过早暂停 CPU，H743 GPIOB 时钟门未立即恢复。用已备份 GPIOB 状态独立回写并逐寄存器核对，再恢复 SRAM、核心寄存器、DWT 和运行态。后续 GPIO SWO 用例先派发空闲电平并等待发送者完成，退出时独立备份、回写和核对 GPIO。收尾 H743 处于运行态，排线和 Flash 内容保留。J7 捕获和队列空闲，探针保持该融合配对的临时加载。原始运行目录与夹具留在本机 `build/h743-norewire-20261123/`。
