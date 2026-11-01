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

## 当前交付状态

本记录为开发基线与进行中证据，不代表新的 bit/ELF 已验收。已知可用配对保持原样。
任何新配对均须记录源码、构建选项、真实加载 SHA-256、实际 FCLK/TCK、STA 与板测结果，
明确区分仿真、静态时序和硬件验收。未写 QSPI 或 target Flash。
