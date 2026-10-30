# ORBTrace 7020 / 120MHz 优化候选

`xc7z020clg400-2`，Vivado 2018.3，源码 `bc9ced6`。
14,767 LUT、16,990 FF、6,304 Slice、10.5 BRAM36 等价、1 DSP。
120MHz routed STA：WNS +0.499ns、WHS +0.020ns、TNS/THS 0；bitgen 成功。

**实验配对：尚未上板验收。** 全部 SHA-256、源码指纹及构建选项见 `manifest.json`。
保留已有验收配对，未替换 `prebuilt/` 顶层默认文件。

- `zynqlink_probe.bit` + `zynqlink_probe.elf`：50MHz 链路上限，运行 FCLK 不超过 100MHz，用于同频对照。
- 同一 bit + `zynqlink_probe_60.elf`：60MHz 链路上限的实验固件，允许 FCLK 达 120MHz，上板回归待做。
- 两个 ELF 均为 `-O3` + Thumb + unused-section GC，代码 71,300 字节，OCM 静态占用 120,976 字节。
- DAP 保持 16×4096 字节；USB 队列和 512KiB DMA arena 保持基线，运行缓冲位于 DDR。
- SWD/JTAG 诊断快照/历史/引脚观察器关闭；普通状态与性能计数保留。

板卡回归授权生效后，在优化 worktree 中加载本目录的完整配对及初始化脚本：

```powershell
E:/Xilinx/SDK/2018.3/bin/xsct.bat tools/download_dap_fpga.tcl `
  prebuilt/20261031_orbtrace_opt_7020_120_candidate/zynqlink_probe.elf `
  prebuilt/20261031_orbtrace_opt_7020_120_candidate/zynqlink_probe.bit `
  prebuilt/20261031_orbtrace_opt_7020_120_candidate/ps7_init.tcl
```

实际加载的 SHA-256、FCLK/TCK、目标状态和测速结果必须随验收记录。
完整优化及仿真记录见 `docs/orbtrace-7010-120MHz-OCM优化记录-20261030.md`。


2026-10-31 board correction: the original compact ELF triggered Data Abort on unaligned SWJ bytes. It has been replaced by a fresh firmware build from f5c938e71e0127ba573f0dcc425f62d924492965 using an aligned, bounded sequence copy. RTL/bit identity is unchanged; full hardware retest is pending. Original failed ELF hashes and logs are retained in the manifest/validation history.

Final firmware source cbedca23cae57402cb1b5e3fb0000544d5b706b8 additionally refreshes HSS counters after the last partial packet drains; no queue sizes or sampling path changed. Strict hardware retest pending.
