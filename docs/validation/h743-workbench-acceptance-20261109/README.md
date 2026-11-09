# H743 Web工作台、JTAG与关键性能验收（2026-11-09）

本轮参考 superlinkPRO 的 F103ZE Web 验收矩阵，验证本工程 H743 的调试、烧录、RTT、J-Scope 与 ETM。关键 SRAM/RTT 吞吐与匹配历史基线的最大偏差为 **0.457%**，未出现超过 2% 的退化。发现并修复 ARM/JTAG 导入与身份检查、OpenOCD 断点登记、H7 烧录工作区、ETMv4 寄存器地址和协议标记等问题。临界跳拍、主机执行环境及 Golden 示例命令边界另行保留，不作为全通过。

## 身份、隔离与比较方法

- 源码起点 `388c3fb006bdf3b495f45481bf996b7c7e0cec7c`；本报告与对应修复一起提交。原有问题表 ZL-170 的未提交新增和已有 `build/` 未纳入本任务。
- 开始时 Zynq 未配置、探针 USB 不存在；确认没有板卡使用者后，只经 JTAG/RAM 加载正式配对。没有写 Zynq QSPI，没有重建或替换 PL/PS。开始与结束均用物理 MEM-AP0 独立核对 85,844 字节运行代码。
- bit：`prebuilt/release-20261106/probe.bit`，SHA-256 `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6`。
- Zynq ELF：`prebuilt/release-20261106/application.elf`，SHA-256 `5895eeb0e79a3681a6b3b966dbea4c82ebfcd01ea7553e094d8a61ed2cf89802`。
- MCU：CPUID `0x411fc271`，DEV/REV `0x20036450`；SWD DPIDR `0x6ba02477`，JTAG CPU TAP `0x6ba00477`、boundary TAP `0x06450041`，IR 长度 4/5。
- 目标初始 Flash 匹配 `prebuilt/targets/stm32h743-cdc-trace-20261101/cpu60-trace20/fw.elf`，该 ELF SHA-256 `246640bf79c8b1e568441a286812326dfb0ae68a0df061a0c023262c07cf221b`。另临时烧录现有 CPU480/HCLK240 配置测速，最后恢复原始完整 Flash。两个配置均 I-cache 开、D-cache 关。
- 脚本、原 Flash/RAM 备份、串口记录、运行令牌、服务数据和诊断构建均置于唯一临时目录；结论归档为本目录 [evidence.json](evidence.json)，不保留原 Flash 内容或完整采集/构建产物。临时路径在证据中标为已删除。
- 50/60MHz 对应实际 FCLK 约 100/120MHz、SWCLK/TCK 约 50/60MHz；由物理 MEM-AP0 读回 PLL/分频计算，**不是外部频率计测量**。没有使用请求60而实际33.333MHz的固定133实验包。
- 历史条件见 [2026-11-01综合报告](../h743-comprehensive-20261101/README.md)。SRAM 固定 512 words、depth32、loops64，三次中位数，另每点10秒交替读写。该脚本使用循环1KiB TAR窗口，不能冒称完整线性SRAM吞吐。RTT 固定 AXI RAM producer、8192B环、1024B块、三次2秒，另 CPU480 每点60秒。每次均核对数据/发布量及 RAM、核心寄存器恢复。

## 关键性能

吞吐单位为十进制 MB/s。CPU60/HCLK60 与 CPU480/HCLK240 分开比较，不用高CPU结果替代默认 ETM 配置。

| 配置 | 链路 | MHz | SRAM读 | SRAM写 | RTT→CDC |
|---|---|---:|---:|---:|---:|
| CPU60/HCLK60 | SWD | 50 | 4.04257 | 3.97748 | 0.73036 |
| CPU60/HCLK60 | SWD | 60 | 4.82933 | 4.51888 | 0.75286 |
| CPU60/HCLK60 | JTAG | 50 | 2.02000 | 2.00586 | 0.65714 |
| CPU60/HCLK60 | JTAG | 60 | 2.41624 | 2.39247 | 0.67152 |
| CPU480/HCLK240 | SWD | 50 | 4.03873 | 3.97117 | 3.87472 |
| CPU480/HCLK240 | SWD | 60 | 4.81189 | 4.73247 | 3.65853 |
| CPU480/HCLK240 | JTAG | 50 | 3.96826 | 2.00514 | 1.94712 |
| CPU480/HCLK240 | JTAG | 60 | 2.41869 | 2.39513 | 2.32071 |

CPU60 最大绝对偏差约0.258%；CPU480 最大绝对偏差0.457%。所有10秒 SRAM 稳态窗口零读写错误；所有 RTT 发布/接收序号逐值一致，停止后发布总量全部收齐。CPU480 四个60秒 RTT 窗口同样零错误、无序号缺口。

JTAG50 的 SRAM 读快于 JTAG60、SWD50 的 RTT 快于 SWD60，是 ZL-067 已有的非单调现象，本轮相同条件再次复现且与各自历史值相差不足0.5%。没有用改目标PLL、重刷或降频来掩盖差异；具体目标等待/时序组合根因仍未关闭。

### J-Scope低于0.1%跳点率

下表为原生 HSS：固定24MHz时间基准，1/3/8个u32，短窗口搜索和三次2秒确认后，各做一次60秒复核。表中为组/秒，单变量时等于 samples/s；逐值、序号、时间戳、停止尾计数均核对，USB丢样与读错误为零。不是任意时长的绝对上限。

| 链路 | MHz | 变量数 | 周期 ticks | 实得组/秒 | 60秒跳点率 |
|---|---:|---:|---:|---:|---:|
| SWD | 50 | 1 | 24 | 999970.53 | 0.0029519% |
| SWD | 50 | 3 | 122 | 196721.32 | 0.0000000% |
| SWD | 50 | 8 | 238 | 100840.34 | 0.0000000% |
| SWD | 60 | 1 | 24 | 999941.86 | 0.0058155% |
| SWD | 60 | 3 | 102 | 235294.13 | 0.0000000% |
| SWD | 60 | 8 | 196 | 122448.77 | 0.0001633% |
| JTAG | 50 | 1 | 89 | 269662.93 | 0.0000000% |
| JTAG | 50 | 3 | 293 | 81911.27 | 0.0000000% |
| JTAG | 50 | 8 | 529 | 45368.62 | 0.0000000% |
| JTAG | 60 | 1 | 74 | 324324.32 | 0.0000051% |
| JTAG | 60 | 3 | 244 | 98360.65 | 0.0000000% |
| JTAG | 60 | 8 | 441 | 54421.77 | 0.0000000% |

SWD50/8变量的235ticks短窗通过，60秒却跳0.2139515%，保留失败；238ticks长窗为0。计数定位到探针采样deadline跳拍，USB与读错误为0，但引起临界延迟的更细机制仍待定位，沿用 ZL-070，不能宣称根治。单变量 SWD50 的1MHz比历史960k高4.17%，本轮三次2秒为0、60秒为0.0029519%；旧表是短窗“严格零跳拍”的已验证边界，本次要求为“<0.1%”，不据此宣称确定硬件性能提升。其余单变量匹配边界在2%内。

另在 CPU480 下用运行中的 RAM 自增计数器复核四种链路，全部相邻值有序、变化与最终样本量正确。初版临时驱动漏改 F103 的 PC，产生 IBUSERR/IPSR3，故障与恢复单独保留；修正 AXI 入口后四组均通过。这是测试驱动错误，未作为探针故障。

Web J-Scope 在 SWD50/60 下实采8种标量（i8/u8/i16/u16/i32/u32/f32/f64，含非对齐地址），CSV每行逐值正确；真实JSP在页面仅选一路时重放恢复8路文件定义，触发定位通过。10ms自动切换 WASM，51个真实样本、约100Hz、主机错拍/读错0。Web最小周期为2µs，表中原生1MHz不能冒充Web最小周期验收。

## 功能验收范围

| 对照项 | 本轮实测 | 结果及边界 |
|---|---|---|
| F01 枚举/CFG/身份 | 冻结原版与隔离候选，SWD与双TAP ARM/JTAG | 原版CFG拒绝及DPIDR误判复现；修正后连通、MEM-AP RTT与Flash可复用CFG |
| F02 复位 | NRST三轮、软件reset-halt/run三轮 | MCU PINRST标志三次确认；reset-halt均停在复位向量，结束恢复运行 |
| F03 SRAM/核心寄存器 | 两CPU配置、两链路50/60；Web非对齐1/2/4字节及跨1KiB访问、R12改写恢复 | 数据及恢复通过；完整Flash最终另行独立核对 |
| F04 调试 | JTAG100次重复暂停、40轮停/走/指令单步，四个硬件断点、回溯与源码行跳出，DWT读/写/读写观察点 | 命中正确，全部8个FPB比较器清零；最终版本另在JTAG50确认后台登记与硬件回读一致 |
| F05 烧录 | SWD10的ELF/HEX/BIN，另JTAG10的原128KiB扇区回写 | 读回通过；只写bank1 sector0，bank2未做擦写；完整2MiB原始哈希最终一致 |
| F06 RTT Viewer | SWD50/60、导入CFG的JTAG50，静态RAM控制块 | 上行两次跨环、暂停显示仍收数、ANSI/文本/HEX切换、8B下行跨环、原始4480B导出全部逐字节一致；不把静态夹具结果当持续吞吐 |
| F07 RTT→CDC | 两CPU/两链路50/60，真实COM52、连续自增RAM producer | 三次2秒及CPU480四组60秒逐值/总量通过；此项性能走原生工具，未冒称Web转发页持续文件记录验收 |
| F08 J-Scope | 原生1/3/8变量边界和动态计数器；Web混合类型/CSV/JSP/触发/WASM | 通过已列工作点；临界失败保留ZL-070 |
| F09 接管/释放 | 各页正常停止/断开、ETM浏览器→本地采集→浏览器恢复 | 探针最终无占用；未进行拔USB中断或所有热状态自动接管故障注入 |
| F10 恢复 | 原始2MiB Flash、临时RAM/FPB/DEMCR/CCR/VTOR、NRST、CDC和PLL | 独立读回与最终运行确认通过 |
| F12 ETM | CPU60/HCLK60/TRACE20，SWD10配置；四个窗口各3轮，Web联动1秒、分析与记录包回放 | 完整窗口与质量通过；ETM控制仍按产品规定低频SWD，不宣称JTAG配置ETM或高频ETM+RTT并发验收 |

ARM RTT 的 MEM-AP 模式还在显式启用一个FPB比较器的暂停现场中，核对 DEMCR、ITM 与全部FPB前后一致（ZL-175的H743范围）。RP2350等其他板型不据此关闭。

## ETM质量与分阶段时间

原生CLI使用真实4ms请求周期的CRC/序号CDC回显。硬件arm时间括号扣除边缘后，10/200/500/1000ms每组均证明回显在硬件窗口内；12轮 requestedWindowComplete=true，frameDrops/parserErrors/readyLosses/writerError=0，解码packetIssues=0。NoSync开始边界、未知执行条件、未成立路径与formatter非整帧尾部仍保留，不把包错误0当完整逐指令证明。

| 硬件窗口 | 三次完整CLI秒数 | 保守窗口内回显次数 |
|---|---|---|
| 10ms | 3.646 / 3.105 / 3.184 | 1 / 1 / 1 |
| 200ms | 4.255 / 4.594 / 4.190 | 36 / 37 / 37 |
| 500ms | 5.531 / 5.836 / 6.000 | 106 / 106 / 105 |
| 1000ms | 9.202 / 10.609 / 8.465 | 224 / 221 / 220 |

1秒CLI中位数9.202s，历史同口径14.030s；当前解码/建库中位数5.011s，历史10.303s，差异集中在主机离线阶段。当前每轮约1835～1837万路径记录，prepared replay约62MB，原生构建/索引阶段详见evidence；硬件窗口仍是1秒。该变化跨越主机实现与临时盘位置，不能据此声称硬件吞吐提升，也不是本次仅改协议字段带来的算法加速。

Web普通联动按钮1秒捕获：18,340,417路径、2,017,583包，packetIssues=0；包含脚本轮询的墙钟约10.997s，不能直接与原生CLI启动边界混比。记录再次打开，读者准备121.2ms、绘制21.4ms、总142.7ms；这只是浏览已保存记录的首屏。六个分析页、#100～2000区间、历史导航、HTML/SVG火焰图均通过。完整.etmrecord约27.3MB，经浏览器文件选择器导入，capture/ETM/ELF哈希和summary一致，重开约1.623s；CLI页面上传24MiB上限未绕过。

## 按优先级的问题、复现与修复

| 编号 / 优先级 | 文件与复现 | 原因 / 处理 / 验证 |
|---|---|---|
| ZL-188 / P1 | `web/app/dbg/openocd-cfg.js`、`web/app/core/openocd-probe.js`；导入含cortex_m、transport jtag及H743双TAP的CFG | 原版先拒绝ARM/JTAG，放开后又用SWD DPIDR判断JTAG身份。允许ARM两种传输，并按选中TAP确认ID。真实JTAG调试/RTT/Flash与Wasm配置回归通过 |
| ZL-189 / P1 | `web/app/dbg/session.js`；原逻辑直接写FPB后，OpenOCD `bp`登记表为空 | 与OpenOCD断点所有权不一致，源码确认会影响M7“异常+断点同时暂停”的勘误处理。普通HAL_GetTick原版本来就能停；早期未命中也含未执行地址，不作为勘误复现。候选统一bp/rbp登记并核对列表与实际比较器；常规板验、失败清理重试模型通过，异常交叠专项尚未触发 |
| ZL-190 / P2 | `web/app/core/openocd-profile.js`、`web/app/flash/openocd-program.js`；H743/10MHz烧同一31,756B ELF | 无工作区回退逐字写，约83.005s。补64KiB AXI工作区后5.412s；只依赖backend backup=1又遗留末尾4B常量，主机独立备份/恢复/读回后完整65536B一致，BIN约6.969s、JTAG原扇区约6.769s。错误路径与短备份拒绝有离线覆盖 |
| ZL-191 / P1 | `tools/h743_trace_capture.py`、`etm-service/web/app/target.js`；复位后第一次原生ETM结束恢复 | 误用ETM+0x310/314（电源控制/带清除副作用的电源状态）代替OSLAR/OSLSR的0x300/304，假锁状态无法恢复。两端改正确地址，12轮原生及Web恢复通过；H743实际OSLSR=0。并修正帮助中的20MHz默认基线 |
| ZL-192 / P2 | 原生主机工具执行环境；同SHA的etm_framed从工程/安装目录运行，向本次临时目录创建输出失败 | 进程令牌实测原文件启动为Low完整性(0x1000)，同字节临时副本为High(0x3000)，原文件继承Low标签。完整性写入边界是本次拒绝的已定位原因，未修改ACL/安全标签。临时副本的解帧/建库/导出通过；诊断重建物全部丢弃，没有把重建当二进制修复 |
| ZL-193 / P1 | `etm-service/web/app/target.js`、`etm-service/tools/decode_trace.py`；Web H743普通联动完成采集后解码报缺protocol | Wasm迁移/原生构建契约残留：旧Python默认v4，H7回读未显式标记，C++要求protocol。前端标记ETMv4，输入正规化补齐历史默认。新Web记录与旧失败记录重新解码、完整包重导入通过，配置严格校验未放宽 |
| ZL-070 / P2 | 原生HSS，SWD50/8×u32/235ticks长测 | 短窗零跳，60秒0.2139515%。238ticks复核0；精确跳拍来自采样deadline，进一步延迟机制仍待定位，保留旧编号及失败，不声称固件已修 |
| ZL-194 / P3 | `firmware/target/stm32h743_cdc_trace/src/main.c:242,294,470`；默认echo开时发PING/INFO，或单次写入两条命令 | Golden示例先异步发送回显，再发回复；唯一TX槽busy即丢，回复可能消失，且handle_command把整包当一条命令。独立单命令、ECHO off后PONG/INFO正常，再ECHO on并确认原文回显。已定位、未改Golden；原始Flash完整恢复 |

寄存器地址核对来源：[Arm ETM-M7 TRM](https://documentation-service.arm.com/static/5e906dfe8259fe2368e2ac54)，配合本轮0x300/304及0x310/314的独立板上读写对照；不是靠重置清掉失败后宣称修复。

## 离线检查、上板待补与最终交接

- 最终Web自测152/152、CLI自测65/65、协议契约2/2、159个模块语法和共享驱动一致性检查通过。断点后台登记/部分清理失败重试、ARM/JTAG Wasm配置、TAP身份选择和H7工作区恢复错误路径均有回归。
- 仍需专项上板：ZL-189的M7异常/断点交叠；ZL-070更长窗口及临界延迟归因。ZL-067非单调现象保留，未把相同历史表现当新增性能退化。真实拔插/故障恢复、RTT转发页持续文件记录/热状态START未在本轮独立覆盖；既有ZL-140/177不因此关闭。
- RV32/HPM的ZL-182/183/184，以及ZL-175中RP2350范围，本轮没有相应目标，不作验收结论。JTAG1/10MHz启动HSS的既有FCLK<24MHz边界、暂停的高频ETM研究没有重启。
- 最终H743为原CPU/HCLK60MHz、TRACECLK20MHz配置，完整2MiB Flash SHA-256 `f4cbd9f002921026f7f1036a7743ed2bb3832f4a9e54d4f394045b1ed05a2b82` 与测试前相同。临时AXI/DTCM及工作区均在复位前逐字节恢复；复位后允许固件正常重新初始化运行内存，不把旧USB运行结构覆盖回运行中的目标。
- 最终DHCSR `0x01010000`，运行且C_DEBUGEN=0；FPB/DEMCR/CCR/VTOR与原快照一致，CFSR/HFSR=0，ETM PRGCTLR和ETF CTL=0，RTT/HSS/DDR均非活动。单独发送PING/INFO得到PONG、sysclk=60000000Hz、hclk=60000000Hz、clk_err=0，echo已恢复。
- 最终探针物理读回FCLK约119.999998MHz、SWCLK约9.999999833MHz，JTAG采样模式0，RISC-V SBA关。正式bit/ELF保持RAM加载状态，不等同QSPI冷启动验收。
- 关闭本任务页面及服务，只回收本任务创建且无外部连接的hw_server；原始工程无关修改、build/dist用户数据均保留。1497个临时文件（约875MB）所在的两个测试目录已移入Windows回收站，原路径不存在，详见 [cleanup.json](cleanup.json)；没有永久清空回收站。最终程序包的版本、哈希与验证结果见 [delivery.json](delivery.json)。

## EXE 与分发 ZIP

`8afebc9b` 修复了 ZL-192 在安装目录中的触发条件。打包时为启动器及六个原生辅助 EXE 设置标准桌面完整性标签。原安装版的同一解帧输入在工程外创建目录失败，新候选、固定安装版和 ZIP 解压版均通过。ZIP 解压使用系统临时目录。旧安装版失败记录见 [delivery-native-before.json](delivery-native-before.json)。

安装版与解压版均核对了 1816 个程序文件的 SHA-256，F103ZE 与 H743 离线记录的解码、索引、查询与 SVG/HTML 导出通过。两组记录的包错误为零，Web 与冻结 CLI 的 HTML 一致。固定安装目录的 49 个用户数据文件按路径和内容计算的哈希与更新前一致。ZIP 包含程序目录和交付清单，离线验证目录已回收。具体身份和测试结果见 [delivery.json](delivery.json)。
