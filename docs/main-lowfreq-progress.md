# main 低频 SWD 工作日志

## 2026-10-28：按用户要求暂停，提交实验检查点

**状态：PAUSED。未合入 main；本提交不是正式发布。**
分支 `codex/main-lowfreq-sample`，基线 `d42b60180e82fccb428c51613a0316776c2bc4fc`。
用户要求先 commit、记录状态并暂停。本次只做状态整理和提交，不再综合、下载、测板或调参。
暂停时没有主机侧 Vivado/XSim/Python 测试任务运行。

### 相对 main 的改动

1. 沿用 main 的单 FCLK、LSM 半周期状态机。新增 CFG bit18 接收边界控制，复位为 0。
   短回程模式把 ACK 捕获/解码和 read 数据边界一起前移；write、WAIT/FAULT、read parity 后保留完整 turnaround，覆盖零 idle 和链式请求。
   关闭新模式时保持 main 行为。没有引入 Q16 或独立可编程事件发生器。
2. 固件检查 FCLK 设置返回值，以实际 PLL 分频所得 SWCLK 选窗口：
   `<=30 MHz` 新边界/Q2；`30..45 MHz` 旧边界/Q1；`>45 MHz` 旧边界/Q2。
   按请求频率分档曾在 35.5..37 MHz 留下失败区间，最后改用实际频率并扩大 Q1 区间。
3. 当前板的 SWCLK 从 FAST/8 mA 改为 SLOW/4 mA，SWDIO 保持 FAST/8 mA；生产时钟约束仍为 FCLK 120 MHz。
4. 复用原 16-word forensic RAM，增加在 SWDIO 释放后记录 16 个 FCLK 采样点的旁路诊断：原始输入、Q1/Q2、SWCLK、方向等。
   Vendor 0x88 action2 触发记录；Vendor 0x89 查询/设置 RX 边界。DRIVE/SLEW 未实现运行时寄存器控制。
5. 增加 main 等价比较、Cortex-M0/线级回归、板测和目标状态检查工具；修正 ACK 小模型的 ACK0 发出时刻，给 XPM 仿真模型补 timescale。

### 已取得的验证结果

- 同一 FPGA/目标、同样的 main BD 与 120 MHz 约束，新建并分别构建 main 和本分支；不拿早期缺少当前 RTT/HSS 包缓存的旧工程作资源对照。
- main：setup +0.443 ns、hold +0.013 ns；检查点：setup +0.278 ns、hold +0.034 ns，bitgen/DRC 成功。
  150 MHz 两版均未通过。本轮没有靠降低 main 的生产约束通过实现。
- 整机资源（含诊断）：main 17407 LUT / 22734 FF；检查点 17546 LUT / 22801 FF；均为 6 BRAM、1 DSP、1064 CARRY4。
- 原接收 core 的完整 ARM 回归 11/11、窗口扫描 18 正例+5 预期负例、线级 18 组通过；legacy 累计 974865 个半 FCLK 观察点与固定 main 一致。
  本轮增加诊断采样仿真，以及 30/35/45 MHz、20 ns 返回路径、RTT/HSS 窗口验证；接收 core 与前轮完整回归的源码相同。
- F103 保持原 96 MHz RCC 配置。最终配对在请求 250 kHz..60 MHz 的 28 个频率点全部通过随机 SRAM 读写与恢复：每点每方向 5×4096 B。
  7 个低频/边界点另做每方向 20×4096 B 长测，均通过。
- RTT：最终 1/10/25/35/40/45 MHz 通过；50/60 MHz 的成功会话全部发布字节均收到，序号一致。
- HSS：最终 15/25/35/40/45 MHz 低频点通过；50/60 MHz 单 u32 至 1 MHz、60 MHz 的变化源和 8×u32 120 kHz 窗口通过。
  不能由此概括所有 HSS 窗口均无跳点，具体例外见下文。
- 目标完整 20 KiB SRAM、核心寄存器和 RCC 最终与测试前快照一致；没有编程目标 Flash。
  板上最后加载的是本检查点对应的 bit/ELF，目标保持测试前的 halt 状态。

### 关键对照与尚未解决的问题

- 1 MHz 同 RTL/固件、只变 SWCLK 电气属性的 A/B/A：FAST/8 mA 为错误 ACK=101，SLOW/4 mA 恢复 ACK=001 和 DPIDR；再次切换可复现。
  SLOW/4 mA 下关闭 RX 新边界仍得到错位 ACK=100，说明在当前链路上两项修正均需要。
  内部数字记录证明输入序列受电气设置影响，但没有外接模拟波形，**未证明具体是振铃、串扰或其他模拟机制**。
- 较早校准版本的 10 MHz RTT 曾出现一次 USB 设备掉线，导致后续测试无效；重载并恢复目标后复测通过。
  本轮没有修改 USB transport，也不宣称修复了 USB 掉线问题。失败日志保留。
- 较早校准版本有一次 HSS 单变量 600 kHz/50 MHz 窗口 0.017% 跳点，随后 6×3 s 定向复测为 0。
  最终配对的 8变量 100 kHz/60 MHz 一次窗口仍有约 0.094% 跳点，另一窗口为 0；SWD error=0，数据/计数/时间洞检查通过。
  后者尚未定向复测或唯一归因，按用户要求在此暂停；不能将它隐藏或直接归为主机抖动。
- API 吞吐测量与 main 相差约 -0.02%..-0.34%，RTL 周期数相同、RTT 基本一致；不把有限窗口近似持平说成任何条件下严格零回退。
- 尚未验证跨板/换线、温压、电气余量。30/45 MHz 分档及 SLOW/4 mA 是当前 F103/接线下验证的板级策略，不是所有目标的通用最优参数。
- 原接口限制保留：SWD 最低 250 kHz，RTT 最低 1 MHz，HSS 配置最低 15 MHz；RTT 250 kHz 与 HSS 10 MHz 均按预期返回 -6。

### 合入 main 的建议（尚未执行）

| 改动 | 建议 |
|---|---|
| ACK 仿真模型修正、XPM timescale、回归/板测/状态恢复工具 | 优先单独合入；板测脚本标明 F103 RAM 布局及配对要求 |
| 检查 PLL 设置结果、使用实际频率而非请求频率 | 适合独立合入的通用改进 |
| RX bit18 与完整 turnaround 修正 | 可作为独立、默认关闭的兼容扩展合入，携带等价和零 idle/链式回归 |
| SLOW/4 mA + 自动 30/45 MHz 分档 | 当前板验证有效；建议做板级可选 profile 后再考虑默认启用，不直接推广到所有目标/接线 |
| 内部 16 拍记录和 Vendor 诊断接口 | 可选 debug 补丁，单独审查面积、接口能力识别及文档，不与核心修复捆绑 |
| 整个检查点直接合并、宣布全面无掉线/无跳点 | 不建议；上述未归因项和适用范围应先明确 |

### 检查点与复现材料

- 板测报告：`docs/main-lowfreq-board-20261028.md`。
- 原始 JSON、STA/资源报告与实验失败记录：`docs/measurements/20261028-main-lowfreq-board/`。
- 已测试配对：`prebuilt/zynqlink_lowfreq_checkpoint.bit/.elf`；哈希与源码标识见 `prebuilt/lowfreq_checkpoint_manifest.json`。
- 既有 main 的 prebuilt 文件未覆盖。大型工程、DCP、完整日志和 RAM 备份仍在被 Git 忽略的 `build/`；提交中的配对和测量记录可独立保留。
- 本提交仅冻结当前工作，不执行 merge，不继续新的配置帧/驱动动态切换方案。后续需用户明确恢复工作。
