# HPM6800EVK JTAG/SRAM/RTT/HSS验收与优化

**后续勘误与高频研究：** 本报告的25MHz是保证范围基线，并非不可逾越的实测极限。原文“26/27/28/29MHz请求补测亦未通过”错误：原始逐点JSON中26/27/28请求均通过（实际25.714/26.471/27.273MHz），只有29失败。ZL-078记录误把整轮退出码当逐点结果的修正；原始JSON未改。加idle及返回窗口的新结果见 [后续研究](../hpm6800-idle-frontier-20261102/README.md)。

2026-11-02（Asia/Shanghai）。本轮HPM限定范围已通过：最佳25MHz下AXI SRAM读 **1.6317**、写 **1.6218MB/s**，AHB读 **1.6176**、写 **1.6074MB/s**；RTT **1.4872MB/s**。HSS单/八u32约 **137.931/23.715kSamples/s**，各三轮10秒零跳采，数据及最终总量一致。交付为 `prebuilt/hpm6800-jtag-20261102/`；没有覆盖Golden/recovery，不是ARM/ETM/QSPI完整release。超规格、过载和隔离试验失败仍保留。

探针Golden配对：`prebuilt/golden/probe.bit` SHA-256 `1da17cb60175bbc2b7abd647770c7053bd7b7097e0d38aa819fb89678d564473`；`application.elf` `e977914c2924ab4cac13f4075de0a5108d1e2e8cf48966fb8fbdea3a358e0b2c`。本轮实际RAM加载，独立物理AP0核对71268字节可执行段。初始DAP报30000021，PL下载后仍无APU，选DAP执行系统复位后恢复，再加载完整配对；本轮初始尚未加载配对，不把USB缺失当作已运行配对的新故障，也不据此关闭ZL-060。未写QSPI。

目标用户指定HPM6800EVK/HPM6880，单TAP IR5，IDCODE `0x1000563D`，DTMCS `0x7071`（idle=7）。相同ID不单独证明芯片型号。SRAM分AXI `0x01240000`/64KiB与AHB `0xf0400000`/32KiB；CPU暂停后备份/恢复，原目标Flash、PLL/分频不改变。MB/s均为十进制，时钟由PS/PL寄存器读回计算，非外部频率计。

Golden完整SRAM矩阵已测1/10/15/20/25/30/35/40/50/60MHz请求，512words、深度32(AXI)/16(AHB)、128块、预热一次+三次计时，校验全部读数据和写回。25MHz AHB读1.613、写1.607MB/s；AXI读0.344、写1.612MB/s。30MHz起四种采样模式均未通过；另外低速识别后直接DMI的诊断也未通过超25MHz各档，恢复均核对。

[官方HPM6800数据手册Rev1.2](https://www.hpmicro.com/Public/Uploads/uploadfile/files/20251128/HPM6800DSV12.pdf)第80页表27规定JTAG周期最小40ns（25MHz）、TDO下降沿至有效最大15ns。当前RTL每字一次41-bit DMI，外加5拍TAP导航和8拍空转，共54拍：25MHz的理想线速约1.852MB/s；若按DTM所需7拍空转的最小53拍则约1.887MB/s。实际约1.61包含PL状态机、包尾检查、地址/配置、USB/主机开销。不能拿F103的60MHz TCK成绩直接作为HPM25MHz协议下必达值，也不能把超规格失败定位为唯一电气根因。

ZL-072已关闭：Golden的AXI读每字 **5.004次扫描/270.218bits**，AHB读和写约1次。白名单缺失使AXI每字检查SBCS和重新寻址；RTL新增限定512KiB AXI窗口及末字保护后，每字约 **1.004次/54.231bits**，AXI读0.344→1.632MB/s，约4.74倍。AHB原本有单扫描流水，不宣称同等提升。25MHz总时间约九成花在物理移位等待，USB不是主要瓶颈。

最终PS仅对RISC-V请求 **<15MHz** 保高FCLK、使用最多16倍整数分频；ARM校准策略未改。FCLK100MHz/TCK25MHz隔离试验四种模式未过DM/SRAM，已撤回高档分频，失败ELF/源码/Golden bit身份在 `prebuilt/hpm6800-clock-divided-failed-20261102/`（ZL-076）。精确DTM空转、减少PL状态气泡、优化TDO相位可继续研究，但在25MHz标准32-bit SBA链路下，理论1.85～1.89MB/s已低于F103ZE的2.4MB/s，不能承诺达到。

RTT使用RAM-only汇编producer、原生ILM `0x10000`、AHB SRAM内8KiB环和1024B块，各档三次2秒；递增u32及停止排空后的发布/接收总字节一致，错误0。不是printf产出速度。每轮恢复ILM、20KiB AHB、GPR/dpc/dcsr可写位/mstatus及运行状态；cache控制前后0x7f03，安全SYSCTL控制前后相同。首版套用旧HPM5301的`0x01050000`别名导致备份FAULT，未写入/执行夹具；修正后实板验证与恢复通过，ZL-074关闭。

最终分档如下；SRAM为512words、深度32(AXI)/16(AHB)、128块、预热一次+三次计时。每次先重复读取备份，再做随机4KiB/非对齐和全部读数据、完整写回校验。两种窗口队列深度不同，不用小差异判断总线优劣。

| 请求 / 实际DR TCK MHz | AXI读 MB/s | AXI写 MB/s | AHB读 MB/s | AHB写 MB/s | RTT MB/s |
|---|---:|---:|---:|---:|---:|
| 1 / 0.986842 | 0.0722 | 0.0722 | 0.0721 | 0.0721 | 0.0650 |
| 5 / 5.000000 | 0.3637 | 0.3632 | 0.3613 | 0.3614 | 0.3279 |
| 10 / 10.000000 | 0.7168 | 0.7150 | 0.7135 | 0.7137 | 0.6497 |
| 15 / 14.999999 | 0.9862 | 0.9830 | 0.9805 | 0.9732 | 0.8952 |
| 20 / 20.000000 | 1.3102 | 1.3032 | 1.2911 | 1.2945 | 1.1907 |
| 25 / 25.000000 | 1.6317 | 1.6218 | 1.6176 | 1.6074 | 1.4872 |

HSS为各档三次2秒已验证零跳采点，25MHz另有各三次10秒复核，不是无限时长绝对上限。所有接收DATA帧逐字节核对，所有扫描/验证点STOP后的样本计数一致。8变量25MHz的920ticks（26.087kS/s）在2秒三轮各跳3点、10秒三轮各跳15点，约0.00575%；1012ticks/23.715kS/s后三轮10秒零跳采。这是ZL-070的新边界证据，未证明与H743同根因。

| 请求TCK MHz | 实际FCLK MHz | HSS 1×u32 kS/s | HSS 8×u32 kS/s |
|---|---:|---:|---:|
| 1 | 31.578947 | 2.248 | 1.136 |
| 5 | 119.999998 | 30.535 | 5.733 |
| 10 | 119.999998 | 60.453 | 11.364 |
| 15 | 29.999999 | 82.759 | 15.645 |
| 20 | 39.999999 | 110.092 | 20.852 |
| 25 | 49.999999 | 137.931 | 23.715 |

**HSS公共clock setter仍有15MHz下限**：本工具明确通过共享RTT clock setter配置1/5/10MHz HSS，不声称GUI或旧公共setter已开放低档。原Golden因FCLK不足24MHz而START -6，新配对低档采样通过；ARM/H743低频策略未改，ZL-064仅部分解决。

额外12.5/14MHz请求实际12.500000/13.235294MHz SRAM通过。25MHz AXI、AHB、AXI末4KiB `0x0127f000`各10秒交替全窗口写读，每方向分别6750208/6651904/5918720B校验通过；末字保护另有仿真访问计数。原始SRAM备份留本机build，Git保存SHA/恢复结果。26/27/28MHz请求原始记录通过，29MHz请求失败；这里原有的“全部未通过”结论已撤回（详见顶部勘误）。超规格点不作保证能力。

ZL-075：额外PLL快照读取0xf40c00c4后SBA长时间忙，发生在SRAM改写前。核对DPC、恢复原程序运行，仅清调试状态未立即解除。用户授权一次明确目标复位；执行前SBCS已回到非忙，因此不把恢复归功于复位。已移除该组未验证寄存器读取，延迟恢复机制待定位。目标CPU/总线频率没有用未验证PLL输出推断。

新bit SHA-256 `fd4a3c91daa29334f9f3fca41e57f303fe95d529e8abcaee27093f0eb55976c1`；PS ELF `1abbff5018299b53e090e026eacbd26b3dcc9397d51c3161f3ad9eac09c15829`。实际加载的 `build/hpm6800-acceptance-20261102/pair/` 与交付文件字节一致；初始和最终独立物理MEM-AP0核对75348字节可执行代码一致。120MHz setup/hold **+0.242/+0.025ns**，SWCLK内部发射路径6.279ns满足7ns预算。既有外部IO/CDC签核缺口ZL-007仍保留。RTL stamp、PS源码SHA/BSP/选项、时序及源码提交随配对，不用旧bit冒充新构建。

验证：完整RISC-V IDCODE/word/full-pipeline及late/Q1三种返回模式，生产探针8组C主机测试；真实DAP_SWJ_Clock C函数的RISC-V分频、ARM/SWD策略、非法频率检查；验收工具非法窗口/零重复参数提前拒绝测试。raw报告driver_sha256和drivers快照标识实测版本，delivered为最后增加非法参数拒绝后的工具，正常参数路径未改。未覆盖GUI、QSPI启动、多板温压、无限时长；没有重启暂停的ETM/跨功能缺DEF研究。

源码与已验收bit/ELF提交：`2bd88adf5fd748678e025e4af7cb1670696f7d87`；manifest固定该提交及逐文件SHA，构建时基提交另行保留。统一CLI 53项自测通过。

最后板上快照 **2026-11-02 01:19:49 +08:00**：新HPM配对，FCLK49.999999MHz、DR TCK24.9999995MHz、mode0，目标运行；RTT/HSS、capture/packet空闲，SRAM/核心/cache及SYSCTL恢复通过。时钟为PS PLL/分频与PL寄存器计算值，非外部频率计；TAP/IR控制序列可更慢。无本任务后台采集/串口进程，共享hw_server保留；随后OCM再次复核通过。

复测先加载/核对同一配对（out须新目录，--elf为探针PS ELF）：

```powershell
python -X utf8 tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/hpm6800-jtag-20261102/application.elf prebuilt/hpm6800-jtag-20261102/probe.bit prebuilt/hpm6800-jtag-20261102/ps7_init.tcl
python -X utf8 tools/verify_probe_ocm_code.py --elf prebuilt/hpm6800-jtag-20261102/application.elf --out-dir build/hpm-identity-new
python -X utf8 tools/validate_hpm6800_performance.py --bit prebuilt/hpm6800-jtag-20261102/probe.bit --elf prebuilt/hpm6800-jtag-20261102/application.elf --out build/hpm-sram-new --speeds 1000000,5000000,10000000,15000000,20000000,25000000
python -X utf8 tools/validate_hpm6800_streams.py --stage rtt --bit prebuilt/hpm6800-jtag-20261102/probe.bit --elf prebuilt/hpm6800-jtag-20261102/application.elf --out build/hpm-rtt-new --speeds 1000000,5000000,10000000,15000000,20000000,25000000
python -X utf8 tools/validate_hpm6800_streams.py --stage hss --bit prebuilt/hpm6800-jtag-20261102/probe.bit --elf prebuilt/hpm6800-jtag-20261102/application.elf --out build/hpm-hss-new --speeds 1000000,5000000,10000000,15000000,20000000,25000000
```

RAM producer使用本机HPM SDK v1.11环境的RV32 GCC13.2.0，仅需工具链、不依赖SDK源码/board_init；探针PL/PS为Vivado/SDK2018.3。raw/保存完整成功/失败JSON、日志、身份、fixture ELF和恢复证据；summary.json是派生表，evidence.json记录文件哈希。其他会话HTML、EXE及build修改未混入本任务提交。
