> 最新交付：用户选定的133.333 MHz已完成配对产物、完整已定义STA和F103范围板测，见133.333 MHz验收（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/fclk-resume-20261101/release-133/README.md`）。ETM输出与60 MHz RTT并行场景仍有原Golden也存在的失败，详见报告；下文150/135/138 MHz为历史过程记录。

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

# 时序优化接手与验收记录

**最终阶段结果：150MHz尚未闭合，已停止新增高频实现。** 最后一轮来源`e749c42`，
WNS=-0.259ns、TNS=-6.006ns、71个setup违例端点；DDR路径+0.032ns、200MHz域+0.363ns。
同一路由138.461MHz的已定义完整时序检查通过（setup+0.297ns、hold+0.033ns），但没有生成/加载新bitstream，不能称为已上板频率。
当前板上仍是原Golden配对。固定尾部100MiB与新固件已实现并通过仿真/链接检查，实际新配对的生成、100MiB读回与1～2秒上板采集尚未验收。
详见[最终评估](final-evaluation.md)，后续需选择138.461MHz作为实际验收目标或另行授权继续150MHz；没有自动降频发布，也没有扩展到160MHz以上。

接手分支 `codex/fclk-resume-20261101`，基线提交 `244ab7136cb810b0103af44bffb29450efd4d2de`。
该提交包含已完成的桥接交付 `5cf5e17` 和 debug/release 开关 `a59d158`。
接手时主目录 tracked 文件干净；旧时序工作树唯一未提交修改是 `fpga/verify_routed.tcl`，已审查并在当前工程接续，旧工作树未修改。
只读进程核对只见既有 `hw_server`，没有 Vivado/XSim/板测任务运行。未终止进程，未清理或重置旧工程。

Golden 配对保持原文件：`prebuilt/golden/probe.bit` SHA-256
`1da17cb60175bbc2b7abd647770c7053bd7b7097e0d38aa819fb89678d564473`；
`application.elf` SHA-256 `e977914c2924ab4cac13f4075de0a5108d1e2e8cf48966fb8fbdea3a358e0b2c`。
其 RTL 源码为 `954de8fd09f4a97aafb7dc42fa5e4a9a019c3f19`。ETM 已验收 24MHz 基线仍为
`prebuilt/etm-ddr-usb-raw4-20261101`，后续 lane-delay 研究镜像不能替代业务 Golden。

## 顺序与配置

先运行 `tools/compare_fclk_sim.py --out build/fclk-resume-20261101/sim --phase golden`，
再运行 `--phase candidate` 和 `--phase compare`。Golden DUT 从明确 Git revision 导出，
两侧共用当前测试台、真实 CM3 模型和相同 PL/外部时钟、target HCLK、返回延迟及 1024-byte 事务。
SWD 使用已验收 60MHz 档位的 legacy 返回配置（rx_boundary=0，模型返回延迟 16ns）；
rx_boundary=1 与该延迟组合的首个探索点 ACK=3，不能作为 Golden 基准或候选回归结果。
仿真有效吞吐、周期数、WAIT、HSS 产出/跳采均记录；不模拟 USB/PS/线缆模拟电气特性。
HSS 硬件将最小周期限制为 24 个 24MHz tick，即配置上限 1MHz；低于 24 的请求会被钳位，
不能把 period=1 的打印值宣称为实际周期。采用产品支持的最小周期 24，并对比有效产出和跳采。
SWD 在该产品配置上限未饱和；JTAG 已出现跳采。另有较低请求率对照点，是否零跳采以实测计数为准。

候选仿真通过且性能不退化后，才运行新的综合/实现。保留 7ns SWCLK pad 预算和真实 CDC/IO 约束，
按 DDR、调试、CDMA、200MHz 参考域分别记录 setup/hold，另存 recovery/removal、CDC 和异常约束报告。
正式构建 `ZYNQLINK_RTL_DEBUG=0`，实际目标频率未闭合必须失败，禁止通过自动降频发布“通过”镜像。
阶段顺序：120MHz 基准 → 150MHz → 163.636MHz（IO_PLL 实际可实现档位），再按剩余裕量决定下一点。

第一轮源码变化仅把 DDR mode/record_mode 限定为合法两位编码，以及按合法连续 keep 直接解码字节数，
去除 32 位 mode 比较及通用 popcount 链。未在串行事务间增加空拍，未更改 B 响应提交语义。
写入 92 例、控制器回归及 RAW4 到 DDR 的 9 例集成仿真已通过。候选时序与板测尚待完成。

## 已完成仿真

最终报告与原始日志保存在 `simulation/`。两侧名义外部链路60MHz、FCLK120MHz，
真实 CM3 target HCLK=100MHz，1024-byte payload，源码/测试台身份匹配。
测试台时间精度为1ps，4.166667ns半周期实际量化为4.167ns；实际仿真FCLK约119.990401MHz、
外部链路约59.995200MHz，两侧一致。周期数以实际8.334ns周期换算，不能用理想120MHz换算。

| 指标 | Golden | 候选 | 结果 |
|---|---:|---:|---|
| SWD SRAM写 MB/s | 5.186803 | 5.186803 | 一致 |
| SWD SRAM读 MB/s | 5.187460 | 5.187460 | 一致 |
| SWD RTT MB/s | 4.959242 | 4.959242 | 一致 |
| JTAG SRAM写 MB/s | 2.539899 | 2.539899 | 一致 |
| JTAG SRAM读 MB/s | 2.540057 | 2.540057 | 一致 |
| JTAG RTT MB/s | 2.446346 | 2.446346 | 一致 |
| SWD HSS最小周期有效 Hz | 999987.209841 | 999987.209841 | 均无跳采 |
| JTAG HSS最小周期有效 Hz | 571382.860800 | 571382.860800 | 均42.857143%跳采 |

较低请求率的第二个HSS点亦一致：SWD 888870.882085Hz/0跳采，
JTAG 506545.089361Hz/1跳采（0.793651%）。这不是零跳采上限的完整扫描。
这些结果为不含USB/PS的RTL仿真，不能替代真机吞吐或证明更高FCLK已稳定。

## 实际构建推进

`b96527e`固定首轮DDR结构变化，`3725cef`强制完整且源码匹配的仿真门槛，
`becba61`修复新建BD时把DDR ref_clk误接到FCLK0的既有脚本问题；参考域保持200MHz。
完整重建已实际尝试150MHz。早期多轮在IP GUI Tcl解释器创建/读取处退出，
失败点包括AXI protocol converter的xgui Tcl、CDMA所需tm.tcl、新建swd_controller xgui，
以及缓存工程对PS属性重配置时的aximm子解释器。所报文件均能独立读取，独立厂商IP创建探针通过；
没有把这些错误归类为150MHz时序失败。

切回既有 `tools/run_vivado.py` 启动适配器后，完整BD校验与IP生成通过并进入综合；
该次目录为 `build/fclk-resume-20261101/implementation-150-repo-launcher-v2`。
预检211项DLL依赖，不需新增安装文件，实际安装新增记录为 `[]`。
隔离复制的已验收BD/IP输入缓存排除了旧bit/ELF/DCP、旧运行目录和验收元数据，
源码路径全部指向当前工作树，依靠源码戳重新综合，绝不以旧产物代替本次构建。
完整输入和过程记录位于 `build/fclk-resume-20261101/`。

只读JTAG发现APU、两个Cortex-A9和xc7z020，连接可用。随后确认采集与流状态均空闲，
明确加载原Golden bit/ELF，并以物理MEM-AP0读取OCM代码，逐段匹配该ELF。尚未加载候选配对。

## 当前现场 Golden 真机基准

证据见 `board-golden/`，实际FCLK=119999998Hz、SWCLK=59999999Hz。
使用512-word块、32深度USB流水，三轮峰值与10秒交替读写：SRAM读4.830683MB/s、写4.745757MB/s，
10秒中位数读4.829779、写4.746131MB/s；完整字节验证和RAM/RCC恢复通过。
RTT三轮2秒、1024-byte块，主机中位数4.648627MB/s，序列精确、已发布数据全部收到、错误数0，
目标RAM/寄存器/RCC均恢复。

HSS在最小周期24（请求1MHz）完成三轮2秒零跳采验证，所有帧和样本计数一致。
另一次峰值重复出现2121次跳采（0.105954%），其余峰值重复和零跳采验证为0；保留该坏点，
不能把整个过程概括为从未跳采。该项将与候选按相同条件比较。

Golden SWD 25/60MHz的普通SRAM矩阵均通过。JTAG初次两档均读到全零IDCODE；
用户确认接线齐全后，只读比较目标Flash的两个加载段（20040+128字节），
与 `prebuilt/golden/f103ze-cdc48.elf` 完全一致。其MSP源码明确执行SWJ_NOJTAG。
使用仓库既有 `run_f103_jtag_fixture.py --restore-swj 2` 临时启用易失JTAG配置，
IDCODE恢复为0x3ba00477；夹具按已核实源码恢复SWJ设置，因为该字段不能可靠读回。

JTAG 25/60MHz SRAM矩阵和60MHz峰值均通过：峰值读2.421895MB/s、写2.397811MB/s。
JTAG HSS峰值610500.674Hz、跳采0.793661%；三轮验证的最高零跳采请求率为324324.324Hz。
所有帧/计数、目标RAM、AFIO可读位、APB使能、RCC及运行/暂停状态恢复通过。
同一现场的Golden 60MHz JTAG RTT出现错误计数2，未形成有效吞吐结果；已保留失败JSON，
其目标RAM/寄存器及外层夹具状态恢复均通过，没有为通过该项改变target时钟或擦除坏点。
此为Golden当前现场限制，不能归因于尚未加载的候选，也不能把JTAG RTT写成通过。
JTAG数字仿真已通过并与Golden一致。未写QSPI或目标Flash。

## 当前交付状态

第二轮 RTL 源码提交 `a303a70`，原始仿真日志补充在 `5740d04`。完整 Golden 对比位于
`iteration2-simulation/comparison.json`：60MHz SWD/JTAG 的 SRAM 读写、RTT、HSS 共十项指标与 Golden 一致。
DDR writer 92 项、RAW4 集成、1022/1023 字包边界、SWD 线级周期预算、JTAG/RISC-V 延迟输入及 posted-read 收尾回归均通过。
本轮 150MHz release 完成全部子模块与顶层综合，正在完整布局布线，尚无新 bitstream 验收结果。

Golden 25MHz JTAG RTT 补测三次通过，主机速率中位数 0.976324MB/s，精确序列、全部发布字节接收及恢复均通过；
此补充不撤销 60MHz 的失败记录。四象限 DDR 样本地址 `0x00800000/0x10800000/0x20800000/0x30800000`
相互独立，四处各16字节测试后全部恢复，OCM 身份为原 Golden。该检查仅排除这些采样地址别名，不等于完整容量验收。

本记录为开发基线与进行中证据，不代表新的 bit/ELF 已验收。已知可用配对保持原样。
任何新配对均须记录源码、构建选项、真实加载 SHA-256、实际 FCLK/TCK、STA 与板测结果，
明确区分仿真、静态时序和硬件验收。未写 QSPI 或 target Flash。
