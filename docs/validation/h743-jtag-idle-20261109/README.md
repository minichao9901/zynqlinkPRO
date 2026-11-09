# H743 JTAG 50/60 MHz idle cycles 实板对照

2026-11-09，ZL-067。CPU480/HCLK240 下，增加少量 idle 能让部分 SRAM 读写接近翻倍。CPU60/HCLK60 下增加 idle 会降低 SRAM 读写速度。CPU480 的 RTT 最快点仍是 idle=1。

## 方法与配对

- 沿用正式 J7 探针配对。开始与结束均用物理 MEM-AP0 核对 85,844 B PS 执行代码。bit SHA-256 dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6，PS ELF SHA-256 5895eeb0e79a3681a6b3b966dbea4c82ebfcd01ea7553e094d8a61ed2cf89802。
- MCU CPUID 0x411fc271、DEV/REV 0x20036450，ARM JTAG CPU TAP 0x6ba00477，IR 长度 4/5。先测 CPU60/HCLK60，经用户确认，再临时烧录已交付 CPU480/HCLK240 ELF。两配置均禁用 D-cache，Flash 装载段及 RCC 均独立核对。CPU480 ELF SHA-256 db5d66656846eeffedb1e1c405afec9345a7a5d8561eb53f987508aa1ee9dc19。
- 两档 FCLK 99,999,999/119,999,998 Hz，TCK 49,999,999.5/59,999,999 Hz，采样模式均为 17。频率由寄存器及分频计算。通过 CMSIS-DAP TransferConfigure 设置 idle，使用 0x8d 与 CFG 读回确认。RTT 期间从物理 MEM-AP0 读取 CFG，确认仍用所选 idle。ARM 路径请求 20 被钳位为 15。
- 每种 CPU 配置和 TCK 逐点覆盖 idle 1–15，首尾各测 idle=1，其余按固定随机顺序。SRAM 使用 AXI 0x24050000，512 字、深度 32、每方向 64 块，预热后三次取中位数。吞吐窗口使用 1 KiB TAR 回绕。写入交替两份不同数据，验证测试区和相邻 3 KiB 哨兵。RTT 使用同区 RAM producer、8192 B 环、1024 B 块，2 秒扫档。idle=1 和最佳档追加三轮 2 秒及一轮 10 秒。全部 RTT 序号及发布/实收总量一致。
- 两个 CPU 配置各有 32 条 SRAM、32 条 RTT 扫档结果，全部通过。另有 SRAM 7 条 10 秒复测和 RTT 20 条重复或持续窗口。逐点数据见 [evidence.json](evidence.json)。

## SRAM 对照

下表采用独立 10 秒交替读写窗口的中位数，单位 MB/s。

| CPU/HCLK MHz | TCK MHz | idle | 读 | 写 |
|---|---:|---:|---:|---:|
| 60/60 | 50 | 1 | 2.0221 | 2.0057 |
| 60/60 | 60 | 1 | 2.4192 | 2.3936 |
| 480/240 | 50 | 1 | 3.9682 | 2.0056 |
| 480/240 | 50 | 3 | 3.8156 | 3.7612 |
| 480/240 | 60 | 1 | 2.4190 | 2.3960 |
| 480/240 | 60 | 2 | 4.6451 | 2.3488 |
| 480/240 | 60 | 4 | 4.4705 | 4.3970 |

CPU480/HCLK240 的 50 MHz 写在 idle=3 时提高 87.5%，读下降 3.8%。60 MHz 的最高读速出现在 idle=2，比默认提高 92.0%。idle=4 的写速提高 83.5%，读也提高 84.8%。CPU60 下 idle=1 的读写均最快，增加到 15 后两档均下降约 22%。

## RTT 对照

下表为 10 秒窗口。

| CPU/HCLK MHz | TCK MHz | idle | 探针 MB/s | 主机实收 MB/s |
|---|---:|---:|---:|---:|
| 60/60 | 50 | 1 | 0.6571 | 0.6562 |
| 60/60 | 60 | 1 | 0.6717 | 0.6729 |
| 60/60 | 60 | 9 | 0.6796 | 0.6803 |
| 480/240 | 50 | 1 | 1.9472 | 1.9464 |
| 480/240 | 60 | 1 | 2.3203 | 2.3248 |

CPU60、60 MHz 的 idle=9 小幅领先，探针 +1.18%，主机 +1.10%。该档 SRAM 读写比 idle=1 低约 14%。CPU480 下两档 RTT 均以 idle=1 最快。

## 额外扫描与恢复

CPU480 同一 32,768 字批次中，60 MHz 读在 idle=1→2 时每字扫描段数从 2.020 降至 1.021。50 MHz 写在 idle=1→3 时从 2.020 降至 1.021，60 MHz 写在 idle=1→4 时从 2.020 降至 1.021。块引擎会在 WAIT 时重试，数据支持短 idle 引发 ARM AP 重扫的解释。扫描段计数包含 IR/DR 与尾部操作，仍缺逐拍 ACK 记录。HPM6800 的历史对照观测到 RISC-V DTM 的 BUSY 门槛，两条路径的 idle 阈值分别适用。[块引擎 WAIT 重试](../../../fpga/rtl/dap_transfer_block_engine.v#L248) · [HPM6800 对照](../hpm6800-idle-frontier-20261102/README.md)

- CPU60 首版收尾已恢复 SRAM、核心寄存器、RCC、SWD10 和 idle=1，但 JTAG 采样寄存器仍保留模式17。末项断言保留，后续显式设回模式0并读回。CPU480 首次脚本预检把空 FPB 的总使能误判为活跃断点，改为逐槽核对，首轮未进入计时。
- 两个 CPU 配置下的 RAM 夹具均已恢复并读回。只临时改写 bank1 sector0。原 Flash 写前读两遍，最终独立读回完整 2 MiB，SHA-256 f4cbd9f002921026f7f1036a7743ed2bb3832f4a9e54d4f394045b1ed05a2b82 与备份一致，64 KiB 烧录工作区也一致。目标回到 CPU/HCLK60、TRACECLK20，DHCSR 0x1010000，处于运行状态。探针恢复 SWD10、idle=1、模式0，RTT/HSS/DDR/DMA 空闲。
- ZL-067 的 H743 CPU480 JTAG SRAM 反转已找到限定配置的规避档位。固件默认值仍为 1，SWD RTT 50/60 MHz 反转仍待单独定位。

板上原固件的 CDC 回显逐字节校验通过。本次启动的浏览器页、测试服务和独占硬件服务均已关闭，临时目录已移入 Windows 回收站。[清理记录](cleanup.json)
