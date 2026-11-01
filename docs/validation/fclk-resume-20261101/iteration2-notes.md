# 第二轮结构优化

首轮完整综合及布线来源 `becba616b153a522e7c93c8612a5e8bf7febaafc`，目标 FCLK0=150MHz、RAW4/DDR/逐线延迟开启、RTL_DEBUG=0。
实际 setup=-0.962ns、hold=+0.059ns；独立 200MHz 域 setup=-0.064ns，因此单纯降低 FCLK0 也不能通过。
完整失败报告及输入指纹见 `iteration1-sta-failed/`。未生成或加载新 bitstream。
第一轮本来就是 fresh placement，旧构建脚本却再次自动 fresh 重试；已停止该任务自己的进程树，保留第一轮报告。第二轮修正为仅在实际使用过 incremental reference 时才允许该回退。

根据具体路径修改：

- DDR writer 把成功接收拍的数据/keep/地址/有效位一起寄存，再写 bank RAM；记账仍按输入接受更新，吞吐保持每周期一拍。最后一拍在进入 AXI ADDRESS 状态的边沿写入，AXI DATA 不会提前读取。
- 200MHz FIFO level 统计先寄存 level，再更新 highwater，拆开 Gray 解码/减法和最大值比较。FIFO full 与溢出保护保持原始实时判断。
- HSS 调度保留绝对 deadline 和时间戳，通过有界有符号 deadline-tick 距离判断到期，避开 32 位减法/比较串接 deadline 加法；正常时间线、跳采和首次采样边沿保持一致。
- TransferBlock 使用原有合法上限 1023 约束计数器宽度，并提前寄存最后一个事务标志；11 位前瞻和显式零扩展保留 1023 字边界和响应长度语义。
- SWD 启动时锁存 result 所属 mode；扩展 ACK 分支提前解码稳定的前两位，使 IDDR Q2 半周期路径仅选择已寄存分支。没有增加串行事务之间的空拍。
- STA 增加 SWDIO/TDO IDDR 两相 setup/hold 报告，并要求完整 timing summary 通过，覆盖 pulse width 等检查。

仿真门槛通过前不启动第二轮候选综合。板上当前仍为已明确加载并核对的 Golden 配对；本记录不构成新产物验收。
