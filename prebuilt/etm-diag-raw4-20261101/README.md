# ETD1 RAW4 诊断配对，非Golden

本目录bit/ELF由当前研究源码实际重建，已JTAG/RAM加载、读回PS执行段、查询ETD1并做Web压力测试。
详细身份、构建选项、SHA、时序及板测见manifest.json；未编程QSPI或目标Flash。

FCLK120MHz / SWCLK上限60MHz，STA setup +0.181ns / hold +0.042ns；SWCLK输出7ns预算通过。
实际Web测试为FCLK119,999,998Hz / SWCLK999,999.98Hz，目标F103ZE CPU48MHz / TRACECLK24MHz。
30次开关探针通过，但第一轮10ms请求即发生记录FIFO满/帧FIFO丢帧，**采集稳定性未通过**。
本配对用于区分问题原因，不能宣传为稳定版、频率提升或DDR采集已完成；Golden保持原文件。

明确加载配对（AI操作）：

```powershell
python tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/etm-diag-raw4-20261101/application.elf prebuilt/etm-diag-raw4-20261101/probe.bit prebuilt/etm-diag-raw4-20261101/ps7_init.tcl
```

加载后71,620字节执行段与ELF一致；初始FCLK约100MHz，DAP建立时由PS选择120MHz。
0x61返回独立参考约200MHz及ETD1能力；0x62回读帧丢失/parser异常/水位/背压计数。
计数跨域有同步延迟，接收停止后保留，下次显式clear清除。
H743 ETMv4支持保留，但本配对尚未在H743上采集验收。
