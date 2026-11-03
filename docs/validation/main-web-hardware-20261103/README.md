# main 合并后 F103ZE 真机验收与 HAL 存储 Trace

2026-11-03～04，Asia/Shanghai。起点main 41e2cee；首批修复/新例程提交ae9b774。本轮不推送、不写探针QSPI。所有结果均限定实际F103ZE及下列配对；不推广到未在线H743/HPM。

新HAL例程与旧CDC共同提供了实际输入。**本轮实际HAL记录的新旧完整60张表及182项查询一致**，普通Web按钮的断点合并回归已修复。8页主流程均已操作；不能宣称所有功能零问题：ZL-130原配对STOP尾包、ZL-131长暂停后的CDC、ZL-137的60MHz标定仍有失败证据。最终固定EXE/新STAT配对已完成下列收尾；ZL-140启动失败和ZL-141控制/烧录性能差距同样保留，不判全功能/全性能通过。

## 现场、身份和恢复

初始探针仅DAP30000021、PL未初始化；按既有JTAG/RAM流程恢复（ZL-060）。F103初始复位进ROM、无CDC；用户确认未通电，接独立电源/BOOT0=0并重新插拔后，COM34 CDC48运行、RCC_CFGR=51040a、CPU/HCLK48MHz、TRACECLK24MHz名义值。供电不足组保留（ZL-129）但排除正式性能比较。

| 实际加载配对 | bit SHA-256 | PS ELF SHA-256 | 验证范围 |
|---|---|---|---|
| hpm6800-usb-fixed-133-20261102 | 106d579bc1b79c2b873fd1e3eb2609d468892a67613d85a6e41d4dc90c8fc177 | e93f1810d48e77f8d9aa097f643e40e0aaee32bdec1c263c1428f092909e608a | 初始ARM SRAM/RTT/HSS；物理76420B匹配；无DDR ETM |
| fclk133-release-20261101 | af1031d3caa0d7bd3b6adffa911d26efdab9e0bfb5223fb18f70dabb70ebeeed | 2137f7d0f507c08574f36223130103c0710645cbfdefb5c1d8c8efb0cfb990a0 | HAL/CDC正式三轮ETM比较；旧PS不兼容当前Web RTT/HSS action10，ZL-087 |
| main-ddr-usb-133-20261104 | 同release bit | f4690b6917d795cf401a16673cea92fe6e2e76f84c7c6f2bd2e41a4a41fc14b5 | 当前源码统一PS；物理76124B匹配；CLI/Web DDR、RTT、HSS通过，保留STAT缺陷 |
| main-ddr-usb-133-statfix-20261104 | 同release bit | ef62ea8171ff7c2affefdcb718c0e2a2fa3cd5630a408b7a83faaf02d5dafc41 | STAT修复PS；物理75756B匹配；最终冻结8页主流程、DDR CLI/Web及物理OCM收尾完成；存在ZL-070/137/140/141，accepted=false |

后两套PS确实重新构建，输入/选项/SHA见各prebuilt manifest；bit复用已布线release，未修改RTL或新做PL实现。133.333MHz是约束，原WNS0.319ns/hold0.033ns。SWD10/50/60时实际FCLK约120/100/120MHz，逐轮物理MEM-AP0读回并计算，非外部频率计；未由主机暗改MCU PLL。

原内部Flash完整512KiB双读SHA `48f226217497607c696a156addbb363925577499b00ee64f187bd5eea7a94499`，有效段原已等于CDC48。HAL完成后已恢复并逐字节匹配完整原Flash。原Flash/SRAM/GPR/NOR/EEPROM字节仅私留build，不提交。最终板上状态见收尾证据，历史快照不代表当前状态。

## 8页功能及性能

使用实际浏览器和公开page describe/click/invoke，核对数据与状态。源码工作台、固定EXE普通按钮、captureNative辅助路径分列。投递成功不等于完成。源/固定版使用独立runtime/data，用户dist数据5文件更新前后SHA相同。

| 页面 | 实际通过范围与限制 |
|---|---|
| 串口助手 | PING/INFO，3×8192B逐字节回显、保存；长RAM测试后WinError31独立保留ZL-131 |
| 终端 | 实际COM34接收PONG和保存 |
| RTT Viewer | 上行3800B、下行31B精确，RAM/核心/时钟/运行状态恢复 |
| RTT转发 | SWD50/60各3轮，全部发布量=接收=moved，递增序列精确、读写错0；CLI/Web同2048B口径补测 |
| 烧录器 | ELF CLI/Web各3轮擦写、完整有效段校验、复位；最终固定EXE HEX/BIN均擦写/校验/复位通过 |
| 调试器 | ELF/DWARF，16KiB SRAM三轮写读及恢复，R12往返恢复、真实单步、cdc_poll硬件断点PC08000590 |
| J-Scope | 1/8变量、多周期、RAW逐值/包序号/最终计数/STOP尾部；8种scalar、非对齐/跨1KiB、CSV逐值、缩放/无误触发、同文件回放；20MHz标定通过，60MHz首读失败另列ZL-137 |
| ETM | CLI/普通Web真实1秒采集、起点/恢复、完整窗口/质量、六视图、导航、源码、八种导出与记录导入；CSV与CLI字节相等，导入summary/quality相等 |

### SRAM、串口、烧录与RTT

SRAM峰值512words/depth32/256blocks/3重复，另3秒soak；历史10/60秒soak不冒称本轮时长。MB/s均十进制。

| 项目 | 当前CLI中位 | 历史最佳或当前Web |
|---|---:|---|
| SRAM SWD50 读/写 | 4.0492 / 3.9806 MB/s | 历史Golden4.0498 / 3.9824，配对不同 |
| SRAM SWD60 读/写 | 4.8315 / 4.7385 MB/s | 历史Golden4.8348 / 4.7479 |
| RTT SWD50/60，1024B块 | 3.8816 / 4.6437 MB/s | 历史3.8832 / 4.6460；当前3秒、历史2秒 |
| 控制API SRAM10，16KiB读/写 | 0.6520 / 0.6413 MB/s | Web含HTTP/JSON0.1094 / 0.0604 |
| 8192B CDC往返有效吞吐 | 0.2270 MB/s | Web发送/接收检查/首屏0.0313；不是USB线速 |
| 约20KiB ELF烧录/校验/复位 | 1.450s | Web2.704s；计时边界近似而非同内部函数 |

初次RTT Web自动选2048B而CLI1024B，原首末活动段3.9795/4.7840不直接算严格提升。统一PS后补同2048B、delay255、生产3秒、各3轮、同首末非空活动段公式 `(total-firstChunk)/(lastTime-firstTime)`：SWD60 CLI中位4.7418、Web4.7764MB/s；约0.7%差异含主机调度。完整数据与尾部均校验。50MHz逐轮值见raw/unified-*-rtt/result.json。

### HSS接收回归与改进

同统一配对/静态RAM/60MHz/flags0xa1，CLI单u32 period48ticks为500kS/s，8u32 period197ticks为121827.4组/s，各三轮3秒稳态跳采0。启动可能跳1点，不能说整个会话任何时刻零跳采；8变量48ticks过载对照保留。

旧固定Web只有约90k/43k组每秒并额外跳采。原生EP87从逐512B同步读取改为65536B连续后台收取，4MiB有界队列溢出显式失败；只有本次调用之后的新USB空完成才可报告排空，不能把队列暂空当EOF。实测PyUSB/libusb部分超时保留已传字节，20项接收/代理单测通过。源Web单/8变量上述高速与1kHz各三轮（12窗口）稳态跳采0，逐值/序号/最终数量一致，停止/尾部通过。单次大块方案仍跳采的中间结果保留。ZL-123仅F103主机路径部分解决，未代替原HPM板复验。旧HPM配对F103停止19点缺尾ZL-130仍待定位，不能以换配对通过关闭。

## HAL SPI Flash / EEPROM例程

[源码及运行方法](../../../firmware/target/stm32f103_hal_storage/README.md)，[目标产物](../../../prebuilt/targets/f103ze-hal-storage-20261104/README.md)。HAL SPI2 PB12～15、1.5MHz；I2C1 PB6/7、100kHz、EEPROM0x50/8位地址/8B页；PE2～6保留Trace。CPU48MHz。实物JEDEC **EF4018、16MiB**；EEPROM应答只证明地址存在，不是独立芯片ID。

启动/100ms循环只读，命令2双读备份，命令3需有效备份及一次性arm 0x53545257。NOR末4KiB扇区0xFFF000，512B图样从偏移0xF0跨256B页；EEPROM从0xDB写29B跨8B页。写后逐字节检查，再恢复整个4KiB/256B并实际独立读回。原SHA分别 `ec49cab04f685666b5536a49d6a9e0ada6975ebb72087ebf8136b41668f2b49f` / `ba6b09b3804088cb4fc17bdee75f974356a1d9fa30d1c1f4b6e4b7685cdf38af`。

功能轮、CLI3、辅助Web3、源码窗口及普通固定Web3均核对外设恢复。另3次受控MCU软复位后backup_valid=0，主机重新提供原备份并恢复两区，实际SHA相同（ZL-138）。最后NVM核对在切回CDC之前；切回后未执行SPI/I2C写入。不能把RAM中的备份相同代替实际外设读回。

实际v3目标ELF SHA `dbaff7a388bb66fb2d1439f729f60c4f6620ff464c623bda80e2a3f7ef6a4d44`。固定ST HAL1.1.10 SPI/I2C补充源码、license/provenance纳入Git；全部构建输入见manifest。保留ZL-132初次向量链接失败、ZL-133 WFI边界，不把其失败产物标交付。

## ETM端到端性能及新旧算法

所有正式三轮ETM均release bit/PS2137、目标48MHz/Trace24、SWD10、硬件1秒。CDC新旧控制对照用同一Echo实现64B/2ms，每个完整硬件窗61～62次精确回显。

| 任务 | CLI三轮秒（中位） | 普通固定EXE Web按钮至首屏秒（中位） |
|---|---|---|
| CDC新C++ | 11.049 / 10.692 / 10.634（10.692） | 12.298 / 12.348 / 12.665（12.348） |
| CDC旧tag实际CLI重测 | 25.081 / 24.537 / 24.613（24.613） | 历史Web六轮中位32.734、冻结单次最佳29.173，跨历史窗口仅作参考 |
| HAL存储读写 | 9.962 / 9.812 / 9.777（9.812） | 11.344 / 10.834 / 10.685（10.834） |

CDC当前CLI较本机重测旧tag中位缩短56.6%，普通Web比CLI约15.5%；HAL约10.4%。CLI计入进程/连接，Web按钮不计之前连接/文件上传，不能把它们当同内部函数微基准。HAL Web外层全流程15.127/14.550/14.585秒另含连接/设置/清理；辅助captureNative10.875/10.798/10.755秒不冒充普通按钮。旧离线7.2秒/估算8.43秒不作为E2E。

旧参考tag archive/main-before-etm-cpp-20261103（06452f2），参考worktree未改。相同HAL CLI输入及最终普通Web输入分别验证：全函数/行区间/segments/Web ELF DTO一致；完整执行块、诊断、analysis、默认视图、语义meta、**60数组dtype/shape/每个值完全相同**；旧Golden真实生成库与new direct/binary/rescan/repeat四种路径一致；5种实际输入变更拒绝；**182个深度查询DTO一致**。最终Web实际store再与重建cpp全60表相等，含源码。限定这些实际输入，不宣称所有可能程序均正确。

最终普通Web记录约1724万路径，入口包含storage_exercise→eeprom_write→HAL_I2C_Mem_Write，源码/指令/火焰图可见。完整输入保存在[hal-storage-write-input](hal-storage-write-input/manifest.json)，PNG在下。六视图、六导航、八导出、导入完成证据见raw/hal-web-views-finish/result.json；原脚本在异步导入清理阶段过早切换的失败保留，纠正等待后通过。

![最终固定EXE打开实际HAL_I2C_Mem_Write源码及执行火焰图](hal-final-exe-trace.png)

[自包含交互火焰图HTML](hal-storage-flame.html)。本机完整可导入包位于build/main-web-hardware-20261103/hal-final-web-views/storage.etmrecord；已保存Git中的完整raw/ELF/source输入可用于独立重建。

## 修复、检查与未完成边界

- ZL-134：普通Web函数起点仍把NativeImage当pyelftools，报get_section_by_name。C++新增按$t/$d/$a映射的Thumb可断点边界；Python仅规格/DTO。三ELF所有边界、函数/行/地址及非法拒绝一致，HTTP同时禁Python ELF/Capstone。ae9b774后干净固定EXE bc624711实际HAL3+CDC3普通按钮通过。
- ZL-135：停止后DATA守卫阻断JSP回放；分离同步回放标志，保留迟到live守卫。原3231点全值回归及新源Web实采/回放通过。
- ZL-136：PS软件STAT复用槽残留；清零payload，新PS实际采样/回放usb错误0。原52719坏STAT保留，不由解析器掩盖。
- ZL-137：60MHz标定首读err=-4/完成0；最终20MHz两种计划成功，60MHz单变量失败后混合又成功。10MHz另为时钟请求被拒，不能混作同一错误。
- ZL-130原配对缺尾、ZL-131长RAM暂停CDC枚举但WinError31仍待定位。CDC已有CaptureEntry+UsbReconnect PA12短拉低/恢复流程，精确回显恢复不等于关闭根因。

检查：161模块语法、130 Web自测、60 CLI自测、20 HSS/代理专项、9生产C模型通过；共享驱动sync --check通过。原生断点13专项、3ELF静态及HAL完整差分另通过。[原生编译身份](raw/native-build-identity.json)保留实际41e2源码底及输入SHA，不能改写为后来报告提交编译。

[公开证据索引](raw/evidence-manifest.json)仅归档有界诊断与已知测试模式，不含运行令牌和私有备份。完整工作输出build/main-web-hardware-20261103/。最终收尾结果见下节。

## 最终固定EXE与板上收尾（2026-11-04）

干净源码02d43aecdd7a8ff4496625a639594e04f8751959构建EXE SHA `1ae6ed71abac01386db708e09e3cb0bc99f5149e388882bed3a58906be2612d7`，package-manifest SHA `3762b6274491a425f85e721a666ece7e9d2d2e2f749408b8473e1d43114c7fc7`，sourceDirty=false。已更新dist/zynq-etm-bridge；用户原data的5文件SHA保持不变，旧程序归档build/bridge-archive/20261104-032757-128ed266/previous，无ZIP。

以下均在最终ef62ea81 PS + release DDR bit上完成，不把前表另一配对或早期源程序的结果代入。

| 收尾项目 | 当前结果 |
|---|---|
| 1u32 / 500kS/s | 冻结Web三轮10秒稳态跳采0，值/序号/最终量/STOP精确 |
| 8u32 / 121827组/s | 三轮10秒跳采0/0/234；短3秒通过不推广长窗 |
| 8u32 / 100k组/s | 三轮10秒0/0/395，保留失败 |
| 8u32 / 50k组/s | 三轮10秒全部0跳采，逐值/最终量/STOP精确 |
| 原生1MHz历史配置点 | CLI三轮2秒39/0/0跳采；历史release曾三轮全0，已见临界波动ZL-070 |
| Web输入1us | 实际归一到2us/48ticks，三轮约500k；是产品周期边界ZL-139 |
| 8种混合scalar | 最终冻结实采/CSV全值、非对齐/跨1KiB、缩放/无误触发、同JSP回放点数及错误计数通过，ZL-135/136关闭 |
| 标定 | 20MHz单/混合11.415/137.884us成功；60MHz单变量err=-4，随后混合69.862us成功；ZL-137保留 |
| RTT Viewer / 调试 | 最终上3800B/下31B精确；16KiB三轮/核心恢复、断点/单步通过；另Watch标量/结构体、CFI/locals、源码单步跳过/进入/跳出、RCC.CFGR SVD实际读值0051040A通过 |
| 串口 / 终端 | 长RAM后再次WinError31，既有恢复后CLI/Web8192B精确及PING/INFO/PONG导出通过，ZL-131保留 |
| 普通ETM | 当前配对CLI/固定Web各一个完整1秒带CDC精确echo，10.985/13.068s；不是三轮统计，前表正式三轮性能仍归release PS2137组 |
| HAL记录打开 | 最终EXE真实导入先前普通Web HAL包，summary/quality相等，选择799653显示HAL_I2C_Mem_Write及火焰图 |

RTT转发最初热状态START三秒仍未运行（ZL-140）。新runtime/页面后的50/60各三轮全部数据正确，但不能以此关闭失败。新建同令牌第二worker的409是队列保护，等待脚本已正常退出/夹具恢复，不算板卡故障。

同口径2048B/生产3秒/首末活动段三轮中位：

| 实际SWD | CLI MB/s | 最终冻结Web MB/s | Web/CLI差异 |
|---|---:|---:|---:|
| 50MHz | 3.9685 | 3.9824 | +0.35% |
| 60MHz | 4.7467 | 4.7755 | +0.61% |

最终配对ELF烧录三轮中位 **CLI1.461s / Web9.526s**；HEX10.092s、BIN9.589s为各一次功能窗口。Web各段擦除约2.6s、写入约4.4s，不能沿用早期另一配对源Web2.704s。16KiB控制内存三轮中位：CLI读/写 0.6424/0.6406 MB/s，最终Web 0.0364/0.0182 MB/s。控制/HTTP/配对差异仍待定位ZL-141，不把它归因于已证明的某次代码退化。

历史全局极限另有固定66.667MHz实验SRAM5.3605/5.2527、RTT5.1452MB/s；其配对/频率不同且仍是实验，当前60MHz结果未达到该全局数值。该实验不能代替当前DDR/USB统一业务，本轮未重启高频扫描。[历史条件](../performance-limits-20261101/README.md)。

最后板上快照为UTC 2026-11-03 19:55（本地11-04 03:55）：完整512KiB Flash与最初备份逐字节一致、SHA48f22621…，目标CDC48运行/RCC51040a；NOR/EEPROM最后实际读回原SHA后未再执行其写入。所有完成夹具已核对恢复；原标定脚本越过finally的一次手工恢复仅独立核对SRAM/RCC/运行，未留GPR前后比较，不能补称全寄存器验收。

实际仍为ef62ea81 PS + af1031d3 bit，物理75756B执行段与提交ELF一致；SWD9999999.833Hz/FCLK119999998Hz，RTT/HSS停止，DDR/采集/DMA硬件观察均空闲。新配对保留accepted=false：是实测候选，未代替Golden/QSPI恢复包，未做QSPI写入/冷启动/其他MCU验收。自有最终EXE PID18532及前序源服务/producer/serial进程均已停止；共享hw_server PID15816保留。截图与HTML为历史HAL记录，不表示板上当前仍运行HAL。

证据：raw/final-performance-summary.json、final-board-state.json、final-ocm/result.json、fixed-final-identity.json。首次失败、跨配对对照、短窗/长窗与完整恢复边界都保留。功能覆盖以本报告明确列出的F103真实业务为准，不冒称每种MCU/浏览器/格式组合或故障注入均已验收。
