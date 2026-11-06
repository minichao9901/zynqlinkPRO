# HPM6800EVK：idle摸高、133.333MHz配对与HSS对照

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

2026-11-02，ZL-070/073/078/080/081/082/083。25MHz不是本板不可跨越的物理墙。增加必要idle并调整TDO窗口后，实际约60MHz TCK下AXI SRAM读 **3.200MB/s**、写 **3.156MB/s**，超过用户给出的F103ZE 2.4MB/s参考数；这不是相同条件的跨MCU对照。25MHz仍是手册保证上限，本轮高频结果属于单板超规格研究。

最终bit按 **133.333333MHz / 7.5ns** fresh实现，setup **+0.179ns**、hold **+0.034ns**。默认XDC、verify、AGENTS及依赖文档已同步，今后无明确对照要求不退回120MHz。先前120MHz研究配对独立保留，没有冒充133MHz验收。

## 配对与时钟

最终交付：prebuilt/hpm6800-idle64-133-experimental-20261102（历史归档 `archive/main-before-formal-release-20261106:prebuilt/hpm6800-idle64-133-experimental-20261102/README.md`）。

| 文件 | SHA-256 |
|---|---|
| probe.bit | `106d579bc1b79c2b873fd1e3eb2609d468892a67613d85a6e41d4dc90c8fc177` |
| application.elf | `7692e3c62b9823f1573c9aed5b3f6a208d6466b321f1695bb55c3db2a0412aee` |

PS为O3/Thumb compact，trace/zero-idle/fixed-FCLK实验关闭，API显式上限60MHz。**133MHz实现约束不等于强制运行FCLK133MHz。** 60MHz档读回FCLK119999998Hz、TCK59999999Hz；50MHz档为FCLK99999999Hz。本报告实际时钟均由PS分频/PL寄存器计算，不是外部频率计测量。60MHz是本配对声明及本轮已测最高档，未证明物理上限。

Golden及原HPM保证配对字节不变。原1～25MHz完整分档见[R19](../hpm6800-acceptance-20261102/README.md)；新bit本轮重点验证高频、50/60MHz业务及25MHz默认档，未声称重新完成全部低频业务、ARM、ETM或QSPI冷启动验收。

## TCK/idle规律

下表为**最小已测通过idle**；25～47MHz先用原HPM配对探索，50～60MHz使用扩展idle配对，最终133约束配对重新验证高频组合。每行身份见[矩阵索引](matrix-summary.json)，混合探索图不是固定配对的性能曲线。

| 实际TCK MHz | idle | mode |
|---:|---:|---:|
| 25.000 / 27.273 | 8 | 0 |
| 28.125 | 9 | 0 |
| 30.000 / 32.143 | 10 | 0 |
| 34.615 | 11 | 0 |
| 36.000 | 12 | 17 |
| 37.500 | 11 | 17 |
| 39.130 / 40.909 | 12 | 17 |
| 42.857 | 13 | 17 |
| 45.000 | 14 | 17 |
| 47.368 | 15 | 17 |
| 50.000 | 16 | 17 |
| 56.250 | 18 | 17 |
| 60.000 | 20 | 17 |

idle与采样窗口（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/hpm6800-idle-frontier-20261102/idle-capture-map.png`）

1. **DTM等待不足。** idle8在28.125MHz出现DTMCS.dmistat=3；50MHz的15失败/16通过，56.25MHz的17失败/18通过，60MHz的19失败/20通过。低速观测DTMCS在TAP reset之前进行，随后清协议状态并核对SRAM/DPC恢复；没有复位MCU。
2. **TDO返回窗口。** 约36MHz以上，部分mode0失败而mode16/17通过，并非都带DTM BUSY。mode0是Q2/current-bit，17是Q1/previous-bit晚返回窗口，16是Q2/previous-bit。多加idle不能代替窗口调整。
3. 最小等待时间大致为 **0.30～0.33µs量级**。异步相位、取整和窗口导致阈值非严格单调，如36/37.5MHz的12/11拍；这是实测规律，不是已证明的内部DTM时钟模型。
4. **idle过大反而变慢。** 最终133配对60MHz/mode17，AHB的idle20读写3.152/3.110MB/s；24为2.988/2.974，32为2.717/2.695，64为1.972/1.981。64是配置上限，不是速度推荐值。

SRAM探索曲线（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/hpm6800-idle-frontier-20261102/sram-frontier.png`）

## 实现、瓶颈与改进空间

旧idle只有4位、最多15拍。新增feature bit5，RISC-V route[23:16]携带扩展idle，扫描计数器扩宽，有效值8～64；旧bit保留旧行为，ARM/SWD仍15。传统CFG只写4位饱和值，避免污染相邻字段。TransferConfigure仍为设置入口，Vendor13/255只读有效idle及上限。改变route后先低速prime再升频。真实生产C测试覆盖能力守卫、旧bit及ARM/SWD；RTL测试24/64拍实际扫描长度与posted值。

60MHz/idle20的AXI每字实测1.0043次扫描、66.282个移位bit，串行理想值约`60e6 / 66.282 * 4 = 3.62MB/s`，实测3.20已约88%；控制/USB排队仍有开销。继续压idle会BUSY。HSS多变量每组约n+6次扫描，单变量约1.05次；可研究减少重复SBCS检查、已验证watermark的批处理。本轮尚未实现这些方案，也没有修改HSS gap语义。

## 最终133配对：SRAM、RTT

SRAM使用512字事务、队列深32、128循环、三次中位数，十进制MB/s；每个窗口另做10秒随机/反相数据交替写读，原数据逐字节恢复。

| 60MHz/idle20/mode17窗口 | 读MB/s | 写MB/s | 压力轮数 | 每方向字节 |
|---|---:|---:|---:|---:|
| AXI 0x01240000，64KiB | 3.200 | 3.156 | 174 | 11,403,264 |
| AHB 0xf0400000，32KiB | 3.160 | 3.129 | 359 | 11,763,712 |
| AXI末4KiB 0x0127f000 | 2.494 | 2.479 | 2377 | 9,736,192 |

重接电后25MHz/idle8/mode0默认档：AHB读1.610/写1.602MB/s，10秒201轮、每方向6,586,368B，恢复通过；该诊断脚本队列深16，与上表不同。峰值与交替压力吞吐不混用。

RTT每档3×2秒，1024B chunk、RAM producer，50MHz探针侧2.4665～2.4670MB/s，60MHz2.9543～2.9553MB/s。序列逐字节核对，停止后published==received、errors=0；ILM/AHB、核心/cache恢复。原始行也保留host_MB_s，不当作GUI完整E2E。

## HSS对照superlinkPRO

只读查阅`E:/superlinkPRO`。旧JSON、报告和实际采样源码的路径/哈希见history/manifest.json（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/hpm6800-idle-frontier-20261102/history/manifest.json`），提取行见history/summary.json（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/hpm6800-idle-frontier-20261102/history/summary.json`）。

| 单变量周期 | superlinkPRO历史优化记录 | 最终133配对，60MHz/idle20 |
|---|---|---|
| 2µs | 约305.2kS/s，约39%跳采 | 三轮36.3～40.9kS/s，约91.8～92.7%跳采 |
| 3.25µs | 约302.7kS/s，约1.61%跳采 | 三轮304.45～305.25kS/s，约0.79～1.05%跳采 |
| 4µs | 约249.5kS/s，约0.192%跳采 | 3×10秒一轮跳1268点(0.0507%)，另两轮零 |
| 4.5µs | 无匹配历史行 | **222.222kS/s，3×10秒零跳采** |
| 5µs | 约199.995kS/s，约0.00275%跳采 | **200kS/s，3×10秒零跳采** |

多变量按完整变量组计数：**3u32、8u32在20µs/50k组/s和40µs/25k组/s，各3×10秒全部零跳采、errors=0、尾计数差0**。8变量50k等于400k个u32值/s，不能误标成400k组/s。历史8变量40µs/25k曾零跳采，需要当时72KiB/9×8192B主机读取窗口；旧12KiB窗口存在USB丢包，两者不能混用。

对照固定周期、变量数及旧AXI地址0x01240000，也保留AHB对照。但旧记录运行其scope ELF/变化波形，本轮为保存原程序后的静态RAM夹具、CPU暂停，因此是探针/传输比较，**不是相同目标固件及GUI的完整E2E复刻**。旧软件TCK约20.7MHz为CPU时序估计，非外部测量。

用户记得305k是对的；当前2µs极端过载确实更差。25MHz原对照每512B DATA包恰好仅1样本：PL STAMP检测名义时间间隔变化即提前封包，每包再做JTAG硬件fence，计数与源码支持短包正反馈解释。60MHz也未修复。旧scope源码为包首时间戳+值，跳拍时推进名义时间，但不会每次内部gap强制封包，两者gap封包语义不同；旧计数/USB无损不能单独证明所有内部gap均可重建。

ZL-080保持部分解决：后续研究每包fence批处理，或能表达逐样本delta/gap map的格式，同时保留时间轴与完整性。**不称250k为稳定零跳采上限，不取消gap检查制造数字。**

## 勘误、失败与验证

* ZL-078：R19原始golden-frontier-over-spec的请求26/27/28MHz，实际25.714/26.471/27.273MHz均passed=true；仅29MHz请求失败。旧报告误把整轮退出码写成逐点全失败。原JSON/提交保留，R19已更正。
* ZL-081：120MHz首次增量route在overlaps=1十余分钟不收敛，仅停止本任务Vivado；fresh120对照+.415/+.034ns通过。另做fresh133最终实现+.179/+.034ns通过，分别保存约束/日志/产物。
* ZL-083：主机08:42重启后探针供电未接。初次补测在预检PL读处AP timeout，下载在APU选择处失败，未进入新测量/加载。用户接电后同一133配对加载、物理OCM匹配，补测完成。失败日志保留，没有据此认定固件故障。
* RISC-V核心/完整流水三采样模式、24/64拍，ARM JTAG核心/完整流水三模式，packet六套、生产C八套、idle/clock/验收参数三个单测、CLI53项均通过。既有编译/ResourceWarning保留在日志。
* ZL-084：收尾修复HSS自动搜索分支未传递新增AXI/observe/idle选项；真实搜索循环模型覆盖scan/refine/verify。>15拍请求增加有效值读回守卫，旧bit不能静默降为15。本轮硬件结果均用direct分支，原执行快照保留；此主机修正不改变bit/ELF或已测数字。

raw/（历史目录：`archive/main-before-cleanup-20261105:docs/validation/hpm6800-idle-frontier-20261102/raw`，按验收索引恢复）保留逐点成功/失败及恢复，logs/（历史目录：`archive/main-before-cleanup-20261105:docs/validation/hpm6800-idle-frontier-20261102/logs`，按验收索引恢复）保留构建/运行/回归，drivers/（历史目录：`archive/main-before-cleanup-20261105:docs/validation/hpm6800-idle-frontier-20261102/drivers`，按验收索引恢复）保留执行脚本快照，build-inputs/（历史目录：`archive/main-before-cleanup-20261105:docs/validation/hpm6800-idle-frontier-20261102/build-inputs`，按验收索引恢复）保留精确输入字节。用户原SRAM备份只在本地build，没有纳入Git。构建stamp哈希为工作树原始字节，快照避免LF/CRLF歧义；manifest另定位可编辑源码提交。

```powershell
# 声明bit/ELF身份不会加载；先显式RAM加载，再独立核对。不会写目标Flash/QSPI。
python -X utf8 tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/hpm6800-idle64-133-experimental-20261102/application.elf prebuilt/hpm6800-idle64-133-experimental-20261102/probe.bit prebuilt/hpm6800-idle64-133-experimental-20261102/ps7_init.tcl
python -X utf8 tools/verify_probe_ocm_code.py --elf prebuilt/hpm6800-idle64-133-experimental-20261102/application.elf --out-dir build/hpm133-new-identity
python -X utf8 tools/characterize_hpm6800_idle.py --bit prebuilt/hpm6800-idle64-133-experimental-20261102/probe.bit --elf prebuilt/hpm6800-idle64-133-experimental-20261102/application.elf --out build/hpm133-new-idle --speeds 50000000,56250000,60000000 --idles 15,16,17,18,19,20,24,64 --modes 17 --loops 128 --repeats 3
python -X utf8 tools/validate_hpm6800_streams.py --stage hss --bit prebuilt/hpm6800-idle64-133-experimental-20261102/probe.bit --elf prebuilt/hpm6800-idle64-133-experimental-20261102/application.elf --out build/hpm133-new-hss --speeds 60000000 --periods 108,120 --variables 1 --seconds 10 --repeats 3 --idle 20 --mode 17 --hss-base 0x0123ff00 --observe-scans
```

PL fresh命令与版本见logs/fpga-133.log；约束/时序报告、PS选项随prebuilt保存。PS构建使用`tools/build_xusbps_daplink.py --compact-code --max-swclk-hz 60000000 --out build/hpm6800-idle-frontier-20261102/ps-133 --timing build/fpga_dma_global/verified_clock.json`。

## 最后板上状态（时间快照）

**2026-11-02 08:55:21 CST**，见raw/final-state.json（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/hpm6800-idle-frontier-20261102/raw/final-state.json`）：最终133约束配对仍在板上，TCK24999999.5Hz/FCLK49999999Hz、mode0、有效idle8，DMSTATUS=0x430ca2、目标运行，RTT/HSS、packet/采集引擎空闲。随后identity-final-133用物理MEM-AP0核对75,692B可执行代码全匹配。各轮SRAM/ILM、核心/cache及目标时钟控制恢复通过。本轮未改目标PLL/AHB/APB，未写目标Flash/QSPI，未复位目标MCU；无本任务后台采集/Vivado进程，共享hw_server保留。

源码、配对及板测证据提交：`36875ef0903640fa479256344f7b15d04aca1efa`。本次身份补记不重建、不重载；见[source-revision.json](source-revision.json)。
