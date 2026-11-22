# 50 MHz SWD 调试 AXI 同域 A/B

A 使用已有标准 SWD 融合 bitstream，B 使用 `--selectio --etm400 --quad-dma`。两组使用同一 PS ELF。目标为同一块 F103ZE，临时 SRAM 夹具保持 HCLK128，使用 SWD tap 8、slot 22、idle 0。HS3 临时加载配对，物理 MEM-AP0 校验 OCM。

## 时钟和地址边界

| 路径 | A | B |
|---|---|---|
| CDMA 控制入口 | GP0，`0x40020000` | GP1，`0x80040000` |
| 调试 GP1、CDMA、HP0、载荷 BRAM 主机端 | 运行态 FCLK0 约 133.333 MHz | 100 MHz `quad_clk` |
| SWD 队列执行端 | 100 MHz `quad_clk` | 100 MHz `quad_clk` |
| ETM 控制 GP0、DDR 写入 HP1 | FCLK0 | FCLK0 |
| ETM 输入和 IDELAY 参考 | 原有 200 MHz 参考与双沿接收 | 原有 200 MHz 参考与双沿接收 |

GP1 的地址窗口从 `0x80000000` 开始。AUX 已占 `0x80020000` 起的 128 KiB，B 的 CDMA 控制地址从下一段起。PS 启动时用 SWD 队列的 `BNK1` 或 `BNK2` 标识选择 CDMA 地址。旧的 cmd、rsp、pkt BRAM 保持 FCLK0，CDMA 通向它们的兼容支路使用 AXI 跨域转换。B 的 SWD 队列在同一时钟下接收 START 和 DONE，保留写回与结果检查流水。

## 短突发测法

原生 USB 命令启动测量。探针用 A9 全局定时器计时，区间只涵盖生产用 `selectio_dma_payload()` 的调用，包括缓存维护、CDMA 编程和完成轮询。每组先预热两次，再计 128 次，5 组均值取中位数。上传写入 SWD TX bank 3，下载读取 RX bank 3 并与预先取得的快照逐字校验。SRAM 实板写入另验证 TX 载荷的实际消费。两组短突发窗口均把 FCLK0 暂设为 133.333 MHz 并在结束时读回恢复。

```powershell
python -X utf8 tools/selectio_dma_latency.py --serial 12345678 --clock 133MHz --out build/swd50-dma-latency
```

| 有效字节 | A FCLK0 133 MHz，上／下行 µs | A FCLK0 100 MHz，上／下行 µs | B quad 100 MHz，上／下行 µs |
|---:|---:|---:|---:|
| 4 | 2.063 / 2.255 | 2.405 / 2.605 | 2.408 / 2.606 |
| 16 | 2.071 / 2.283 | 2.590 / 2.625 | 2.605 / 2.628 |
| 32 | 2.257 / 2.061 | 2.662 / 2.424 | 2.659 / 2.420 |
| 64 | 2.333 / 2.396 | 2.752 / 2.794 | 2.743 / 2.794 |
| 128 | 2.507 / 2.501 | 2.951 / 2.906 | 2.952 / 2.908 |
| 256 | 3.152 / 2.993 | 3.595 / 3.446 | 3.582 / 3.452 |
| 512 | 4.378 / 4.048 | 5.230 / 4.598 | 5.232 / 4.580 |
| 1024 | 6.870 / 6.046 | 7.913 / 7.117 | 7.928 / 7.105 |

B 的 1 KiB 上／下行相对 A 的 133 MHz 各增加 1.058 / 1.059 µs，约 15.4% / 17.5%。对比 A 的降频诊断组，B 差异为 +0.015 / −0.012 µs。A 的 CDMA 与载荷 BRAM 主机口原本都在 FCLK0。迁移消除的是队列提交和完成处的逐批跨域，独立计时的 DMA 短突发主要体现两端同为 100 MHz 的传输成本。[A 133 MHz](a-short-133.json) · [A 100 MHz](a-short-100.json) · [B 100 MHz](b-short.json)

## 目标负载

标准 CMSIS-DAP 使用 2 KiB TransferBlock、USB 深度 32、每方向 256 块，计 3 次。RTT→CDC 使用 8 KiB 环、2 KiB 搬运块，连续 2 × 60 秒。每个窗口保存实际时钟、逐字校验或新图案回读、目标环指针，以及 SRAM、RCC 和核心状态恢复证明。

| PC 吞吐，MB/s | A | B | B 相对 A |
|---|---:|---:|---:|
| 标准 CMSIS-DAP SRAM 读 | 3.846 | 3.827 | −0.503% |
| 标准 CMSIS-DAP SRAM 写 | 3.873 | 3.853 | −0.508% |
| RTT→CDC | 3.810 | 3.788 | −0.572% |

两组实际 SWCLK 均为 49,999,999.5 Hz（时钟树及分频折算），DWT 测得 HCLK 分别为 128.045 / 128.061 MHz。两个 RTT 会话合计逐字核对 A 463,106,040 B、B 460,853,240 B，探针报告零错误。以 2 KiB 有效载荷折算，B 多耗时读 2.69 µs、写 2.70 µs、RTT 3.10 µs。其量级与每次 1 KiB DMA 上／下行多耗约 1 µs 一致，端到端的时长差还包含 USB 调度和上层收尾。B 已达到时钟统一目标。这个工况的三项性能继续采用 A 布局。[A SRAM](a-cmsis.json) · [B SRAM](b-cmsis.json) · [A RTT](a-rtt.json) · [B RTT](b-rtt.json) · [A 恢复](a-target.json) · [B 恢复](b-target.json)

## 实现和恢复证据

B 的 133.333333 MHz FCLK0 实现约束保留，最终 setup +0.020 ns、hold +0.019 ns。布线后核对 GP1/HP0、CDMA、SWD 的 TX、RX BRAM 均在 `quad_raw`，GP0/HP1 仍在 `clk_fpga_0`。ETM 双沿五线仍接到五个独立输入采样端点。A/B 的 OCM 均由 MEM-AP0 读回 124,460 B，并使用同一个 ELF SHA-256。B 现场返回 `CDMA_BASE=0x80040000`。调试引脚仿真覆盖使用共用 AXI 时钟的 SWD、实时与队列 AP 状态交接，以及 JTAG 队列 SRAM 数据回读。[布线检查](routed-checks.txt) · [时序](timing.rpt) · [A OCM](a-load.json) · [B OCM](b-load.json) · [B 现场](b-state.json) · [仿真](swd50-quad-shared-pads-regression.txt)

前两次 GP1 地址验证分别暴露窗口起点和 AUX 区段冲突，随后在块设计中复核新地址。最初的短突发诊断尝试从写入型 TX aperture 读回，返回失败；最终诊断将上／下行分别落在真实 TX、RX 窗口。最终图案验证和 A/B 使用相同诊断版本。
