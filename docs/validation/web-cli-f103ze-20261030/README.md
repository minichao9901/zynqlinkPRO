# Web CLI / F103ZE 验收工作记录（2026-10-30）

## 接手时的事实

- 当前工作目录为 `feature/superlink-zynq-web`，接手 HEAD `5805988`。
  `codex/orbtrace-cm3` HEAD `00b9f2f` 已包含在当前分支，另有独立 worktree。
- 已有两处未提交改动：`etm-service/tools/zynq_la.py`（采集质量/恢复）和
  `etm-service/web/app/view.js`（自动检查接收端）。保留，未作为本阶段改动提交。
- 原 `docs/toolbox-cli-ai.md` 指向不存在的 `web/tools/toolbox.mjs`，验证脚本和
  `web/tests/` 也不存在；不能据此认定统一 CLI 已交付。
- 实际存在 Web automation adapter，但页面列表还包含已删除的 SPI/I2C/ADC/SWO。
- 原工作台8898与ETM8766跨源，父页面无法读取iframe和执行CLI；父ETM适配器的
  releaseProbe为空，busy永远false，未接回子页的探针互斥桥。
- 历史资料同时存在“尚未接线”“24MHz已验收”和CLI只能6MHz工作的记载；需按
  实际加载版本和本轮记录复核，不能沿用旧验收结论。

## 第一阶段：统一入口

- 新根目录 `toolbox.py`，参考 superlinkPRO，所有本仓库九页使用统一 page 命令，
  trace 转发到本仓库 `etm-service/trace.py`。
- 同源服务挂载ETM与本机鉴权队列；ETM父子页面接入共享探针所有权。
- catalog --full 从当前 HTML 生成454个静态控件，运行时 describe 提供动态方法。
- Python四项验证通过：目录/二进制传参/运行时限制/同源后端与队列鉴权。
- Node十三项验证通过：命令转交、失败中止、探针选择、事务/断点恢复、取消等。
- 真实浏览器CLI已通过 ping/status、dbg/flash/etm describe、etm state；无页面异常。
  这些是浏览器链路验证，不是板卡功能验收。

## 本轮加载的探针配对

本阶段未修改RTL或Zynq固件，使用已纳入Git的现有实验配对，不是本轮新构建。
通过 `tools/run_xsct.py tools/download_dap_fpga.tcl ELF BIT` 重新加载，避免板上版本不明。

| 项目 | 路径/值 |
|---|---|
| bit | `prebuilt/20261030_orbtrace_oversample_parser/orbtrace_oversample_parser.bit` |
| bit SHA-256 | `230531cef335e6a0b81586be16025fa06bfef28a8106553d6fb8f9296ab09c68` |
| ELF | `prebuilt/20261030_orbtrace_oversample_parser/zynqdap_orbtrace.elf` |
| ELF SHA-256 | `6419c8b00a71b70a1572a55f84c3478f32b67aae8eda95a3821684dc7b3f1a30` |
| 源码/构建/时序 | 配对目录 `manifest.json`，source `43f5524f15431aa288e8b2cfa650b3ebbbbc9c3b`；FCLK100MHz，setup+0.476ns/hold+0.050ns（历史构建报告） |
| 本次JTAG加载回读 | SWD_FEATURES=`0x4450001F`，PACKET_SIGNATURE=`0x53545232` |
| USB恢复 | 重载前未枚举0D28:0204；重载后doctor通过，存在ETM bulk-in 0x82 |

## 待完成

- Chrome/Edge首次USB/串口/HID授权：内置浏览器点击读IDCODE后等待设备选择器超时；
  外部Edge启动被工具环境拒绝。未使用模拟授权或修改浏览器权限绕过此边界。
- 真实 CLI→Web→F103ZE 的串口、调试、RTT、RTT转发、J-Scope、烧录验证。
- 重点：CLI→Web 的完整ETM目标识别、断点、时钟、配置、采集、解码、查看、导出与恢复。
- 原始波形、导出、质量统计和实际FCLK/TCK需要本轮实测证据，不以旧样例代替。

本文件是阶段工作记录；未完成项没有标记为通过。

## 第二阶段：复现与结果语义修复

- 实际浏览器CLI冒烟56条通过（`browser-smoke/results.json`），覆盖九页describe/state/show/read，
  ETM ELF上传、history/target方法发现、set/event、真实Blob导出与分块下载、request/batch/job/ack，
  以及私有方法/非唯一选择器/非法停止按钮拒绝。
- `browser-inventory.json` 保存九页运行时控件和方法；这些动态结果比静态catalog更完整。
- Python回归8项、Node回归14项通过。烧录页面内部捕获错误时，旧高层flash动作仍返回
  programmed:true；现要求本次页面明确显示ok才确认烧录。普通invoke仍需读取业务结果。
- ETM接收端检测从判断zynq对象存在改为检查zynq.ready===true，避免未接入时显示在线。
- 修正原生capture：Trace ID传入目标而非只修改解码元数据；开放SWD控制时钟；保留
  target-before.json原始寄存器快照；解码失败也返回record/quality；拒绝覆盖json-out。

### 真实硬件复测（独立原生工具，不冒充Web硬件通过）

- 旧oversample_parser配对：50ms，23,393 ETM字节；FCLK=99,999,999Hz，TCK=9,999kHz；
  synced/ended=true，loss=false，恢复成功。OpenCSD offset1427遇到BAD_SEQUENCE，退出5。
  因此历史“50ms建议窗口”不能作为稳定解码保证。
- usbfix配对重新加载：bit SHA `15a0ec16c0c62a12c70eb1fb2914e126c13fb4edeafe9048e3cbae47f0ed4193`，
  ELF SHA `6419c8b00a71b70a1572a55f84c3478f32b67aae8eda95a3821684dc7b3f1a30`。
  `native-probe-usbfix-20mhz.json` 和 `native-probe-usbfix-100fclk.json` 均通过RTT/HSS。
  后者名称包含100fclk但**实测仍为78,260,868Hz**，不能按文件名当作100MHz测试；
  实际SWCLK=19,565,217Hz。第二次加载显式指定了prebuilt/ps7_init.tcl。
- RTT21轮/19,965字节逐字节一致；HSS v1/v2单变量和v2八变量逐字节一致、背压计数有效、
  24次DAP上下文检查通过，4KiB SRAM备份/恢复SHA一致。
- 最初在1MHz跑HSS失败，源码HSS配置只接受15..60MHz；RTT本身通过。保留native-probe.json
  作为该未完成HSS运行的证据，不把它整体标为通过。

### 正在构建的RTL修复

旧 `orbtrace_tpiu_stream` 把帧内HSYNC当载荷，并在每帧后只等待FSYNC而丢弃连续帧。
新回归明确使旧实现失败（首帧混入ff7f），修复后连续帧、重复FSYNC、帧内HSYNC、
半字节相位、非法帧内FSYNC恢复/丢失标志通过。异常结构会传播为transport loss。
Vivado构建日志为build/web_cli_tpiu_fix_build.log；本段尚不代表新产物上板验收。
