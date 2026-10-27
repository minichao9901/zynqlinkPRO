# Probe 性能差距与 RTL 化审查

这是早期 `42edc7f` 的基线审查。当前改造见 [PL→DDR 通路](probe-pl-ddr.md)。
此前只用 `--impl-only` 的实验未重新综合 sampler RTL，对应实测不能算作修改后 RTL 的成绩；
新增构建流程使用源码 SHA256 拒绝这类过期 checkpoint。

基线：已发布 `42edc7f`，F103CB HCLK96MHz，SWCLK50/60MHz。
本次重新逐段核对 `E:/superlinkPRO/firmware/application_5301/src/` 的 RTT、scope、
swd_host 和 USB 热路径。结论是：第一版主要完成协议和功能接通，没有充分保留参考工程
已有的软件访问缓存、posted-read 流水线与零拷贝路径，不能作为性能完成版。

## 参考工程已有的关键机制

| 机制 | 参考实现 | 当前版本的差距 |
|---|---|---|
| AP寄存器访问缓存 | `swd_host/swd_host.c:248`，SELECT/CSW及有效TAR缓存；失败时作废 | `probe_target.c` 的读、写、claim/release重复配置和恢复；没有DAP命令也按块切换上下文 |
| 单字固定地址流水 | `swd_host.c:442/460`：CSW禁用自增，TAR只设一次，连续DRW返回上一拍值 | RTL每个样本仍执行TAR、DRW、RDBUFF，共3笔 |
| 变量span合并 | `scope/scope_sampler.c:208`：邻近地址合并；按span块读 | PS把变量展开成独立对齐字，RTL对每个字重复3笔 |
| 直接写包 | `scope_sampler.c:621`：连续布局直接写包槽；单字结果回填上一槽 | PL样本FIFO→PS逐字MMIO→栈数组→fill缓冲→USB队列，多次搬运 |
| HSS缓冲所有权 | 8个512B包，直到USB完成才回收；完成回调继续kick | 当前已有软件队列，但仅一个IN请求在途，回调只清busy，下一次主循环才提交 |
| RTT缓存与CDC续传 | `rtt/rtt_bridge.c:428`→CDC环；`usb/usb_composite.c:693`在线性窗直接续传 | 当前每块固定上限1024B，按块发送且每个512整数倍块都补ZLP |
| CDC ZLP处理 | 参考工程已移除每块无条件ZLP | 当前将纯字节流按内部块结束，增加USB事务和回调 |

所以后续重点是把这些已验证机制做成硬件持续执行、DMA和USB传输重叠，不能把“加缓存”
当成新发现，也不能只是把逐字软件算法翻译成RTL。

## 当前短测数据

数据见 [`20261027-probe-speed-baseline.json`](measurements/20261027-probe-speed-baseline.json)。
HSS为1秒稳态窗口，预热与停止阶段排除。每个会话的数据、包序号和最终样本计数一致；
跳点率 = skipped / (produced + skipped)。这些是边界探索，尚非长时间稳定验收。

| 配置 | 请求速率 | 实际有效速率 | 跳点率 |
|---|---:|---:|---:|
| 1×u32，SWD50MHz | 307.69kHz / 78ticks | 307.69kHz | 0% |
| 1×u32，SWD50MHz | 315.79kHz / 76ticks | 42.30kHz | 86.60% |
| 1×u32，SWD60MHz | 363.64kHz / 66ticks | 363.64kHz | 0% |
| 1×u32，SWD60MHz | 375kHz / 64ticks | 42.62kHz | 88.63% |
| 1×u32，SWD60MHz | 500kHz / 48ticks | 42.53kHz | 91.49% |
| 8×u32连续地址，SWD50MHz | 38.71kHz | 38.71kHz | 0% |
| 8×u32连续地址，SWD60MHz | 46.15kHz | 46.15kHz | 0% |
| 8×u32连续地址，SWD60MHz | 48kHz | 23.99kHz | 50.02% |

高频下的断崖不是单纯的SWD速度上限：当前DATA只带首样本时间与固定周期，遇到时间洞
就提前结束包。单字过载后常变成一个4B样本占一个512B包，使USB提交和主循环成为新瓶颈。
增加缓存容量只能吸收短暂抖动，不能消除这个持续速率问题。

RTT用SRAM中的持续阻塞生产者，输出连续u32序号；主机核对所有字，停止后排空，
总接收字节等于目标已发布字节；20KiB SRAM、核心寄存器和RCC检查恢复一致。

| SWD | 块大小 | 主机实际接收 |
|---|---:|---:|
| 50MHz | 256B | 1.94MB/s |
| 50MHz | 512B | 2.61MB/s |
| 50MHz | 1024B | 3.20MB/s |
| 60MHz | 256B | 0.40MB/s |
| 60MHz | 512B | 0.75MB/s |
| 60MHz | 1024B | 1.31MB/s |

60MHz反而慢的一个明确原因是每块claim都调用SWJ_Clock。当前分频搜索以整数Hz比较，
60MHz对应FCLK计算误差为2Hz，未命中`err<=1`提前退出，从而每块遍历63×63候选。
这个开销应从稳态热路径消除。上一轮简单缓存实验的ELF启动失败，未接受、未更新预编译
产物；补丁保存在本地 `build/perf_experiments/`，板上已恢复42edc7f配对。

## 现在还有哪些工作在PS

1. **RTT几乎整个服务状态机**：控制块搜索、描述符读取、可读长度、回绕、块调度、RdOff
   回写和重试、缓存空间检查均由PS完成。只有其中的SWD TransferBlock由现有RTL执行。
2. **总线所有权与配置**：PS按块保存/恢复SELECT、CSW、TAR、FCLK、SWD CFG及软件状态。
3. **HSS计划编译**：变量排序、地址对齐与字节映射在PS。这属于启动时冷路径，可继续放PS。
4. **HSS数据面**：PS轮询FIFO，每个样本读timestamp与所有数据字，提取变量、复制、判断
   分包、构造DEF/DATA/STAT、维护USB队列。稳态仍不是纯硬件数据通路。
5. **USB提交与回收**：PS驱动XUsbPs、提交dTD、处理中断、维护cache与缓冲所有权。

## 应优先改成的结构

### P0：HSS先保留参考工程的正确快路径

- 单个对齐u32：RTL只在进入会话/恢复后写SELECT、CSW_HOLD与TAR，prime一次。
  稳态每拍一笔DRW，结果与上一拍的时间戳、有效标志配对。WAIT不能推进目的槽；
  错误、DAP让路、STOP均须显式处理未完成的posted read。
- 连续变量：按span启用自增，一次TAR后连续DRW，末尾收尾；N个字从当前约3N笔减到
  N+2笔。连续8个u32从24笔减到10笔。离散地址保留多span路径，不能错误复用TAR。
- 用真实变化数据验证上一拍回填、包边界、STOP、WAIT/FAULT、DAP切换后的重新prime，
  不能只读固定常量判流水线正确。

### P1：把HSS打包、发布和搬运下沉

采样器 → 字节gather/时间戳/计数 → 双/多bank包BRAM → AXI DMA写DDR → PS USB DMA。

- RTL按预编译映射直接写最终512B DATA包，维护样本数、包序号、首时间戳与跳点计数。
- PS按完成包批量处理，取消逐样本MMIO、栈数组及两次memcpy。
- 明确FILLING/READY/DMA/USB所有权，只有USB完成才能回收。DMA与SWD执行重叠。
- 24MHz周期协议当前最小48ticks，已经硬限制请求≤500kHz。验证>500kHz时需放开这个
  限制并确认主机解析，例如40/32/24ticks对应600/750/1000kHz。

### P2：RTT持续搬运状态机

- PS只做发现、配置与异常报告；RTL缓存buffer/size、本地RdOff和AP状态。
- RTL轮询WrOff、计算连续可读长度、处理环形回绕与TAR自增页界，连续读入多bank缓冲，
  确认数据已进入受保护的缓冲后回写RdOff。失败不重复发布，背压时不提前释放目标空间。
- 没有真实DAP命令时持续持有链路；在块边界收到DAP接管请求才保存/恢复上下文。
- 增大连续搬运单位到2～4KiB并与DMA/USB重叠，避免每1KiB重新初始化整个访问路径。

### P3：PS USB仍保留，但改成批量提交

USB控制器在PS，保留XUsbPs枚举、EP0/HID、dTD提交/回收和cache一致性处理。
它们不必为了“全RTL”而重写。应利用控制器的dTD链，减少单请求在途和主循环回填空洞；
CDC稳态连续发送，ZLP/短包仅用于必要的空闲尾部刷新，不能照内部1024B块无条件补发。

## 目标的协议预算

- 主线同一硬件已有60MHz raw约4.85MB/s、线性SRAM约4.56MB/s的验收记录，
  RTT >4MB/s有现实带宽基础；需要减少额外事务并重叠搬运，尚未由当前RTT版本达到。
- 以47个SWCLK/32位传输估算，60MHz下三笔/样本约2.35µs，尚未算状态机空拍，
  当前算法本来就达不到500kHz。单笔posted DRW约0.783µs，具备验证500kHz以上的预算。
- 500kHz以上应先按**单个u32**验收；8个u32×500kHz为16MB/s，超过60MHz SWD的
  原始数据带宽，不能把单变量指标套到多变量上。

下一轮验收应同时列请求频率、有效频率、scheduler跳点、缓冲不足跳点、SWD错误、主机
实收样本/字节以及最终计数一致性；先在500kHz连续跑，再验证600/750/1000kHz边界。
