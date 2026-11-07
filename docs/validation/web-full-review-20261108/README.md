# Web 工作台完整审查

2026-11-08，Asia/Shanghai。审查入口为 `web/index.html` 的九个页面及 `etm-service/web`，包括连接、资源交接、目标控制、文件导入、数据显示、导出和失败恢复。开始时 HEAD 为 `9f9435b9`，审查过程中另一会话提交迁移为 `18dd2ce9`，最终结论已核对该提交。原有未提交 ZL-170 文档条目属于其他工作。

本轮完成源码审查、浏览器入口检查和离线故障复现。没有操作板卡，以下硬件影响均标明静态依据或待板验。没有修改产品实现。

## 按优先级排列的发现

### ZL-173 · P1 · ARM 断点清理失败会丢失恢复依据

位置为 `web/app/dbg/session.js:1031` 的 `bpAdd`、`:1044` 的 `bpDel`、`:1054` 的 `bpClear`，以及 `:201` 的 `disconnect`。

三个操作都先修改 `bps/bpNotes` 再写比较器。特别是 `bpClear()` 先清空数组，首笔 USB 写失败后硬件断点仍可能存在。下一次 `disconnect()` 因 `bps.length===0` 跳过清理并释放会话。添加失败则相反，UI 表里已有断点，重试会得到“已经有断点”。比较器回读不符也只记 warning，调用者仍得到成功。

离线复现用一个已登记断点，让 `_programFpb()` 抛错，`bpClear()` 拒绝后本地数组已为空。应保留事务前状态和未确认清理集合，成功回读后再提交状态。上板需在部分比较器已写入后注入失败，重试断开并检查全部 FPB 寄存器与目标状态。此问题也表明 ARM FPB 仍由 JS 直接维护，OpenOCD 的断点表不能代为恢复。

### ZL-174 · P1 · RTT 连续发送可相互覆盖

位置为 `web/app/rtt/view.js:748` 的 `_sendBytes`、`:655` 的终端输入回调，以及 `web/app/rtt/protocol.js:401` 的 `writeDown`。

快速键入或连续点击发送时，多个 `writeDown` 可以同时执行。WASM 会话只串行单条命令，不能保护“读取 WrOff → 写数据 → 推进 WrOff”整笔事务。两次发送都读到相同 WrOff 后会覆盖同一位置，两次均返回成功。

离线模型并发发送 A/B，两次返回 1，数据都写到 `0x20000100`，两次发布的 WrOff 都是 1。应按 RTT 实例/通道串行发送，并在复位、重新扫描和断开前排空写事务。上板需检查快速键入、跨环边界粘贴和发送中复位后的目标实际字节序列。

### ZL-175 · P1 · 读 IDCODE 和 RTT 连接会重置现有调试配置

位置为 `web/app/flash/view.js:212` 的 `_openTarget`、`:275` 的 `readIdcode`，`web/app/rtt/view.js:327`，`web/app/core/openocd-probe.js:44` 和 `web/app/core/openocd-profile.js:43`。

读身份和 ARM RTT 都建立完整 `cortex_m` 目标并执行 `init`。本地配套 OpenOCD 源码 `src/target/cortex_m.c:3015–3043` 显示首次 examine 会写 DEMCR、配置 ITM、清 FPB 比较器。两个页面均没有备份恢复这些寄存器。已有的 `OpenOcdEtmProbe` 专门采用 `mem_ap`，其注释也明确记录了相同副作用。

静态复现路径为读 IDCODE → `_usingTarget(false)` → `_openTarget(false)` → `connect/init` → Cortex-M examine。目标已有 Trace、vector catch 或外部设置的 FPB 时，读身份/连接 RTT 就会改变现场。应为只需内存的操作采用适当的 MEM-AP 路径，或显式管理完整快照。上板需预置 DEMCR/ITM/FPB 后分别执行身份读取、RTT 连接和断开并核对差异。本轮未宣称实板已复现。

### ZL-176 · P2 · DHCSR 动态位变化被误判为时钟不可靠

位置为 `web/app/dbg/session.js:183` 的 `verifyClock`。

该函数对连续三次 DHCSR 整字要求完全相同，否则将选定时钟改到 1 MHz。DHCSR 包含运行过程中可变化的 S_RETIRE_ST、S_SLEEP 等位，正常运行不能保证整字恒定。迁移 WASM 后仍保留这段旧探针降频策略。

离线输入 `0x01010001 / 0x00010001 / 0x01010001`，函数确定调用 `setClock(1000000)`。应仅依据适合验证传输的稳定字段或独立读写证据决定失败处理。上板需在运行、睡眠切换及暂停状态下核对请求频率、实际 FCLK/SWCLK 和日志，避免把正常状态变化记录为链路故障。

### ZL-177 · P2 · RTT 自愈仍调用旧驱动接口

位置为 `web/app/rtt/view.js:547`、`:577`，`web/app/rtt/protocol.js:76`，以及 `web/app/core/openocd-probe.js:103`。

页面在连续错误时提示 SWD 重激活/重开 USB，却调用 `recover?.()`、`reopen?.()`。新后端只有 `recoverDebugPort()`，可选调用静默跳过。`fast` 与 `_strict` 的旧快速/严格档逻辑对新后端也没有作用，注释仍承诺双读和写回读。

离线检查实际 `OpenOcdProbe` 实例的两个方法均为 undefined。复现可让 RTT 连续返回 corrupt 或 FAULT，观察“正在自愈”时没有恢复事务。应明确新后端的恢复协议、现场保留和错误提示，并删除失效分档。恢复涉及重新 examine 的副作用，不能直接把方法改名视为完成。需上板验证恢复后控制块、字节顺序、目标配置和 USB 所有权。

### ZL-178 · P2 · 硬件 JSP 回放依赖当前变量选择并可能报告假成功

位置为 `web/app/scope/view.js:1818` 的 `replayFile` 和 `:1615` 附近的 DEF 处理。

HOST_POLL 文件从 DEF 建立变量表，但硬件 HSS 文件仍用当前 selected 或八路 mockVars 创建缓冲。打开两路记录而当前只选一路时，DEF 校验禁止解码，末尾却覆盖错误为“回放完成：0 个样本”。同数量但类型/地址不同的选择还需检查通道命名和存储类型一致性。

附带复现生成两路 DEF/DATA，当前选择一路，结果确认 defMismatch 非空、样本为 0、最终仍显示完成。应让所有格式以文件 DEF 为准，匹配名称时校验地址和类型，失败保留错误状态。此问题离线即可验收，补充历史文件跨变量组合、空选择和损坏 DEF 回归。原 ZL-135 处理的是停止后 DATA 守卫，根因不同，原关闭证据保留。

### ZL-179 · P2 · 低频 WASM 仍展示硬件采样计划及标定动作

位置为 `web/app/scope/view.js:646` 的 `updatePlan`、`:1427` 的 `bench`、`:1504` 的 `applyRecPeriod`，以及 `web/index.html` 的采样设置。

浏览器选择自动模式、周期 10000 µs，页面依然建议 17 µs/58.82 kHz，显示“标定真实速率”和“用建议周期”。这些计划来自探针 HSS 的成本模型，标定实际调用私有 HID。接受建议会把周期降到 10 ms 阈值以下，后续自动选择硬件采样。计划详情仍称时间来自目标侧，与 WASM 的主机时间戳不一致。

应让建议、标定、批次和暂停 CDC 选项随有效采样路径更新，明确修改周期引起的路径变化。浏览器已复现提示错误，修复显示无需板卡；两条采样路径切换后的时钟、采样来源和资源恢复仍需上板。

### ZL-180 · P3 · 旧目标驱动、测试和自检入口未随迁移收敛

从主页面 `main.js` 和 ETM `view.js/standalone-flame.js` 沿静态及字面量动态 import 检查，发现以下旧目标栈未被生产入口引用，仍随前端发布。

| 文件组 | 当前用途与清理要求 |
|---|---|
| `web/app/flash/runner.js`、`algos.js`、`data-clock.js` | 当前烧录页使用 `openocd-program.js`。旧 runner 仍被 `flash-default-clock.test.mjs` 测试，这些测试不能证明当前烧录器默认档行为 |
| `web/app/dbg/riscv.js`、`web/app/rtt/riscv-mem.js` | 新入口分别使用 OpenOcdRiscvSession 和 OpenOcdProbe，旧整套目标会话未被入口引用 |
| `web/app/flash/hpm/{algo,chips,dap-transport,entry,flash,jtag,native-memory,riscv-dm,xip-copy}.js` | 旧烧录/DM 栈，少量文件仍被历史单元测试直接导入。先迁移有价值的协议测试，再移出生产分发或删除 |
| `web/app/rtt/dap-webusb.js` | 新生产路径仅为复用 `withTimeout` 而仍导入约 1700 行旧 DAP 驱动。应先提取公共超时工具，保留诊断/对照工具实际需要的旧驱动 |
| `etm-service/web/app/shared/rtt/dap-webusb.js` 及其旧依赖 | ETM 已改用 OpenOcdEtmProbe，旧共享驱动仍在同步/分发清单。保留共享 source/bp/USB 基础设施，按引用关系逐项收敛 |
| `web/app/main.js:185` 附近 | `?selftest=1` 动态导入已不存在的 `tools/selftest/ui.selftest.mjs`，得到 selftestError。生产测试入口需要恢复或移除，沿用 ZL-161 的入口清理主题 |

另外，`core/bus-periodic.js`、`core/expr.js` 和若干旧 pin-map/reg-grid/spark UI 文件也无上述生产入口引用。引用图只能证明所检查入口的可达性，删除前仍需核对 CLI、测试和直接 URL 消费者。

ARM FPB/DWT、RTT 环协议和 ETM CoreSight 配置仍在 JS 中，底层内存访问经过 WASM。这属于迁移层次的实际边界。FPB 的事务缺陷见 ZL-173，RTT 协议缺陷见 ZL-174。原生数据下载、浏览器渲染、ELF/DWARF UI 解析有独立职责，无需仅因它们使用 JS 就认定为冗余。

## 页面覆盖与待上板项目

| 页面/能力 | 本轮覆盖 | 后续验证 |
|---|---|---|
| 串口助手、终端 | 共享 SerialSession、发送队列、关闭/取消、显示缓冲、保存源码与浏览器入口 | 实串口收发、断线/重连、CDC 模式交接和落盘完整性 |
| RTT Viewer | 连接/扫描/轮询/发送/复位/清理，发现 ZL-174/175/177 | F103/H743/HPM 实环数据、缓存与恢复 |
| RTT 转发 | HID 请求关联、启停确认、CDC 排空和模式仲裁 | ZL-140 等已有启动边界，真实尾字节及跨页切换 |
| J-Scope | 两条采样路径、原始包/CSV/触发/回放/质量摘要，发现 ZL-178/179 | ZL-172 低频与 HSS 交接、实际频率、尾计数、变量值 |
| 烧录器 | 解析、区域预检、扇区保留/校验、CFG、身份/复位，发现 ZL-175 | 全部受影响扇区读回、失败中断、目标恢复；新型号 CFG 支持须逐型号验证 |
| 调试器 | ARM/RISC-V 控制、寄存器、内存、FPB/DWT、异常/源码路径，发现 ZL-173/176 | 断点清理注入、连续步进、复位状态、寄存器/cache 一致性 |
| ETM | 内嵌服务就绪、目标控制/采集交接/恢复与历史分析代码；浏览器历史列表和离线控件就绪 | ZL-171 的 F103/H743 现场恢复、完整窗口与首屏；原 ZL-011/006 范围继续保留 |
| 工程下载 | 页面入口、release 链接与本地 staging 实现 | 本轮未访问远端 release，未核验下载包与当前源码一致性 |
| 全局资源管理 | ProbeManager、USB lease、跨页释放和失败保留 | WebUSB 与本机代理的实设备占用/拔插矩阵 |

ZL-172 最新报告已记录用户确认保留私有 HID 和高速回传。RTT 转发、HSS、复位输出模式及通用串口按该边界保留。ETM 网页联动移交服务后的 CPU 放行仍走原生 DAP，而源码独立 Trace CLI 已走 WASM。该差异继续挂在 ZL-172 的能力边界中，不能将独立 CLI 迁移成功推及网页联动。ZL-170 的旧 Web README 仍需同步。

## 验证记录

- `python -X utf8 toolbox.py project run web.check` 通过，共享副本一致，179 个模块语法通过。
- `python -X utf8 toolbox.py project run test.web` 149/149 通过。
- `python -X utf8 toolbox.py project run test.cli` 最终 63/63 通过。首轮较早快照为 62 项。存在 Flask 弃用提示和临时文件 ResourceWarning。
- `node docs/validation/web-full-review-20261108/reproduce.mjs` 通过全部缺陷存在断言。脚本是审查证据，修复后相应断言应失效。
- 本机源码服务、原生硬件访问关闭，在内置浏览器检查九页导航，初始化摘要 errors 为空。另确认 ETM iframe 服务就绪及历史列表、低频 J-Scope 建议错误。Edge 浏览器连接器不可用，使用内置浏览器完成入口检查。

浏览器入口正常及既有自测全通过的范围有限。故障注入揭示的事务缺陷仍待修复，硬件数据、Flash 擦写和真实恢复尚待板验。审查临时服务在收尾停止。
