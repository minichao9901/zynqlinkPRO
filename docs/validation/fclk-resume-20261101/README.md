# 时序优化接手与验收记录

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

Golden SWD 25/60MHz的普通SRAM矩阵均通过；JTAG两档均读到全零IDCODE，
因此当前没有有效JTAG硬件基准，等待确认TDI/TDO/nTRST接线。没有把该故障归因于候选。
JTAG数字仿真已通过并与Golden一致。未写QSPI或目标Flash。

## 当前交付状态

本记录为开发基线与进行中证据，不代表新的 bit/ELF 已验收。已知可用配对保持原样。
任何新配对均须记录源码、构建选项、真实加载 SHA-256、实际 FCLK/TCK、STA 与板测结果，
明确区分仿真、静态时序和硬件验收。未写 QSPI 或 target Flash。
