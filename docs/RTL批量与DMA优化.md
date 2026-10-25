# RTL 批量执行与 CDMA 优化记录

日期：2026-10-25。目标：F103 SRAM 读写均超过 3 MB/s，SWCLK 50 MHz。
所有速率使用十进制 MB/s，20 KiB 是 20480 字节。

## 先校正测量条件

1. 原测速脚本 `reset halt` 后直接访问 SRAM。实读 RCC_CR=0x00005983、
   RCC_CFGR=0，目标仍用 HSI 8 MHz。仅临时把目标切到 HSI/2 ×16、HCLK
   64 MHz，旧实现就明显加速。`tools/f103_clock64.tcl` 不修改 flash。
2. 原固件把 IO PLL 写死为 1.6 GHz，但 SLCR IO_PLL_CTRL=0x00036008，
   按板上 33.333333 MHz 参考时钟，实际为约 1.8 GHz。
   原 FCLK_DIV=1×16，SWCLK 实际约 56.25 MHz；LA 请求头时钟测得约
   56.46 MHz。现在从 PLL 反馈倍频数计算，FCLK_DIV=1×18，SWCLK 50 MHz，
   LA 请求头测得约 49.90 MHz。不能直接用量化后的周期中位数判频率。
3. STM32 官方 OpenOCD target 脚本会把 adapter speed 改回 1000 kHz。
   测试配置将速度设置放在加载 target 脚本之后。DMA 固件还通过调整 FCLK
   实现真实调速，命令接受 250 kHz–50 MHz；25/50 MHz 已实测，1/10 MHz
   的连接仍失败，不能把整个范围视为已验证。超过命令范围返回错误。

严格基线：相同随机 20 KiB 数据、HCLK=64 MHz、SWCLK=50 MHz，三次独立
OpenOCD 会话，每次读、写各 50 轮。每次均比较完整读回数据，并恢复测速前
SRAM 内容、读回核对。

| 实现 | 读 MB/s | 写 MB/s | 数据与恢复检查 |
|---|---:|---:|---|
| 原 batch + AXI-Lite，修正 SWCLK 后 | 2.078 | 2.421 | 三次均通过 |
| AXI4-Full + CDMA + repeat batch，仅加速 0x06 | 2.608 | 3.027 | 三次均通过 |
| 再加速普通 0x05，并让 idle=0 配置生效 | 2.803 | 3.307 | 三次均通过 |
| 再缩短 RTL 收尾/预启动，关闭诊断，最终版 | **3.052** | **3.367** | 三会话各读写 100 轮，均通过 |

基线原始结果：`results/optimization/legacy_exact50/results.json`。
最终结果：`results/optimization/dma_release_exact50/results.json`。
最终单次 20 KiB 平均读约 6.71 ms、写约 6.08 ms。

## HFLink 的借鉴点

本地参考 `reference/HFLink` 采用 Apache-2.0 许可证。其
`FPGA/src/DAP_Controller/cmd_worker/DAP_SWJ.v` 在硬件中解析 TransferBlock，
`interface/DAP_Seqence.v` 执行 SWD 并在硬件内重试 WAIT。核心思路是连续的
命令/数据流和硬件循环执行，避免 MCU 每个字都配置寄存器。

本次沿用 Zynq 的 USB 与 CMSIS-DAP 上层，在独立的 `fpga/` 与
`firmware/xusbps_daplink_dma/` 中实现批量流接口；没有直接搬用 HFLink 的
Gowin USB、PLL、采样时钟和整套 CMSIS-DAP 控制器。

## 数据通路

```text
USB → PS DDR 命令缓冲 → CDMA → AXI BRAM Controller → 命令 BRAM
                                                      ↓
                                                 SWD batch/core
                                                      ↓
USB ← PS DDR 响应缓冲 ← CDMA ← AXI BRAM Controller ← 结果 BRAM
```

AXI-Lite 只承担控制、启动与状态轮询。BRAM 的主机端口可突发访问，执行端
仍是双端口 BRAM 的另一端。CDMA 经 PS S_AXI_HP0 访问 DDR。

| 地址 | 作用 |
|---|---|
| 0x40000000 | 既有 AXI GPIO |
| 0x40010000 | 既有 SWD 控制寄存器 |
| 0x40020000 | AXI CDMA 控制寄存器 |
| 0x42000000，4 KiB | 命令 BRAM |
| 0x42010000，4 KiB | 结果 BRAM |

新增命令编码 `[31:24]=opcode，[23:8]=count，[7:0]=SWD request`：

- `0x04`：重复读 count 次，结果连续写入结果 BRAM。
- `0x05`：重复写 count 次，后面紧跟 count 个数据字。

旧命令格式仍保留。AP posted-read 首项丢弃，末尾读 RDBUFF；大于 1000 字
的块分段。写块也提高到每段 1000 字，避免原来 500 字的额外拆分。

缓存维护只操作独占、32 字节对齐的中转缓冲：DMA 读 DDR 前 flush，DMA 写
DDR 前清理该缓冲、完成后 invalidate，然后 memcpy 到 USB 响应缓冲。
避免对与 USB 队列共享 cache line 的地址做 invalidate。

## 同时修复的问题

- SWD 单次传输在 `data == NULL` 时仍写入结果，会写到地址 0；DMA 固件
  已修复，并将单次传输的 parity error 转换为 CMSIS-DAP ERROR。
- 完整 4096 字节响应不应再追加 ZLP，否则下一次 USB read 可能先收到空包。
  只对小于 DAP_PACKET_SIZE、且为 512 字节倍数的响应追加 ZLP。
- 既有 AXI-Lite WREADY 常高，可能在尚无 AW 地址时接受 W；新包装器按
  独立 AW/W 通道握手，并在背压时保持响应。

## 验证与工具

- `fpga/sim/tb_batch_dma.sv`：1/2/770/1000 字读、WAIT 重试、1000 字写加
  RDBUFF、FAULT 返回和出错后恢复。使用 Icarus 便携 XPM 行为模型，已通过。
- `tools/dap_dma_validate.py`：随机数据 1/2/127/128/255/256/500/770/1000/
  1001/1022 字读写；1023 字读满 4096B 后继续发下一命令。
  最终 DMA 版在 idle=0/1 下均已通过，另包含混合普通 0x05 命令检查。
- `tools/benchmark_sram_optimized.py --tag NAME`：三次独立会话，每次读写
  各 50 轮，完整数据比较和 SRAM 恢复；JSON 和日志均保存在独立目录。
- `tools/capture_optimization.py NAME`：有限 12 秒 OpenOCD 流量与 1 ms LA
  同步采集；`tools/la/swd_microtiming.py` 结合已知 IDCODE 对齐微时序。
  `swd_efficiency.py` 为启发式重同步，含毛刺波形的 WAIT/FAULT 计数可能误报。
- `tools/deploy_dap_capture.py ELF BIT --tag NAME`：JTAG 临时加载并记录
  COM5 的启动日志。固件启动时对两块 BRAM 的 4 KiB CDMA 往返逐字校验，
  失败时不开放 USB DAP 服务。

## 构建

```powershell
python tools/run_vivado.py -mode batch -nojournal -log build/fpga_dma_global_build.log -source fpga/build_dma.tcl
python tools/build_xusbps_daplink.py --project xusbps_daplink_dma --opt 3
```

Vivado 工程由 Tcl 从本地源文件创建，位于 `build/fpga_dma_global`。旧工程
源目录未修改。原 bit/ELF 与当时固件源码保存在 `build/baseline_20261025/`。

首次试验曾使用全局综合（`synth_checkpoint_mode=None`），全局综合耗时约
13 分钟。后续脚本默认复用工程、启用 `Hierarchical` 分块 OOC DCP/IP cache；
切换模式需先建立一次分块缓存。只改约束时可加 `-tclargs --impl-only`，
复用综合 DCP。通过完整时序检查的 routed DCP 会保存到
`build/checkpoints/dma_routed_reference.dcp`，后续用作增量实现参考。
子 run 的 PRE hook 设置 `general.maxThreads=8`，IP run 并行数为 4；两者
分别控制单进程线程数和多进程任务数。目录名保留 global 以复用本轮工程。

本机 Vivado 2018.3 缺少可用的程序目录 DLL 依赖。启动器从安装包自身的
lib/tps 目录补齐缺失 DLL，不覆盖安装目录既有文件；新增路径记录在
`build/vivado_runtime/installation_added_files.json`，可据此恢复。

## 当前限制

最终版读写均超过 3 MB/s。已通过 CDMA/cache 启动自检、两个 idle 配置下的
随机 SRAM 边界/混合命令检查和 OpenOCD 三会话实测。新版 RTL 增加读数据
parity error 反馈，错误时取消下一笔预启动；错误注入与恢复由线级仿真覆盖。
默认关闭非缓存逐事件 trace 与 MMIO 诊断计数；构建加 `--trace` 可恢复分析版，
分析版的性能与发布版不同。USB MPS 仍为 512，DAP_PACKET_SIZE 仍为 4096。
增量实现曾因复用旧位置导致采样路径不收敛，已使用缓存综合结果重新完整
布局布线，采用 Performance_Explore，避免重新综合 IP。

尚待完善：低频采样位置（早期 DMA 版 1/10 MHz 未通）；异常时的精确部分完成
计数。当前 batch 在错误时明确报错，但尚未为每笔已完成操作返回精确进度，
不应把它视为所有异常场景均已完成生产验证。
