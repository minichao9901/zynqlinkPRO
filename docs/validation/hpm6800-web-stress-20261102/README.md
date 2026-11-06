# HPM6800EVK Web压力、缺陷修正及10MHz烧录对比

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

2026-11-02，先完成[R21原生分档测速](../hpm6800-speed-completion-20261102/README.md)，再开展本报告。**Web压力已执行并归档，不能判全通过**：ZL-005缺首DEF仍复现（保持暂停），另新增ZL-094随机CDC字节缺口待定位；性能差距ZL-093待改进。其余本轮修复和限定验收范围见问题表ZL-085～092。

## 配对、目标与测试边界

本轮Web实际配对为prebuilt/hpm6800-web-133-20261102（历史归档 `archive/main-before-formal-release-20261106:prebuilt/hpm6800-web-133-20261102/README.md`）：

* bit SHA256 `106d579bc1b79c2b873fd1e3eb2609d468892a67613d85a6e41d4dc90c8fc177`。
* Zynq ELF SHA256 `e1bf65a6369273225c0e46684308e05a02a0b297029d2159e91e37cb98e62066`。
* PL复用133.333333MHz/7.5ns通过的R20 bit，setup+0.179ns、hold+0.034ns；本轮没有更改RTL或重做实现。PS O3/Thumb compact、cap66666666Hz，增加原生最高档与旧HID RISC-V兼容、启动诊断。原生R21 ELF是另一明确源码变体，不能混用。

按用户建议做过一次**同Web配对bit+ELF重载**，前后证据保留。重载后物理MEM-AP0核对76380B代码相同，再以66.667MHz/idle22/mode17复测：AXI约3.437/3.400MB/s、RTT三轮约3.189MB/s、HSS单变量296.296kS/s三轮1秒零跳采。故Web慢不能仅用“探针未重载”解释；这些短对照不冒充R21三轮10秒/30秒压力。

只读参考superlinkPRO的全流程、HPM RTT/HSS与随机组合记录；三套现有ELF、源码、构建说明和精确SHA/来源提交见[目标夹具](../../../firmware/target/hpm6800_web_validation/README.md)。scope/RTT flood/dbgstress是原有产物快照，不声称本轮新构建。采用实际ELF符号和可计算波形/参数作判据。历史HSS差异和“软件TCK约20.7MHz是估算”已在R20说明，不把不同目标程序/CPU状态当同条件E2E。

Web测试采用日常EXE相同的**本机native代理通路**，经公开、鉴权的page CLI操作真实页面；未使用浏览器脚本注入、假探针、模拟数据或仅检查按钮投递结果。Chrome直接WebUSB和其他芯片不在本次实板覆盖内。

## 烧录默认10MHz与OpenOCD对比

已统一空选项标签、FlashRunner/DataClock、RISC-V及桥fallback为**10MHz**；保留用户显式选档，Cortex-M执行控制仍1MHz。ZL-089同时修复每次DAP Connect/Configure覆盖时钟：修前页面称10MHz但烧录中的物理MEM-AP0读回实际50MHz；修后FCLK119999998Hz、CFG0x2a011，实际TCK9999999.833Hz。频率来自PLL/源/分频寄存器推导，未使用外部频率计。

同探针配对、同scope ELF（SHA e5124ca35a872c2c54f210df99c5cfc3ca7a0d8f6a64f1cfa29a907aeb9b73a9），相同3216B+44640B两区域，**实际编程47856B**，擦除/逐字节验证/复位运行都打开：

|路径|三次总耗时 s|中位数 s|
|---|---|---:|
|Web日常native路径|22.987 / 21.905 / 21.855|21.905|
|OpenOCD|2.987 / 2.971 / 2.953|2.971|

**OpenOCD快约7.4倍。** OpenOCD另有独立warmup3.016s，未并入三轮。它采用SDK OpenOCD0.12.0+dev-04410-g45e78b300、CMSIS-DAPv2 JTAG10MHz，XPI参数与SDK HPM6880板一致；配置排除无关DDR/PLL reset-init钩子。校验通过CPU progbuf读回同样的两个合并区域，再由主机逐字节比较，未用CRC代替Web全字节校验，也未把331KB ELF调试文件大小当加载字节。

Web典型阶段为准备约0.3s、算法约1.5s、擦除约1.0s、写入约14s、校验约5.8s、复位约0.17s；OpenOCD编程约2.14s、校验约0.72s。Web约7156个原始JTAG批次（前端为兼容旧软件探针仍限制512B），未复用PS高速内存队列。**优先改进空间在主机传输批量化与往返次数**；分项是实际计时，但尚未进一步把HTTP/JS/USB开销完全拆开，未声称已量化所有瓶颈。原生串行效率及RTL减少多变量n+6次扫描的研究方向见R20/R21。

修前实际50MHz的flash-scope-default10/fixed-result和ZL-088结果栏遗漏均保留。修后HPM成功栏显示真实加载量/校验/复位，清除旧结果并提供阶段计时；三种固件及随机镜像切换均核对业务完成。

## 功能及随机组合结果

|功能|实际覆盖与结论|
|---|---|
|烧录|scope/RTT/debug三种镜像，默认选项、完整校验、复位运行；32步随机中29次镜像切换均成功。|
|RTT Viewer|真实32768B阻塞环，30秒196602B、约6544B/s，保存的字节模式一致、corrupt/lost计数0；仍走原始DMI，性能偏慢。|
|RTT→CDC|独立5秒3358720B约671516B/s通过；新EXE10秒6727680B约672741B/s通过；随机第7步出现内容缺口，见下文，不能称无损。|
|J-Scope|1/3/8通道已知波形与tick测试；8通道1kHz完整RAW/CSV/最终计数对照通过一次；其他多轮缺首DEF失败保留。停采尾包修正与缺DEF是两个问题。|
|调试|寄存器x5读改恢复、64B SRAM读写恢复、真实dcsr.step且cause4/step位清除；8个硬件触发器和第9个拒绝；runTo/参数/CFI≥4帧/位域对shadow通过。|
|源码单步|新EXE五轮核心检查后，stepOver至engine.c:9、stepOut至调用者engine.c:29，PC与ra、函数返回值均精确匹配。非调用处stepInto明确退回指令级；没有冒充该例验证了真正调用处的源码“进入”。|

固定seed680020261102，原24步+修正脚本后8步，合计32次操作、29次实际Web镜像切换，约19.9分钟；RTT/CDC/debug通过后保持活动状态，下一步使用真实页面所有权切换，最终各控制器均关闭、无清理错误。原始判定原样保留：

* 原24步：7通过、17失败。其中6个Scope因CDC串口仍开且“暂停CDC”被选中，**保护性拒绝符合预期**；5个CDC失败是脚本试图重设已选中且禁用的控件；6个debug参数失败是入口断点尚未执行prologue，却拿旧栈槽比较。后两类为ZL-090验收脚本问题。
* 修正后8步：5通过、3失败。Scope两次缺首DEF（ZL-005），CDC一次真实字节缺口（ZL-094）。Debug两次通过、RTT两次通过、CDC一次通过。没有把旧失败覆盖成“32/32通过”。
* 更早一次页面离开再回到相同服务，CLI第二个worker被409守卫拒绝，**尚未开始硬件动作**；只重新启动本任务服务后再测试。保留该日志，不当USB故障或绕过单worker保护。

### ZL-005：保持暂停的缺首DEF

例如scope-missing-def-wire第一包seq1/DATA，缺DEF0；RAW151552B中含全部3244个DATA点，探针最终也为3244，但页面等待DEF丢掉前133包后才fallback，CSV仅1792点。新最终计数检查明确报失败。后续1/3通道及两个随机Scope也复现；各RAW中DATA点数/首包/最终计数汇总在summary.json。按仓库授权边界保持暂停，没有重启专门RTL/readEpoch研究，也未用后续偶尔成功抹去失败。

### ZL-094：新增随机CDC字节缺口，待定位

修正后随机第7步958464B文件在偏移733184、749568、794624发生三次13字节模式相位跳变，均在2048B边界；实际异常行如`hello worlo world!`，不是窗口首尾截断。captureWindow显示complete且探针rdErr/wrErr=0，说明这些计数不能证明端到端无损。模式相位变化是事实，“丢了三个2048B块”仅为假设；重复文本不能唯一反推出丢失总字节/整行数。文件SHA和原始二进制、切换顺序已保存。

同一PS未再次重载，新EXE重烧RTT靶子后连续10秒6727680B模式核对通过；保留为恢复/对照，**不关闭问题**。下一步应用严格序号/CRC靶子复刻这次Web交接，区分PS CDC发布/USB与主机COM缓冲；本报告未对未知根因加补丁。

## 本轮修复与验证

ZL-087旧HID RISC-V选择、HSS后端位兼容；ZL-086默认10MHz；ZL-088成功栏；ZL-089重连覆盖时钟；ZL-091 STOP尾包；ZL-092累计请求硬停。ZL-085最高档cap与原生分档证据在R21。均同步问题表，剩余边界单列，不冒充全平台release。

ZL-091修前8变量CSV/RAW3146点而探针3216点，静默丢70点/4096B，即使seq/USB错误为0。修后仅在生产者STOP确认后读空排尾，在确认完成前保留旧轮DATA接收，启动任务仍立即取消。增加receivedSamples/tailCountDelta，超时/不一致显式失败。四个并发/尾部/超时模型与完整8变量实测通过；缺DEF病例的RAW DATA完整而页面少样，归ZL-005。

ZL-092首次在100000次请求硬停，step确认和bpClear也被拒绝。保存现场后仅重启自有主机服务，核对目标dcsr.step已清、恢复/继续运行，**该恢复未重载PS或复位MCU**。后续性能对照重载另有时间和日志。改为客户端单调序号+4096位有界已见窗口，缓存256个结果和在飞请求；同ID返回原结果、内容冲突和过旧请求拒绝重放，旧UUID兼容守卫保留。模型100009次、乱序/重载/iframe/回退缓存通过，真实压力**316510次、缓存256、旧UUID0**，最终清理通过。

生产C九变体、Web92项、152模块语法/共享驱动、CLI54项及定向Python20项通过。保留已有Deprecation/ResourceWarning日志，不把它们等同硬件失败。新脚本可通过`toolbox.py project describe hpm.web` / `hpm.web-stress`发现；实际会写目标Flash，须阅读帮助并确认当前板上配对与初始固件，不能靠目录名推断。

## 已更新EXE、恢复与最终状态

`python toolbox.py bridge-build`已重建并更新固定`dist/zynq-etm-bridge/`，原程序归档、用户data保留、不生成ZIP。候选冻结程序在无Python/Node可发现的环境完成离线F103/H743记录、解码/查询/导出与文件校验，1797个文件核对通过；然后实际运行该EXE完成上述两次默认10MHz烧录、CDC10秒与完整调试。package-manifest/package-check及离线验收结果归档在本目录。构建时源码HEAD为b5bb054且dirty=true，精确打包文件SHA保留；最终源码提交另由manifest承载，不把旧HEAD冒充构建后源码已提交。

受影响原Flash完整65536B，烧录前CPU progbuf双读一致，最终写回并独立reset/boot后再通过CPU progbuf读回，**全部字节相同**，SHA `afdb834a734d0c18f9d2269b28d8a0abe6eacd5d694077657c961521025397d4`。用户原Flash/读回二进制仅留build，不入Git；探针QSPI从未写入。恢复原程序是重新启动，不是恢复原PC/GPR运行时快照；原程序自行初始化其时钟。本任务未直接改目标PLL/DDR钩子，临时调试寄存器/SRAM逐次恢复。

最终快照 **2026-11-02T13:00:09.671353+08:00**：Web配对仍在板上，物理MEM-AP0核对76380B代码一致；FCLK49999999Hz/TCK24999999.5Hz、mode0、idle8；DMSTATUS0x430ca2、原目标程序运行，RTT/HSS/packet/采集空闲。自有Python/Web/EXE/OpenOCD/XSCT采集进程均结束；共享hw_server PID19676保留。见raw/identity-final、logs/final-state.json、raw/original-flash-restore/result.json、logs/final-processes.json。之后未再操作板卡。

新EXE默认10MHz和烧录成功界面（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/hpm6800-web-stress-20261102/frozen-flash-proof.png`）

## 原始证据

summary.json为提取索引，raw/保存每次页面调用、成功/失败、RAW/CSV/CDC字节、物理身份及恢复；drivers/保存执行版本和比较/恢复配置，logs/保存构建与检查。所有文件由evidence.json绑定SHA。build-inputs是实际Web PS六个修改输入的精确快照，完整PS输入哈希及构建选项在prebuilt的ps-build.json。未归档运行时令牌、私有Flash备份、用户记录；未推送远端。

交付源码、实际配对及证据承载提交：`eb67e9c2995b898e22f9b476665b09a6c19c9cc0`；配对manifest已绑定该提交，原生/控制变体仍须按各自base+overlay复现。
