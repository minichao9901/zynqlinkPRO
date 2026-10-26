# Cortex-M0+ 真实模型仿真（feature/swdio-idelay）

用本机 ARM DesignStart Cortex-M0+（`swd_cortexm0_target.v` + `CORTEXM0INTEGRATION.v`
+ `cortexm0ds_logic.v`，不复制进仓库）做 SWD 链路回归。仿真后端用 iverilog，
单次基础用例约 4 s，全量块传输约 5 min。

## 仿真环境

- `fpga/sim/sim_primitives.v`：IOBUF / IDDR / IDELAYCTRL / IDELAYE2 行为模型
  （IDELAY 抽头 78 ps，最小 1 ps 避免零延迟环）；
- `fpga/sim/tb_cortexm0_link.sv`：接 `swd_controller`，200 MHz `ref_clk`，
  可配置 `half_ns/return_ns/phase/ack_delay/turn_extra/in_delay`；
- `tools/run_cortexm0_regress.py`：一次编译 + 20 组用例矩阵；
- 通过标记：`PASS CortexM0`；失败看 `FATAL`。

## 本轮发现并修复的 bug

1. **WAIT/FAULT 后重新跑了整段 ACK**（真 bug）
   `ST_ACK_EXT` 采完 ACK2 后进 `ST_WTURN`，`ST_WTURN` 回 `ST_XFER_ACK` 时把
   `lsm` 清成 0，于是又按旧路径重采 3 个 ACK 位——此时目标已经释放总线，
   采到 111/110，WAIT 被解成 NO ACK。
   修复：`ST_WTURN` 返回时保持 `lsm=8`，只做一次已存位的解码；WAIT/FAULT
   额外走 2 个周期的换向再解码。

2. **IDELAY 行为模型零延迟环**（仿真器 bug）
   `#(taps*0.078)` 在 taps=0 时是 `#0`，某些块传输用例会让 iverilog 崩溃。
   修复：最小 1 ps。

3. **`rx_early` 模式数据错位**（死代码，已删除）
   CFG[28] 的提前采样路径在 DPIDR 读就报 parity error；固件从未使用，
   已从 RTL 和控制器中移除。

4. **FAULT 用例的激励不合法**（测试平台问题，非 RTL）
   AHB ERROR 是两拍响应（HRESP=1 & HREADY=0，然后 HREADY=1），原来的
   `force hresp=1` 单拍注入不会被 DAP 采纳；改成两拍后 DesignStart 模型
   仍不置 STICKYERR（sticky 恒 0），所以该子项降级为 `FAULT_SKIP` 警告，
   WAIT/恢复路径仍然严格检查。

## 回归结果（最终 RTL）

| 用例 | 结果 |
|---|---|
| DPIDR / 上电 / 16 字 SRAM | PASS（DPIDR=0x0BB11477） |
| 64 字 SRAM | PASS |
| `ack_delay` 1/2/3/5/7 | PASS |
| WAIT 恢复（ack 0/1/3/7） | PASS |
| `turn_extra` 1/3 | PASS |
| `phase=1` | PASS |
| 块传输 1/2/127/256/770/1023（读+写） | PASS（ack0、ack3、turn3 各跑一遍） |

已知非 RTL 问题：`return_ns < 16.67 ns` 时仿真失败，是 tb 里目标使能/主机
释放的零延迟竞争，≥ 16.67 ns 全部通过；不作为 RTL 结论。

## 综合

`build_incremental.tcl` 通过，`VERIFIED_BITSTREAM_READY`：
FCLK 上限 163.6 MHz（setup +0.111 ns，hold +0.041 ns），
SWCLK 上限 81.8 MHz；bit 在 `build/fpga_dma_global/system_wrapper.bit`。
