# DDR HP1 内存路径已验证；ETM接入未完成，非Golden

本目录为本轮实际综合、生成、JTAG/RAM加载及验收使用的bit/ELF配对。
源版本、选项、时序、实际加载身份和文件SHA见manifest.json。

- RTL 348d73a；配套PS f364085，以ABSOLUTE边界符号保留512MiB，程序不隐式清零大段内存。
- STA：FCLK120MHz / SWCLK上限60MHz，setup +0.284ns、hold +0.066ns；SWCLK输出6.575ns / 7ns预算。
- 物理AP0读回：FCLK100/120MHz分别20轮×1MiB全部通过；完整512MiB逐字节及SHA通过。
- 完整模式写入硬件计时1.433054s，已核对数据的PL→DDR速率374.634MB/s；不是USB下载或ETM输入速度。
- 同一配对10次明确重载均通过物理OCM身份、USB枚举、正常DAP和1MiB物理数据检查。

早期CPU上下文mrd返回了32字节旧缓存线。未重录同一数据，改AP0读取即全量匹配；
旧错误记录保留用于审计，不能再作为物理DDR损坏或降低FCLK的依据。
最初一次PS进入_exit/USB缺失仍是独立历史现象，本轮10次未复现，不宣称根因已解决。

这是模式源内存pilot，没有接入ETM帧、硬件录制窗口和采后USB下载，也没有逐线校准。
当前bit不包含fpga/experiments/etm_ddr新增的窗口/FIFO模块。整体不升格Golden。
H743 ETMv4主机接入继续保留，不能把模式源测试当作H743上板采集验收。

最后一轮板上仍加载此配对，实读FCLK119,999,998Hz、配置SWCLK999,999.98Hz，写入器已结束。
Golden/recovery文件未覆盖；全程未编程QSPI或目标Flash，未修改target RCC。
原始512MiB与分块文件在私有build目录；Git内保留完整结果/块SHA、命令及首尾真实样本。
统一结论见docs/F103ZE-Web-CLI-ETM统一验收-20261031.md。
