# 极限 SWD 与 Golden 50/60 MHz 性能复核

本轮接续 `ec6d028` 交接，使用已经纳入 Git 的三个 bit/ELF 配对，未修改或重建 RTL、Zynq 固件、目标 Flash 或 QSPI。实验配对继续 `accepted=false`，没有替代 release 或 Golden。新的主机验证驱动位于 `tools/validate_fclk_performance.py`、`tools/validate_fclk_edge_cases.py` 和 `tools/run_fclk_comparison.py`。

用户补充的业务边界：ETM 模式仅使用低频 SWD 做配置（例如10 MHz），不要求高频 ETM 与 RTT 并发。本文高频 ETM 输出实验仅保留为范围外诊断，不作为产品退化判据。补充验收重点是 RTT/J-Scope 运行时插入普通调试命令、暂停/单步/恢复是否卡死。

## 测试条件与身份

固定 133.333 MHz 实验仅支持 SWD，可实现的最高 SWCLK 是 66,666,666 Hz；请求 50/60 MHz 会降到 33.333 MHz，不能用它进行正常 50/60 MHz 对照。本轮极限测试用精确 Hz 请求。Golden/release 的普通 DAP 策略在 50 MHz 时使用约 100 MHz FCLK，60 MHz 时使用约 120 MHz FCLK。没有重新探索已失败的 150 MHz FCLK。

目标是 STM32F103ZE、CPUID `0x411fc231`、device ID `0x10036414`。Flash 的两个加载段已与 `prebuilt/golden/f103ze-cdc48.elf` 逐字节比对；RCC_CFGR `0x51040a`，目标 HCLK 48 MHz，未重置/重刷目标、未改变目标频率。所有频率来自 PS_REF、PLL、来源与分频寄存器计算，未做外部频率计校准。

| 配对 | bit SHA-256 | ELF SHA-256 |
|---|---|---|
| `prebuilt/golden/` | `1da17cb60175bbc2b7abd647770c7053bd7b7097e0d38aa819fb89678d564473` | `e977914c2924ab4cac13f4075de0a5108d1e2e8cf48966fb8fbdea3a358e0b2c` |
| `prebuilt/fclk133-release-20261101/` | `af1031d3caa0d7bd3b6adffa911d26efdab9e0bfb5223fb18f70dabb70ebeeed` | `2137f7d0f507c08574f36223130103c0710645cbfdefb5c1d8c8efb0cfb990a0` |
| `prebuilt/fclk133-swd-fixed-test-20261101/` | `ef9252c87529078c1d18ea1c05c3a19a333a20e1eee16205646b88518899ebe7` | `b7ffe71c0edc5b8ccbd04adb14a0e43fdb7e67082d1ee00655066ee2ddd0853f` |

源码、构建参数与既有 STA 以各配对 manifest 及 [上一轮交接](../fclk-resume-20261101/HANDOFF-20261101.md) 为准。release/实验 RTL 来自 `e749c42`，PS 分别来自 `0118b16`/`08a63b2`；Golden 来源由其 `golden-release.json` 记录。本轮重新加载前核对文件哈希，加载后独立读回 OCM 可执行段。bit 身份依据文件哈希、下载日志和 PL 特征，不声称回读完整 FPGA 配置得到 SHA。

## 测量方法

- SRAM：相同 512 words、depth 32、256 blocks、三次重复；每档附加 10 秒交替读写，数据逐字节验证。报告有效 payload 十进制 MB/s 中位数。测试窗口 `0x20008000` 起 4096 字节，完整备份和恢复。
- RTT：同一 RAM producer、1024 字节块、三次 2 秒，检查递增序列和最终发布/接收总量，完整恢复 20 KiB SRAM、核心寄存器与目标运行/暂停状态。主表使用探针 payload 计数窗口中位数，原始报告同时保留主机接收速率。
- HSS：单 u32，24 MHz 时间基准，先试公开接口最小周期 24 ticks，再二分并用三次 2 秒验证零跳采边界。过载结果、失败的验证窗口与重复 STAT 均保留；不把一次零跳采当作稳定上限。
- 每个服务记录实际 FCLK/链路频率，50/60 MHz 对照有频率一致性断言。JTAG 仅临时开放 AFIO SWJ_CFG，fixture 显式恢复目标源码中的 SWJ_NOJTAG=2、APB2ENR 和运行/暂停状态。

## 固定 FCLK133 的极限 SWD

| 实际 SWCLK | SRAM 读 MB/s | SRAM 写 MB/s | RTT MB/s，原始 ETM 关闭 | HSS 三次零跳采 |
|---|---:|---:|---:|---:|
| 33.333 MHz | 2.718961 | 2.661139 | 2.591363 | 685714 Hz，35 ticks |
| 66.667 MHz | 5.343297 | 5.249100 | 5.145180 | 1 MHz，24 ticks |

66.667 MHz 另做 60.101655 秒 SRAM 交替读写，303 轮、零数据错误，三重复读/写 5.360517/5.252687 MB/s，备份恢复匹配。本轮最高通过频率仅适用于这块 F103、接线、目标状态及测试时长；没有温压/多板/长时间可靠性结论。HSS 已达到公开 API 的最小周期，不声称测得硬件无限制采样上限。

## 50/60 MHz 对照

以下各项使用原始 ETM 关闭状态。速率是三重复中位数；持续测试样本范围重叠，未见实质吞吐恶化，但没有做千分量级统计等效性认证。

| 链路 | Golden SRAM读/写 MB/s | release SRAM读/写 MB/s | Golden/release RTT MB/s | 吞吐中位数最大下降 |
|---|---:|---:|---:|---:|
| SWD50 | 4.049813 / 3.982393 | 4.047412 / 3.982236 | 3.883157 / 3.881358 | 0.0593% |
| SWD60 | 4.834781 / 4.747919 | 4.828845 / 4.749041 | 4.645973 / 4.644119 | 0.1228% |
| JTAG50 | 2.023488 / 2.007666 | 2.023173 / 2.006498 | 1.948939 / 1.947819 | 0.0582% |
| JTAG60 | 2.421164 / 2.398020 | 2.419352 / 2.396754 | 2.320109 / 2.319314 | 0.0748% |

每档 SRAM 三重复及10秒持续校验通过，RTT 三次2秒序列/总量校验通过。HSS：SWD60 双方均24 ticks/1 MHz三次零跳采；JTAG50 双方均89 ticks/269662.921Hz；JTAG60 双方均74 ticks/324324.324Hz。SWD50 的 Golden 在24 ticks三轮验证中有一轮跳3064点，25 ticks/960kHz三次通过；release 在24 ticks三次通过。边界存在运行间波动，不把这一个tick的差别宣布为确定性能提升。

旧记录的 JTAG60 RTT 失败被保留。本轮在 ETM 完全关闭状态下 Golden/release JTAG60 均通过，因此旧结论的现场状态不能省略。

## RTT/J-Scope 插入调试命令

入口 `tools/validate_stream_debug_interleave.py`，同一RAM-only producer、完整20KiB SRAM与核心寄存器恢复。覆盖每个速率的 RTT、8×u32/1kHz J-Scope、1×u32/1MHz高负载J-Scope。每轮约2秒密集请求，每个burst有DPID/CPUID/DHCSR、独立SRAM读写、4次不重写TAR的读和8个流水读请求（23条DAP请求），随后三轮halt/读取及写回R12/单步/resume，再观察流继续前进。HSS高负载允许抢占导致的跳采，显式检查DEF seq0、数据、帧序列、最终样本总量及DAP_yields；RTT检查所有发布字节与递增序列。

普通DAP插入与完整SWJ重新初始化分开：后者包含线复位和一系列连接初始化命令，不能用其失败替代普通调试读写结论。初版测试把全局整数周期相位当作跨DAP接管的不变量，因固件重启计时而中止；原失败记录保留。最终reader继续严格校验数据、序列、计数，并独立记录计时重启和时间戳顺序。

目前release SWD/JTAG50、60全部完成普通调试命令与三轮暂停/单步/恢复，未卡死、数据和总量匹配。**这不是J-Scope采样时序完整通过：8变量配置1kHz时，SWD50调试期间有效采样率3756.575Hz，SWD60为1220.898Hz，结束后约1000.09Hz；时间戳未倒退。** `probe_after_dap()`每次调用`sampler_arm()`，后者通过`W(7, now())`重启采样计时，与观察到的相位/采样密度变化相符。根因和修复仍需单独验证，不能以“没有挂死”掩盖此行为。

最终共30个服务/速率/负载条件（Golden/release各12个、fixed各两个速率共6个），4508轮混合请求、103684条burst内DAP请求、90轮暂停/单步/恢复全部完成；其他准备、控制及校验请求未计入103684。每个结果均校验SRAM、核心寄存器和运行状态恢复。HSS共20个条件均有首DEF、数据/总量匹配、无时间戳倒退、无重复STAT。该结果不等于此前Web跨功能切换缺DEF问题已关闭。

| 配对/链路 | 测试频率 | 所有负载中最慢一轮23条DAP请求 |
|---|---|---:|
| release SWD | 50 / 60 MHz | 10.392 / 21.976 ms |
| release JTAG | 50 / 60 MHz | 29.803 / 41.268 ms |
| Golden SWD | 50 / 60 MHz | 18.602 / 19.995 ms |
| Golden JTAG | 50 / 60 MHz | 29.785 / 41.267 ms |
| fixed SWD | 33.333 / 66.667 MHz | 9.507 / 6.971 ms |

Golden同样出现采样密度改变：8变量1kHz在SWD50/60密集调试期间为3167.620/1222.003Hz；不是新版新增。release JTAG50/60同条件约971.815/643.198Hz，也体现调试抢占带宽。暂停采样和时间戳重启必须对上层如实表达，不能把全部输出点仍解释为均匀1kHz。

## 低频 SWD 配置 ETM

按用户补充范围，release使用实际SWCLK9999999.833Hz、FCLK119999998Hz进行配置与100ms DDR/USB采集。完成硬件窗口0.100000001秒，formatter1909699字节、解复用ETM452450字节；丢帧/解析/IDELAY参考失锁/writer错误均0，完整下载，ETM/核心调试相关配置及RCC恢复。原始结果保留3字节末尾不完整formatter边界（tailAmbiguous=true），未把该短测称为全指令解码验收，也未在本轮重做133MHz的1/2秒全量验收。

## 已复现与仍遗留的问题

### 33.333 MHz 标准占空比采样配置

同一固定 FCLK、目标与 ETM 状态，仅改变 phase/boundary：Q2/boundary1 的 128 次 DPID + 128 次 CPUID 通过；Q2/boundary0、Q1/boundary0、Q1/boundary1 均在首个 DPID 返回异常状态。每个条件之间恢复 DAP 并以安全速率重新建立连接。该受控结果支持当前实验 profile 的选择，但没有改变普通 release 策略，也不把先前不同现场状态的故障一概宣布修复。

### 范围外诊断：高频 ETM 输出并发 RTT

接手时 ETMCR 实际为 `0x411`、DBG_CR=0，ETM 处于编程/掉电状态。旧报告故障时是 ETMCR=`0x810`；两种现场状态必须分开。

本轮显式配置与原板测相同的 ETMv3 / 4 位并行 TPIU：ETMCR=`0x810`、ETMSR 编程状态=0、TRACEID=2、TEEVR=`0x6f`、DBG_CR=`0xe0`。固定133/33.333 MHz 下 RTT 三轮通过；固定133/66.667 MHz 下失败。保存失败并重新加载同一探针配对后，ETM 编程暂停至 `0xC10`，66.667 MHz 三轮通过。trace 配置及锁状态均恢复原值。

这里检验的是目标 ETM 输出与 RTT 并存，未同时启动探针 DDR 采集，不能扩展成 ETM+DDR+RTT 全链路验收。尚未定位物理信号/目标/探针内部机制。

Golden额外对照：SWD50在`0x810`/`0xC10`均三轮通过；SWD60在`0x810`失败，重新加载同一配对后`0xC10`三轮通过。用户明确不要求该高频ETM组合，未继续对release补做这一范围外矩阵。

### RTT 出错后的服务清理

66.667 MHz ETM 并发故障后，SRAM和核心寄存器成功恢复，但后续 RTT configure 返回 `-7`。STOP、DAP EP0 恢复、SET_CONFIGURATION=1 在本次现场未清除该状态。不能把这次配置拒绝当作“暂停 ETM 后仍有吞吐故障”。新驱动保留原失败，再重新加载同一配对、核对 OCM 后进行下一条件；这是测试隔离方法，不是固件修复。

普通业务补测中，release RTT/SWD50运行时执行完整SWJ重新初始化，DPID返回`05 00 07`，后续RTT配置返回`-7`，同样需重新加载清理。这一项不同于上面的范围外ETM高频组合，属于调试重连/服务切换的待处理边界。失败时所有备份和目标运行状态均恢复。

Golden在普通混合请求与三轮暂停/单步/恢复均已通过后，追加完整SWJ重连，同样返回`05 00 07`。因此这是双方共有的边界，不能归为release新增退化。当前可复测规避方式是先STOP流，再完整SWJ初始化；每个普通测试条件的流停止后初始化均成功。服务运行中只插入已建立连接上的调试请求，与重新初始化整条链路的能力不同。

### RAM加载时偶发启动退出

从Golden切换release的第一次下载成功、OCM代码匹配，FCLK初始133333332Hz，但USB设备不存在，加载日志PC=`0x60a8`，ELF定位到`_exit`。重新加载相同bit/ELF后PC=`0xc19e`、定位到`kick`，USB恢复，随后性能测试通过。不能把该现象称为纯枚举等待，也不能仅凭这两次加载推断失败概率或断言DMA/USB具体根因；未覆盖冷启动/QSPI。两个加载记录均保留。

### 其他未关闭事项

- HSS 跨功能切换偶发缺首 DEF：此前用户暂停的独立问题仍为 DEFERRED。当前吞吐 reader 校验 DATA/计数/时间线，不能据此宣称 Web 连续切换首 DEF 已修复；原证据见 `../combined-etm-web-20261031/deferred-hss/issue.json`。
- 五个双向 GPIO/SWDIO 缺外部 delay、既有 CDC 审查项仍在。本轮未重做或放松约束，STA 通过范围不等于全接口形式签核。
- 150 MHz FCLK 既有时序失败未关闭；保持原决策，不盲换种子或修改 PLL。

## 复测与证据

正常比较入口：`python tools/run_fclk_comparison.py --out <新的独立输出目录>`。固定实验需先用 `validate_fclk_performance.py --pair fixed --phase load` 加载，再使用同目录 `--phase swd`；边界实验用 `validate_fclk_edge_cases.py`。所有入口直接访问硬件，不能并行运行；输出应使用新目录，不能覆盖原始失败记录。

本地完整证据位于 `build/performance-limits-20261101/`。Git 归档保留结果、实际命令、加载/OCM核对、失败日志、驱动快照和逐文件 SHA-256；原 SRAM 备份和 OCM 二进制保留本机。Golden 初次加载后的预检曾误读不存在的 DDR 寄存器，未进入性能计时；修正为按 feature 位读寄存器后在新 `ab/` 目录重新加载、核对并测试。该预检错误不算板卡性能失败。

## 收尾板上状态

2026-11-01 **19:30:57（上海）**最后快照：已重新加载并核对`prebuilt/fclk133-release-20261101/`，不是实验配对。普通DAP安全档实际FCLK119999998Hz、SWCLK999999.983Hz，IO PLL来源；FCLK1/CPU/DDR/USB/PLL保护寄存器保持原值。采集、packet、DDR writer和CDMA均观察为空闲；目标DHCSR=`0x01010001`，未halt；ETMCR=`0x411`、锁状态`0x3`恢复。最终再次逐段核对目标Flash身份。无遗留测试/构建/读取线程，只有原有共享hw_server PID38356。未推送。

`summary.json`、`interleave-summary.json`是可读汇总，`raw/`为逐次原始报告与失败记录，`evidence.json`给出归档文件/本地未归档二进制的SHA-256和源文件快照。报告中的passed按各脚本的限定范围解读，尤其插入命令测试的passed只表示响应/流/数据通过，不代表J-Scope全局采样周期保持不变。
