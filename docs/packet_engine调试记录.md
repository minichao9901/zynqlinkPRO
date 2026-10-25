# RTL TransferBlock 引擎调试记录（2026-10-25）

> 本文是早期调试记录，下面的初步根因和硬件阻塞状态已被后续工作更新。
> 当前 packet 路径已上板通过，新增根因包括地址译码截断、成功 status=0、
> 缺少写后 RDBUFF 和错误整包重放。详见 [修复与验收](RTLTransferBlock修复与验收.md)。

## 现象

`dap_transfer_block_engine` 接入后，第一次 0x06 块读就失败：

- 固件回退到 batch 路径后返回 `06 00 00 07`（count=0，status=7）；
- 之后整条 SWD 链路失效（单条 0x05 也 FAULT/NO ACK）；
- OpenOCD 下一次会话出现 `Sent 0x12 received 0x6`（上一次的 0x06 响应迟到，响应队列错位）。

## 二分定位

| 组合 | 结果 |
|---|---|
| 新 bitstream + 旧固件 | 块读正常，数据正确 |
| 新 bitstream + 新固件 | 块读失败 |

→ RTL 集成本身没问题，问题在新固件的 packet 路径与引擎交互。

## 固件侧证据

在 `DAP.c` 的 packet 路径加调试计数器（cache flush 后可经 JTAG 读）：

```
dbg_pkt_taken    = 1
dbg_pkt_fallback = 1
dbg_pkt_status   = 0x00000A01   # busy=1, done=0, error=0
```

说明：引擎启动后 **永远 busy**，固件 2M 次轮询超时→回退；回退时 SWD 已被半截事务破坏，于是返回 07，并留下迟到的 0x06 响应。

## 根因与修复

1. **写数据错位**：BRAM 读延迟 1 拍，`ST_FETCH_DATA_WAIT` 在数据有效前就采样，把包头当第一个数据字发出。
   → 新增 `ST_FETCH_DATA_SAMPLE`，晚一拍采样。仿真验证 `wdata=12345678`（修复前是 `0d000106`）。
2. **写响应长度**：`response_words = count+1`，写操作应为 1。
   → 改成 `is_read ? count+1 : 1`。
3. **core 忙时重启**：`ST_START_CORE` 不看 `core_busy` 就拉 start，会把上一笔事务从中间打断（NO ACK）。
   → 启动前等 core 空闲；`ST_FINAL_RDBUFF` 也改走同一入口。
4. **没有 WAIT 重试**：F103 在 50/60 MHz 下每字要回 2 个 WAIT，旧引擎把 WAIT 当错误。
   → 加 `RETRY_MAX=64`，WAIT 时重发同一笔。
5. **没有超时**：等 core 永不到来时 busy 永久为 1。
   → 加 24 位看门狗，超时报 status=0x09 并置 done。
6. **诊断**：`PACKET_STATUS[7:3]` 现在直接回读引擎状态；固件加了 `dbg_pkt_*` 计数器（可关）。

## 仿真

`fpga/sim/tb_engine_retry.sv`（1 拍 BRAM 延迟 + WAIT/WAIT/OK）：

```
read : err=0 words=3 hdr=00000002 d1=a500000f d2=a500000e
write: err=0 words=1 hdr=00000001 wdata=12345678
```

## 构建

- 含以上全部修复的增量实现已通过时序：**WNS=0.094 ns，WHS=0.045 ns**；
- `build/fpga_dma_global/system_wrapper.bit`（2026-10-25 18:32）；
- 提交：`d6dd468 fix packet engine data fetch and add WAIT retry/watchdog`。

## 待办（被硬件阻塞）

JTAG-HS3 与 CH340 掉出 USB（`Status=Unknown`，父 hub `VID_05E3&PID_0608` 无法 soft reset），无法下载新 bitstream。恢复后按顺序验证：

1. 部署新 bit + 当前 ELF，跑 `tools/dap_block_step.py`，确认块读返回正确数据且 `dbg_pkt_fallback=0`；
2. 读 `PACKET_STATUS`，确认 `state` 在正常路径上（不应停在 8/9）；
3. 50/60 MHz 下跑 `tools/benchmark_sram_optimized.py`，对比 batch 路径的 3.18/4.05 MB/s；
4. 用 LA 复核 0x06 的 SWD 波形（应无每字空档、WAIT 重试连续）。
