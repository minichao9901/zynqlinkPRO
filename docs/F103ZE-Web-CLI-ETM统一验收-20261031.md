# F103ZE / ZynqDAP：Web CLI、ETM与压力测试统一记录

本文件集中记录本轮结论。**2026-10-31追加离线原生链路复测：同一份1s数据完整处理中位7.208s，
解码后完整首屏中位221.5ms；首次半段缩放1.12～1.39s。此前268s与GB级JSONL来自入口漏配，
不能代表superlinkPRO C++引擎性能。**新入口默认二进制/C++存储，不再生成逐事件JSONL；详细口径见末节。
前一阶段为离线验收。随后另一AI已交付合并配对，本轮接续JTAG/RAM真机验收，进展见末节；
此前频率基线与新配对结果分别记录，不把旧结果替代新验收。

已验收滤波执行流配对的TRACECLK 18MHz、1s、两种GPIO驱动档各3次均通过；
24MHz可做10ms短窗，但长窗仍丢失，36MHz未通过。RTT完整序号流约2.34～2.38MB/s。
J-Scope单变量无跳拍测到166.7kHz、八变量无跳拍测到20kHz，超过这些点会跳拍。
原始证据保存在`docs/validation/`；没有测完的项目
明确标为待测。入口和全部命令见`docs/toolbox-cli-ai.md`，统一脚本为根目录`toolbox.py`。
本轮提交位于`feature/superlink-zynq-web`，产物、源码、回放与实板证据均随阶段提交保留。

## 配对与版本身份

上一轮ETM上板验收使用`prebuilt/20261031_filtered_tpiu/`，五线稳定滤波、64K-record FIFO，实际重新构建并JTAG加载。
bit SHA-256为`306fa26134e63509ec64a2982dfb22ab8b7164d15c1fbb617df30fbdb5f29619`；
配套重新编译Zynq ELF SHA-256为`a67ed2d1d61b99ac1e9c4d08b2f68a6308dffaca7ddb09213053896e538b855e`。
STA上限FCLK120MHz，setup +0.013ns、hold +0.041ns；测试实际FCLK100MHz，独立采样参考200MHz。
所有精确Hz数字均由晶振标称值和寄存器回读换算，含晶振误差，不是外部频率计测量值。

保留的C4基线为`prebuilt/20261030_tpiu_framefix_cli/`，同样本轮重新生成并加载，
源码提交`4a828b2`。bit SHA-256为
`2e9dff5aec83bf4eae31054f403d8b6a4c2d99a236e73c4c7cb1e0c20bbc6ed6`，
Zynq ELF SHA-256为
`a67ed2d1d61b99ac1e9c4d08b2f68a6308dffaca7ddb09213053896e538b855e`。
STA上限FCLK100MHz，setup +0.487ns、hold +0.015ns；19,237 LUT、27,916 FF、15.5 BRAM、1 DSP。
实际FCLK/TCK逐次记录于acceptance.json，不能用上述上限代替实测。

旧配对、旧目标ELF均保留。切换代码目录不会切换板上固件；需要明确JTAG加载配对。

## 已确认的问题及修复

1. 原统一CLI文档指向不存在的toolbox.mjs；已建立toolbox.py和九页动态命令入口。
2. ETM iframe跨端口导致CLI/探针互斥不可用；统一服务改为同源，接回子页所有权。
3. TPIU parser吞掉连续帧、混入HSYNC、固定半字节相位；修复后两相位及真实引脚回放通过，
   8,180个原始字节解出874字节，与独立解复用器逐字节一致；非法结构传播为loss。
4. 接收端状态误把zynq对象存在当作在线；改为检查ready。
5. 原生capture未传Trace ID、覆盖原始寄存器快照、错误JSON丢质量信息；已修复。
6. iframe返回的对象被CLI误判为类实例，丢失record字段；已修复，并阻止跨realm原型方法泄露。
7. Web烧录桥未迁入；已补入。修正ELF文件大小冒充编程量：本目标实际加载20,168字节，
   带调试信息ELF约1.2MB。烧录结束等待后端退出并释放探针，避免后续ETM抢占失败。

## 源码与目标固件

用户提供的web-etm-trace-master.zip SHA-256：
`f36427af597aaaf837ecfbc44655ac301aa0bebd1cbf2af9a7a312d5b616637e`；归档提交
`12746fc035833e90f695d45e15a1f7ffa1e132ad`。项目为
`firmware/stm32f103_cdc_trace`，使用GNU Arm 10.3.1构建F103ZE / CPU48MHz版本。
未修补重建目标ELF为`prebuilt/20261031_f103ze_cdc_trace/fw-48.elf`，SHA-256：
`a10133ec3e12e337d316a395e03287f32e1851e4160964bc936959407e3342e7`。
已通过CLI驱动Web烧录、校验、复位。后续测试使用匹配源码，旧ELF与新源码不混用。
22个DWARF引用源码文件已通过CLI上传并保存快照；稳定目录为
`docs/validation/f103ze-web-flow-20261031/source-snapshot/`。

本轮发现CDC OUT按512字节挂接收，整64/128字节发送会等待下一短包；改为端点MPS64。
配套`cdc-packet-boundary.patch`及修补后`fw-48-echo.elf`纳入Git，后者SHA-256：
`e379b4680925a1aa06208620494028a65b99de0367df23645becaae8954f676f`。
当前源码快照与此修补版匹配，31/64/65/128/512/1024字节实际回显均逐字节一致。
源码原有IN ZLP逻辑正常，本次修复位置是OUT接收长度。

## ETM流程与当前结果

已实际执行CLI→Web→本地服务→ZynqDAP→F103ZE：上传ELF、选择硬件断点、复位到起点、
配置ETM/TPIU、采集、解码、载入分析、恢复CoreSight/GPIO/RCC/FPB。
本地服务入口复用板卡事务；原WebUSB入口保留。可选本地探针服务转发实际USB/HID/COM字节，
网页仍运行原DAP、RTT、HSS解析逻辑，测试记录会区分通路。

| 已测试窗口/情况 | ETM字节 | 恢复路径 | 包问题/overflow/解码器错误 | 说明 |
|---|---:|---:|---|---|
| 10ms连续窗口 | 15,110 | 60,525 | 0/0/0 | 2个边界gap，991条未知条件 |
| 重复10ms | 15,348 | 61,497 | 0/0/0 | 目标恢复通过 |
| Trace ID 7、10ms | 15,178 | 60,827 | 0/0/0 | 自定义ID传入真实目标 |
| 50ms | 69,510 | 278,599 | 0/0/0 | 目标恢复通过 |
| usbd_initialize断点、100ms | 112,609 | 555,295 | 0/0/0 | PC准确命中0x08002278，FPB恢复通过 |

以上记录实际FCLK=99,999,999Hz，TCK=999kHz，AHB /4工作点。目标48MHz系统时钟下
HCLK12MHz、TRACECLK6MHz。同步/结束包均确认、transport loss=false。
传输无丢失不等于全部路径可证实；保留gap、未知条件与缺失源码映射统计。

初始化记录明确包含usbd_initialize、usb_dc_init、usb_dc_low_level_init等函数。
匹配新源码的10ms初始化记录已采集，包含90,298条路径、包问题0、解码器错误0。
修补后目标已用CLI采集初始化100ms及CDC echo200ms。CDC窗口中四次31字节回显逐字节一致，
发送发生在采集开始后10.0、20.8、36.9、52.5ms；执行流包含bulk_out、cdc_console_feed、
usbd_ep_start_write及bulk_in。路径1,140,170条，packetIssues=0；保留2个gap和30,781条未知执行。

### 采集长度与处理时间

以下为实际CLI→Web端到端时间，包含目标准备、采集、解码、索引与载入；不是USB带宽。
所有行目标为修补版48MHz、AHB /4、TRACECLK6MHz。

| 请求窗口 | 主机计时实际启用窗口 | ETM字节 | 路径数 | 端到端秒 | 结果 |
|---|---:|---:|---:|---:|---|
| 10ms | 20.566ms | 24,953 | 100,016 | 8.46 | 通过 |
| 100ms | 102.397ms | 137,783 | 552,374 | 28.56 | 通过 |
| 200ms | 201.950ms | 273,605 | 1,096,948 | 51.64 | 优化后通过一次 |
| 1s | 1002.394ms | 1,363,722 | 5,467,740 | 268.11 | 优化后通过一次 |

实际启用时长以host monotonic计量，包含开始/停止SWD控制开销，非周期精确时长。
200ms曾有一次PL loss=true（保留失败记录capture-6d280f2e5d5a492c8c158fef1bcd2c34），
接收端改为bytearray批量保留16-bit记录，避免逐条tuple/int分配后，200ms与1s通过。
尚未证明该分配开销是丢失的唯一原因，也不把一次成功称为长期可靠性上限。
通过行均同步、结束、无loss，完整字节核算、无packetIssues/overflow、解码器错误0；
200ms/1s仍各有2个gap及17,974/89,591条未知执行，不能隐藏。
当前接口限制最长1秒；1秒是本轮已验证的最大请求窗口，不是硬件物理极限。

## 缩放与导出

100ms初始化基线实际通过：放大到#0～#277674，再到#0～#138837，回退恢复前一区间，
缩小恢复全记录且区间提示隐藏。相关CLI返回保存在验证目录。
已从初始化区间#2～#3953导出SVG并校验XML：58个rect、16,089字节；这是旧ELF基线，
旧图仅作基线保留。此前C4基线匹配修补版源码的两张图已通过Web实际导出；当前滤波配对的最终图见文末：

- [USB初始化](validation/f103ze-web-flow-20261031/usb-initialization-matched.svg)：记录
  capture-3f283d20471c432f8a82c3a5225983ff，区间#2～#8210，18,000字节，
  SHA-256 `fd487378d413932bd77d2296e0f044ca01e37d3cec5417e3f6211951ba021529`。
- [CDC echo](validation/f103ze-web-flow-20261031/cdc-echo.svg)：记录
  capture-8befceae549f4369bd5f6acb3e8a81aa，区间#189～#243868，11,873字节，
  SHA-256 `51678822b84fef6ee71e646fadb26d882b9886c6d7d940b0d6c23cf40afb1e42`。

宽度权重为恢复路径记录数；当前未启用周期元素，不能把图宽解释为实测执行时间。

## TRACECLK上限与软件滤波实验

### 当前执行流配对的实测频率

以下均明确加载C4执行流bit/ELF，FCLK实际99,999,999Hz、采样参考199,999,998Hz；
SWD设1MHz并读取divider确认，实际约999,999.99Hz。TRACECLK按HSE8与RCC读回值换算，
原始波形另行检查边沿周期。GPIO 1=10MHz驱动、3=50MHz驱动；驱动档不是TRACECLK分频。

| 目标系统时钟 / AHB | TRACECLK | 10ms：GPIO 1 / 3，各3轮 | 更长窗口 |
|---|---:|---|---|
| 48MHz /4 | 6MHz | 3/3、3/3通过 | Web 1s通过一次，曾有200ms丢失，见前表 |
| 72MHz /4 | 9MHz | 3/3、3/3通过 | 尚未做1s重复 |
| 48MHz /2 | 12MHz | 3/3、3/3通过 | GPIO 1的1s连续3/3通过 |
| 72MHz /2 | 18MHz | 3/3、3/3通过 | 100ms两档各3/3；1s GPIO 1为2/3，另一次loss |
| 48MHz /1 | 24MHz | 0/3、0/3，均loss | 不接受为可用点 |
| 72MHz /1 | 36MHz | 0/3、0/3，均loss | 不接受为可用点 |

因此，**C4基线已验证到18MHz短窗/100ms，但1s尚不稳定；24/36MHz在C4不可用**。
这不是18MHz绝对物理上限，也不是任意软件负载下的无损保证。18MHz长窗失败发生于约76%
记录位置，USB包序列连续、source ID始终2、PL loss=true；仅凭这项综合标志不能断定
是引脚误采还是后级背压。测试时同时运行Vivado，系统负载属于本轮环境条件。
证据集中在`validation/f103ze-web-flow-20261031/frequency/`，失败均保留。

72MHz目标为`fw-72-echo.elf`，同一源码和CDC补丁，`-Chip ze -CpuMHz 72`重新构建，
已由CLI控制Web烧录/校验/复位；USB仍48MHz。不能将48MHz ELF加载后仅修改目录名当成72MHz。

### 同一份原始波形的滤波对照

诊断配对为`prebuilt/20261031_raw_samples_filter/`，RAW_DIAGNOSTIC=3，真实JTAG重载。
bit SHA-256 `beba18893b667a32385eb58e6dcf24a6a3868e55fea899f7db4f78de1ee20da1`；
重新编译Zynq ELF SHA-256 `a67ed2d1d61b99ac1e9c4d08b2f68a6308dffaca7ddb09213053896e538b855e`。
STA上限120MHz：setup +0.028ns、hold +0.036ns；**板上实际仍100MHz FCLK**，不是120MHz。
每个16-bit记录保留三个五线样本，单次65,024记录=195,072样本、约975.36us，
所有28次物理采集均确认样本数、顺序、结束、无loss及目标恢复。synced在此只表示采样器启动，
不代表TPIU或ETM已经同步。短版48,768样本产物未上板、未作为本轮交付。

滤波在5ns采样点上作用于全部五根线：三点多数为当前/前一/前二样本逐位多数；两点稳定
为同一位连续两点相同才改变输出。两者均为因果滤波。每份数据另外独立扫描半周期的
0/0.25/0.5/0.75位置及两种半字节相位，严格TPIU解复用后交OpenCSD；不补写ETM字节。

| TRACECLK | 原始样本份数 | 不滤波 | 三点多数 / 两点稳定 |
|---:|---:|---|---|
| 6MHz | 6 | TPIU结构失败 | 可恢复TPIU，但短窗无I-SYNC、路径0；不算执行流通过 |
| 9MHz | 2 | 有效ETM | 有效ETM；多个相位可用 |
| 12MHz | 6 | TPIU结构失败 | 6/6恢复有效ETM |
| 18MHz | 4 | 逐份结果见comparison.json | 两种滤波均恢复有效ETM，须选合适相位 |
| 24MHz | 6 | 6/6失败 | 两种滤波均6/6恢复有效ETM，固定offset=0/nibble=1可用 |
| 36MHz | 4 | 全失败 | 全失败，不能修复 |

24MHz固定相位下恢复3,794～3,804字节ETM、14,755～15,449个OpenCSD指令范围，packetIssues=0，
decoderLastError=0。记录保留开始时未同步字节和短窗尾部，不将这0.975ms称为完整业务采集。
个别相位即使解码器未报错，得到的ETM字节SHA也不同；应使用相位一致性与全部质量统计，
不能只凭“能解码”认定数据正确。9MHz不滤波的边沿取样也出现过这种差异。

**软件滤波有帮助，但本轮只证明其可恢复部分原始短窗，未把当前连续采集上限提高到24MHz。**
36MHz样本中约924～984个单采样点半周期，滤波后边沿数量明显改变，仍无法通过TPIU。
不能把被滤掉的合法短脉冲与毛刺混为一谈，也不能把滤波后的边沿计数当作精密频率计。
现有执行流通路只上传已经解复用的ETM字节，主机拿不到时钟/数据波形，无法事后重新滤波。
若要连续应用，需在FPGA中先滤波/调整取样位置，或改为保留波形；五线200MHz原始数据
本身125MB/s，本方案打包后约133MB/s，当前USB2链路无法持续传这些原始样本。

短窗需等待周期同步。Cortex-M3的ETMSYNCFR为只读0x400，不能靠向它写更小值增加同步频率；
参见[Arm Cortex-M3 TRM，§10.2/10.3](https://documentation-service.arm.com/static/5e8e107f88295d1e18d34714?token=)。
本轮6MHz短窗可解TPIU但无执行路径的结果因此保留为限制，未伪造成功。

## RTT、J-Scope、烧录与调试压力

- 原生底层RTT21轮、19,965字节逐字节一致；HSS v1/v2单变量和v2八变量通过，SRAM恢复一致。
  这是底层验证，不能替代完整Web压力结果。
- Web/OpenOCD烧录已通过，实际20,168字节、约1.5s，校验与复位完成。
- Web调试器IDCODE0x1BA01477、6个FPB比较器和23项寄存器状态正确。修复后的实际20轮
  暂停→断点cdc_poll→继续→精确停下→读寄存器→指令单步两次→清断点→继续，全部通过，
  结束清理并断开。证据在`http-and-debug/f103-debug-keepalive-20261031/`。
- 串口整64/128字节问题已通过目标源码修复及真实echo验证。复位采集时PA12临时断开后，
  COM34重新枚举并可继续逐字节回显；Web串口64字节、DTR=true/行尾none也已实测一致。
- RTT、J-Scope实测速率和完整性见下表；数十次Web桥烧录/校验/复位与各页间探针交接已实际执行。


### 五线滤波移入FPGA后的连续采集验收

新增执行流配对将软件实验有效的逐线两点稳定滤波放在TPIU解复用之前，时钟与数据取同一时刻，
并把记录FIFO增至64K。6份24MHz真实波形回放中，新RTL输出与软件结果逐字节一致、无loss；
原C4 RTL对同样6份输入全部复现loss。仿真与真实板卡结果分别保存，不能相互替代。

| 配对 | 18MHz / 1s | 24MHz / 10ms | 24MHz / 100ms | 24MHz / 1s | 36MHz / 10ms |
|---|---|---|---|---|---|
| C4基线 | 2/3通过 | 0/6 | 未接受 | 未接受 | 0/6 |
| 新滤波配对 | 两档GPIO各3/3，共6/6 | 两档各3/3，共6/6 | 5/6 | 0/3 | 0/6 |

新配对的6/9/12MHz短窗也均通过。18MHz每个1s窗口约2.925MB ETM，OpenCSD约1,441万条
指令范围，无packetIssues/地址不可读/解码器错误，完整结束、无loss，寄存器与FPB恢复通过。
因此当前建议18MHz工作点；它是本轮重复验证的上限，不是已经穷尽全部频率、线长和负载的物理极限。
24MHz长窗仍失败，不能因短窗能解码就发布为长期无损。失败样本source ID仍为2，综合loss标志
本身不足以区分采样错误与背压；尚不能把剩余原因确定为USB带宽或某一个环节。

### RTT转发：完整原始窗口，而非显示区历史

测试靶为额定72MHz的`prebuilt/20261031_f103ze_rtt_seq72/fw.elf`，源自固定快照并保留源文件哈希。
每条`seq NNNNNNN`记录13字节，阻塞式32KiB上行缓冲。每档先经Web实际烧录/校验/复位，
然后CLI设置HID转发、打开COM33，在Web端记录3秒原始字节，逐条检查连续序号及首尾边界。

| 请求SWD MHz | PS寄存器回读实际MHz | Web窗口 MB/s（10^6 B/s） | 完整性 |
|---:|---:|---:|---|
| 20 | 19.565217 | 1.562 | 连续序号通过 |
| 30 | 25.000000 | 0.024 | 读错；不接受 |
| 36 | 36.000000 | 2.378 | 连续序号通过 |
| 45 | 45.000000 | 2.379 | 连续序号通过 |
| 50 | 50.000000 | 2.344～2.378 | 3次×3秒全部通过 |
| 60 | 未形成有效输出 | 0 | 当前配对上限50MHz，此请求不接受 |

50MHz三次分别核对548,799、542,004、541,286条记录，序号缺口/读错均0；FCLK回读99,999,999Hz，
SWCLK回读49,999,999.5Hz。约2.34～2.38MB/s是当前整套Web/本地转发/目标生产者的实测结果，
不是保证所有目标和浏览器都相同，也不能把更高的请求时钟自动视为更快。30MHz档的读错明确保留。

排查并修复了两类接收问题：高速关闭显示前必须先写有界原始缓存；本地串口必须实际传入Web请求的
64KiB接收预算，原实现遗漏该选项时出现过20,480字节差额和16处序号缺口。长窗口采用新增
`captureWindow`独立原始记录，不受2MiB显示历史上限影响；普通显示历史的截断仍明确保留。

RTT Viewer独立WebUSB解析通路也读到真实控制块0x2000000c，持续读取98,301字节，原始导出核对
7,555条连续序号、无缺口。修复后台轮询/统计时基、抑制显示时原始历史保存及断开前等待在途readUp。
交接后下一客户端再次读到IDCODE和完整RTT签名。`save`保留可读显示输出，`saveRaw`导出有界原始字节。
本轮Native RPC通路带有额外往返，Viewer的读速不作为浏览器直接WebUSB性能上限。

### J-Scope：单变量与八变量

靶为`prebuilt/20261031_f103ze_scope72/fw.elf`，额定72MHz，Flash与RCC实读核对通过。
单变量为`g_pack.u_hi`；八变量为连续24字节的浮点正弦、三角、计数器、16/8位有符号与无符号数。
每份CSV逐样本检查高位、计数回退；八变量再按已知数学波形核对，允许非原子更新造成的±1 tick。
所有下列记录数据值错误、USB丢样和读错均0；跳拍另列，不把“数据值正确”当成“请求速率达到”。
实际频率由采样时间戳和完整记录计算；开始时的live快照可能早于首包，最终以CSV/结束摘要为准。

| 通道 | 请求周期µs | 实际kHz | 探针跳拍 | 说明 |
|---:|---:|---:|---:|---|
| 1 | 100 | 10.000 | 0 | 无跳拍 |
| 1 | 20 | 50.000 | 0 | 无跳拍 |
| 1 | 10 | 100.000 | 0 | 无跳拍 |
| 1 | 5 | 198.898 | 1,733 | 未达到完整请求速率 |
| 1 | 2 | 99.167 | 735,939 | 未达到完整请求速率 |
| 1 | 8 | 125.000 | 0 | 无跳拍 |
| 1 | 7 | 142.857 | 0 | 无跳拍 |
| 1 | 6 | 166.667 | 0 | 无跳拍 |
| 8 | 100 | 10.000 | 0 | 无跳拍 |
| 8 | 20 | 43.368 | 14,410 | 未达到完整请求速率 |
| 8 | 12 | 57.094 | 56,570 | 未达到完整请求速率 |
| 8 | 10 | 68.847 | 64,899 | 未达到完整请求速率 |
| 8 | 60 | 16.667 | 0 | 无跳拍 |
| 8 | 50 | 20.000 | 0 | 无跳拍 |

本轮单变量无跳拍测到166.7kHz，200kHz已有跳拍；八变量无跳拍测到20kHz，25kHz已有跳拍。
因此无跳拍边界分别在已测166.7～200kHz、20～25kHz之间，尚未声称穷尽每个细分点或长期负载。
500kHz请求实际约99kHz，存在大量跳拍，不能宣传支持500kHz。

同时修复HSS端点识别：只在厂商接口中选择IN3/IN7，避免把Zynq的CDC IN3误认成HSS；Zynq HSS为IN7。
STOP必须检查返回码；Zynq返回忙时保持读流排空，确认停止后才关闭端点，避免下轮配置被-7拒绝。
完整矩阵跨档启停已通过。FPGA重载后，同一会话重新打开自己的HID/USB/串口句柄；generation保护
防止旧的迟到close关闭新句柄。实际执行保持连接→JTAG重载→刷新→HID/IN7重连通过，无需重启服务。

### 最新配对上的完整ETM流程、导出与最终状态

滤波配对+48MHz修补目标再次完成CLI驱动Web：导入ELF/22份源码、UI选择`cdc_acm_init`断点、
复位准确命中PC0x080004d0，USB初始化100ms；随后从`cdc_poll`采200ms并同步发送四次31字节。
四次回显逐字节一致，发送位于22.85、41.82、57.88、73.44ms，均在采集窗口内。

| 阶段 | ETM字节 | 路径 | 未知执行 | gap | 包问题/overflow/解码器错误 | 服务解码/索引秒 |
|---|---:|---:|---:|---:|---|---:|
| USB初始化 | 111,019 | 550,167 | 32 | 2 | 0/0/0 | 17.21 |
| CDC echo | 344,651 | 1,139,372 | 30,759 | 2 | 0/0/0 | 36.54 |

两者同步、结束、无loss、全部输入字节核算通过，CoreSight/GPIO/RCC/FPB均恢复。
初始化包含cdc_acm_init/usbd_initialize/usb_dc_init；echo执行流包含OUT回调、队列处理、发送及IN回调。
缩放、再次缩放、回退、缩小恢复全记录通过；源码导航显示main.c第182行，切换火焰图后也跟随选中行。
记录打开入口同步选择框与分析内容，避免低层history.load造成标题与实际记录不同。

最终SVG均由Web在实际记录区间导出，XML已检查，权重为路径记录数：

- [USB初始化SVG](validation/f103ze-web-flow-20261031/final-flow/usb-initialization-filtered.svg)：
  capture-a63604803b8947d1a26d0ed1c3766132，#0～#6934，48个rect、13,449字节。
- [CDC echo SVG](validation/f103ze-web-flow-20261031/final-flow/cdc-echo-filtered.svg)：
  capture-5a32966b3a6e4d70848bb4b35073ff5c，#123005～#414358，29个rect、8,231字节。

各图SHA-256与CLI步骤在final-flow/exports-cli/summary.json。
最终板上保留滤波Zynq bit/ELF与fw-48-echo.elf；最后又做10ms采集及64字节CDC逐字节回显，
确认目标运行、FPB恢复、COM34可用。要复测18MHz需按文中明确加载72MHz目标，AHB /2；
当前48MHz目标用于完整USB业务演示，AHB /4采集时TRACECLK6MHz。

本轮硬件验收通路为CLI→实际Web页面→经鉴权的本机USB/HID/COM服务→真实探针和目标，
页面原有DAP/RTT/HSS解析器照常运行。IAB未完成浏览器原生设备选择授权通路的独立硬件验收；
这项边界明确保留，不能拿本机RPC吞吐替代直接WebUSB结果。旧兼容采集shim修正ETM LAR地址和
编程握手超时，未把它的独立浏览器入口冒充本轮已验收的Native采集入口。

### Web长压力时的HTTP与MMIO修复

原服务逐请求关闭TCP连接，调试期间观察到11,887条TIME_WAIT，Windows动态端口范围
49152～65535、共16,384个。失败时刻System日志Tcpip事件4227明确报告本地端点重复使用
造成出站连接失败，说明此前的Failed to fetch并非用户拔线。切换为支持HTTP/1.1连接复用的
Waitress 3.0.2后，5,000次请求只使用1个客户端端口，耗时2.38秒；随后完整20轮调试通过，
59,417次本地传输请求，重投递次数0。采用的参数见[Waitress官方文档](https://docs.pylonsproject.org/projects/waitress/en/latest/arguments.html)。

本地传输另加请求ID与结果缓存：网络交付失败可用相同ID重新取得原结果，服务端只执行
一次硬件动作；已回收的结果拒绝重放。不是重做烧录、复位或USB读写。队列轮询和完成回传
也可恢复短暂连接中断。端口事件、5,000次连接复用记录和所有失败现场均保留。

通用写内存还曾把MMIO回读值与写值比较，DCRSR等写只/自清除寄存器被无意义地重写。
已改为MMIO只写一次并排空posted AP写，避免读副作用寄存器；SRAM仍做回读校验。
该修复有针对性测试及上述20轮实际调试验收。

## 提交与复核

本轮完整实现与配对源码提交：`13c7b524aa1f88acdf9073efb278af6434e48820`。本地Python 25项、Web自测27项均通过；
既有九页Web CLI冒烟56条通过。所有仿真与实板结果在各自JSON中标明，不混为硬件验收。
bit/ELF、PS初始化、构建元数据及测试靶源文件的SHA-256已对照Git暂存字节再次核对。
当前保留已知配对和失败样本；工作台最终截图为
[ETM界面](validation/f103ze-web-flow-20261031/etm-final.jpg)。


## 1秒数据量、USB HS承载与实时显示

以下来自已保存的1秒实际记录，MB=10^6字节；不同固件/分频/业务负载不能直接当作恒定码率。

| TRACECLK | ETM净字节 | USB应用层载荷字节 | 约合USB载荷MB/s |
|---:|---:|---:|---:|
| 6MHz | 1,363,722 | 2,909,364 | 2.90 |
| 12MHz | 2,121,671 | 4,526,318 | 4.51 |
| 18MHz | 2,926,065 | 6,242,306 | 6.23 |

这里的USB列不是直接拿ETM文件大小代替：每个记录含8位source ID和8位ETM数据，另有32字节
ZET1包头；满包240记录，共512字节。18MHz这一份为2,926,065记录、12,193包，因此
`2×2,926,065 +32×12,193 =6,242,306`字节，且与保留的usb-wire.bin文件长度一致。
这个数还不含USB总线协议开销、EP0控制请求和零长度包在总线上的开销。

USB HS的标准信号速率为480Mbit/s（60MB/s仅为位速率折算，不是可用应用吞吐），见
[USB-IF FAQ](https://www.usb.org/faq)。约6.24MB的1秒载荷在总线带宽预算内；当前完整实现也已在
18MHz下通过6个独立1秒窗口。24MHz长窗loss仍不能仅凭标志归因为USB HS物理带宽不足，
也不能把有限窗口通过等同于已经验证10分钟/无限持续采集。程序负载改变后需重新测量码流。

此前实板已经验证采集期间持续经USB收取原始记录；FPGA并非先存满1秒再上传。当前应用流程仍为
**有限窗采集结束→保存→解码与存储→索引准备→Web分析**，尚未实现持续执行流的增量解码和实时显示。
本节原来引用6MHz一秒Web全流程268.11秒、100/200ms服务17.21/36.54秒，以及两份JSONL约4.71GB，
这些是**新增入口漏启原生配置时的历史结果**。它们不能用于判断已迁入C++引擎的能力；原始证据保留，
本次不重跑旧JSON路径。268.11秒包含采集等阶段，与下节离线处理计时边界不同，不据此宣传精确加速倍数。

## C++原生默认链路与同一份1s数据离线复测

### 原因与修复范围

核对`E:/superlinkPRO/docs/etm-native-engine.md`、`etm-performance-baseline.md`和
`etm-1s-release-20261023.md`后确认：OpenCSD二进制输出、C++ storebuild、数值查询索引和原生导出已迁入。
原有`trace_cli.engine_environment()`已经定义原生运行配置；我新增的Web服务和Zynq采集CLI没有调用它，
落入低层库的text/Python默认值。问题在新入口接线，先前将其描述为“还需改成二进制和紧凑存储”不准确。

修复提交`5940c5c`：Web后端启动时和Zynq CLI采集解码前均调用同一个原生配置函数；离线`trace decode`
原本已通过迁入CLI设置该配置。开启`STORE_WRITE=1 / STORE_ENGINE=native / NATIVE_FORMAT=binary /
STORE_ENGINE_FALLBACK=0 / DECODE_ENGINE=fast / EXPORT_ENGINE=native / QUERY_ENGINE=native /
PREPARE_CACHE=1`。继承旧环境变量也会被产品入口改正。原生工具不可用会报错，不静默转Python建库。
Web `/etm/api/health`、`/etm-launcher.json`及CLI运行信息会报告`decodeEngineProfile`。

实际链路为：`capture.bin → C++ OpenCSD native.bin → C++ storebuild → 数值索引/默认视图准备 → Web按需查询`。
数值索引的NumPy向量计算等既有实现照常使用，不能把“原生配置”解释成所有代码均已纯C++。
控制响应、会话元数据、分桶查询结果仍有小型JSON；已去除主路径上的逐指令/逐事件JSONL。
低层参考入口保留供回归对照，不作为Web/Zynq CLI默认路径。更改启动配置需重启旧服务进程才生效；本次已退出旧8882进程，保留8883离线原生工作台。

### 输入、计时边界与环境

本次完全离线，使用同一份已保存的真实6MHz、1s、F103ZE 48MHz/AHB /4记录：
`capture-1419738de1e7417bb0d8a34346823242`；原记录只读，复制原始输入到三个独立新记录重建，未复用旧派生索引。

- ETM：1,363,722字节，SHA-256 `2cb5838887188cbdebf554967281ad44f03eca9aab2867cde82e548ca9873199`。
- ELF：SHA-256 `e379b4680925a1aa06208620494028a65b99de0367df23645becaae8954f676f`。
- 源码快照：SHA-256 `6533c1d4df3832ae8b9ad1013e6bb3c2fc5c8660e26531e2068d8891328bec44`。
- 主机：Ryzen 7 PRO 5850U、8核16线程、Python 3.13.5；实际版本及五个原生EXE的哈希及支持`--version`工具的协议握手见
  [environment.json](validation/native-engine-offline-20261031/environment.json)。
- Web：IAB视口694×668，ETM iframe 694×632，页面可见。使用真实工作台CLI队列调用，未用模拟DOM替代浏览器测量。

“完整处理”从提交正常Web解码请求计到任务完成：包含解码、源码解析/存储、数值索引、元数据和browse准备；
不包含采集/USB、复制测试输入或浏览器绘制。三次同一服务顺序执行，第一次ELF缓存未命中，后两次命中；
OS磁盘缓存未清空，不能称为三次冷启动。准备默认查询缓存的工作已计入处理时间。

“完整首屏”从CLI调用正常打开记录开始，到执行流、默认函数时间线、历史选择/源码状态完成，再等待两帧；
不包含工作台初次启动和前述解码。`painted=true`且文档可见才计为完成，隐藏页和时间线失败不能冒充首屏。
“缩放”使用同样的显示完成边界，包含后端窗口查询、前端更新和两帧等待。

### 完整处理与磁盘结果

| 同一输入重建 | API完整处理秒 | 服务解码/建库秒 | 服务任务秒 | 解码后完整首屏ms |
|---|---:|---:|---:|---:|
| 第1次 | 7.955 | 6.976 | 7.730 | 210.9 |
| 第2次 | 7.208 | 6.457 | 7.149 | 221.5 |
| 第3次 | 6.832 | 6.124 | 6.801 | 251.5 |
| 中位数 | **7.208** | **6.457** | **7.149** | **221.5** |

第2次内部计时：OpenCSD 0.771s，storeBuildAndIndex整体5.668s；后者内含C++ nativeBuild 1.914s、
数值queryIndex 1.444s等，嵌套阶段不能相加重复计算。browse准备另0.463s。
初次离线CLI探测解码6.723s、整个CLI约7.928s；严格质量门禁因原记录`gaps=2`返回5，
并非原生引擎执行失败，也没有为了通过测试放宽门禁。这份输入不能宣称CLI质量门禁全绿。

三份新记录均明确`engine=native / fallback=false`；无`native.jsonl / events.jsonl / elements.jsonl /
packets.jsonl / browse-columns.tsv / browse-v3.sqlite`。每份`native.bin`为360,776,440字节，
最终`store.bin`约20,351,857字节，整个结果目录约385.29MB。20.35MB只是最终存储文件，
不是全过程磁盘占用；本次仍保留360.78MB原生二进制中间件，并非完全消除了数据展开。

### 首次缩放与缓存差异

各记录均从全段连续放大三次，再连续缩小三次；序号区间和逐次结果保存在
[zoom.json](validation/native-engine-offline-20261031/zoom.json)。缩小时所选中心会改变边界，不能笼统视作每档全命中缓存。

| 显示操作 | 次数 | 完整显示耗时ms | 口径 |
|---|---:|---:|---|
| 执行流：首次全段→半段 | 3 | 1118.8 / 1392.2 / 1299.4 | 各记录首次大区间计算，中位1299.4 |
| 执行流：后续半段→1/4→1/8 | 6 | 208.6～230.4，中位216.9 | 连续放大，含默认时间线 |
| 执行流：三档连续缩小 | 9 | 81.7～314.4，中位219.4 | 最终恢复全记录 |
| 执行顺序火焰图：连续放大 | 3 | 57.8～78.0，中位58.5 | 第3份记录，执行流已查询过邻近区间 |
| 执行顺序火焰图：连续缩小 | 3 | 69.8～200.6，中位123.7 | 包含恢复全记录；不是全冷查询 |

火焰图使用“按执行顺序”，并非只显示预计算聚合统计。首屏快和已缓存缩放快，不代表首次任意窗口都同样快。
当前首个大区间仍存在约1.3秒可感知等待；三份输入和少量窗口测试不能覆盖所有函数深度、业务负载或长时压力。

### 语义一致性、验收结果与实时差距

三次原生重建的全部summary和共有quality字段均与保留旧结果相同：5,467,740条路径，
5,019,787条已证实，89,591条未知，250次异常，2个gap，包问题/overflow/解码器错误均0；全部输入字节核算通过。
另从保留SQLite/JSONL只读取样，与原生存储重建的完整事件字典比较1,759条：包含全部503个边界/中断事件及
相邻指令、全段均匀样本、未知及未成立条件；PC、机器码、源码行、调用栈、执行状态及边界payload全部一致。
这是抽样语义验证，不能写成对546万事件逐条全量比较。
[比较证据](validation/native-engine-offline-20261031/equivalence.json)记录了具体序号。

默认配置Python回归28项、Web自测30项通过。包括旧环境强制修正、Zynq解码前启用原生配置、
隐藏文档/不完整时间线拒绝伪造绘制完成，以及实际Web首屏/24次缩放无CLI错误。
新脚本和计时接口提交`7b7ea55`；[默认时间线截图](validation/native-engine-offline-20261031/native-first-screen.jpg)保留了实际分析页面；
原始处理、首屏、缩放和命令证据统一在
[离线验收目录](validation/native-engine-offline-20261031/)。
本次未接板，不改变既有18MHz实板结论，也不声称合并后的PL/PS产物已经通过ETM真机验收。

以本负载计，当前完整处理7.208秒才能消费1秒记录，约为实时所需吞吐的13.9%，
串行路径若要跟上持续输入仍需约7.2倍吞吐提升；不能用OpenCSD单项0.77秒或首屏0.22秒代替整条链路。
记录已准备好后可快速显示和交互；当前实现仍是有限窗采集后分析，**尚不能全量持续实时显示**。
将1秒采集与中位处理/首屏简单串行预算相加约8.43秒，但这是离线分段估算，并非本次真机端到端实测。

后续实时化应在已有二进制/C++链路上做增量和流水化：保留OpenCSD状态，分块生成可追加的数值存储和索引，
采集、解码/存储、统计与绘制使用有界队列并分别量化积压。优先调查本次5.67秒的建库/索引整体及首次大区间查询，
再独立验收统计预览和全量指令/源码显示；软件滤波不能解决这部分CPU/存储吞吐，也不能恢复已经丢失的引脚信息。

### 离线复测命令

在仓库根目录运行。第一个命令启动与产品共用的Web服务和默认引擎，复制原始输入并连续重建三次；
本脚本禁止状态探测和采集接口，无需连接板卡。`--out`必须是新目录，避免复用派生缓存。

```powershell
python tools/bench_etm_native_offline.py --record etm-service/records/capture-1419738de1e7417bb0d8a34346823242 --out build/native-offline-repeat --repeat 3 --port 8883
# 等待 OFFLINE_BENCH_READY；在浏览器打开脚本打印的本机 URL，再用另一个终端运行：
python tools/bench_etm_native_browser.py --campaign build/native-offline-repeat --out build/native-offline-repeat/browser
python tools/verify_etm_native_equivalence.py --legacy etm-service/records/capture-1419738de1e7417bb0d8a34346823242 --native <新记录目录> --out build/native-offline-repeat/equivalence.json
```

浏览器测量会使查询缓存变暖；需要重新测首次行为时必须重建新记录。本次先顺序测三份首屏，后独立执行
`--skip-open`缩放批次，原始日志分别保留。私有CLI令牌不入Git；原始capture/ELF/源码保留在本地记录目录，
原生360MB中间件和测试结果副本留在build，不作为新FPGA/Zynq交付产物。

## 主分支合并与删除worktree前的材料保留

本轮已与“优化PL资源时序与PS代码体积”聊天核对：对方源码合并窗口已经结束，PL/PS优化、QSPI CLI和ETM改动
共同位于主工作分支`feature/superlink-zynq-web`。对方正从`954de8f`的隔离快照统一构建和先行板测；
本轮后补仅涉及target归档和离线材料，未改变该快照的FPGA/PS输入。本地`main`原无独占提交；本次在归档核验后
安全快进到同一合入头；不切换当前工作区，不重置、不推远端，也不删除worktree。

复查对方的PL诊断裁剪/FIFO资源优化、PS紧凑构建/SWJ/USB上下文修复和QSPI工具时，确认不能拿旧优化线
bit/ELF替代ETM合并头。新配对、SHA、实际FCLK/TCK与板测仍由统一构建验收记录确认；双方探针独占顺序不变。

| 必须保留的内容 | 仓库内入口 |
|---|---|
| 统一CLI、Web和原生配置 | `toolbox.py`、`web/`、`etm-service/` |
| C++原生源码、OpenCSD与构建入口 | `etm-service/native/`、`vendor/OpenCSD-1.8.3/`、`CMakeLists.txt`、`build-decoder.ps1` |
| ETM完整流程/断点/容量、RTT和J-Scope验收 | `tools/f103_web_acceptance.py`、`f103_stream_acceptance.py`、`f103_capture_entry.py`、`f103_trace_sweep.py` |
| 实板采集及物理边沿分析 | `tools/test_orbtrace_board.py`、`trace_signal_analysis.py`及原始回放证据 |
| 离线完整处理、首屏/缩放、语义比较 | `tools/bench_etm_native_offline.py`、`bench_etm_native_browser.py`、`verify_etm_native_equivalence.py` |
| 可恢复1s原始输入和小型事件基线 | `tools/prepare_etm_offline_fixture.py`及`validation/native-engine-offline-20261031/fixture/manifest.json` |
| CDC/ETM target的完整编译依赖与host用例 | `firmware/target/stm32f103_cdc_trace/`（含CB/ZE必需CMSIS/HAL和许可证、CherryUSB、RTT、链接/构建脚本） |
| RTT序号与J-Scope波形target | `firmware/target/stm32f103_rtt_seq72/`、`stm32f103_scope_rated/`；重建入口`tools/build_f103_fixtures.py` |
| 已验收target ELF及身份 | `prebuilt/20261031_f103ze_cdc_trace/`、`20261031_f103ze_rtt_seq72/`、`20261031_f103ze_scope72/` |
| 统一结论及原始验收记录 | 本文、`docs/validation/f103ze-web-flow-20261031/`、`native-engine-offline-20261031/` |

新增CDC target包含全部22份已验收DWARF源码，其SHA与原快照一致；另补齐头文件、启动/链接、构建工具和host用例。
迁移后48/72MHz均成功编译并通过USB HP/LP向量自检，8项CDC host场景通过。路径变短改变了USB驱动`__FILE__`
字符串及装载段内容，因此新ELF只计离线构建通过，**不冒充旧版已上板固件**；已验收prebuilt文件及哈希保持原样。
[归档核查](validation/etm-merge-20261031/handoff.json)分别记录新旧ELF及装载段哈希。

1s夹具复用已入库的`capacity-packed/window-1000ms/capture.etm`和48MHz echo ELF，不重复提交raw文件。
补入原样sources映射与summary/quality参考、25KB压缩事件oracle。它保留1,759份完整事件字典及全部503边界，
可在没有旧2.81GB events.jsonl、SQLite、原records目录和外部源码worktree的情况下做同一抽样比较。
这些小型测试oracle不进入生产解码路径。

从新的checkout复测示例（服务端口需空闲，所有输出目录必须尚不存在）：

```powershell
python tools/prepare_etm_offline_fixture.py --out build/etm-1s-fixture
python tools/bench_etm_native_offline.py --record build/etm-1s-fixture --out build/etm-portable-bench --port 8884 --repeat 3
# 打开脚本输出的URL，等待ready后执行：
python tools/bench_etm_native_browser.py --campaign build/etm-portable-bench --out build/etm-portable-bench/browser
python tools/verify_etm_native_equivalence.py --oracle docs/validation/native-engine-offline-20261031/fixture/events-oracle.json.gz --native <该轮新记录目录> --out build/etm-portable-bench/equivalence.json
```

未入库的主目录build/releases/HPM历史文件没有混入本轮提交，也没有删除；另一AI的私有Flash备份保留约定仍有效。
worktree删除必须等对应真机验收通过并核对新产物身份后再做，本轮不删除。

归档补齐提交`cff18fa`已用`git archive`导出到仓库外全新目录验证：没有.git、没有原records和build，
只用Git跟踪文件恢复输入。原生1s解码、全部summary/共有quality及1,759事件oracle通过；CDC 48MHz
USB向量自检、8项host场景、RTT 72MHz和J-Scope 72MHz target均构建成功。此轮与其他编译并行，
额外单次耗时只作为可运行性检查，不替换前文三次性能基准。

另补齐此前只交付EXE的原生工具源码：从superlinkPRO固定提交`2ca380ab6cf96e5742cae61a01e8871d2df6de28`
导出C++、CMake/build脚本、OpenCSD 1.8.3及许可证，共204份原始文件，逐文件SHA见
`etm-service/native/source-provenance.json`。选择该提交的依据是已迁入storebuild EXE报告的源码版本；
其余旧EXE没有报告完整源码版本，不能反推它们全部来自同一提交。

全部五个工具已在私有build目录重新编译，重建工具再处理同一1s输入并对照全部summary/共有quality和1,759条
完整事件字典均通过。已跟踪的运行EXE保持原SHA，本轮不替换。原生重建仍需已安装的MinGW C/C++、CMake、
Ninja及zlib/OpenSSL/SQLite开发库；这些为外部工具链，源码和上游许可证均在仓库内。
针对私有输出目录的复核命令（不覆盖运行EXE、不连接硬件）：

```powershell
cmake -S etm-service -B build/etm-native-rebuild -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=C:/msys64/mingw64/bin/gcc.exe -DCMAKE_CXX_COMPILER=C:/msys64/mingw64/bin/g++.exe
cmake --build build/etm-native-rebuild --parallel 2
```

原始导出及原生重建的完整处理/事件比较结果、target编译清单与日志见
[最终归档核查](validation/etm-merge-20261031/handoff.json)。原有source-provenance.json中main.c仍记着CDC补丁前哈希，
本次已改为与已保存的补丁后source-snapshot相符，并保留被纠正的旧值；没有修改该target源码或旧已验收ELF。

## 合并版JTAG/RAM真机验收：单步握手修复

另一AI已明确释放设备，主分支基于`311fc3b`接续验收。实际重新JTAG加载
`prebuilt/20261031_combined_raw4_io_7020_120/probe.bit`（SHA-256
`1da17cb60175bbc2b7abd647770c7053bd7b7097e0d38aa819fb89678d564473`）及同目录`application.elf`
（`e977914c2924ab4cac13f4075de0a5108d1e2e8cf48966fb8fbdea3a358e0b2c`），匹配PS init。
加载前读回71,268字节OCM执行段与ELF逐字节一致；本轮全程不编程QSPI或F103 Flash。

此前粗粒度Web调试20轮虽均返回成功，逐指令核对却发现第二步可以回到函数入口。
根因之一是Web `_stepByDhcsr()`只写`C_HALT|C_STEP|C_MASKINTS`，没有随后清`C_HALT`触发执行，
却把没有前进解释成“探针/内核不支持C_STEP”，长期改走断点兜底。已按本机pyOCD CortexM.step的
握手顺序修正：暂停时设置中断掩码，再用`C_STEP|C_MASKINTS`释放暂停；清除旧retire状态，
确认新指令执行/PC变化，结束或失败均清理单步残留。自跳转PC不变时允许以新的S_RETIRE_ST确认执行。
正确握手真正失败时仍保留断点兜底；Web摘要额外暴露`lastStepOk`。

修复后真实Web CLI连续5组×5步，均使用`dhcsr`模式：`cdc_poll`入口`0x08000590`后依次停在
`0x08000592 / 0x08000596 / 0x08000598 / 0x0800059a / 0x0800059c`，25个PC和成功标志全部核对通过。
覆盖16/32位指令及CPSID。旧20轮的原始命令/返回值和修复后结果一起保留，不能用“调用返回成功”代替正确PC。
新增握手、自跳转、失败清理三项测试，Web测试共33项通过。
[实际配对、下载和单步证据](validation/combined-etm-web-20261031/step-fix/)。

同一配对上Web CLI采集10/100/1000ms、串口PING/INFO/64字节回显、USB初始化和4轮窗口内CDC回显、
应用RTT启动日志、8变量J-Scope均已初步通过；完整最终矩阵、直接Zynq CLI、交互/导出和现场恢复仍在继续，
本阶段不提前标记整个新配对ETM/Web验收完成。

### 按用户要求暂停：跨功能切换时J-Scope缺首DEF

用户已明确要求先记下、不继续分析。状态为**DEFERRED，未验收通过**。在RTT/ETM/J-Scope连续切换时，
8×u32、1kHz采样偶发缺少DEF seq0：失败原始81,408字节中159包全部是DATA seq1～159；
对照61,440字节是DEF seq0加DATA1～119。页面在解析前保存raw，因此不是单纯界面未画出来。
只等1.5秒后按本地变量表解码不能算恢复成功。

特别纠正计数边界：此Zynq固件的HSS metrics word5和STAT usbErr字段未实现，回0不能排除USB侧丢弃。
已提出旧异步读消费首包、发送退役/publish边界等假设，尚未定根因。不把这些猜测写成结论。
未验收的readEpoch实验已从运行源码撤出，补丁和测试原样归档，后续可继续研究；未修改PL/PS或Flash。
[完整复现、对照与实验归档](validation/combined-etm-web-20261031/deferred-hss/issue.json)。

`validate no-flash --skip-scope`可显式跳过这一项，报告仍标DEFERRED；不能因此宣称全套通过。
接下来工作转为火焰图Web导出和全项目Web/非Web CLI覆盖审计。

### 火焰图按钮没有下载文件：已修复并验证实际落盘

用户在区间 #913～#977 点击“导出当前火焰图 SVG”，服务已生成2,531字节SVG，但界面无提示、下载目录无文件。
确认存在两个交付问题：工作台CLI全局下载钩子无条件吞掉手动Blob下载；内置浏览器不支持嵌入ETM页面发起Blob下载。
修复后手动下载经同源外层工作台发起，CLI显式指定`captureOnly:true`才抑制浏览器保存。
CLI缓存最多32文件/128MiB，缓存满时不会阻止手动下载。

按钮现在显示生成进度、文件名与大小、下载请求状态及“再次下载 SVG”；失败原因直接保留在页面，按钮可重试。
页面只声称已请求下载，不伪称已知用户最终保存路径。实际验收另外监听浏览器下载完成并检查磁盘文件。
保持用户原记录、区间及光标，真实点击按钮和重试链接均保存到Windows下载目录，两个文件均为有效SVG且SHA-256一致。
覆盖原问题的自动化测试包括手动/CLI分流、缓存满、外层文档下载与重试、进度和失败反馈；全部39项Web测试通过。
本轮无硬件操作，没有修改PL、PS或目标Flash。

[下载落盘及哈希证据](validation/flame-download-20261031/result.json)、
[当前区间SVG](validation/flame-download-20261031/flame-913-977.svg)、
[页面状态截图](validation/flame-download-20261031/web-download.jpg)。
