# RTT/HSS 的 PL→DDR 改造

当前源码的主通路是：目标 MEM-AP → PL SWD 引擎 → 专用包 BRAM → 现有 AXI CDMA → HP0 → DDR USB 槽 → PS USB DMA。
PS 负责配置、整包搬运提交和 USB 描述符；稳态不逐样本读 AXI FIFO，也不复制采样数据。
USB 描述符沿用本分支 HID/CDC/HSS 的四接口布局。

## HSS

单个字只配置一次 SELECT/CSW/TAR，prime 后每个 deadline 发一笔 DRW。
返回数据与前一笔 DRW 的时间戳配对；WAIT 不推进槽位；STOP 用 RDBUFF 收回最后一笔结果。
FIFO 预留一个槽，确保 USB 背压时仍可收尾并让出 SWD。

多字计划把连续地址作为 span 自动流水读取，遇到不连续地址或 1 KiB 页界重新设置 TAR。
一个 N 字 span 使用 TAR、prime、N−1 笔 DRW 和 RDBUFF。PS 去重重叠变量的读地址，
编译字节映射；PL gather 支持 1/2/4/8 字节及未对齐变量。

PL 直接构造 512 B DATA 包，包括零填充、样本数、序号、首时间戳。
1 字节变量每包可装 496 点；时间洞必须拆包，不能把缺拍压成连续时间轴。
低频尾包约 10 ms 发布，STOP 发布未满尾包。DEF/最终 STAT 是 PS 冷路径。

## RTT

PS 搜索控制块并验证 UP 描述符；随后 PL 自主轮询 buffer/size/WrOff/RdOff，
计算连续可读长度，处理环尾、未对齐字节和 1 KiB AP 自增边界。
最大块 2048 B，posted DRW 可链式执行；慢 SWCLK 不接受 next_ready 时回退显式发起。

`READY` 后包不可修改。PS 把它 CDMA 到空闲 DDR 槽，成功后才 ACK。
PL 执行 RdOff 写入并用 DP RDBUFF 确认完成，再回收 BRAM；PS 此时才向 USB 发布 DDR 槽。
DMA 失败不 ACK，RdOff 失败重试同一写入，两者均不重复发布。
DTR 关闭、USB 队列满时保留受保护数据并施加背压。

DAP 接管先停发新目标事务，等当前事务完成；保存/恢复 AP 与时钟上下文。
若暂停发生在等待 DMA 的边界，恢复后的 RdOff 提交重新配置 SELECT/CSW/TAR。
描述符被目标重建或读事务失败时退出硬件会话，回到发现/恢复路径。

## 缓冲区所有权

8 个 PL bank，每个 2048 B。HSS 每 bank 使用 512 B。
DDR 的 CDC/HSS 发送队列分别为 8×2048 B、8×512 B，直到 USB 完成回调才释放槽。
CDMA 和 SWD 并行；当前共用的 CDMA 在 PS 主循环串行提交，不与 DAP DMA 交叉使用。
DDR 槽在 DMA 前 flush、DMA 后 invalidate；USB 使用同一目的地址，不再 memcpy。
USB reset 作废整个会话和队列，不宣称恢复复位前尚未到达主机的数据。

## 寄存器和构建身份

SWD `FEATURES(0x4001004c)=0x44500007`，bit2 表示 PL 包通路。
专用窗口 `0x42020000` 由 PS 和 CDMA 共同访问，32 KiB 映射：

| 字偏移 | 读/写用途 |
|---|---|
| 0 | 读 `0x53545232`；写 0 停、1 HSS、2 RTT；bit8 清包队列（须停机） |
| 1 | 高16位排队包数；bit7 RTT fault；bit3 RTT active；bit2 sampler active |
| 2 | 最老包描述符：bits11:0 字节数、18:16 bank、bit24 RTT |
| 3 | 读 consumer 索引；写1表示 DDR 搬运成功 |
| 4/5 | HSS produced / 下一包序号 |
| 6/7 | 配置索引/数据：0帧字节、1版本、2周期、3初始序号、5读字数、16～79字节映射 |
| 8～12 | RTT UP 地址、ring 地址、size、初始 RdOff、最大块 |
| 13～15 | RTT poll、提交字节、错误计数 |
| byte `0x1000+bank*0x800` | 只读包数据；CDMA 源地址 |

增量构建比较所有 RTL 的 SHA256。源码变化时禁止 `--impl-only`，综合期间变化则拒绝发布 bit。
路由后检查专用包 RAM 确实使用至少 4 个 RAMB，再做 setup/hold 和 bitgen DRC。
测速工具记录实际传入的 bit/ELF SHA256，避免固定旧提交号误标新实验。

## 验证范围

`python tools/test_probe_rtl.py` 覆盖变化数据的 posted 配对、最终 flush、span/页界、WAIT、
next_ready 回退、HSS 包头/未满包/跳点/u8 大计数、RTT 未对齐 2 KiB 数据、描述符页界，
以及 DMA ACK 前不改 RdOff、失败提交不释放包。
`python tools/test_probe_host.py` 还覆盖 DMA 失败重试、RdOff 完成前不提交 USB、USB 队列满时不复用槽。
原 packet engine 与 USB transport 回归保留；真实 Cortex-M0 MEM-AP 仿真验证采样和 DAP 恢复。

本文件描述源码结构。板上成绩及配对产物的验收记录以对应测速 JSON 和构建 manifest 为准。
