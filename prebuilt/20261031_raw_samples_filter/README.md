# 有界200MHz五线原始采样诊断配对

RAW_DIAGNOSTIC=3，单次195,072样本，约975.36us。此配对不能作为常规执行流采集使用。
manifest.json记录源码哈希、构建选项和实际bit/ELF身份；timing.rpt为本次长版结果。
本次重新编译Zynq ELF与基线字节相同，但构建元数据不同，均保留真实文件。
STA通过120MHz、板上FCLK实际100MHz；采样参考实际199,999,998Hz。

```powershell
python tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/20261031_raw_samples_filter/zynqdap_samples.elf prebuilt/20261031_raw_samples_filter/zynqdap_samples.bit
```

28份真实五线样本已验收计数/顺序/无loss/目标恢复。滤波后的ETM可用性依频率和相位而定，
并非所有频率通过；统一结论与全部失败见docs/F103ZE-Web-CLI-ETM统一验收-20261031.md。
结束实验后须重新JTAG加载常规执行流配对，不能只切换CLI的文件路径。
