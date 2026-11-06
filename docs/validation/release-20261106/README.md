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

139 Web自测、61 CLI自测、10项发布器/生产C测试通过；869构建依赖身份通过。[Web](evidence/web-tests.txt) · [CLI](evidence/cli-tests.txt) · [主机C/发布器](evidence/host-tests.txt)。

EXE 1.3.0 已从干净提交 `4d87c78cafd9a38ed35333c7ff176177fe8e0f62` 冻结，1824个包文件逐项校验；F103/H743离线解码、查询、HTML导出及重复启动复用通过，无系统Python/Node、硬件路由关闭。[冻结验收](evidence/frozen-verification.json) · [交付摘要](evidence/package-summary.json)。固定程序已更新，49份用户data文件路径和SHA全部保持一致。实际本机更新使用普通目录重命名成功；新增ACL回退目前为专项模型覆盖，不能据此声称真实DENY ACL场景已关闭。

[原仓库在线页面](https://minichao9901.github.io/zynqlinkPRO/#download)已由gh-pages提交 `d603898b28bf945bb50a28b69847808cfd4ab8b5` 发布，Pages状态built，匿名首页200；浏览器完整初始化、下载链接及布局通过。[网页截图](download-page.jpg)。初次静态发布受Windows Git autocrlf影响，index/main.js字节与manifest不符，现通过静态分支 `* -text` 保留字节，145个Git blob逐项SHA一致，4个在线关键资源也匹配（ZL-165）。[字节验证](evidence/site-byte-verification.json)。

[Release v1.3.0](https://github.com/minichao9901/zynqlinkPRO/releases/tag/v1.3.0)已公开，完整ZIP为54391206 B，SHA-256 `5ba2605e93218625ff4f610d6fdc6bdbf8bcecf932bbc306c87f03f719792777`；匿名从latest固定链接完整下载并逐字节哈希一致。[上线及下载证据](evidence/published.json)。大包先经urllib与普通curl两次连接中断，限速1 MiB/s流式上传成功，草稿查询改为兼容未创建tag的草稿；失败与成功日志保留（ZL-164）。网络中断的根因未定，不声称限速解决所有网络故障。

本地29个旧输出目录共41.291568 GiB已可逆移至 `E:/zynqlinkPRO-local-archive-20261106`，没有删除用户唯一记录或共享缓存，[移动清单](evidence/local-archive.json)。前后两次Git归档tag均已推送，历史报告中的失败和暂停结论继续有效。工具及根README导航收敛到当前正式入口。

最后板上仍为上述正式bit/ELF，目标CPU/HCLK48 MHz、TRACECLK24 MHz；SWD配置读回FCLK119999998 / SWCLK约10 MHz。所有采集/DDR/DMA/RTT/HSS空闲，DHCSR最终 `0x01010000`，目标运行；原始序列测试使C_DEBUGEN为1，已按最初控制位恢复为0并读回。RCC与初始匹配，未写目标Flash/QSPI。[最终板状态](evidence/final-board.json)。测试EXE和本任务9017预览服务均已停止，保留共享hw_server。

用户要求删除刚创建的空仓库 `zynqlinkPRO-web`。当前Git凭据仅repo/workflow，无delete_repo，删除API返回403；本机浏览器窗口激活也失败，因此该删除尚未完成，需要账号管理页面操作。此仓库没有发布网页或上传产物，所有正式链接已使用原仓库。
