# 五线稳定滤波执行流配对

RAW_DIAGNOSTIC=4：200MHz同步采样后，对五线逐位做因果两点稳定滤波，同一时刻的时钟/数据
一起解码；64K-record FIFO缓冲。实际bit/ELF、源码输入及构建选项见manifest.json。

本次fresh构建，STA120MHz：setup +0.013ns、hold +0.041ns；测试实际FCLK100MHz，参考200MHz。
6份24MHz真实波形回放与软件滤波结果逐字节一致；板上18MHz、1s、两种驱动档各3次通过。
24MHz仅短窗通过，长窗仍有loss；36MHz未通过。不能把此配对标成24MHz长期无损。

```powershell
python tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/20261031_filtered_tpiu/zynqdap_filtered.elf prebuilt/20261031_filtered_tpiu/zynqdap_filtered.bit
```

全部结论、限制和失败证据统一记录于docs/F103ZE-Web-CLI-ETM统一验收-20261031.md。
其它已知配对均保留；加载本配对后应在toolbox serve/trace命令中明确指定相同文件。
