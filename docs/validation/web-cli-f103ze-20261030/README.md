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
