# main 低频 SWD 接收边界修复
> 历史阶段记录：本文保留首轮仿真/OOC 结果。后续板测发现还需处理 SWCLK 电气设置与实际 PLL 分档；当前已暂停，最新状态见[工作日志](main-lowfreq-progress.md)和[板测报告](main-lowfreq-board-20261028.md)。


日期：2026-10-28。基线固定为 `d42b60180e82fccb428c51613a0316776c2bc4fc`。
分支：`codex/main-lowfreq-sample`，从 main 派生；没有引入 Q16 时序发生器。

## 原因与协议

Arm ADIv5 B4.3.1 规定 target 在 SWCLK 上升沿采样输入，也在上升沿改变/释放输出。
主机发送在下降沿改变 SWDIO；接收必须取到 target 下一次上升沿换位前的当前 bit。
参考：[Arm ADIv5](https://documentation-service.arm.com/static/622222b2e6f58973271ebc21?token=)、
[Arm DSTREAM-XT 接口说明](https://documentation-service.arm.com/static/624b0988f7d10f7540e0cc7e)。

main 的 ACK 在 half-step 3/5/7 消费三个 sample，相对于短回程路径晚了一个 SWCLK 周期。
16 ns 回程、50 MHz FCLK / 25 MHz SWCLK 时，ACK OK 的 `001` 会被取成
ACK1、ACK2、D0，即首个 DPIDR 的 `100`。降低频率不会改善这个 bit 对应关系。
Q1/Q2 只差半个 FCLK，不能独自修复整 bit 的边界偏移。
50 MHz SWCLK、16 ns 回程时，返回延迟恰好让旧流水取到前一 bit，所以 main 能通过。
这是 RTL 与回程延迟的组合结果，不能推断任意目标都具有同样的切换频率。

## 改动

- 新增 CFG bit18 `rx_boundary`。0 完全保留 main；1 在 `ack_delay=0` 时启用短回程接收边界。
- ACK 改为 1/3/5 采样，最后一位进入寄存器后下一拍解码，不把输入半周期路径直接串进 ACK 分支。
- ACK 解码和首个 read data 边界一起移动；ACK/read 共用输入采样路径。
- write 和 WAIT/FAULT 保留完整 turnaround。
- read parity 后显式完成 turnaround，随后才允许 idle 或下一条请求。
  单独读通并不够：最初 idle=1 掩盖了漏掉 turnaround 的问题，零 idle 连续读测试将它检出并修正。
- bit17 仍选择 IDDR Q1/Q2，原 turn_extra、ack_delay 接口保留。非零 ack_delay 使用原来的扩展 ACK 路径。
- 固件沿用原来的 35 MHz 低频分界，低频改为 bit18=1、Q2；50 MHz 仍为原模式。
  分界值是待上板校准的策略，尚无板上裕量结论。
- 修正 ACK 小模型：ACK0 从 request turnaround 的上升沿发出；不再用错误的 bit 排列迎合原采样流水。

## 返回窗口扫频

固定 16 ns 回程、ack_delay=0：

| SWCLK | 新边界 + Q2 | 新边界 + Q1 |
|---|---|---|
| 50 MHz | 预期失败 | 预期失败 |
| 40 MHz | 通过 | 预期失败 |
| 35 MHz | 通过（另有完整固件配置回归） | 预期失败 |
| 30 / 25 / 10 / 5 MHz | 通过 | 通过 |
| 1 MHz / 250 kHz | 未单独扫 Q2 | 通过 |

旧边界 + Q2 在 50 MHz 通过，旧边界 + Q1 在 25 MHz 重现原 ACK 失败。
10 MHz 新边界 + Q1 另扫了 0/4/8/12/16/24/32 ns，均通过。
高速负例说明新 bit 用来选择匹配返回窗口的边界，并不是所有频率都强制打开。

## 已验证的吞吐

同 idle 配置，真实 packet FSM + 物理 SWD core + 上升沿发送的 target 模型：

| 1022 数据字 + AP drain，idle=1 | main | 修复后的短回程模式 |
|---|---:|---:|
| write FCLK cycles | 96173 | 96173 |
| read FCLK cycles | 96171 | 96171 |
| write/read SWCLK rises | 48081 | 48081 |

测试覆盖 idle=0/1/2、256/1022 字、WAIT 重试、部分 FAULT/parity 取消、链式请求。
速度比较使用 FCLK 周期数，避免把降低 SWCLK 的绝对时间拿来比较。
高频 legacy 模式另外逐半 FCLK 比较 immutable main 的引脚、结果、状态和移位寄存器。

## 核心 OOC 布局布线比较

同 Vivado 2018.3、xc7z020clg400-2、100 MHz 时钟，均重新综合、布局布线：

| 项目 | main | 修复版 | 差值 |
|---|---:|---:|---:|
| Slice LUT | 465 | 575 | +110 |
| FF | 444 | 457 | +13 |
| CARRY4 | 11 | 11 | 0 |
| BRAM | 0 | 0 | 0 |
| Setup WNS (ns) | +3.556 | +3.941 | +0.385 |
| 最差路径逻辑级数 | 8 | 6 | -2 |

修复版最差路径是 lsm_cnt 到 FSM CE，5.817 ns（logic 1.456、route 4.361）。
main 是 state 到 wr_shift CE，6.201 ns。
这些是 **core 内部 OOC** 结果；输入输出端口没有板级约束，工具也提示缺少 PARTPIN_LOCS。
它不代表完整 SoC、IDDR 半周期输入和板级 I/O 已签核，不据此宣布整机最高频率。
新增状态可达后 Vivado 自动选择 one-hot FSM，解释了部分 FF 增量。

## 回归与复现

完整 Cortex-M0 回归 11/11 通过：50 MHz legacy、25/10 MHz 新模式均覆盖 1/2/127/256/770/1023 字 packet 读写、RTT/HSS、WAIT/ABORT、执行引擎中断与 SWJ 恢复；另有两组 sampler、三组旧 ACK hold、三组 turn_extra。
legacy 与 immutable main 累计比较 974865 个半 FCLK 观察点，无引脚、结果、状态或移位寄存器差异。

已完成：15 组线级 packet 配置 + 3 组 batch stream 配置；全部通过，并显式断言 packet 周期不超过 main。
返回窗口 sweep 共 23 组：18 组正例通过、5 组预期负例均重现；其中含 250 kHz 与 1 MHz。
另外 4 组边界检查通过：固件 35 MHz/Q2 全功能、零 idle 大块 packet、delay_fast=1/3。
probe 单元回归覆盖 HSS/RTT 的背压、停止、posted flush、1 KiB 边界、WAIT、FAULT、parity 和 watchdog；packet engine 六项回归通过。
ACK 专项三组正例通过，一组过晚响应负例按预期失败。


- `python tools/run_swd_rx_regress.py --suite full --out build/swd_rx_final`
- `python tools/run_swd_rx_regress.py --suite sweep --out build/swd_rx_sweep_final`
- `python tools/run_swd_rx_regress.py --suite boundary --out build/swd_rx_boundary`
- `python tools/run_swd_rx_wire.py`
- `python tools/run_vivado.py -mode batch -nojournal -source fpga/sim/compare_swd_rx_core.tcl`
- `python tools/test_probe_rtl.py`
- `python tools/test_packet_engine.py`
- `python tools/simulate_swd_ack.py --output build/swd_rx_ack_summary.json`

ARM DesignStart RTL 只在原位置读取，不复制进仓库。
每次 ARM 编译记录 source hash，reuse 前检查 hash，日志和 JSON 保留在对应 build 目录。
Sweep 中“旧模式低频失败”和“高速短回程模式不适用”属于明确列出的负例，不能把它们称为正常通过。
真实 Cortex-M0 的强制 HRESP 注入未触发 FAULT，保留 FAULT_SKIP；FAULT/parity 行为由独立线级模型验证。
HSS 低 FCLK 的 packet 数据验证不代表 24 MHz 时间戳精度；固件原有的采样时钟限制未放宽。

固件 `xusbps_daplink_dma` O3 已用 Xilinx BSP 编译链接通过，限定最高 SWCLK 50 MHz；未下载运行。
本次未生成用于上板的整机 bit，也未烧写或连接目标测试。

归档结果和资源/时序报告位于 `results/optimization/main_lowfreq_rx/`；完整日志、编译快照与固件 ELF 保留在 `build/`。所有 ARM 仿真 manifest 与最终 RTL 的 source hash 已再次核对一致。
