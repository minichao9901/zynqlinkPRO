> 本文件保留原验收/测量结论。已退出主目录的逐轮细节可由Git tag `archive/main-before-slim-20261031`追溯；当前使用入口见根README和prebuilt/golden。

# F103ZE / ZynqDAP：Web CLI、ETM与压力测试统一记录

> 最新操作边界：用户双击bridge EXE并通过Web完成采集；CLI用于AI自动化与打包。
> PLL、AHB/APB分频由target固件负责，生产Web和Trace CLI不再设置AHB分频。
> 本文之前6/12MHz中通过上位机临时分频得到的结果属于历史实验，不能套用为当前Web默认频率。
> F103ZE 48MHz Golden目标默认物理TRACECLK24MHz；如需更低频率由target固件提供，并载入匹配ELF。
> H743保留superlinkPRO的ETMv4能力；新增Kingst真实记录作离线回归，不冒充Zynq上板验收。
> 用户操作见[Web操作说明](Zynq-ETM-Trace操作说明.md)。

## 2026-11-01：独立worktree的校准与有限DDR采集研究（进行中）

### Golden真实压力基线与ETD1诊断阶段

已重新通过JTAG/RAM加载Golden 1da17c/e977，71,268字节执行段读回匹配。
目标F103ZE仍为e379的48MHz CDC固件，未编程QSPI/目标Flash，也没有更改target分频。
真实Web按钮30次连接/关闭全部成功：连接中位1.737s，最短1.416s、最长3.637s；关闭中位0.435s。
每轮RCC推算CPU48MHz/物理TRACECLK24MHz。采后PS寄存器读回FCLK119,999,998Hz、SWCLK999,999.98Hz；
vendor参考查询为199,999,998Hz，旧Golden未提供细分接收诊断。

随后按计划交替cdc_poll/cdc_tx_poll并连续收发64字节CDC echo。第一轮cdc_poll采集120,291字节，
packetIssues=0，loss=false/synced/ended=true，401,617条指令，接收窗口内有4份逐字节正确echo。
第二轮切换cdc_tx_poll时，129,136字节原始数据出现loss=true、synced/ended=true，脚本立即停止，未重试掩盖失败。
因此不能宣称采集压力验收通过。30次探针开关只证明这一轮基线，不能外推所有上电/故障状态。

请求窗口为10ms，主机接收/排空跨度约44/47ms；这不等于目标实际录制了44/47ms。
它也说明不能用软件线程停止与USB排空时间冒充精确硬件窗口，DDR有限采集需要硬件停止边界和有效长度。
当前65536个16bit记录槽只容纳至多65536字节有效Trace（另带source tag），不能按128KiB估算有效Trace缓冲。
旧lost合并解析错误和帧FIFO溢出，暂不能认定物理误采或后级背压中的哪一个占主导。
[完整基线](validation/etm-baseline-stress-20261101/baseline-summary.json)、
[两份原始输入身份](validation/etm-baseline-stress-20261101/raw-inputs.json)。

压力脚本`tools/stress_etm_web.py`通过Web公开CLI驱动真实按钮，保存每轮RCC、PC/配置、质量、原始SHA和echo时序，
不使用captureNative绕开普通Web采集。另修复Zynq LA适配器sendall等待到采集结束的问题：现在启动后即可发布armed，完成等待属于recv。
浏览器日志另有运行至断点阶段的C_HALT警告，尚不能当作探针连接失败；原文保留在基线目录。

新的实验RTL增加ETD1寄存器，诊断独立于receiver stop reset，下一次显式clear才清除。
分别记录帧FIFO丢帧、parser malformed、同步获取、帧/记录FIFO高水位、记录FIFO背压周期、IDELAYCTRL RDY下降沿；
后者不是完整的参考时钟或眼图监测器。扩展AXI-Lite地址为8bit，避免高寄存器别名到控制/FIFO。
Source Gray计数跨域，停止后等待同步再读；已实现能力用bitmap声明，未实现字段在主机中为null而不是0错误。
PS通过0x61回复的能力位声明0x62/64字节只读诊断，主机在文件落盘、USB释放前读回，旧Golden不会被发送不支持的0x62请求。
接收失败仍保留原始输入；细分原因可随captureQuality进入Web报告和AI记录。

| FPGA字索引 | ETD1字段 |
|---|---|
| 8 | 签名0x45544431 |
| 9 | 帧FIFO丢失/parser异常/IDELAY RDY丢失粘滞位 |
| 10/11 | 帧FIFO/记录FIFO高水位 |
| 12/13 | 丢帧次数/parser异常次数 |
| 14/15 | RDY下降次数/记录FIFO背压周期 |
| 16/17/18 | 同步获取次数/RAW模式/实现能力bitmap |

11项RTL用例通过，包括数据路径旧回归、单独解析异常、单独FIFO压力、RDY失锁、停止保留、clear时CDC旧标志不能重新锁存。
46项CLI主机回归、8项研究测试及生产USB/ETM/JTAG host测试通过。
诊断RTL/PS的构建与时序及随后上板结果见下段，旧Golden保持原文件。
[RTL证据](validation/etm-diagnostics-rtl-20261101/result.json)。

首次完整构建随后已结束：100MHz STA通过，但120MHz setup为-0.176ns，最差路径为帧BRAM输出经demux有效信号、
lookahead水位加法/比较到新增高水位寄存器CE。SWCLK 7ns独立预算余量+0.291ns，hold+0.011ns。
这版只验证到FCLK100/SWCLK50，**没有加载，也没有与SWCLK60固件标为已验收配对**。
不以降低既有120/60工作点作为完成；已把高水位改成观察寄存指针的一周期延后水位（仍能精确保留峰值），
去掉BRAM到统计加法的长组合路径，RTL原有/新诊断用例通过。
另增加显式`ZYNQLINK_IMPLEMENT_FCLK_HZ=120000000`的实现约束选项，保留SWCLK7ns预算，准备重实现。
PS已按Golden相同O3/Thumb/MAX_SWCLK60重建，SHA b07980ab…，OCM跨度120,976B；尚待120MHz新bit及上板验证。
[失败时序与定位](validation/etm-diag-timing-attempt1-20261101/result.json)。

### ETD1新配对上板：确认这次24MHz失败存在后级背压

第二轮使用修正后的统计路径、120MHz实现约束。初始route未满足SWCLK7ns预算，随后在同一新网表DCP上
phys_opt/route修复；最终FCLK120MHz setup +0.181ns、hold +0.042ns，SWCLK clock-to-pad 6.819ns，
bitgen DRC为0错误（仍有异步BRAM控制等46项警告，未宣称无警告）。128.57MHz档setup -0.332ns，不作交付频率。
RTL输入提交`3d7663b`，O3/Thumb/compact的PS从`75fba4a`重新构建，明确绑定该bit的verified_clock。
源码输入SHA、完整频率表和时序报告已归档。

新配对保存到`prebuilt/etm-diag-raw4-20261101/`，实际JTAG/RAM加载：

| 文件 | SHA-256 |
|---|---|
| probe.bit | 0863332c4381d3bcc210eb75d150e9acdb6171ccd2d6c95e82ccc0749c32c8d0 |
| application.elf | b07980abf5d1d107c1356dab8022533d3d9863d9b2e107b97241536378121cf0 |
| ps7_init.tcl，来自本次BD生成 | aa9747c31f705be7c28af1c6b1cdeaf282f0dcdb01faecee2a9f72e4d3489132 |

71,620字节PS执行段逐字节读回匹配。0x61参考199,999,998Hz并声明ETD1；0x62签名/能力/模式正确，
刚启动的错误计数为0。实际Web测试FCLK119,999,998Hz、SWCLK999,999.98Hz，目标仍为e379固件的CPU48/TRACECLK24MHz，
没有编程QSPI、目标Flash或更改target时钟。

30次真实Web连接/关闭全部成功：打开中位1.771s，范围1.616～3.763s；关闭中位0.402s。
随后第一轮cdc_poll请求10ms就出现loss，保留125,531B并停止，未重试补过。原始输入SHA为
`0d3d86be2726a648f73c7505250af482febc8c94a9e81e6edab4afb4f3a2a112`。
诊断为记录FIFO峰值65,536/容量65,536、记录背压349,223个FCLK周期、帧FIFO峰值8、丢帧2,166，
parserErrors=0、syncAcquisitions=1、IDELAY RDY下降=0。主机接收跨度内4份64字节echo逐字节正确，清理无错误。
这直接证明**本次失败包含后级排空不足→记录FIFO满→帧丢失**；不能凭parser为0证明模拟链路零误码，
也不能外推更高频均由同一原因造成。应优先做PL→DDR有限采集与采后下载，再研究接收时序极限。

本配对的诊断功能已上板验证，但**采集压力验收失败，非Golden，不声称频率提升、H743已验收或DDR已实现**。
manifest记录加载身份和限制；原Golden/recovery未覆盖。
[板测、时序及原始压缩数据](validation/etm-diag-board-20261101/result.json)。

此次还发现captureExtent虽标sampleCountMeasured=false，却把主机46ms接收/排空跨度乘500MSa/s当成实际采样数，
继而标complete=true。这些原始失败元数据不追改，已明确标出口径问题。
新保存路径不再生成这类伪采样数：ZET1的actualDepth/actualTime、actualSamples/actualSeconds/complete均为null，
主机跨度单独保留为hostReceiveSeconds；收到结束包不能证明硬件录满请求窗口。3项后端用例覆盖F103/H743真实C++回放及失败记录，均通过。

压力测试同时暴露并修复失败历史展示：失败捕获未刷新进state.records时，openRecord误入decoded.json路径；
现在失败后刷新并显示原始记录，列表/正文明确标“采集失败/采集未通过”，不再继续展示上一条成功结果。
另修复成功重解码清掉采集失败的语义问题：captureError和captureStatus=failed独立保留；OpenCSD成功不等于接收无损。
缺失或数字占位的质量标志显示“未知”，不能显示“无丢失”。真实失败记录已在Web打开并保存截图；
后端回放明确注入loss后再成功C++重解码，确认采集错误仍保留。3项后端、44项Web回归通过。
[展示与保留验证](validation/etm-failure-visibility-20261101/result.json)。

### H743接入保留与换板准备

保留superlinkPRO的H743识别、独立CPU/Trace时钟计算、ETMv4选项及Funnel/ETF/TPIU路由，
原生Zynq接收交接不会向H743写F103的ETMv3控制寄存器。7项主机/3项Web检查通过。
当前代码重新处理原始Kingst H743参考：210,497条指令、182,006条执行、packetIssues=0，
native完整处理0.628s，TraceStore存在且无逐指令JSONL。该单次离线结果不证明H743 Zynq上板或实时吞吐。

迁入`etm-service/firmware/stm32h743_cdc_trace/`及构建helper，固定superlinkPRO提交`be75311236da2665a2edc54b9b4d4561f0219456`，
共38份原始源码/构建文件，包含CherryUSB许可证，逐文件Git内容SHA见source-provenance。
统一AI入口`target.h743-build`已生成执行计划、PowerShell语法通过；完整H743 SDK仍是外部依赖，未完成目标编译或烧录。
压力入口支持显式profile/ELF/HSE/函数/CDC端口，不会默用F103目标文件。换板后按Web说明低频短窗开始验收。
[保留验证](validation/h743-preservation-20261101/replay.json)。

### 最初的只读研究与容量计划

DDR接入前已做有限地址别名实验：实际运行的PS ELF执行段再次匹配后，
在0x00800000、0x10800000、0x20800000、0x30800000各备份16字节，
同时写入四组不同模式、读回核对后全部恢复，恢复内容与原备份一致，四个样点互不别名。
没有暂停/复位CPU、没有Flash或批量DDR写入。它支持继续核查0x10000000～0x30000000候选区，
不证明每个DDR单元、缓存一致性或持续带宽已验收。
第一次选择0x00080000时被PS调试端报告SCU M1地址无效；发生于第一份备份读取，尚未写入任何测试模式，
随后改用DDR配置范围内、避开ELF静态区的8MiB偏移。两个原始日志均保留。
统一AI入口`etm.ddr-geometry`，要求显式提供实际PS ELF，先验证执行段身份，
检查采样地址不与分配段重叠，再作带恢复的少量写入；必须在采集/DMA客户均空闲时运行。
[地址样点结果](validation/etm-ddr-geometry-20261101/result.json)。

随后实现可选HP1 DDR内存路径试验模块（`ZYNQLINK_ETM_DDR=1`，默认关闭）：
独立CSR 0x40040000、AXIS64写入器、两组16拍缓冲、单个在途写事务、128字节对齐基址、
每次最多16拍且不跨4KiB、硬件地址范围0x10000000～0x30000000。
`response_bytes`仅在OKAY的B响应握手后增加；输入接收数与响应数分别记录。
中止会完成已发出的AW/W/B，不撤回被背压的VALID、不把未回应事务标为完成，也不自动重试错误写入。
这遵循[ARM AXI写响应依赖](https://developer.arm.com/-/media/Arm%20Developer%20Community/PDF/IHI0022H_amba_axi_protocol_spec.pdf)，
HP接口选择参考[AMD UG585 PL DMA](https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/PL-DMA-via-AXI-High-Performance-HP-Interface)。

内存路径pilot仅生成带地址索引的已知模式，不宣称已接入ETM源；能力寄存器不置Trace采集位。
先测同一写入器的真实DDR写入、结束与读回，再接接收帧、硬件窗口和采后USB下载，避免把仿真当成整条链路已完成。
PS链接器已将普通DDR分配区限制在0x10000000以下，并以独立MEMORY区保留512MiB；
只导出ABS边界符号，不生成或在启动/下载时隐式清零512MiB的巨大NOLOAD段。
试编译O3/Thumb ELF通过，OCM跨度仍为120,976B；这份试编译尚未与新bit配对加载。

28项写入器仿真及控制器寄存器/模式读回用例通过，覆盖分离AW/W、背压稳定、B延后、
首尾1～7字节、4KiB边界、越界拒绝、忙时修改/重启拒绝、中止排空、错误B和合法重启清除旧错误。
原11项Trace RTL回归及生产主机C回归通过。新DDR网表构建和板上读回尚待进行；旧诊断配对仍在板上，Golden不变。

首轮DDR pilot实现进行到布局/phys_opt后，placed DCP最差setup -1.902ns：
accepted_bytes经32bit剩余量减法、动态TKEEP与预算判断到缓冲存储控制，21级逻辑、12级CARRY4。
缓冲被综合为2,000余个FF，叠加大扇出控制使物理优化估算仍约-1.8ns。
已停止这一轮实现并保留placed DCP身份和报告；它没有生成、加载或验收新的bit，不能拿旧bit配新时序声明。
修正为寄存remaining_bytes、用“高位是否非零+低4bit比较”检查最多8字节的拍预算，
并把无复位的payload RAM写入移出异步状态复位过程，保留原边界/中止语义。
原28项及控制器用例、预算守恒检查通过，准备重综合以核实RAM推断和120MHz时序；尚未声称已收敛。
第二轮模块综合已确认LUT RAM推断：DDR控制/写入模块由1,281 LUT / 2,762 FF变为620 LUT / 480 FF，
其中52个LUT用于存储；这是模块综合资源，未冒充最终整片面积或布线时序。
另补64轮不复位连续录制，改变长度和内容、检查新数据、响应计数清零及相邻字节不被覆盖，
写入器共92项仿真通过，控制器回归继续通过。
真实板验脚本`etm.ddr-memory-test`会先核对并加载指定bit/ELF/PS init、验证OCM代码和ABS DDR保留区，
再启用已知模式，检查最终B响应计数、逐字节完整读回及SHA、相邻保护字，记录实际FCLK。
普通Golden ELF缺少保留区符号时在任何硬件写入前拒绝；3项规划/保护测试和46项CLI回归通过。
该脚本尚待通过新配对上板执行；JTAG读回速度不是USB吞吐，也不证明CPU缓存/USB下载已验收。
第二轮bit已生成并通过120MHz STA（setup +0.284ns / hold +0.066ns，SWCLK launch 6.575ns）。
首次配套ELF的边界值正确，但SECTIONS内普通赋值被链接器标为.text相对符号，
硬件验收脚本的ABS检查在加载/写入前拒绝；已改用ABSOLUTE并重新构建PS ELF，不能绕过该检查。

### DDR HP1候选已上板，但数据完整性与启动稳定性未通过

> 后续更正：本段的DDR“读回不匹配”采用了CPU上下文，混入旧缓存线，不能作为物理DDR写坏或FCLK上限的证据。
> 原始数据保留用于审计，当前物理内存结论见后面的“物理AP0对照更正”。启动时USB缺失仍单独待验。

本轮实际配对保留在`prebuilt/etm-ddr-pilot-raw4-20261101/`：bit SHA
`6690d8dd214be1986b7f89f64f93096b99aa7a5b30fb93b65e7f51919577c720`，
PS ELF SHA `ab7c097764bea91272783ec59a51d200bf154ba5d4f9adbf1e7350466c17947f`。
RTL来自348d73a，配套PS来自f364085；PS init来自该BD实际输出，SHA与前诊断版相同，不虚构不同哈希。
PS执行段71,620B匹配，候选全部已分配PROGBITS及地址也与前诊断版一致，仅链接元数据/保留区声明变化。

初次加载PS在CDMA启动自检后停入_exit、USB未枚举；CDMA没有硬件错误位，但CMD BRAM内容与
响应DDR数据不一致，4KiB响应开头两word为旧值，后续错位。不得跳过自检把USB打开当修复。
随后用JTAG单独启动HP1模式源（不是ETM），一次受控重载、FCLK切换和逐字节读回得到：

| 顺序 | 1MiB模式读回 | 时钟与边界 |
|---|---|---|
| 首次失败启动状态 | 262,144个u32均不匹配 | 初始JTAG实读FCLK99,999,999Hz，未经过DAP换频 |
| 对照重载后 | 全部匹配，SHA f9a86f476aabe331ec30f74e2a5c73c324e0433ebc1d955314f37d15d1f985df | 名义启动档；该次没有在写入前单独记录实际时钟，不作为带宽测量 |
| 正常DAP设置后 | 78,992个u32不匹配 | 实读FCLK119,999,998Hz、SWCLK999,999.98Hz |
| 显式改回100MHz后 | 90,600个u32不匹配 | 实读FCLK99,999,999Hz、配置SWCLK833,333.325Hz |

后三次都收到最终OKAY B并报告输入/响应各1,048,576B、错误码0，但两次内容仍错。
因此不接受响应计数作为DDR完整性证据，不公布这些失败数据的有效吞吐，也不能据此认定100MHz稳定或120MHz硬件上限。
一次成功与后续失败同时保留，尚未确定是初始化、换频、接口/复位或其它状态问题；没有通过重试覆盖第一次失败。
新旧网表中所查CMD RAMB的DOA_REG/DOB_REG均为0、读取宽度36，未发现该处读延迟参数发生变化；
这只是缩小检查范围，不证明整个旧CDMA路径完全等价。

待继续隔离：现有JTAG工具在fpga配置前调用ps7_post_config，
而[AMD启动顺序](https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/PS-Bring-up-with-PL-Configuration-Example)
在PL配置完成后再使能level shifter；
[电平转换隔离说明](https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/PS-PL-Voltage-Level-Shifter-Enables)
要求避免PS输入上的额外跳变。这是需实测的加载顺序线索，不是已确认根因；还需独立检查FCLK切换/AXI静默及HP FIFO状态。
本轮尚未修改加载器、绕过启动自检或把工作点降为100MHz交付。

候选状态明确为**REJECTED_NOT_GOLDEN**，其实际bit/ELF与失败证据一起纳入Git供复现。
板上已经恢复上一诊断配对086333/b07980，USB重新枚举、执行段读回通过，当前初始FCLK99,999,999Hz。
Golden/recovery保持原文件；无Flash写入/target RCC改动。1～2秒ETM DDR采集、逐线校准及最终Web压力验收仍未完成。
[完整结果、压缩输入与实际加载记录](validation/etm-ddr-pilot-board-20261101/result.json)。

### 物理AP0对照更正：40轮DDR模式数据通过

先增加不重载、不换频的连续模式测试，计划20轮。CPU上下文读回第1轮正确，第2轮报告102,504个u32错误；
前后FCLK均实读99,999,999Hz、采集ID正确、硬件已完成。
进一步比较发现这些坏值全部是同地址的上一轮内容，并完整落在32字节缓存线：12813条整线旧值，没有半条旧线或其它错位数据。
不重录、不改内存、不切时钟，只把同一已完成采集改用APU的MEM-AP0物理读取，1MiB全部匹配原期望SHA。
因此这次失败来自CPU上下文读回路径的缓存影响，不能归因PL写入或时钟切换。
尚未定位CPU与调试器具体哪一缓存层提供了旧线，不把这一点写成已定根因。

SDK 2018.3本机xsdb.tcl与[AMD mrd说明](https://docs.amd.com/r/2020.2-English/ug1400-vitis-embedded/mrd)
确认`-address-space AP0`选择MEM-AP；`-force`只覆盖地址访问保护，并不是绕过CPU缓存。
新增`tools/zynq_memory.py`，DDR模式读回、保护字、OCM身份核查和地址别名实验改用显式物理AP0路径；
MMIO写使用cache-sync bypass，避免通过CPU上下文同步旧缓存线覆盖新的DMA数据。
验收脚本现在核对本轮新采集ID、每轮前后实测FCLK、完整数据SHA和相邻保护字，保存失败阶段并在首个失败停止，不自动补过。

修正后的两组测试均使用同一6690d8/ab7c09配对，分别加载一次、轮间不重载/不复位并改变seed：

| 内部PL FCLK实读 | 连续轮数/数据 | 完整数据、SHA、保护字 | 硬件计时的已校验模式数据速率中位 |
|---|---|---|---:|
| 99,999,999Hz，不调用DAP换频 | 20 × 1MiB | 全通过 | 328.187 MB/s |
| 119,999,998Hz，正常DAP设置后 | 20 × 1MiB | 全通过 | 374.614 MB/s |

速率只表示已知模式在PL→DDR通路中从开始到最后OKAY B的硬件周期，数据另外通过物理读回全量核对。
它不是USB速度、ETM TRACECLK或已完成的1～2秒采集能力，也不证明512MiB全容量或CPU/USB缓存一致性。
此前按CPU上下文读取的四个地址样点也已物理AP0重测：四组不同模式独立读回、原16B逐点恢复验证通过；
71,620B OCM执行段同样物理读取后与配套ELF匹配。

原DDR读回“错位”和换频的关联需要撤回，不能据旧缓存数据要求降低既有120MHz工作点；未修改RTL/FCLK实现来迎合错误判据。
最初那次USB缺失/PS进入_exit的启动现象仍然保留，不能由缓存对照直接销案。
候选暂不晋升Golden；接下来验证完整保留区和重复加载，再接ETM帧/硬件窗口/采后USB下载。
[缓存对照与40轮结果](validation/etm-ddr-physical-readback-20261101/result.json)、
[同一采集的两种读取路径](validation/etm-ddr-physical-readback-20261101/cache-comparison.json)。

### 完整512MiB保留区：物理全量数据通过

同一6690d8/ab7c09配对重新明确加载，OCM执行段通过物理AP0核查，正常DAP设置后
FCLK119,999,998Hz、配置SWCLK999,999.98Hz。PL已知模式写满0x10000000～0x30000000，
536,870,912B的接收/OKAY B响应计数一致，硬件计时1.433054s。
随后不经CPU缓存上下文，通过AP0按16MiB分块独立读回全部32块，逐字节模式检查及整体SHA完全一致：
`10a9421967397c392be07f9fc08f7f0a48dfe420c1fc7200123dbaee05f68b8e`。
已核对内容的模式写入速率374.634MB/s；时钟前后未变化，起点前保护字未变。
末端严格等于保留区边界，没有在区外写保护字；不要将空的末端保护列表解读为测过任意区外地址。

调试器分块读取耗时不属于录制时间，也不是Zynq USB速度。脚本限制每次TCF响应16MiB并保存进度/块SHA，
避免一次创建512MiB Tcl二进制字符串；原始512MiB和分块文件留在私有build目录，Git保存完整结果、命令、
匹配SHA及首尾实际4KiB样本。46项CLI回归通过。
这证明本次实际板卡上的保留区与模式PL→DDR写入通路可用；未证明CPU/USB缓存一致性，
尚未接ETM源、硬件录制窗口、采后USB下载或逐线校准，候选整体仍不作为Golden。
[完整保留区结果](validation/etm-ddr-full512-20261101/summary.json)。

### 同一配对重复加载10次与窗口/帧桥接仿真

继续按原JTAG加载器，逐轮重新明确加载同一bit/ELF及PS init、物理OCM身份核查、
等待USB枚举、正常DAP设置、不同seed的1MiB模式写入和AP0完整读回。10/10均通过，
每轮FCLK119,999,998Hz、配置SWCLK999,999.98Hz，首个失败才停止且不补过。
最初那次启动退出在本次10轮未复现；这不等于证明全部复位/上电状态都可靠，也没有建立其根因。
本阶段没有为消除不可复现现象修改加载顺序或绕过启动自检。
[10轮加载与物理数据核查](validation/etm-ddr-load-stress-20261101/summary.json)。

有限采集的下一步模块已独立仿真：参考时钟域窗口锁定N周期、拒绝忙时重开、停止保留实际周期与原因；
134bit帧+长度/EOF桥接使用同步BRAM读取、寄存输出和Gray跨域指针，背压不改数据，停钟不制造帧。
8项FIFO核对1,028帧，512项FIFO核对2,597帧，均覆盖多次指针回绕、停读/停写时钟及新捕获复位；
每个变体12项参考窗口用例通过。仿真使用缩小计数宽度检查边界，不声称已经跑过或上板完成200MHz下1～2秒窗口。
这些文件位于`fpga/experiments/etm_ddr/`，**尚未进入生产BD或当前bit**。
还需配置CDC、源端停止确认、部分帧/EOF入队及DDR全部写响应完成后的发布握手，再做真实ETM采集验证。
统一AI入口`etm.capture-sim`、`etm.ddr-load-stress`已生成执行计划。
[窗口/帧桥接仿真](validation/etm-capture-primitives-20261101/result.json)。

DDR前端已有隔离的实验RTL：`fpga/experiments/etm_ddr/etm_ddr_packetizer.v`，尚未加入生产BD或本轮ETD1构建输入。
它把带有效长度/EOF的128bit帧转为64bit AXIS，保留最后一拍直到后续数据或EOF确定，正确产生TKEEP/TLAST；
不发送零字节DMA包，不越过锁定的byte_limit，背压期间数据稳定，源暂停不会伪造结束，busy时拒绝重启。
39个正常长度/边界/停顿用例及非法帧检查通过；输出stream_bytes只表示AXIS握手字节，不等于DDR已提交字节。
仍需接入源时钟跨域打包、独立硬件停止、AXI HP/DMA、显式DDR保留与cache一致性，并完成真实内存读回。
因此本阶段不能宣称已实现或验收1～2秒DDR采集。
[实验前端仿真](validation/etm-ddr-packetizer-20261101/result.json)。

研究分支`codex/etm-lane-calibration`，目录`E:/zynqlinkPRO_etm_calibration`，从main `bc0d3ad`建立。
目标为反复连接/关闭、采集/解码/更换断点及CDC echo压力测试，并研究可靠采满1～2秒到DDR、采后下载。
本阶段仅检查源码/官方资料和离线容量，未改生产RTL/PS，未综合、未上板；Golden仍为原1da17c/e977配对。

官方核实：SEGGER明确提供每条data线独立的采样时序调整，默认偏移+2ns。
2026-11-01直接打开的当前产品页规格写200MHz TRACECLK；搜索缓存中出现过不同旧值，因此本记录以当前原文为准。
没有官方证据确认其内部芯片是Zynq，也没有足够证据把逐线可调解释为已公开的全自动眼图训练。
[SEGGER时序说明](https://kb.segger.com/Adjusting_trace_timings_and_general_troubleshooting)、
[当前J-Trace PRO规格](https://www.segger.com/products/debug-probes/j-trace/models/j-trace-pro/)。
7-series的IDELAYE2支持按输入引脚延迟，IDELAYCTRL提供参考校准；RDY不等于信号眼图已测好。
[AMD UG471](https://docs.amd.com/api/khub/documents/IbGcnPFe6eF19RHma_Y~IA/content)。

本地确认：Golden的RAW_DIAGNOSTIC=4，真正路径是200MHz异步同步/两点稳定滤波/检测滤后时钟边沿，
未使用源同步IDDR路径的IDELAY输出。已有源同步路径四条data共用FIXED tap=16，无运行时逐线装载/读回。
所以只把现有FIXED常量改成寄存器不会改善正在用的RAW4；需要接入真实源同步采样路径并重新约束和验证。
RAW4在200MHz下每点5ns，无法观察200MHz TRACECLK的每个2.5ns半周期；这不是Zynq I/O极限结论。
当前overflow还合并了frame FIFO与parser malformed，必须先补独立计数，不能把所有lost直接归因于杜邦线。

DDR方向拟为“源同步接收/逐线校准→紧凑打包→CDC弹性FIFO→AXI突发写DDR→到时/到界停止→USB下载”。
这可以解除采集期间USB连续吞吐要求，但不能纠正输入误采；当前PS逐条MMIO读记录不能冒充高吞吐PL→DDR路径。
4线DDR按两nibble合一字节，最坏每个TRACECLK周期1字节，不假定空闲过滤降低容量：

| 目标TRACECLK，仅作容量算例 | 1秒原始payload | 2秒原始payload |
|---|---:|---:|
| 24MHz | 24MB | 48MB |
| 36MHz | 36MB | 72MB |
| 100MHz | 100MB | 200MB |
| 150MHz | 150MB | 300MB |
| 200MHz | 200MB | 400MB |

MB为十进制。这不是支持相应频率的承诺；若每字节带16bit记录tag，200MHz/2s仅payload就达800MB。
当前BSP/链接文件配置DDR上界0x3fffffff；这只是配置，不是本轮测得的物理容量。
Golden ELF的静态DDR段在低地址约1～1.76MB及0x3f000000，链接器另保留0x3f000000起1MiB。
暂以0x10000000起512MiB作**未保留的候选范围**；实际还需核查动态DMA/USB/heap、地址别名、缓存属性及屏障。
不可仅凭静态段不重叠就写入，必须在链接器明确保留并验证PL写入/停止边界/采后读回身份。

新增纯离线AI入口：`python toolbox.py project run etm.ddr-plan`，保存baseline文件SHA和静态重叠检查。
默认200MHz/2s容量计算raw8为400,000,000B，能装入候选512MiB；record16为800,000,000B，不能装入。
输出始终`safeForDeployment=false`，四项容量/重叠/边界测试通过，尚未生成任何新bit/ELF。
[容量计划](validation/etm-calibration-study-20261101/capacity-raw8-200mhz-2s.json)、
[16bit格式对照](validation/etm-calibration-study-20261101/capacity-record16-200mhz-2s.json)。

下一阶段依次验证：独立错误计数；可装载/读回的逐线tap及配置握手；两沿眼区/固定偏斜/毛刺/停钟仿真；
已知模式下的真实比对；有界DDR写入及cache一致性；最后新配对STA、明确加载、分级频率和USB停用时的1～2s板测。
无已知模式时，TPIU结构/合法source/能解码只能用于选窗评估，不能证明零误码；恒定线或翻转不足必须报未测得窗口。
校准先在采前完成并锁定，不能有效采集中静默改tap。杜邦线造成的伪时钟边沿或闭合眼图仍需改善电气。
压力测试将记录每轮探针开关、实际FCLK/TCK/RCC、入口PC、原始数据与echo SHA、解码质量和恢复状态；
不通过重试隐藏首次失败，不更改target分频，也不继续已暂停的HSS缺首DEF修复。

## 2026-11-01：Windows bridge EXE与纯Web操作

交付`dist/zynq-etm-bridge/zynq-etm-bridge.exe`及完整`dist/zynq-etm-bridge.zip`，ZIP为51,653,326字节，
SHA-256 `0f9a7542c9d8ad3592cd08d50e9f9790abfb223b442a60271956ed266c3b7926`。
源码版本`dc81148`，构建时源码无未提交修改。生成目录不进Git；可用已提交的一条AI命令
`python toolbox.py bridge-build --out NEW_DIR`重建，自动检查冻结EXE后才发布目录和ZIP。
用户完整解压后双击EXE，浏览器自动打开；不安装Python/Node，不手输CLI。

产品流程沿用superlinkPRO：载入匹配ELF/源码、连接探针、选择函数起点、只读核对时钟、配置ETM/TPIU、
点击“联动采集”、自动解码与浏览。主要替换LA接收后端，同时保留本仓库USB互斥、镜像核对、实际质量检测、
C++/TraceStore、分页浏览、火焰图源码跟随及真实下载反馈。
此前建议用户用CLI临时设置AHB/4的操作不再适用。Web主采集与原生辅助API拒绝hclkDiv；生产Trace capture也移除该参数。
低层频率实验工具仍显式保留在研究入口，不能当作产品默认流程。

本轮发现并修复普通Web采集路径的两处遗漏：导出阶段新建Vis导致丢失实际窗口（误用10ms默认值）和Zynq接收质量。
现在退出接收会话前保存主机单调时钟窗口、FCLK/TCK、loss/synced/ended；loss、未同步或未结束均保留原始输入并明确失败。
主机窗口不是目标周期计时，导出深度换算不是物理采样点实测，metadata明确标注。

离线验收结果：46项Python、42项Web测试通过，143个Web模块语法、298个已入Git必要依赖校验通过。
两种协议的Web capture任务接口替换**外部LA/USB输入**后执行真实上传、任务、C++解码、TraceStore与浏览；
另检查loss/未同步/未结束不能误报通过，F103/H743 Trace配置不会写PLL/AHB/APB分频寄存器。
这些结果不冒充硬件采集或真实探针反复开关的压力验收。

最终冻结EXE在PATH只保留Windows System32、去掉系统Python/Node的环境中，五个原生工具、libusb/HID/串口运行库均可加载。
真实EXE HTTP服务导入、解码、首段浏览、区间查询、SVG导出及重复双击复用均通过；无生产events.jsonl/native.jsonl。
浏览器实际用文件选择器导入ELF、选cdc_poll，再导入H743记录、自动解码、点火焰图、设913～977区间并下载2,187字节SVG，
磁盘文件与API产物逐字节一致。

| 冻结EXE的单次离线检查 | 完整处理 | 完整首屏 | 半段缩放 |
|---|---:|---:|---:|
| 同一F103ZE 1s夹具，SHA 2cb583… | 6.882 s | 204.8 ms | 176.4 ms |
| H743原始10ms参考，210,497条指令 | 0.889 s | 119.8 ms | 178.4 ms |

首屏/缩放来自真实可见Web的公开测量方法，缩放视图为instructions；已有解码索引/缓存，单次检查不替换前文三次基准。
1s数据处理仍明显超过1s，不能宣称实时采集显示达标。

H743保留自动识别、独立CPU/Trace时钟计算、ETMv4选项及Funnel/ETF/TPIU路由。
新增可迁移回归夹具`tools/tests/fixtures/h743-etmv4/`，包含原始ETM、匹配ELF、配置与来源哈希；源记录来自superlinkPRO的Kingst LA，
CPU60MHz/TRACECLK30MHz、210,497条指令、packetIssues=0。H743接Zynq的真机验收仍待换板进行。

本机系统TEMP和C盘用户目录出现原生工具写入拒绝，原因未定；桥将TEMP/TMP显式放自己的data/runtime内，
本轮EXE与数据在E盘验证通过，没有修改系统权限；C盘解压运行不计已验证。
全时序SVG的200,000段限制、超宽聚合图、Python精确SVG重建及已暂停的HSS缺首DEF仍未消除。
Golden/recovery及生产PL/PS均未改变，本轮未综合、未连接板卡或写Flash。

[完整发行身份与范围](validation/bridge-exe-20261101/release.json)、
[冻结EXE回归](validation/bridge-exe-20261101/frozen-api.json)、
[浏览器测量](validation/bridge-exe-20261101/browser-timing.json)、
[H743页面证据](validation/bridge-exe-20261101/web-h743.jpg)。

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

- USB初始化（归档路径：`validation/f103ze-web-flow-20261031/usb-initialization-matched.svg`）：记录
  capture-3f283d20471c432f8a82c3a5225983ff，区间#2～#8210，18,000字节，
  SHA-256 `fd487378d413932bd77d2296e0f044ca01e37d3cec5417e3f6211951ba021529`。
- CDC echo（归档路径：`validation/f103ze-web-flow-20261031/cdc-echo.svg`）：记录
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

- USB初始化SVG（归档路径：`validation/f103ze-web-flow-20261031/final-flow/usb-initialization-filtered.svg`）：
  capture-a63604803b8947d1a26d0ed1c3766132，#0～#6934，48个rect、13,449字节。
- CDC echo SVG（归档路径：`validation/f103ze-web-flow-20261031/final-flow/cdc-echo-filtered.svg`）：
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
ETM界面（归档路径：`validation/f103ze-web-flow-20261031/etm-final.jpg`）。


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
  environment.json（归档路径：`validation/native-engine-offline-20261031/environment.json`）。
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
zoom.json（归档路径：`validation/native-engine-offline-20261031/zoom.json`）。缩小时所选中心会改变边界，不能笼统视作每档全命中缓存。

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
比较证据（归档路径：`validation/native-engine-offline-20261031/equivalence.json`）记录了具体序号。

默认配置Python回归28项、Web自测30项通过。包括旧环境强制修正、Zynq解码前启用原生配置、
隐藏文档/不完整时间线拒绝伪造绘制完成，以及实际Web首屏/24次缩放无CLI错误。
新脚本和计时接口提交`7b7ea55`；默认时间线截图（归档路径：`validation/native-engine-offline-20261031/native-first-screen.jpg`）保留了实际分析页面；
原始处理、首屏、缩放和命令证据统一在
离线验收目录（归档路径：`validation/native-engine-offline-20261031/`）。
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
归档核查（归档路径：`validation/etm-merge-20261031/handoff.json`）分别记录新旧ELF及装载段哈希。

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
最终归档核查（归档路径：`validation/etm-merge-20261031/handoff.json`）。原有source-provenance.json中main.c仍记着CDC补丁前哈希，
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
实际配对、下载和单步证据（归档路径：`validation/combined-etm-web-20261031/step-fix/`）。

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

下载落盘及哈希证据（归档路径：`validation/flame-download-20261031/result.json`）、
当前区间SVG（归档路径：`validation/flame-download-20261031/flame-913-977.svg`）、
页面状态截图（归档路径：`validation/flame-download-20261031/web-download.jpg`）。

### CLI覆盖审计与SVG能力边界

统一入口补入`toolbox.py project list|describe|run`，支持32个常用别名，按实际Git跟踪源码动态生成清单。
本次索引371项：252个可运行入口及119个支持库/上下文片段。252个入口均成功构造执行计划；
**没有实际执行所有252个工具，更不等于所有功能已真机通过**。旧/参考入口单独标注，产品ETM仍默认原生链路。
9个现有Web页面全部通过真实CLI读取describe，共701个控件、146个顶层公开方法；嵌套session/target/history按需describe。
list/describe/dry-run不需要浏览器；具体工具如自身需要SDK、USB或浏览器，依赖仍须满足。

| 范围 | 当前覆盖和验收结论 |
|---|---|
| Web串口、终端、RTT、RTT转发、J-Scope、调试、烧录、ETM、工程生成 | 9页面均有统一CLI；此前串口、RTT、IDCODE、ETM及精确单步有真机证据，不能把界面入口存在当作每个参数组合已通过 |
| 非Web PL/PS/boot构建、JTAG/RAM加载、QSPI、仿真、测速、target | project按原工具参数转交，全部入口已生成计划；本轮没有额外执行Flash或SDK构建 |
| 主机验证 | 43项Python测试、39项Web测试通过；全部142个Web模块语法通过 |
| Web开发构建 | 当前直接加载源码；旧package.json的build:web/check:web/test:etm引用缺失脚本，登记待迁移，未虚构可运行别名 |
| 连续切换J-Scope首DEF | 按用户指示暂停，DEFERRED；没有继续实验或宣称恢复 |
| 火焰图手动下载 | 原区间913～977的自动下载及再次下载均实际落盘，2,531字节、XML及SHA核对通过 |

`web.check`恢复自superlinkPRO提交`be75311236da2665a2edc54b9b4d4561f0219456`的check-syntax.mjs，
使用当前目录自动遍历，不需Node依赖包。CLI清单、9页describe和测试日志见
[覆盖证据](validation/cli-coverage-20261031/summary.json)。用法统一收在[CLI手册](toolbox-cli-ai.md)。

对同一6MHz、1s已解码记录（5,467,630个事件）重新通过**显式CLI捕获**导出：

| SVG | 大小 | 调用段 | 包含CLI保存耗时 |
|---|---:|---:|---:|
| 顺序区间2～2000 | 44,968 B | 134 | 0.337 s |
| 缩放后0～999 | 22,905 B | 68 | 0.504 s |
| 汇总区间0～999 | 2,894 B | 9 | 0.656 s |
| 汇总全记录 | 4,402 B | 14 | 0.613 s |

全部XML、区间和函数名核对通过，四个SVG与完整命令/返回值归档在
[导出证据](validation/flame-svg-20261031/summary.json)。本次打开130.5ms/缩放51.9ms为已有缓存上的检查，
不替换前文完整处理、首屏和首次大区间缩放基准。

仍有明确限制：全记录顺序导出扫描31.263秒后触及200,000调用段上限并明确拒绝；
全记录汇总SVG虽生成成功，为完整文字比例扩成207,750,782px宽，实际查看不方便。
精确SVG生成仍有Python按事件重建调用段的开销；这与已默认C++的解码/TraceStore处理链不同，
没有生成生产events.jsonl，但不能声称所有导出耗时都已C++化。后续需改善几何尺寸及大记录SVG重建性能。

同一交付配对已完成直接Zynq原生CLI的12MHz TRACECLK、1s采集：2,592,006字节，
10,391,585条指令记录，loss=false、synced/ended=true、packetIssues=0，整体14.842秒。
实际FCLK119,999,998Hz、ref199,999,998Hz；运行后恢复RCC/FPB，未写Flash。
这不是更高频极限或实时显示证明；与6MHz的离线1s基准输入不同，不用于直接性能比较。
[直接CLI原始返回](validation/cli-coverage-20261031/direct-cli-12mhz.json)。

### 2026-11-01：真实RAW4接收器接入有界DDR窗口，RTL阶段冻结

已将独立验证过的参考时钟窗口、异步帧FIFO和DDR打包器接入生产模块；本阶段是源码/仿真冻结，尚无新bit上板，不能当作新采集路径已验收。板上仍是前述已记录哈希的DDR模式数据pilot。

窗口按200MHz参考时钟计数，目标TRACECLK停止也能正常结束；先准备并清空接收器，再锁定采集所有权，结束后停止取样、排空解析器、写入带长度的EOF。只有EOF被消费、快照稳定且最后一个AXI写响应完成才释放缓冲。旧USB清理操作不能清掉进行中的DDR源。记录保存START时的mode/nonce，下一次配置不会更改上一条记录身份。

DDR格式FRM1为去掉TPIU同步的连续16字节formatter帧，末尾不足16字节单独记录长度/歧义标志；**它不是可直接送ETM指令解码器的BIN**。必须先通过原生C++解复用恢复源ID与数据位，再调用现有ETMv3/v4解码。计时、实际写入字节数、窗口stop原因、溢出/解析错误/同步计数分别上报，不以主机下载时间冒充硬件覆盖时间。

离线验证：9项真实RAW4引脚→解析→异步FIFO→AXI DDR集成场景、92项DDR writer场景及原接收器11项回归通过。覆盖完整帧+5字节尾部、精确窗口、32字节容量停止、目标时钟停止后的手动结束、无信号空记录、最终B响应延迟、512帧FIFO溢出、B错误、准备超时与取消。结果及源码SHA见[本轮仿真归档](validation/etm-ddr-trace-rtl-20261101/integration/result.json)。所有测试hardwareAccess=false，未将仿真结论扩大为板上频率结论。

当前DDR引脚入口限制为RAW4，传输格式与F103 ETMv3/H743 ETMv4无关；H743原有Kingst接入、目标识别、独立时钟读取、ETMv4配置与原生解码保留。此阶段没有修改任何目标PLL/AHB/APB寄存器，没有写目标Flash/QSPI。后续需完成新bit时序、配套ELF、真实DDR采集和USB采后下载，才可将此路径接为Web默认。每条lane校准及高频上板仍未完成。

### 2026-11-01：FRM1原生C++解复用与H743兼容性回归

新增独立`etm_framed.exe`，按仓内OpenCSD 1.8.3 `TraceFmtDcdImpl::unpackFrame()`语义恢复formatter的LSB、源ID及“跟随字节属于旧ID”标志，按源输出BIN。保留superlinkPRO原生前端/解码器/TraceStore二进制与源码；新增CMake目标，不替换原始Kingst路径。`native/source-provenance.json`仍描述导入时快照，当前CMake的本地扩展及新EXE哈希另见[本地构建记录](validation/etm-framed-native-20261101/build.json)。

每个源有64KiB输出缓存，输入64KiB分块，内存不随采集总量增长。要求显式给出末尾长度并与文件大小核对；缺失flags的残帧只计数、不生成虚构ETM字节；保留源ID 127或输入变更均拒绝发布。Python仅作版本/身份/大小检查及SHA，不逐字节解复用，不产生逐指令JSONL。AI入口为`toolbox.py project run etm.framed -- INPUT --out NEW_DIR --tail-bytes N --trace-id 2`，构建仍用`native.build`。

48项离线检查全部通过：28种尾部有效载荷长度、多源切换、15种残帧长度、非法ID和长度拒绝，以及两份真实ETM字节流重封装的一致性。F103原1s数据1,363,722字节经1,558,544字节FRM1恢复后逐字节一致，原生解复用段7.17ms；H743 ETMv4 15,306字节恢复后逐字节一致，原生段0.325ms。这些时间只涵盖解复用，不包含SHA、进程启动或完整指令解码；测试FRM1由已保存ETM流重封装，不是真实DDR采集。结论是新增阶段保持两种协议的输入字节，H743 Zynq实机和完整性能仍待验收。[48项结果](validation/etm-framed-native-20261101/result.json)。

FRM1后续主机检查：新增超大尾部参数拒绝用例，共49项通过；修正后的F103原生段6.72ms，时间口径同上。[最终EXE哈希及源码哈希](validation/etm-framed-native-20261101/v2/build.json)。桥启动预检可运行全部6个原生工具，现有3项Web完整测试再次通过（含真实F103/H743 C++解码及损坏采集不能冒充通过）；5项传输生命周期检查通过。EXE打包脚本仅复制6个明确运行工具，不把本地CMake缓存/对象/静态库打包。此处尚未重新交付桥ZIP。

新增AI真机验收选项`tools/test_orbtrace_board.py --ddr-physical`，沿用原F103 ELF/Flash只读核对、断点/CoreSight恢复；拒绝搭配目标分频或GPIO诊断改写。硬件窗口完成后通过物理AP0分块读DDR，再由C++解复用。nonce/captureId不符即拒绝读取负载，2项主机安全边界测试通过。该入口是DDR源首次上板的JTAG验收工具，不是用户Web操作入口，也不等于PS USB下载接口已实现。新RTL120MHz时序通过，setup +0.060ns、hold +0.003ns、SWCLK clock-to-pad 6.389ns/7ns；新bit/ELF及实际加载结果在完成后单独登记。

### 2026-11-01：首轮真实ETM→DDR 1秒采集与原生解码通过（仍非Golden）

新配对目录`prebuilt/etm-ddr-trace-raw4-20261101/`。bit SHA-256 `56a70e493ee0f276e02bb6b8f7f358ee3e7fb9cdfeeaec1613ee02f065687581`；本次实际重新构建的ELF SHA-256 `ab7c097764bea91272783ec59a51d200bf154ba5d4f9adbf1e7350466c17947f`（PS源码未变，因此与前pilot ELF相同；构建日志/时间及输入时序另记，不冒充新PS代码）。RTL提交`d212517`、PS构建提交`e6c40a1`；init及完整哈希/选项在配对manifest。通过JTAG加载新bit及PS RAM，物理OCM执行段核对，随后同次运行2轮不同seed的1MiB模式数据，全部读回通过，未复位重试。

首轮F103 `cdc_poll`、固件HCLK48MHz/TRACECLK24MHz：参考时钟199,999,998Hz，窗口199,999,998ticks，精确1秒；实际FCLK119,999,998Hz、SWCLK999,999.98Hz。FRM1实际写入19,277,266字节（含2字节残帧，另有未成字节的边界歧义，未伪造末尾数据），帧丢失/解析错误/ready丢失均0，frame FIFO高水位1。C++解复用53.0ms，输出4,567,468字节ETM，剔除零源padding 8,661,088字节。物理AP0采后读回，采集中没有下载trace负载。

OpenCSD实际处理全部4,567,468字节，packetIssues=0、unsyncBytes=0、addressInaccessible=0、lastErrorCode=0；3,919,374个packet、18,306,718个指令范围元素。范围数不是指令数；本次没有以Python展开逐指令JSONL。验证统计工具扫描原生二进制的时间也不是生产C++解码耗时。Flash与ELF逐段只读匹配，目标CoreSight、FPB与RCC均恢复，没有改目标时钟、目标Flash或QSPI。

[加载/模式数据与首轮完整证据](validation/etm-ddr-trace-board-20261101/first-1s/acceptance.json)、[原生解码结果](validation/etm-ddr-trace-board-20261101/first-1s/decode/summary.json)、[真实FRM1压缩原始数据](validation/etm-ddr-trace-board-20261101/first-1s/capture.frm1.gz)、[可回放记录](validation/etm-ddr-trace-board-20261101/first-1s/capture.etmrecord)。原始压缩前SHA与native工具版本在ddr/result.json，可以离线复现解复用。

结论限于首轮1秒24MHz实际链路；这是解决下游排空瓶颈后的新证据，不证明更高频、零BER、实时显示或完整Web验收。此版本没有PS USB DDR下载接口，也没有逐线IDELAY校准。保留原Golden；F103 1/2秒更换函数+CDC压力、H743 Zynq实机、USB采后传输和逐线校准继续推进。
