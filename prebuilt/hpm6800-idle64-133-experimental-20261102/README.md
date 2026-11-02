# HPM6800EVK idle64实验配对，133.333MHz约束

2026-11-02。最终板测使用的bit/ELF原始字节，身份见[manifest.json](manifest.json)，详细范围及失败点见[验收报告](../../docs/validation/hpm6800-idle-frontier-20261102/README.md)。

* fresh实现约束133.333333MHz/7.5ns，setup +0.179ns、hold +0.034ns。以后默认保持133MHz；运行时仍自适应FCLK。
* RISC-V有效idle8～64，能力位守卫，ARM/SWD仍15。PS O3/Thumb、API上限60MHz，非fixed-FCLK固件。
* 实际60MHz TCK/idle20/mode17：AXI读3.200/写3.156MB/s；三个SRAM窗口各10秒恢复通过。RTT三轮约2.955MB/s；HSS单变量222.2kS/s、3/8变量50k组/s各三轮10秒零跳采。250k存在坏点，2µs极端过载短包限制仍在。
* 25MHz/idle8/mode0默认档回归及10秒压力通过。目标未改PLL/Flash/QSPI；最后运行及探针状态是报告中的带时间快照。

25MHz以上为单板超规格实验；不是Golden、ARM/ETM/QSPI正式release。不得只换脚本而假定板上配对已切换。

```powershell
python tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/hpm6800-idle64-133-experimental-20261102/application.elf prebuilt/hpm6800-idle64-133-experimental-20261102/probe.bit prebuilt/hpm6800-idle64-133-experimental-20261102/ps7_init.tcl
python tools/verify_probe_ocm_code.py --elf prebuilt/hpm6800-idle64-133-experimental-20261102/application.elf --out-dir build/hpm133-new-identity
```
