# 最后一轮 150MHz 小范围试验

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

按用户“避免死折腾”的最新要求，不再扩展到 160MHz 以上。本轮不换布局种子、不放松约束，最多再做一次基于第二轮真实路径的 RTL 修复及完整布线。若仍不能闭合，则停止新的高频尝试，报告最佳已经完成的验证层级和剩余代价，不把128.571MHz的静态重算称为已上板频率。

第二轮来源 `a303a70`：150MHz setup=-0.641ns、hold=+0.055ns。200MHz域已从第一轮-0.064ns改善到+0.424ns；SWDIO Q2半周期setup=+0.120ns。完整证据和本地保留的 routed DCP 身份见 `iteration2-sta-failed/summary.json`。

仅处理三处有量化依据的结构：

1. DDR `remaining_bytes -> payload_data/CE`：12级、6.965ns、slack=-0.641ns。第二轮虽把RAM WE隔离，但数据流水本身仍带复杂合法性CE，关键路径被搬到了77路使能。按用户随后明确的固定尾部100MiB需求，移除writer逐拍容量判定；数据/keep/地址无条件随拍采样，有效位只判断流协议合法性。生产packetizer按固定16字节formatter帧计数，预解码最后一帧；writer仅在启动及burst边界保护保留区。预期消除数据寄存器CE及remaining→keep→count→at_limit→valid反馈，保持每周期一拍与原始B响应记账边沿。具体固定内存布局见 `fixed-tail-100mib.md`。
2. HSS `stamp -> sample_pop -> fifo_forward`：18级、10个CARRY4、7.034ns、slack=-0.491ns。利用已有STAMP状态提前保存gap判定，CHECK只读取该寄存器；处理配置写与取样同边沿，保留32位回绕和gap分包语义。预期把32位减法/比较和后续读地址/forward逻辑拆开，不增加消费状态或空拍。
3. HSS 控制写入到 `deadline/deadline_gap`：-0.277/-0.350ns，控制选择被综合折叠到32/26位进位链之前。保留明确的deadline加法边界，并在配置稳定期间预计算period-1/-2，避免到期判断之后再做宽减法。预期去掉控制前缀串接长进位链；不改变首次采样、时间戳、跳采或停止语义。

验收顺序仍为 DDR/posted-read/WAIT/FAULT/包边界功能回归与相同CM3 Golden吞吐门槛先通过，再启动唯一一次候选综合实现。新结果若失败不自动重试fresh布局。已有Golden bit/ELF和板卡状态保持可回退；任何新产物必须明确区分仿真、STA和上板验收。
