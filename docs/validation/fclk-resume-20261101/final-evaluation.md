> 最新交付：用户选定的133.333 MHz已完成配对产物、完整已定义STA和F103范围板测，见133.333 MHz验收（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/fclk-resume-20261101/release-133/README.md`）。ETM输出与60 MHz RTT并行场景仍有原Golden也存在的失败，详见报告；下文150/135/138 MHz为历史过程记录。

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

# 本轮最终评估

**150MHz没有通过，本轮高频RTL/布局尝试已停止。** 没有生成150MHz bitstream，也没有将任何新bit/ELF加载到板上；当前仍为已明确加载、核对并测速的`prebuilt/golden`配对。

固定尾部100MiB、DDR逐拍容量判断移除及HSS结构修改在`e749c426a018cab6f543415772bbe88efb6652e4`。
共享FCLK0占用锁及相应板测入口在`5e6655c`。固件没有修改目标MCU Flash或时钟。

## 相同150MHz约束下的收敛

| 轮次 | WNS | TNS | setup违例端点 | hold最差 |
|---|---:|---:|---:|---:|
| 第一轮 `becba61` | -0.962ns | -224.268ns | 690 | +0.059ns |
| 第二轮 `a303a70` | -0.641ns | -102.934ns | 408 | +0.055ns |
| 最后一轮 `e749c42` | -0.259ns | -6.006ns | 71 | +0.033ns |

表格均取requested target报告的保守6.666ns周期。原生route报告用6.666667ns，最后一轮WNS=-0.258ns、TNS=-5.935ns；两种报告不能混用TNS。
没有更换随机种子或用假路径掩盖违例，最后一轮失败也没有自动重跑布局。

DDR数据流水的77路复杂CE已消除，实际综合CE为常量1，`at_limit`网络消失；该路径族本轮最差+0.032ns。
独立200MHz域最差+0.363ns，CDMA+0.507ns，SWDIO Q2半周期+0.169ns、TDO Q2+0.263ns，recovery+0.453ns、removal+0.477ns。

剩余负路径包括：

- HSS sampler的`head[4]`到stream `gap/D`：17级、11个CARRY4、6.754ns，slack=-0.259ns。FIFO非空/数据选择仍与时间戳减法、比较串接；本轮将gap提前到STAMP后，又暴露了上游FIFO选择链。
- SWD batch状态到SWD FSM CE：-0.212ns。
- JTAG状态到rdata CE：-0.198ns，同一路径影响多个数据位。

150MHz仍有结构优化空间，但需要进一步切分FIFO/事务控制链并重新验证完整Golden吞吐。本轮不继续扩大修改或反复跑physopt。原始报告、输入哈希及DCP身份在`final-sta-failed/`。

## 可回退工作点和验收边界

保留同一路由DCP后，仅进行了138.461539MHz静态复核，未重新综合或布局、未生成bitstream、未接触板卡。
已定义的setup/hold/recovery/removal/pulse-width检查全部通过，setup=+0.297ns、hold=+0.033ns，报告在`rerate-138-analysis/`。
这只是可选择的工作点，**不是新的上板性能结果**。目前本任务实际板测的仍是Golden的120MHz FCLK/60MHz外部调试档。

仍有5个双向GPIO/SWDIO端口缺少外部input/output delay；内部无未约束端点。CDC报告仍列35项CDC-1、8项CDC-7和4项CDC-10，另有Gray同步与握手快照警告，数量与前轮相同。
其中包括异步输入采样、跨域异步复位及命令/冻结快照握手结构；报告本身不等于全部已形式化清零，不能宣称全接口时序覆盖完成。真实7ns SWCLK pad预算一直保留，没有放宽。

## 已完成与未完成

最终同条件CM3 Golden比较的SRAM读写、RTT、HSS共十项性能指标全部一致，证据在`final-simulation/`。
DDR writer 92项、固定录制区/历史模式的集成9用例、尾部与B响应延迟、posted-read/WAIT/FAULT/gap及主机USB协议检查通过。
Debug开关已统一，独立模块核对关闭后移除9352个可选观测单元；同模块对比节省3376 LUT和9673寄存器，属于综合资源证据，不是额外debug业务镜像的验收。

尾部布局为`0x39C00000–0x40000000`，100MiB=104857600字节；诊断区从冲突的`0x3F000000`迁到`0x39000000`。
尾部两端与低512MiB对应样本独立，四处16字节全部恢复；新ARM链接通过，录制区没有已分配ELF段，OCM余量140656字节。详细布局见`fixed-tail-100mib.md`；编译检查位于`ps-layout-check-only/`，明确未配对、未加载。

**待决定后执行：**以138.461MHz为实际工作点生成bitstream，使用其真实时序元数据重建ELF，核对/加载哈希后做100MiB模式写入与物理读回、1～2秒ETM无USB排空采集，以及Golden同条件SRAM/RTT/HSS板测，最后把实际验收bit/ELF配对提交Git。当前尚未执行这些新配对验收，未用旧预编译文件冒充。
原Golden在当前48MHz目标下60MHz JTAG RTT错误计数2的现场限制仍保留；25MHz JTAG RTT基准有效，不能把既有坏点写成通过。

为复核保留的本地DCP：`E:\zynqlinkPRO\build\fclk-resume-20261101\final-routed-150.dcp`，SHA-256 `aa3897d8b421ec15431b7b56762376b313030bc3f2a05121bb70b49753112916`。未清理该文件或原工程成果。
