# 固定 FCLK133 SWD 实验配对：未验收

用户要求停止并移交，当前配对只完成短程阶梯功能检查，`accepted=false`。它不是 `../fclk133-release-20261101/` 的替代交付；后者及 Golden 均保留。

源码 `08a63b2dbc38539578dd41ec01b9a21f6a4bf10d`，RTL `e749c426a018cab6f543415772bbe88efb6652e4`；`RTL_DEBUG=0`、`DAP_FIXED_FCLK0_TEST=1`、`DAP_MAX_SWCLK_HZ=66666666`，只支持 SWD。所有 SWJ 时钟请求都保持 ARM PLL /10，计算 FCLK133333332Hz，不会暗退到120MHz。标准占空比，Q2采样，half=1时boundary=0，其他档位boundary=1。请求60MHz会向下取可实现档位33.333MHz，不能与正式配对的60MHz策略混用。

本配对在2026-11-01实际加载，OCM可执行段已逐字节核对。短程最高SWCLK66666666Hz通过；未测持续吞吐、RTT、HSS和最高可靠频率。结束时SWCLK约995025Hz，FCLK仍133333332Hz，采集/DDR/DMA空闲，目标运行、SRAM恢复。未写QSPI或目标Flash。频率依据PLL/分频回读计算，没有外部频率计测量。

接手后追加的[极限性能与Golden对照](../../docs/validation/performance-limits-20261101/README.md)已测66.667MHz SRAM三重复及60秒校验、RTT、HSS。ETM关闭时通过，ETM输出开启时66.667MHz RTT失败；实验仍未获完整验收，`accepted=false`保持不变。上段“未测”及板上状态是最初交接时的历史快照，当前板上状态以新报告收尾记录为准。

用户随后明确ETM只用低频SWD配置，高频ETM并发不在产品要求内。追加的66.667MHz RTT/J-Scope插入普通DAP命令及暂停/单步/恢复通过；J-Scope采样周期变化、完整SWJ重连边界另行记录，不能从“未挂死”推导全部业务语义已验收。

- `probe.bit` SHA-256：`ef9252c87529078c1d18ea1c05c3a19a333a20e1eee16205646b88518899ebe7`
- `application.elf` SHA-256：`b7ffe71c0edc5b8ccbd04adb14a0e43fdb7e67082d1ee00655066ee2ddd0853f`

[先读中文交接](../../docs/validation/fclk-resume-20261101/HANDOFF-20261101.md)，[实验原始证据](../../docs/validation/fclk-resume-20261101/swd-fixed133/evidence.json)。构建参数、其余文件哈希见本目录 `manifest.json`、`firmware-build.json`、`fpga-test-job.json`。已指定约束STA通过，但既有5个双向IO外部delay缺口和CDC审查项仍存在，不能视为全部接口正式签核。
