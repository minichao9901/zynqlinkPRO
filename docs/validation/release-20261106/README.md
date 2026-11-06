# 正式交付、工程整理与 GitHub 发布

2026-11-06，F103ZE / J7 限定验收。用户指定使用已改为 public 的原仓库 `minichao9901/zynqlinkPRO`；网页由 gh-pages 托管，完整 Windows ZIP 放 Releases。

## 清理与实现

23 套实验、失败或被替代的 prebuilt 已归档到 `archive/main-before-formal-release-20261106`（清理前 `641f1bce`），[目录清单](evidence/archived-prebuilt.json)。当前保留 release、Golden、QSPI recovery 和目标固件。历史报告的对应链接改为归档引用，问题编号和失败证据保留。业务 Trace 仍只留5份精选记录。恢复缺失的151552 B HSS回放夹具到测试目录，修正 npm 三个已删除脚本引用（ZL-161）。

工作台新增“工程下载”，列出便携完整包、版本、使用步骤及 ETM 本地服务说明。EXE 升至1.3.0，因此需重新冻结。固定目录受 DENY DELETE_CHILD 时，发布器先完整备份并核验程序，再逐文件更新，失败回滚，data 不参与操作（ZL-152）。

PS 添加 WebUSB capability：BOS 57 B / 两项 capability；GET_URL 0x21/index2/value1 返回 HTTPS 原仓库下载页，原 WinUSB 178 B 不变。首个候选的非法请求只返回软件错误，IRQ 调用方忽略该返回值，导致超时；改为显式 STALL 后三种非法请求及后续合法请求、DAP 均通过（ZL-162）。[失败对照](evidence/webusb-rejected-request-timeout.json) · [最终实板](evidence/webusb-live.json)。浏览器提示尚须在正常浏览器/插拔场景验证，描述符通过不等于已观察到弹出通知。

## 固件与实板

正式配对在 [prebuilt/release-20261106](../../../prebuilt/release-20261106/README.md)。bit 是之前已经验收的相同字节，未重新综合；PS 为本轮重新编译。SHA、编译选项和实际源码字节见其 manifest / ps-build / source-binding。

| 检查 | 结果 |
|---|---|
| bit SHA-256 | `dd69106c46a4bd1a52badecbf9125e51beca8435c25d2742cca62323efaaf4e6` |
| ELF SHA-256 | `5895eeb0e79a3681a6b3b966dbea4c82ebfcd01ea7553e094d8a61ed2cf89802` |
| 约束 / 余量 | 133.333333 MHz；setup/hold 0.067/0.044 ns，继承同 bit 布线结果 |
| PS 身份 | 物理 MEM-AP0 的85844 B执行段完全匹配；[OCM证据](evidence/ocm.json) |
| USB | BOS/URL短读、完整读、WinUSB、非法请求STALL、合法请求恢复、4096 B DAP；[实板证据](evidence/webusb-live.json) |
| SWD / JTAG | SWD10 DPID / 固件Flash只读对拍；JTAG1/10 IDCODE、4096 B和实际扫描计数通过，AFIO/运行状态/时钟恢复；[证据](evidence/jtag.json) |
| 原始 SWD | 16次0x1D DPID、ACK与奇偶一致；[证据](evidence/raw-sequence.json) |
| ETM | 24 MHz TRACECLK、100 ms完整DDR/USB窗；119468帧、1911500 formatter B、包错误/丢帧/parser错误0；[完整结果](evidence/etm-smoke.jsonl) |

ETM解码记录1814411 instructions、2 gaps、29727 unknownExecution，保留原始边界，不将零包错误解释为完整执行流。实际控制SWCLK约10 MHz、FCLK119999998 Hz；装载后空闲FCLK为133333332 Hz。频率来自PLL/分频寄存器读回，不是外部频率计。目标CPU/HCLK48 MHz、TRACECLK24 MHz，未改PLL或目标Flash。相同bit的SWD/JTAG60和32 MHz TRACECLK验证继承先前报告，本轮未重测。

开始时发现PL隔离/未配置、USB未枚举。误走“已加载”探测路径读取AXI造成MEM-AP错误，已保存[初始状态](evidence/initial-unconfigured-board.txt)和[错误](evidence/unconfigured-axi-failure.txt)，只复位Zynq后按初始加载路径成功。状态探测现先查PS侧PL隔离/复位，避免未配置AXI访问（ZL-163）；不把本次恢复当成原硬件问题修复。未写QSPI。

## 主机与发布状态

139 Web自测、61 CLI自测、9项发布器/生产C测试通过；869构建依赖身份通过。[Web](evidence/web-tests.txt) · [CLI](evidence/cli-tests.txt) · [主机C/发布器](evidence/host-tests.txt)。

冻结包、匿名下载与Pages上线结果将在完成后补入本报告；当前不把源码通过当成已发布。
