# DDR HP1 内存路径候选：板测拒绝，非Golden

这是本次实际综合、布线、生成并加载过的bit/ELF配对。保留用于复现实验，不能作为稳定版推广。
manifest记录bit/ELF/PS init SHA、RTL与PS各自源码提交、构建选项和板测结论。
RTL输入348d73a，PS后续f364085显式导出ABSOLUTE的512MiB保留区符号；
rtl-build-inputs中的PS文件仅是FPGA构建时的上下文快照，配套PS以ps-build.json为准。

STA通过FCLK120MHz/SWCLK上限60MHz：setup +0.284ns、hold +0.066ns、SWCLK输出6.575ns/7ns预算。
DRC 0错误、46警告；这不是板上数据完整性证明。

此模块只有地址相关模式源和AXI DDR写入器，尚未接入ETM帧、硬件录制窗口或USB采后下载。
实际加载后71,620字节执行段匹配。初次PS在CDMA启动自检后退出、无USB；
一次对照重载后启动成功且1MiB模式完整比对通过，但随后另两轮实际读回失败。
B响应计数、错误码为零不能取代逐字节验证。根因尚未定位，不能把一次成功当成稳定性或频率上限。

板测归档：`docs/validation/etm-ddr-pilot-board-20261101/`，含成功/失败压缩原始输入和时钟口径。
已恢复板上到`prebuilt/etm-diag-raw4-20261101/`，恢复后的USB枚举及OCM执行段验证通过。
原Golden/recovery未覆盖，全程没有编程QSPI或目标Flash，也没有更改target RCC。
