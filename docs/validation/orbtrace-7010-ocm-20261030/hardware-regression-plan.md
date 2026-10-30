# ZynqDAP + STM32F103ZE 实板回归入口

## 使用门槛

最早北京时间 **2026-10-31 06:21:23**。先确认另一聊天
`01a18d3e-aacf-7cd3-bd66-fe132794462c` 已停止工作，且没有进行中的 probe 采集、调试、
烧录、测速任务。门槛满足前只读文件，不运行任何连接 probe 的脚本。
当前聊天心跳 `automation` 已启用，预计首轮约 06:24。

所有命令显式使用 `E:\zynqlinkPRO_orbtrace_opt`，输出写入此 worktree 的
`docs/validation/orbtrace-hardware-20261031/<pair>/`，不写另一 AI 的目录。

## 基线和加载身份

1. 使用时重新核对 `E:\zynqlinkPRO` 中最近真正通过的 STM32F103ZE 结果及其配对，
   查验测试范围、目标 HCLK、实际 FCLK/TCK、采样模式、错误数、恢复校验和文件 SHA。
   不能把“最新文件”或未验收候选直接视为已通过基线。
2. 只读识别实际 Zynq 芯片/目标，选择匹配 part 的 bit。现有 probe 的目标配对为 7020。
3. 每次切换前核对 bit/ELF/PS 初始化文件 SHA，显式加载并保存 XSCT 输出；
   切换 worktree、参数或主机脚本不能当作已切换板上固件。
4. 对照首先使用相同频率范围的原基线和优化 50MHz 固件，随后测试优化 60MHz 实验上限。
   每点重新记录实际 FCLK/TCK/采样模式及目标 RCC/HCLK，区分时钟变化与代码/逻辑变化。

7020 候选目录：
`prebuilt/20261031_orbtrace_opt_7020_120_candidate/`。
同一 bit 的 `zynqlink_probe.elf` 是 50MHz 上限，`zynqlink_probe_60.elf` 是 60MHz 实验上限。
配对同目录的 `ps7_init.tcl`，加载脚本参数依次为 ELF、BIT、初始化脚本。

## 每个配对的主要矩阵

以下是准备好的调用方式，必须在门槛满足并显式加载对应配对之后执行。
`$bit/$elf/$out` 使用绝对路径；每个配对使用独立输出目录。

```powershell
# 50MHz 配对的公共范围，包含此前模型与实板配置有差别的 30MHz 点。
$rates = '1000000,10000000,25000000,30000000,35000000,50000000'
# 60MHz 实验配对另加 60000000，不要求 50MHz 固件接受超上限请求。

python tools/benchmark_sram_matrix.py --bit $bit --elf $elf `
  --speeds $rates --transport both --seconds 0.6 --repeats 5 --output "$out/sram.json"

python tools/benchmark_rtt_matrix.py --bit $bit --elf $elf `
  --speeds $rates --seconds 2 --repeats 3 --output-dir "$out/rtt"

python tools/benchmark_hss_matrix.py --bit $bit --elf $elf `
  --speeds $rates --transports swd,jtag --seconds 0.5 --output "$out/hss.json"
```

- SRAM：完整读/写校验、顺序与流水读、流水写；检查实际 TAR wrap，恢复备份窗口与运行状态。
- RTT：运行于 SRAM 的连续生产者，验证数据、RdOff 提交/队列所有权，恢复 SRAM、CPU 寄存器及 RCC。
- HSS：峰值、零跳点边界的多次确认、完整帧/样本数与错误/跳点计数。
  高负荷峰值的跳点如实记录，不能与零跳点稳定速率混淆。
- 增补运行 `test_probe_board.py`、`test_jtag_board.py` 的适用验收范围，并使用
  `benchmark_hss_dynamic.py` 验证运行中计数器顺序、DAP 接管和停止尾样本。
  根据脚本实际参数选择频率范围，避免运行 50MHz 固件不支持的 60MHz 默认值。
- 可用的消费者回归包含 OpenOCD RAM load/dump；保持当前目标时钟和运行状态，
  不为测速任意改目标 Flash。先读取其配置和参数再调用。

## 比较和归因

按同目标、同负载、同实际时钟匹配最近结果；同时重新运行基线，使用多轮中位数和范围，
保留原始数据。分别比较 SRAM read_seq/read_pipe/write_pipe、RTT MB/s、HSS 峰值及零跳点稳定率。
错误、字节不匹配、样本数不符或恢复失败不能作为有效吞吐结果。

稳定退化要重现，并按相同 PL + 不同 ELF、相同 ELF + 不同 PL、实际时钟/采样模式、
USB 背压和主机负载区分原因。保持既有 USB/DAP 队列深度。
必要时继续修复并重新生成、验证对应 bit/ELF，不把旧产物当成本次构建。

仅在实测通过后更新相应配对的硬件验收状态、实际时钟、SHA、源码/构建选项、
结果 JSON/日志和比较说明；保留旧已知可用配对。7010 当前只有静态 100MHz 结果，
没有物理 7010 板验收。完成全部目标后停用心跳并将 goal 标记完成。
