# SWD 时序发生器重构与仿真

本文保留第一阶段 `5a92f51` 的实现与验收记录。后续已开放的配置、固件/主机接口和
新增验证见 [SWD 时序可配置接口](SWD时序可配置接口.md)。下文“没有开放配置”指第一阶段。

工作分支：`codex/swd-timing-generator`。冻结基线：main 的 `d42b60180e82fccb428c51613a0316776c2bc4fc`。
本阶段只做 RTL 仿真与软件回归，不生成发布 bit，不加载硬件，不修改目标板。

最终汇总：[仿真结果与源码哈希](measurements/20261027-swd-timing-simulation.json)。
58 项运行均符合预期：51 项正向通过，7 项明确的拒绝负例（包含三项原版单独对照）。
带 main 对照的各层合计比较 **36,516,557 个半拍**，没有波形或协议寄存器差异。

## 实现

借用 DS 的“协议状态机消费时序事件、输入采样单独调度”的思路，新增
`fpga/rtl/swj_clk_gen.v`。它在 FCLK 域产生半周期 `edge_tick` 和独立的
`sample_tick`，支持 Q16 半周期与半周期内的采样偏移。它不产生 fabric 时钟；
ACK 保持、turnaround、空闲等阶段是否翻转 SWCLK，仍由协议状态机决定。

`swd_core` 原有 14 处分散的半周期计数逻辑改为消费发生器事件。
ACK 和读数据采样寄存器有独立的 sample 事件处理块；ACK 解码、parity 判定
继续使用寄存后的数据，保留原有完整 FCLK 的判断预算。

发生器的事件是当前 FCLK 边沿使用的组合使能，不多打一拍寄存器。
这避免了 DS 在段启动时遇到的“注册 strobe 的额外消费延迟”。

本阶段适配器把原 `delay + 1` 映射成整数 Q16，使用 sample-at-end 复现原捕获槽位。
原 CSR、固件调频、IDDR Q1/Q2 选择、compact ACK、连续握手及 idle 策略均保留。
RTT/HSS/packet/batch 的生产状态机没有重写。

**这次没有把任意小数频率暴露给 SWD，也没有改成固定 FCLK。** 小数半周期和独立
采样偏移在发生器单元仿真中验证；它们在完整 SWD 引脚链路中的新配置仍需后续单独验证。
发生器禁用会重置小数余数，相应的频率积分保证适用于连续启用区间，不能直接外推到
频繁重启的短帧。固定 FCLK、小数周期不能自动增加物理采样余量。

## main 波形对照方法

`tools/swd_timing_sim.py` 从固定提交提取原版 `swd_core`，不读取可能继续变化的 main。
测试时在新版 core 旁放置一个原版，输入完全相同。测试代码只生成到 `build/`，
不会进入生产 RTL。每个 FCLK 上升/下降沿、非阻塞赋值稳定后，比较：

- SWCLK、SWDIO 输出、SWDIO 方向；
- busy、result_valid、next_ready、ACK、parity、读结果、timestamp；
- 状态、半周期序号、ACK/数据采样寄存器、写移位寄存器等协议进度。

任何差异立即 `$fatal`，不使用容差、重试或只看最后结果。由于输出管脚寄存器在
FCLK 边沿更新，这同时检查了事务内和事务间的边沿位置、建立/保持动作与完成时刻。
这属于已运行输入空间内的逐拍仿真一致性，不声称是对所有输入序列的形式化证明。

控制空间矩阵完成 **8,208 次事务、512 次链式接续、128 次传输中复位**，比较
**22,065,302 个半拍**，没有差异。覆盖全部 16 档传输分频、8 档 ACK 保持、全部
8 个 ACK 编码、读写、WAIT/FAULT 数据相位、turnaround、idle、多种数据/parity、
全部 SWJ 长度 0～255 与 16 档 SWJ 分频。16 个可达协议状态全部进入；原版保留但
不可达的 `ST_RD_FINAL` 不伪装为已覆盖。

独立波形示例：`build/swd_timing_sim/main_vs_timing.vcd`。
同一 scope 下 `swclk/swdio_o/swdio_t` 对应 `ref_swclk/ref_swdio_o/ref_swdio_t`。
该文件是缩短的可视检查例子；完整矩阵通过自动比较，不靠人工看图判定。

## 性能预算

新版与原版分别运行同一个真实 packet/core 线级 testbench，并比较整组
周期数、SWCLK 上升沿数、事务启动数。包含 256/1022 字块、WAIT、部分完成 FAULT、
parity 中止以及禁止在错误后发起下一写操作。

1,022 字结果如下，读写均包含相同的 posted prime/尾部收取与引擎开销：

| SWCLK | idle | main 读/写 FCLK 周期 | 新版读/写 FCLK 周期 |
| --- | --- | --- | --- |
| 50 MHz | 0（实验） | 94125 / 94127 | 94125 / 94127 |
| 50 MHz | 1 | 96171 / 96173 | 96171 / 96173 |
| 50 MHz | 2 | 98217 / 98219 | 98217 / 98219 |
| 60 MHz | 1 | 96171 / 96173 | 96171 / 96173 |
| 60 MHz | 2 | 98217 / 98219 | 98217 / 98219 |

因此已验证的这些配置下没有周期性能下降。idle0 的等价性不扩大原版发布范围：
普通固件仍使用原有的 idle0 钳位策略。这里没有 USB、布局布线或实板吞吐测量，
不把仿真周期成绩称为新的板级 MB/s 成绩。

## 功能验证层次

发生器的 41 个单元配置检查整数首拍/稳态、小数积分误差、floor/ceil 半周期界限、独立
采样偏移、禁用/重启和参数下限。小数频点包括相当于 120 MHz 下的 50/45/40/25 MHz；
这是发生器事件能力的验证，不是这些频点的物理 SWD 数据验收。

线级批量测试检查 64/255 位 SWJ、1/2/770/1000 字读写、WAIT 重试、RDBUFF 收尾、
FAULT/parity 中止和恢复。延迟 ACK 另有故意过晚的负例：原版与新版均必须拒绝，
扩展高相位后必须恢复。这些负例不能被统计成“所有时序设置都能通信”。

包/采样/流引擎的事务模型回归继续检查 posted 结果配对、变化值、跨 1 KiB、
连续 gather、链式握手回退、FIFO 背压、timeout、HSS v1/v2、496 点 u8 包、
时间戳回绕/时间洞、STOP 尾包、不可变 bank、RTT DMA-before-RdOff、RdOff 失败重试、
2 KiB 未对齐读取与环形缓冲回绕。

真实 ARM Cortex-M0 DesignStart 模型读取本机原始文件，没有修改或复制其源代码入仓库。
在这个模型下运行 DP/AP 连接、posted SRAM 访问、1～1023 字 packet、ACK 保持、
turnaround、返回延迟、Q1/Q2、idle1/2、50/60 MHz、活跃事务复位和恢复。
每个真实串行运行也带原版 core 的逐半拍比较。

默认 Q2 配置下，8/30/50 ns 的外加返回延迟扫描不能完成连接。新版和对照 core 的
波形、错误 ACK 完全一致；另用原版 main 单独编译运行，分别重现 ACK 4/3/7。
因此这三项保留为**原版窗口之外的拒绝负例**，不称作通信通过，也不通过更改生产
采样相位或延长周期把它们掩盖。16 ns 默认工况和实际 Q1 配置的正向案例单独验证。

新增 `+services` 把真实串行 MEM-AP 接到生产 sampler/RTT/packet BRAM，覆盖：

- 单字 HSS 的高频请求与稳态包、双字跨 1 KiB 采样、DAP 接管后的访问；
- 时间洞造成的合法部分包、稳定档满包、DMA ACK 前不可变的 bank；
- 2 KiB RTT、非对齐字节、描述符自身跨 1 KiB、数据跨页、环尾/环头；
- 模拟 DMA 读取并确认后才推进目标 RdOff，确认完成后才回收 bank。

主机 DMA/USB 所有权仍由生产 C 回归覆盖，包括 DMA/RdOff 失败重试、队列满、
ZLP、USB reset、70,000 次完成以及序号回绕。仿真中的 DMA/USB 是测试驱动，
没有声称真实 Xilinx CDMA/USB 控制器的硬件模型已参与串行服务测试。

## 修正的测试基础设施

- 旧 ACK bench 等待私有 FSM 的 ACK 状态，扩展 ACK 实际走另一状态，会死等。
  改成观察真实方向释放/turnaround 上升沿，并补全读数据和 parity。
- 几个旧 packet bench 只有打印，没有断言；现增加 payload、重试、状态、watchdog
  的失败断言。batch bench 补齐当前引擎的 packet 端口。
- 旧 `rx_early` plusarg 没有被 testbench 消费，删除这项虚假额外覆盖，保留真实 phase 测试。
- Icarus 11 Windows 在完整 ARM 模型上触发 StringHeap 内部断言；真实 ARM 层改用
  本机 XSim。没有修改目标模型来绕过它。XSim 使用实际 `--testplusarg`，成功条件同时
  要求 PASS marker、进程状态和没有 fatal，服务 case 还要求 `SERVICES_PASS`。
- 原 ARM 模型的 AHB FAULT 注入存在既有 `FAULT_SKIP` 限制，报告保留该标记。
  FAULT 编码/部分完成/停止未来写的行为另由控制矩阵和线级错误注入覆盖。

## 复现

```powershell
python tools/swd_timing_sim.py
```

完整执行需要 Icarus/vvp、Vivado 2018.3 XSim、本机 ARM 模型，以及本机 C 编译器。
源列表已加入新发生器，Vivado 增量构建也登记该文件，但本阶段没有运行综合/实现。

分层重跑：

```powershell
python tools/swd_timing_sim.py --groups unit,control,wave
python tools/swd_timing_sim.py --groups wire,budget,packet,probe,host
python tools/swd_timing_sim.py --groups m0
python tools/swd_timing_sim.py --groups baseline
python tools/swd_timing_sim.py --groups m0 --m0-only services
```

`build/swd_timing_sim/summary_*.json` 保存各层结果和生产 RTL SHA-256；原始日志、
参考 core、编译用对照 core、VCD 都在同目录。原始 ARM 源码保持在本机模型目录。
运行时间较长的 ARM 大块矩阵与 8k 控制空间矩阵是有意保留的完整验证。

下一步先根据这些仿真结果讨论是否进入综合/时序与上板验收。未经讨论，不把任意
小数频率或新的采样位置加入发布配置，也不把 RTL 仿真通过等同于板上电气时序通过。
