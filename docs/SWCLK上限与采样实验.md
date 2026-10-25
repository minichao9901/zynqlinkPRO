# SWCLK 上限与采样相位实验（分支 feature/swclk-sampling-delay）

2026-10-25 晚。目标 STM32H743（480 MHz 固件），逻辑分析仪已拔掉，
全部结论来自 USB 侧的可观测行为（IDCODE / AP 访问 / 流水线吞吐）。

## 结论

**60 MHz 是当前采样架构的硬上限；改 `SWD_CFG[17]` 相位救不了，需要更细的
输入采样延迟（IDELAY）。**

## 方法

`tools/swclk_sweep.py`：

1. 在 50 MHz 建立链路（H743 的 DP 不接受首帧就是高频）；
2. 改频后**重发线复位**（152 bit：0xFF×8 + 0x9E,0xE7 + 0xFF×8 + 0x00）；
3. DP 上电：写 ABORT(0x1E) → CTRL/STAT(0x50000000) → 轮询两个 power ACK；
4. 校验 IDCODE + 4 字块读，再测 32 个 1023 字块读的流水线吞吐；
5. 每档都试 phase 0/1（vendor 0x80 写 `SWD_CFG[17]`）。

## 结果

固件把请求映射到 FCLK（SWCLK = FCLK/2），实际只有 4 档：

| 请求 kHz | 实际 FCLK | SWCLK | phase 0 | phase 1 |
|---|---:|---:|---|---|
| 60000 | 120.0 MHz | 60.0 | **OK，4.47 MB/s** | 失败 |
| 62000 / 64000 | 120.0 MHz | 60.0 | OK（同一档） | 失败 |
| 66000 / 68000 / 69000 | 128.57 MHz | 64.3 | IDCODE OK，**AP 访问 NO ACK** | 连 IDCODE 都失败 |
| 70000 / 72000 | 138.46 MHz | 69.2 | 同上 | 同上 |
| 75000 / 80000 | 150.0 MHz | 75.0 | 同上 | 同上 |

64.3 MHz 的细节：DP 级全部正常（IDCODE、ABORT、CTRL/STAT 读回 `0xF8000040`，
两个 power ACK 都在），但 `CSW` 写开始 NO ACK（status 7），TAR/块读全挂。

## 根因分析

- 当前 SWD 核在 SWCLK = FCLK/2 下，一个 bit 只有 2 个 FCLK 周期：
  上升沿在周期 T，数据相位只有 **T+0.5 周期**这一个采样点
  （`swdio_i_fall`/IDDR Q2）。
- 64.3 MHz 时半周期只有 7.8 ns，采样点 = 3.9 ns；AP 的 ACK/数据
  （经 AHB-AP 桥，tCO 比 DP 长）在 3.9 ns 时还没到，采到的是上拉高电平 →
  ACK=111 → NO ACK。DP 的 IDCODE 路径短，所以仍能通过。
- 想采到 T+1.0 周期只能选 Q1（phase 1），但那是下一个 bit 的边沿，
  在 60 MHz 就已经失败——所以 2 档相位在 /2 架构下没有余量。

## 下一步（已确认可行性的方案）

SWDIO 引脚 **D19 = IO_L4P_T0_35，HP Bank 35**，支持 `IDELAYE2`
（31 抽头 × ~78 ps ≈ 2.4 ns）。把输入采样点从 0.5 周期往后推 0.5–1.5 ns，
正好覆盖 64.3/69.2/75 MHz 的需求：

1. BD 使能 FCLK1 = 200 MHz 并接到 `swd_controller/ref_clk`；
2. `swd_controller` 内加 `IDELAYCTRL`（200 MHz）+ `IDELAYE2`
   （`IDELAY_TYPE="VAR_LOAD"`），插在 IOBUF.O 与 IDDR.D 之间；
3. `SWD_CFG[22:18]` = 5 bit 延迟，vendor 命令 0x82 运行时可写；
4. 重扫 60/64.3/69.2/75 MHz × 0–31 抽头，找稳定点并测吞吐。

预期：64.3 MHz 打开 ≈ +7%，69.2 ≈ +15%，75 ≈ +25%（相对 60 MHz 的 SWD 时间）。

## 帧间 50 ns 间隙

60 MHz 下 1023 字块读实测 4.47 MB/s，对应 916 µs/块；纯帧时间
1023×46/60 MHz = 785 µs，**约 17% 是帧间/事务间开销**（含每事务的
turnaround、park、状态机切换）。这部分没有 LA 无法逐项定位；可用的
度量是「吞吐 vs 块大小」和「吞吐 vs 事务类型」，本次未做 RTL 改动。

## 复现

```powershell
python tools/swclk_sweep.py --freqs 60000,66000,69000,70000,75000,80000 `
    --address 0x24010000 --output results/optimization/swclk_sweep.json
```

## IDELAY 实测（分支 feature/swdio-idelay）

实现：

- BD 使能 PS FCLK1 = 200 MHz，接到 `swd_controller/ref_clk`；
- 控制器内 `IDELAYCTRL` + `IDELAYE2`（VAR_LOAD，78 ps/抽头，31 抽头 ≈ 2.4 ns），
  插在 `IOBUF.O` 与 `IDDR.D` 之间；
- `SWD_CFG[22:18]` = 延迟抽头，vendor 0x82 运行时可写；
- 另加 `SWD_CFG[24:23]` = ACK 前额外 turnaround 周期，vendor 0x83。

结果（H743，480 MHz 固件，64 KiB 基准）：

| 条件 | 结果 |
|---|---|
| 60 MHz，抽头 0–16 | 正常；抽头 18/26 偶发错块（过延迟） |
| 60 MHz，OpenOCD nightly 64 KiB | 读 3.59 / 写 4.06 MB/s（与无 IDELAY 版本一致，**无回退**） |
| 64.3 / 69.2 MHz，抽头 0–12 | DP IDCODE 正常、AP 写（CSW）正常、**AP 读一律 NO ACK**（status 7） |
| 64.3 / 69.2 MHz，抽头 ≥16 | 连 IDCODE 都失败（DP 过延迟） |
| 64.3 / 69.2 MHz，turnaround +0..3 | AP 读仍然 NO ACK，无改善 |
| 75 MHz | 所有抽头 IDCODE 都失败 |

结论：

1. **输入延迟确实生效**（抽头过大能破坏链路），但 AP 读需要的采样点比 DP 晚
   约 1–2 ns，而 DP 只容忍 ~1 ns —— 单一全局延迟没有交叠窗口。
2. 加长 ACK 前 turnaround 无效：它整体平移 ACK 相位，不改变"采样点落在 ACK
   边沿后 0.5 周期"这一事实。
3. 根因仍是 `SWCLK = FCLK/2` 下只有 0.5 / 1.0 两个采样点，AP 读的 ACK 落在
   两者之间。要真正解决，需要：
   - 把 ACK/数据的采样整体延后**一个 bit**（在每个 bit 的下一高相位采样，
     相当于 T+1.5），或
   - 提高 FCLK / 用输出侧延迟改变 SWCLK 与数据的相对相位。

IDELAY 版本保留在分支上供后续使用；60 MHz 基线未受影响。
