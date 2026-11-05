# H743综合性能与Golden对照（2026-11-01）

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

本轮使用用户换上的阿波罗STM32H743，完成SWD/JTAG六档SRAM、RTT、HSS，50/60MHz Golden对照及调试插入；并将指定superlinkPRO例程复制为本工程H743 Golden，完成20MHz TRACECLK的真实CDC负载ETMv4验收。没有修改或重建探针RTL/PS固件，没有写QSPI。失败、边界和较低负载对照全部保留。

## 配对、目标与方法

- 主配对为 `prebuilt/fclk133-release-20261101/`，bit SHA `af1031d3caa0d7bd3b6adffa911d26efdab9e0bfb5223fb18f70dabb70ebeeed`，PS ELF SHA `2137f7d0f507c08574f36223130103c0710645cbfdefb5c1d8c8efb0cfb990a0`。Golden对照bit/ELF为 `1da17cb60175bbc2b7abd647770c7053bd7b7097e0d38aa819fb89678d564473` / `e977914c2924ab4cac13f4075de0a5108d1e2e8cf48966fb8fbdea3a358e0b2c`。分别RAM加载并独立核对物理OCM可执行段。
- 目标CPUID `0x411fc271`，DEV/REV `0x20036450`，HSE25MHz。原Flash完整2MiB已备份，SHA `fff304656bc59d0f4910560aed321f933d24a3974f27e445441ef7e6987e6f46`，见 `raw/target-original-flash.bin`。按用户授权烧录例程，原程序不是当前运行镜像。
- ETM和六档SRAM/HSS基础表固定CPU/HCLK60MHz。RTT另测CPU480/HCLK240；Golden 50/60对照及调试插入使用此高吞吐配置。两套固件都设TRACECLK20MHz，RTT/HSS阶段ETM输出关闭。实际RCC由本工程clock.js独立核对，见 `raw/verified-target-clocks.json`。
- 频率来自PLL/来源/分频寄存器与固件读回，非外部频率计。35MHz请求实际约34.615384MHz。JTAG链IR为4,5。没有启动150MHz或高频逐线扫描。
- SRAM：先做随机4KiB全页功能校验；吞吐用512 words、depth32、64块、三次重复，读数据与写回均校验；50/60MHz附加10秒交替读写。H743 TAR在1KiB回绕，吞吐为周期1KiB缓冲反复传输，不冒称全SRAM连续大地址流；备份/控制助手逐1KiB重新设TAR。
- RTT：AXI SRAM `0x24040000` 的RAM producer、8192B环、1024B块、各三次2秒，用probe payload计数窗口算十进制MB/s。递增u32序列与最终发布/接收总量均核对。完整备份/恢复20KiB、核心寄存器与运行状态。I-cache开/D-cache关；不是SEGGER printf应用产出速率。
- HSS：单u32，24MHz时间基准；扫描/二分后用三次2秒验证零跳采边界。表中是该条件最高已验证零跳采速率，不是任意时长的物理绝对上限。过载和跳采数据保留。JTAG1/10MHz START返回-6，因低频JTAG策略下FCLK不足采样器要求的24MHz，明确列为不支持。SWD低档保持120MHz FCLK，通过共享RTT clock setter配置，不冒称HSS公开setter允许低于15MHz。
- 主机为Windows11 build26200、Python3.13.5、ARM GCC10.3-2021.10。SDK子集及许可证/哈希随工程保留。未清OS文件缓存，不声称冷启动时间。

## 六档测量

SRAM/RTT为MB/s；HSS为kSamples/s（每样本4B，不含帧头）。SRAM在CPU60下测量，RTT分别列两种目标时钟。

### SWD

| 请求 / 实际 MHz | SRAM读 | SRAM写 | RTT CPU60 | RTT CPU480 | HSS CPU60零跳采 kS/s |
|---|---:|---:|---:|---:|---:|
| 1 / 1.000000 | 0.0848 | 0.0838 | 0.0808 | 0.0803 | 21.220 |
| 10 / 10.000000 | 0.8381 | 0.8261 | 0.6275 | 0.7979 | 208.696 |
| 25 / 25.000000 | 2.0505 | 2.0101 | 0.6752 | 1.9473 | 510.638 |
| 35 / 34.615384 | 2.8304 | 2.7922 | 0.7073 | 2.7003 | 666.667 |
| 50 / 50.000000 | 4.0468 | 3.9845 | 0.7298 | 3.8749 | 960.000 |
| 60 / 59.999999 | 4.8418 | 4.5190 | 0.7525 | 3.6597 | 1000.000 |

### JTAG

| 请求 / 实际 MHz | SRAM读 | SRAM写 | RTT CPU60 | RTT CPU480 | HSS CPU60零跳采 kS/s |
|---|---:|---:|---:|---:|---:|
| 1 / 1.000000 | 0.0819 | 0.0819 | 0.0757 | 0.0757 | 不支持 |
| 10 / 9.999999 | 0.8140 | 0.4087 | 0.3903 | 0.3924 | 不支持 |
| 25 / 25.000000 | 1.0200 | 1.0144 | 0.4976 | 0.9784 | 134.831 |
| 35 / 34.615384 | 1.4036 | 1.3992 | 0.5524 | 1.3519 | 186.047 |
| 50 / 50.000000 | 2.0230 | 2.0063 | 0.6567 | 1.9471 | 269.663 |
| 60 / 59.999999 | 2.4202 | 2.3958 | 0.6706 | 2.3209 | 324.324 |


CPU60时RTT高档仅约0.73～0.75MB/s；CPU/HCLK一起提高后明显变化，说明目标供数/AXI条件影响结果，不能归为探针USB上限，也尚不能区分纯CPU、总线等待和争用的贡献。CPU60的SWD60 SRAM写4.519MB/s，CPU480/HCLK240时提高到4.749MB/s。

CPU480时JTAG50 SRAM读约3.98MB/s，高于JTAG60约2.42MB/s；SWD50 RTT约3.875MB/s，也高于SWD60约3.660MB/s。Golden有同类非单调行为，根因待定位（ZL-067），不能以“档位更高”代替实际测速。

## 50/60MHz与Golden（CPU480/HCLK240）

| 链路 | SRAM读 Golden / release | SRAM写 Golden / release | RTT Golden / release |
|---|---:|---:|---:|
| SWD50 | 4.0517 / 4.0494 | 3.9873 / 3.9894 | 3.8735 / 3.8749 |
| SWD60 | 4.8384 / 4.8291 | 4.7450 / 4.7493 | 3.6640 / 3.6597 |
| JTAG50 | 3.9688 / 3.9771 | 2.0083 / 2.0076 | 1.9483 / 1.9471 |
| JTAG60 | 2.4199 / 2.4217 | 2.3989 / 2.3943 | 2.3214 / 2.3209 |

有效吞吐中位数最大下降约0.194%，未见实质恶化，未做千分量级统计等效性认证。通过条件均三次重复，SRAM另有10秒持续验证，RTT序列/总量一致。

Golden首轮SWD50已完成三次短测，随后持续测试出现USBError(5)，自动恢复也失败，该轮不计通过。重新打开同一设备的DAP epoch后，原SRAM、时钟和运行状态核对恢复，在独立目录复测通过（ZL-069）；不把恢复或重试通过当作问题已修复。

HSS相同period对照：双方SWD50的25ticks/960k、SWD60的32ticks/750k、JTAG50的89ticks/269662.9Hz、JTAG60的74ticks/324324.3Hz均三次2秒零跳采，数据/总量一致。release额外在SWD60的24ticks/1MHz三次通过；Golden的1MHz第三轮跳27602点（1.37885%），960k第二轮跳1134点（0.05901%）。750k是本轮双方留裕量验证点，不是Golden的绝对上限，也不把单次近限波动宣布为确定性能提升（ZL-070）。

## 调试命令插入

release在SWD/JTAG50、60各跑RTT、8×u32/1kHz HSS及1×u32/1MHz HSS，共12条件、1479轮混合burst、34017条burst内DAP请求、36轮暂停/改写并恢复R12/单步/恢复。无卡死，响应、数据、计数、SRAM/核心寄存器及运行状态恢复通过。未重做已知失败的流运行中完整SWJ重新初始化，ZL-002/003仍保留。

HSS调试抢占的时间语义缺陷仍复现：8变量设1kHz，在SWD50期间约3637.3Hz、SWD60约1216.2Hz，结束恢复约1000.09Hz；JTAG50/60期间约975.7/643.8Hz。有首DEF，时间戳无倒退，但有计时rebase，不能按均匀1kHz解释。ZL-001未关闭，也不替代此前暂停的Web跨功能缺DEF问题。

## ETM：真实约4ms CDC负载

CPU/HCLK60MHz、PLL1R40MHz、物理TRACECLK20MHz；SWD约10MHz、GPIO速度2、4位DDR，ETMv4 CONFIGR读回0x1011（返回栈/周期计数开，分支广播关），TraceID2。通过本工程DDR USB直接取得formatter/ETM，不使用Kingst、500MSa/s KVDAT或软件4ns滤波。每次逐段核对ELF，采完整硬件窗口，恢复CoreSight、锁、GPIO及运行状态，再解码/建库。

周期banner20ms；CRC/序号文本回显请求周期4ms，1秒窗口实测发包间隔中位数4.246～4.268ms。用硬件arm时间括号并扣20ms边缘证明回显在窗口内：1秒三次224/222/224次正确回显。首版Windows Event.wait(4ms)实际约15.6ms，旧12轮保留在 `raw/etm20-matrix`，不能冒充4ms负载；最终使用高精度sleep并以时间戳核对（ZL-068）。

| 窗口 | 三次完整CLI耗时 s | 三次保守窗口内回显数 | 质量 |
|---|---|---|---|
| 10ms | 3.619 / 3.384 / 3.215 | 1 / 1 / 1 | 完整窗口，硬件/解码包错误0 |
| 200ms | 5.103 / 5.288 / 5.251 | 37 / 37 / 37 | 完整窗口，硬件/解码包错误0 |
| 500ms | 8.487 / 8.452 / 8.031 | 105 / 106 / 107 | 完整窗口，硬件/解码包错误0 |
| 1000ms | 13.732 / 14.458 / 14.030 | 224 / 222 / 224 | 完整窗口，硬件/解码包错误0 |

完整CLI计时从启动采集子进程前至命令返回，包含目标Flash核对/配置、硬件窗口、USB下载、目标恢复、原生解码及TraceStore/索引发布；不含浏览器首屏、之前烧录或打开CDC串口预热。离线处理时间另列。

| 1秒轮次 | ETM bytes | 路径指令记录 | 完整CLI s | 解码+建库 s | OpenCSD s | Store/索引 s |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 2176688 | 18373686 | 13.732 | 10.303 | 1.222 | 8.853 |
| 2 | 2175632 | 18359408 | 14.458 | 10.767 | 1.357 | 9.139 |
| 3 | 2175483 | 18355012 | 14.030 | 10.132 | 1.224 | 8.676 |

1秒完整CLI中位数14.030s，解码/建库中位数10.303s；约1836万条路径记录，与superlinkPRO当年H743规模相近。历史完整处理14.247s包含Kingst物理前端，历史请求到完成24.916s的边界也不同；不能直接宣称GUI E2E提升某个百分比。历史条件见 [ZL-006核实](../zl006-decode-audit-20261101/superlink-1s-conditions.md)。

本轮每个1秒native.bin约0.325GB；此前F103大输入约1.305GB，路径条数相近但协议/中间表示形态不同。不能把F103的22～25秒泛化为移植后H743解码退化；F103大输入建库/索引问题ZL-006保留，跨路径同一大输入重放未完成。

最终12轮reference ticks均完成请求窗口，formatter parser/frameDrops/IDELAY readyLoss/writer错误0；OpenCSD packetIssues/overflow/unprocessed/unaccounted为0。初始NoSync gap、unknownExecution及formatter末尾非整帧边界均保留在逐轮decoded/session/summary中；这些计数不等于逐条完整执行流证明。

TRACECLK30MHz先测10ms，出现17个formatter parser错误，尽管frameDrops=0仍判失败，原始capture.frm1与恢复证据保留。按用户授权改20MHz后通过最终矩阵；没有继续高频自动校准，30MHz不作为Golden（ZL-063）。

## 交付与收尾

- 源代码/SDK/许可证在 `firmware/target/stm32h743_cdc_trace/`，默认CPU60/TRACECLK20/banner20ms。旧etm-service/firmware同名目录保留固定历史来源快照；构建不再依赖superlinkPRO绝对路径。
- 三套目标ELF/bin/hex及SHA/选项见 `prebuilt/targets/stm32h743-cdc-trace-20261101/manifest.json`。CPU60/TRACE20为ETM Golden；CPU60/TRACE30仅失败诊断；CPU480/TRACE20用于DAP/RTT/HSS吞吐，未对CPU480做完整1秒ETM验收。
- 2026-11-01 22:56:08（上海）最终硬件快照：release探针配对已重载并再次核对OCM；目标Flash逐段匹配CPU60/TRACE20 ELF，SHA `246640bf79c8b1e568441a286812326dfb0ae68a0df061a0c023262c07cf221b`。FCLK约120MHz、SWCLK约10MHz，H743运行，ETM PRGCTLR=0，capture/packet/DDR/CDMA空闲；所有读流/CDC刺激线程退出，共享hw_server保留。
- 主机检查：81项Web自测、149模块语法/共享检查、53项CLI自测；H7成功/失败清理5项、1KiB跨页/非对齐恢复1项、Trace生命周期5项、DDR身份2项、时钟请求2项通过；491个固定依赖哈希通过。
- 未覆盖GUI首屏、Web换函数起点/导出、原生CLI entry/reset、QSPI冷启动、温压/多板/长时间可靠性。高频ETM输出并发RTT不在要求范围。固定dist EXE本任务未重建，新增H743原生CLI/文案当前属于仓库源码交付，不能说旧EXE已包含。
- 用户断线期间Golden SWD50/60已保存，JTAG未启动；恢复后重核Golden OCM、确认目标运行，在独立目录继续。另有初始PS不可访问/USB未枚举（ZL-060），用户回复继续后加载恢复，原因未定。

`summary.json` 为汇总；`raw/`为逐次成功/失败、实际命令、身份/恢复、原始formatter/ETM、匹配ELF及测试日志；`drivers/`为最终源快照，`raw/executed-driver-versions/`还保留与各轮SHA匹配的SRAM驱动版本。`evidence.json`给出逐文件SHA。派生native.bin/store缓存留在本机build中，最终1秒native的尺寸/SHA已记录，归档原始输入可重建。问题表同步更新，本任务未推送。
