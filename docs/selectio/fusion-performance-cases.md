# J7 SelectIO 融合版精简性能用例

2026-11-23。基线为 `codex/selectio-efficiency` 的 [F103ZE 实测融合配对](../../prebuilt/selectio-variable-board-20261122/full/manifest.json)，由匹配的 bit、PS ELF 和 PS 初始化脚本组成。本表适用于融合版单镜像和 JTAG/RAM 临时加载。F103ZE 的 96/128 MHz 是 SRAM 夹具的临时实验 HCLK，额定上限为 72 MHz。测试前由 RCC 和 DWT 分别核对配置与实际 HCLK。 [ST 数据手册](https://www.st.com/resource/en/datasheet/stm32f103ze.pdf)

## 本轮选点

- SWD 和 JTAG 各跑 **50/96、73/128、100/96、100/128** 四个「链路 MHz／目标 HCLK MHz」初筛组合。50/96 对齐历史基线，73/128 覆盖 FCLK1 分频变化，100/96 与 100/128 可直接比较目标 HCLK 效应。73 MHz 是请求值，现有配对预期约 **72.727 MHz**。50 和 100 MHz 共用 N=32 的参考档，73 MHz 使用 N=44。记录实际线频、FCLK0/1/2、tap、slot、请求及生效 idle。 [时钟与换档](../validation/selectio-variable-20261122/README.md#时钟与换档)
- **先确认接收裕量，再筛性能。** 先跑 CAL-01，再在默认 idle 做 SRAM、RTT 和 HSS 单/八变量各一次 3 秒筛选。历史点、最快候选和失败边缘才复跑长窗。100 MHz 对照先在两个 HCLK 上验证共同可用的 tap/slot，并固定相同 idle、载荷与口径对拍，再分别调参。50/128 或 73/96 只在现有最优值接近、目标等待异常或 100 MHz 的 HCLK 对比改变结论时补一个针对性点。
- **一次只改变一个量。** 锁定 tap/slot 后，idle 上下各试一个表列相邻值，先用跨页 SRAM 初筛，再把胜出档和稳健档分别用于 RTT/HSS 短测。各服务可保留不同 idle。遇到非法 ACK、错字、恢复失败或 STOP 尾差，保存原始证据并结束该点。普通 WAIT 可以重试，必须记录次数、有效 idle 和自动退避，带退避成绩按实际档记录。若降低 idle 后出现非法 ACK、奇偶错或错字，用已知稳定 idle 和 tap/slot 复核，再判断是返回采样、换向/事务衔接还是目标响应。表内的待测设置均为起点。
- **最佳值按指标各自选。** 读、写、RTT、单变量 HSS 和八变量 HSS 分别按 PC 有效载荷中位数排名。每项先确认短测第一名。长测失败或两点短测相差不超过 2% 时，才确认第二名。结果写成「本次已验证组合中的最佳」，并同时保留失败组和实际参数。

IDELAYCTRL 用固定 200 MHz 参考校准延迟单元，tap 的标称步进约 78 ps。链路训练再选择 SWDIO/TDO 的通过窗口。slot 选取反串化样本，SWD/JTAG 在 50/100 MHz 档的 slot 步进约 2.5 ns，在 72.727 MHz 档约 3.4375 ns。固定 slot 增加 tap 会推迟数据到达，固定 tap 增加 slot 会选更晚的样本。idle 以 SWCLK/TCK 周期计，给相邻事务之间留出响应时间。只有单一离散通过点的组合标记为裕量待确认。ETM 在 D0–D3、TRACECLK 上分别选 tap，按 ETM 用例独立核对。 [Zynq-7020 延迟规格](https://docs.amd.com/api/khub/documents/uaBd8Qxmf_K1~~tiVnOxrw/content) · [变频时钟树](../validation/selectio-variable-20261122/README.md#时钟与换档)

## Case 表

时钟栏按「调试链路／目标 HCLK」或注明独立物理时钟。吞吐单位为十进制 MB/s，采样速度用组/s。tick 以 HSS 定义帧里的实际 24 MHz 时基和周期为准。

| 编号 | 项目 | 条件与初始参数 | 执行和验收 | 备注与历史参考 |
|---|---|---|---|---|
| CAL-01 | SWDIO / TDO 接收裕量 | 每个协议的三种实际线频，沿用 DBG 表的 tap/slot 起点。固定线频、HCLK 和稳健 idle；在 MMCM 锁定、IDELAYCTRL 就绪且链路空闲时换档 | 固定 slot，先测 tap 起点和 ±4/±8，限在 0–31。用 ID ＋ 跨页 SRAM 读/写回比较筛选，再检查候选的相邻 ±1/±2 tap，优先选落在连续通过区中部的档。窗口不够才固定 tap 试 slot ±1，并对胜出 slot 做同样邻域复核 | 按 tap/slot 保存通过区和首个错误。100 MHz 的第二个 HCLK 只复核中心及 ±2 tap，裕量不足才扩扫。50 MHz/slot22 历史上 RTT 短测通过、长测报非法 ACK，slot24 通过长测。 [实板对照](../validation/selectio-variable-board-20261122/README.md#实测结果) |
| SIM-01 | SWD SRAM、RTT 和换向 | 50/96、73/128、100/128。CM3 实际原语模型，SWDIO 返回延迟 16 ns；模型 slot 22/22/24，idle 0/0/2 | 512 字读写全量比较，RTT 8 KiB 环按 2 KiB 搬运并校验最后 RdOff。50 MHz 另跑 OK、WAIT、FAULT、奇偶错和换向。换档检查停钟、MMCM 重锁和固定 200 MHz 校准参考 | 变频模型 73 MHz 读/写 5.520/5.846，RTT 至最终 RdOff 5.250。模拟值。 [记录](../validation/selectio-variable-20261122/README.md#三频结果) |
| SIM-02 | JTAG SRAM、RTT 和 WAIT | JTAG 50/96、73/128、100/128，模型 slot 21 起步；idle 按 DBG-05～08 | 三档均做双 TAP 识别、整页逐字比对和 posted read 尾字。50/100 MHz 用服务台架确认 RTT RdOff 和 WAIT，100 MHz 跑共享引脚回归。73 MHz 的 RTT 用 DBG-06 定向板测 | 100/128、idle33 的 256 字模型读/写约 5.064/5.063。73 MHz 请求对应模型 TCK 周期 13.75 ns。 [记录](../validation/selectio-variable-20261122/README.md#三频结果) |
| SIM-03 | SWD/JTAG HSS 周期边界 | 每条链路先测 50/96 与 100/128。单 u32、八个连续 u32，周期取下表起点及邻档 | 周期正常和超额请求各测。检查值、时间戳、序号、包级确认及 STOP。JTAG 故障注入须验证未确认包不发布。仿真结果作为实板筛选起点 | 100 MHz 模型稳定窗 SWD 1.500 M/150.0 k，JTAG 299.9 k/83.3 k 组/s。短模型窗口。 [原始口径](../validation/efficiency-20261122/README.md#j-scope-的稳定与超额请求窗口) |
| DBG-01 | SWD 低档与历史对拍 | **50/96**，tap8/slot24，idle **0/1**，HSS 起点 **32/288 ticks** | 四项短筛。额外做一次标准 CMSIS-DAP 2 KiB、depth32、256 blocks 的历史口径对拍。当前 50 MHz 稳定基线 RTT 做三轮 60 秒 | HCLK96 历史标准 SRAM **4.047/3.983**、RTT→CDC **3.995**，后者两个 3 秒窗。HCLK128 旧原生 IF4 **4.016/3.972**、RTT **3.915**，为不同路径。 [历史与口径](../validation/swd50-review-20261122/README.md) |
| DBG-02 | SWD 中档 | **73/128**，tap8/slot22，idle **0/1**，HSS **28/240** | 四项短筛。核对 N=44、线频约 72.727 MHz。可从本点晋级各指标长测 | 标准 SRAM **5.028/5.299**，RTT→CDC **5.021**（旧 12 秒窗）。 [实板](../validation/selectio-variable-board-20261122/README.md#实测结果) |
| DBG-03 | SWD 高档 HCLK 对照 | **100/96**，tap8/slot25，idle **2**，HSS **24/192** | 和 DBG-04 先同参数对拍。出现目标 WAIT 或可能胜出时才试 idle 1/4，再按各指标晋级 | 旧 100 MHz 同 HCLK128 的 slot20/22 识别失败，slot24 RTT 曾出现非法 ACK。 [失败和通过参数](../validation/selectio-variable-board-20261122/README.md#实测结果) |
| DBG-04 | SWD 高档冲峰 | **100/128**，tap8/slot25，idle **2/1/4**，HSS **24/192** | 四项短筛；idle 1 通过且读写、RTT均无异常时可追加 idle 0 短测。每项各自选最佳，胜出点做长窗。100 MHz 标准路径加一次旧口径对拍 | 历史同 HCLK128 标准 SRAM **6.498/6.702**、RTT→CDC **6.506**（12 秒窗）。旧融合 HCLK48 原生 SRAM **约 6.17/6.17**（3×60 秒），HSS **约 1 MS/s／125 k组/s**（60 秒、3／0 跳拍）。 [变频](../validation/selectio-variable-board-20261122/README.md) · [长窗](../validation/selectio-fusion-20261121/README.md) |
| DBG-05 | JTAG 低档 | **50/96**，tap16/slot28 起步，idle **17/13/21**，HSS **144/480** | 低速确认双 TAP 及目标 JTAG 连接后上档。四项短筛。可从本点晋级长测 | 旧 CM3 50 MHz、idle17：SRAM **3.212/3.212**，RTT **2.602**，均为模型。 [模型](../validation/efficiency-20261122/README.md) |
| DBG-06 | JTAG 中档 | **73/128**，tap16/slot28 起步，idle **25/21/29**，HSS **128/448** | 四项短筛，核对实际 72.727 MHz、TDO 采样和 DAP WAIT；作为中频实板覆盖点 | 以 100 MHz 归档档位和 50 MHz 模型作相邻参考，本表基线尚无同条件历史成绩。 |
| DBG-07 | JTAG 高档 HCLK 对照 | **100/96**，tap16/slot28，idle **33**，HSS **96/416** | 与 DBG-08 先同参数对拍。WAIT 或可能胜出时才试 idle 29/37。原生和标准吞吐分别记录 | 纯 JTAG 分支 HCLK96、100 MHz/idle19 的 **6.081/6.081** 是 A9 驻留图案。 [纯 PHY 对照](../validation/selectio-fusion-20261121/compare100/README.md) |
| DBG-08 | JTAG 高档冲峰 | **100/128**，tap16/slot28，idle **33/29/37**，HSS **96/416** | 四项短筛。idle29 通过且无自动退避时，才追加 idle25 短测。100 MHz 标准路径加一次旧口径对拍 | 历史同 HCLK128 标准 SRAM **4.100/4.035**、RTT→CDC **4.038**（8 秒窗）。旧融合 HCLK48 原生 SRAM **约 4.68/4.56**（3×60 秒），HSS **约 250 k／57.7 k组/s**（60 秒、1／0 跳拍）。 [变频](../validation/selectio-variable-board-20261122/README.md) · [长窗](../validation/selectio-fusion-20261121/README.md) |
| IO-01 | Windows COM，UART NRZ 双向 | 115200 8N1 独立 F103 回送，100 Mbaud 用 N=32、物理回环。检查 4,096 B 边界 | 小包与边界包先过功能，再测 100 Mbaud 60 秒。每方向记录发送/实际收到的字节与有效 MB/s，逐字节匹配，零帧错、零溢出 | 旧配对 100 Mbaud/60 秒每方向 **261,959,680 B，约 4.37 MB/s**，为带往返等待的物理回环。 [实测](../validation/selectio-fusion-20261121/README.md#comswo-与-spi) |
| IO-02 | 真目标 ITM，SWO NRZ 和 Manchester | F103 CDC48，UART NRZ **3/48 Mbaud**，Manchester **1.5/24 Mbit/s**。低档分别用 IF4 做功能，高档分别验证 IF4、IF0 | 每个高档发送 **500,000 个独立 u32**。核对 ITM 端口、宽度、载荷和尾包。每档应完整匹配 2,500,000 B，零丢失、帧错和溢出 | 旧融合配对两接口四档全匹配。 [实测](../validation/selectio-fusion-20261121/README.md#comswo-与-spi) |
| IO-03 | SWO 两编码最高接收档 | J7 L14 独立源。N=32 先 50 再 **100**，UART 用 Mbaud，Manchester 用 **Mbit/s 信息位率**。N=44 做一次支持上限内复验和上限外拒绝 | 独立源发送混合码型、递增序号和长连续窗。候选最高档先 3 秒，再三轮 60 秒。原生 Manchester 记录 tap/phase，先固定码率检查相邻设置。保留源端波形/有效字节计数，接收逐字节全匹配，零错/溢出。Manchester 100 Mbit/s 源须能输出 200 Msymbol/s，区分连续线速和突发线速 | 旧 100 Mbit/s 混合码 **M15** 物理突发通过；**L14** 外部交替码 100、任意字节 50 通过。L14 任意混合码 100 需要独立源。N=44 接收预算约 72.727 Mbit/s，执行时按固件协商的实际限值。 [外部源边界](../validation/selectio-fusion-20261121/README.md#comswo-与-spi) · [变频预算](../validation/selectio-variable-20261122/README.md#100-mbits-swo) |
| SPI-01 | 四线 SPI 四模式仿真 | SCK **100 MHz**，mode **0/1/2/3** 对应 CPOL/CPHA **00/01/10/11** | 使用独立 SPI 从机模型，同一 CS 窗交换 1、5、4,096 B，检查两方向全量、首末位、边沿、CS 极性与时序 | 现有 [SPI 仿真台架](../../fpga/sim/tb_selectio_spi.sv) 覆盖这些长度。IF4 CLI 的单个连续 CS 载荷上限为 4,079 B，板测以该上限验边界。 [模型与硬件口径](../validation/selectio-fusion-20261121/README.md#comswo-与-spi) |
| SPI-02 | 四线 SPI 实际最高 SCK | 空闲时选 **N=32**，SCK 100 MHz，四个 mode，用能在对应模式响应的独立从机 | 四个 mode 均用不同的 MOSI/MISO 预期数据逐字节对拍。每 mode 先 3 秒，最高档再 60 秒，记录 MISO tap/slot、实际 SCK、CS/包间空隙以及 PC 有效 MB/s。现有 TAP/PWM 夹具作物理预检 | 旧融合 100 MHz mode0 有双 TAP 回送。四模式都验证过物理 MOSI、12 MHz 异步 MISO；全速四模式双向验证需独立从机。 [物理证据](../validation/selectio-fusion-20261121/README.md#comswo-与-spi) |
| SPI-03 | SPI 从机 SelectIO 仿真 | 独立 SPI 主机模型，50/72.727/100 MHz、四模式、8 个初相，用 UNISIM 模拟 IOBUF、IDELAY 和 ISERDES | 片选择内所有字节完全匹配，片选中止的部分字节记错且下一帧恢复，接收占用期间 SCK/CS/MOSI 均为高阻 | `python -X utf8 tools/selectio_spi_slave_sim.py --out build/spi-cdc-sim` |
| SPI-04 | SPI 从机 → CDC 实板 | 先用有保护的 F103 SRAM GPIO 源，四模式各 16 KiB。100 MHz 用独立 SPI 主机，记录实际 SCK 和 MOSI 负载 | COM 原始字节完全匹配，片选后尾包收齐，零溢出、零帧错误。记录 DTR 绑定/释放和目标恢复。最高持续档先短测，再 3×60 秒 | 统一入口 `--only spi-cdc` 跑板上 F103 低速段；独立源用 `selectio_spi_cdc_test.py --expected ...`。100 MHz 仿真与物理验收分别记录。 |
| ETM-01 | ETM 接收器数字边界 | 固定 FCLK2 200 MHz，TRACECLK 先 **24/48/64/72 MHz**。64/72 各跑 8 初相 × 2 占空比（45/55%）× 2 时钟相对延迟（200/1600 ps） | 每个相位逐字匹配 128 个 formatter 帧及 3 字节尾，零错误。只在全通过档与首个部分失败档之间补一个中间频率 | 旧双沿模型 **64 MHz 32/32、72 MHz 16/32**；这是数字窗口边界。 [数字偏斜记录](../validation/efficiency-20261122/README.md#占空比和相对延时) |
| ETM-02 | F103ZE 额定范围内的 ETM | TRACECLK **24→32→36 MHz**，分别 HCLK **48/64/72**。四位 DDR、匹配 ELF、同一源流和固定低速 SWD 控制 | 每频先 100 ms 确认，最高通过档三轮 1 秒。确认上下行采集计数、完整 DDR/USB 字节、严格解码，以及已知循环的指令/分支流 | 历史正式 J7 **32 MHz 三轮 1 秒**完整通过；36 MHz 固定校准点也曾三轮通过，相邻 tap 失败。当前变频融合版应重新确认。 [32 MHz 证据](../validation/j7-traceclk-20261106/README.md) · [36 MHz 邻域](../validation/j7-eld1-20261106/README.md) |
| ETM-03 | ETM 实板高频边界 | ETM-02 基线通过后，优先试 **48/64 MHz TRACECLK**，可用同一 SRAM-only 负载的 **96/128 MHz HCLK** 并实测引脚，或用独立四位已知 formatter 源 | 100 ms 初筛。每个候选保留相位/tap 邻点和失效点，最高档三轮 1 秒。目标运行流与外部已知帧分别确认。源不稳时记录码源受限和最高已确认点 | 外部源证明探针接收上限，已知目标程序的解码证明目标 ETM 端到端上限。旧融合 24 MHz 运行态严格解码已通过。 [原始运行态](../validation/selectio-fusion-20261121/README.md#etm-硬件与解码) |
| REC-01 | 模式切换与恢复 | 同一融合 bit/ELF 下，SWD 50→73→100，JTAG 100→73→50，在空闲边界做 SWD→JTAG→SWD；另测活动流拒绝非法换档 | 每次重识别、读守卫字。跨页读写、RTT STOP 和 HSS STOP 均完成恢复对账，核对探针空闲、目标 SRAM、哨兵、RCC、AFIO、核心与运行态 | 旧融合已有 128 次 SWD/JTAG 交替接管证据。本行对变频路径补验。 [切换证据](../validation/selectio-fusion-20261121/README.md#usb-与模式切换) |

## 长窗判据与执行入口

- **SRAM** 主成绩走 IF4，固定 4 KiB 帧、4,032 B 请求、depth4，从同一安全地址的 +32 B 跨四个 1 KiB TAR 页。读、写、交替各 3×60 秒，读和交替逐字节比对；单向写每轮用独立低速读回最后图案和保护字。按各方向 PC 有效 MB/s 计算中位数。记录 PL 队列和 PS 块计时以解释差额。若要核对最新标准口径，另单列 2 KiB/depth32/256 blocks 的 CMSIS-DAP 三轮结果。16 KiB 只作一次获胜配置的几何对照，记录实际协商帧长。
- **RTT** 主成绩为 RTT→CDC，固定运行中的 SRAM 递增生产者、8 KiB 环及 2 KiB chunk。按 PC 实收的服务窗口计算 MB/s。候选 3×60 秒都须通过逐字序号、目标发布量、RdOff、STOP 和排空对账，并记录生产者是否足以持续供数。原生 IF4 RTT 单列，旧 HCLK48、100 MHz 的独立 RTT 计入 CLI 启动时，SWD 为 5.413、JTAG 为 3.485 MB/s。 [历史双链路](../validation/selectio-fusion-20261121/README.md#运行中的-rtt-与变量)
- **J-Scope** 每个组合独立配单 u32 和同一 TAR 页内八个连续 u32。起点通过后试一个较短周期，失败则试一个较长周期。SWD 单变量每次调 2–4 tick，八变量 16–32 tick。JTAG 单变量每次调 8–16 tick，八变量 32–64 tick。保留实际 DEF 周期，遇到固件钳位时相同实际档只测一次。晋级档每种宽度独立跑 **3×60 秒，每一轮** `skipped / (samples + skipped) < 0.001`，且样值正确、帧序号连续、读错误为 0、STOP/STAT/主机组数和尾包一致。报告应保留完整窗口计数、启动和尾段差异、请求值、实际值、实收组/s 及最差跳拍率。
- **串行与 SPI** 保留实际线速、传送字节数、主机有效吞吐、硬件错误和首个差异。确认前固定 N=32 参考档并读回。ETM 分别报告接收成帧、DDR/USB 下载、目标严格解码的通过频率。完整窗口、非边界数据缺口为零、frameDrops/parserErrors/IDELAY ready loss/writerError 为零；已知程序还要核对实际执行流。硬件上记录测得的 TRACECLK、占空比、每线 tap 和邻域结果。
- **入口** 先用 `toolbox.py project run board.accept -- --selectio --board f103ze --pair <配对目录>` 预览。统一入口支持 50/73/100 MHz，请求档位需要配对清单提供对应 profile，默认板测夹具为 CDC48。HCLK96/128 和按服务择优可用 [SRAM 时钟夹具](../../tools/selectio_f103_clock_accept.py) 的 `--command` 分次运行，JTAG 子命令加 `--enable-jtag`。开始板测前核对实载配对并独占目标，子命令的写入范围必须由同一次 SRAM 备份覆盖。时钟夹具的一键 `memory/rtt` 路径仍固定 SWD50。
- **定向入口** SRAM 用 [流水测速](../../tools/selectio_pipeline_bench.py) 的 `--clock 73000000` 等请求，CMSIS-DAP 用 [标准块测速](../../tools/h743_peak.py) 的 `--speed-hz`。CDC RTT 用 [转发压力工具](../../tools/benchmark_rtt_forward.py) 的 `--speeds` 与 `--chunks 2048`。HSS 用 `toolbox.py selectio profile` 先设 tap/slot/idle，调用 `scope --clock … --period … --var …`，再由 [HSS 导出器](../../tools/selectio_scope.py) 核对原始帧、预置样值和尾部。COM、SWO、SPI 入口见 [物理串口、SWO 和 SPI](README.md#物理串口swo-和-spi)。ETM 用 [Trace CLI](../Trace-CLI使用说明.md) 的 `capture --running-window` 和 `verify --require-decoded`。时钟夹具直接支持 48/64/72/96/128 MHz HCLK，分别对应本表的 24/32/36/48/64 MHz TRACECLK。独立源子项按表中硬件能力准备。
- 每个结果以 Case ID、协议、实际时钟、HCLK、tap/slot/idle 和轮次命名，记录配对哈希、目标/探针序列号、全部原始计数和恢复结果。固定 EXE、Pages、Release 和 QSPI 沿用主线既有交付。

纯 PHY 的驻留图案数据可用于判断探针侧上限。独立分支在 HCLK128、100 MHz 的 A9 读/写为 SWD **7.485/7.759**（idle0）和 JTAG **6.713/6.713**（idle13，短窗）。这些窗口的图案预装在探针，置于 PC 成绩旁作机制对照。 [纯 PHY 历史与计时边界](../validation/selectio-fusion-20261121/compare100/README.md)

### 可直接复用的离线起点

在融合工作区根目录运行，为每次仿真选新的输出目录。模型 slot 对应仿真引脚延迟。

```powershell
python -X utf8 tools/selectio_cm3.py --swd-only --variable-clock 44 --target-clk-ns 7.8125 --return-ns 16 --swd-slot 22 --idle 0 --wire-budget --swd50-windows --out build/case-sim01-swd73
python -X utf8 tools/selectio_cm3.py --variable-clock 32 --half-rate --jtag-only --target-clk-ns 10.416667 --jtag-slot 21 --jtag-idle 17 --out build/case-sim02-jtag50
python -X utf8 tools/selectio_cm3.py --variable-clock 44 --jtag-only --target-clk-ns 7.8125 --jtag-slot 21 --jtag-idle 25 --out build/case-sim02-jtag73
python -X utf8 tools/selectio_cm3.py --variable-clock 32 --jtag-only --target-clk-ns 7.8125 --jtag-slot 21 --jtag-idle 33 --out build/case-sim02-jtag100
python -X utf8 tools/selectio_etm_sweep.py --mhz 64 72 --duty 45 55 --clock-delay-ps 1600 --out build/case-etm01-late-clock
python -X utf8 tools/selectio_etm_sweep.py --mhz 64 72 --duty 45 55 --clock-delay-ps 200 --out build/case-etm01-early-clock
```

2026-11-23 定向离线抽查通过。SWD 72.727 MHz 完成 512 字 SRAM 与四包 RTT，JTAG 50/72.727/100 MHz 完成 256 字读写。两种协议的 72.727 MHz 摘要均核对为 13.750 ns。SPI 台架通过四个模式及三种长度。ETM 合并两个时钟相对延迟的 32 个样本，64 MHz 通过 32/32，72 MHz 通过 16/32。实板 Case 保留待执行。
