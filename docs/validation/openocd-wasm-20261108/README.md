# OpenOCD Wasm 工作台迁移

2026-11-08，北京时间。参考 superlinkPRO `f2fa8ca` 的 Worker、目标脚本和 HPM 验收，以及 `5fc3cc6` 的共用 Flash、RTT、原版 CFG 实现与 F103ZE、H743、HPM6800EVK、RP2350 报告。该仓的板测使用 akaLinkPro。Zynq 工作台验收范围以下表为准。 [运行时指纹与源码](../../../web/app/core/openocd-runtime/README.md)

调试器、烧录器和 RTT Viewer 共用 OpenOCD。浏览器 Worker 通过现有租约向页面请求 USB 操作。本机代理沿用 owner 与 resourceEpoch，仅增加标准 USB 描述符读取。Zynq 的 DAP 为接口 0、OUT2、IN1，保留 IN2 的 ETM 通道和 IN7 的 HSS 通道。正式固件使用 DAP 队列新 epoch 与空闲回读，短于 4096 字节的整 USB 包写入补 ZLP。RTT 转发、J-Scope、ETM 和独立 Trace CLI 使用各自已有的专用数据通路。

| 离线项目 | 范围 |
|---|---|
| WASM 本体 | 运行浏览器版 OpenOCD。注册 F103、H7、HPM、nRF52、RP2350 的目标和 Flash driver，解析含变量与相对依赖的 CFG，拒绝越界目录 |
| Edge 工作台 | 真实页面加载 `.mjs` 和 `.wasm`，导入 CFG 后烧录器和 RTT Viewer 沿用同一核心。另解析 HPM SDK 1.11.0 的原版入口及上游 RP2350 双核 CFG |
| 模拟 USB | 浏览器 Worker 通过描述符选中接口 0、OUT2、IN1，完成 CMSIS-DAP Info 交换。夹具故意返回无 SWD 能力，建链报错后接口与设备均关闭。模型另核对 ZLP、队列 epoch、禁止访问 ETM 端点和原生描述符请求隔离 |
| Flash 安全模型 | 固件所有地址在擦除前预检，保留未覆盖的扇区字节，烧录后比较完整扇区 |
| 既有入口 | Web 142/142、CLI 62/62、176 个模块语法检查、共享驱动检查及 `trace doctor --offline`。Edge 首轮发现 RTT 初始化仍引用旧类名，修正后重新加载通过 |
| 静态站点候选 | `build/openocd-wasm-20261108/pages-candidate/`，运行时 JS 和 WASM 与 Git blob 的 SHA-256 一致 |
| Windows 候选 | `build/openocd-wasm-20261108/windows-candidate/zynq-etm-bridge.exe`，校验 1840 个包文件及 HTTP 的 Worker、WASM 类型和指纹。冻结 EXE 的 F103ZE、H743 保存记录分别解码 5,467,740 和 210,497 条指令，原生 TraceStore 和 Web/CLI 火焰图对账通过。Edge 从冻结 EXE 的鉴权页面重跑上述 CFG 和模拟 USB 检查 |

Windows 候选来源为 `b24dfa73a354e3231d867f86b8b9727097ed48c6`，EXE SHA-256 为 `7e51b288fb4ce839e95fcb2914099577cf635ce2b963fd31da8ea6413811103d`。构建时工作区有一条原有的未提交问题记录，故清单标注 `sourceDirty:true`。候选使用独立目录，可直接启动并保留其 `_internal`。冻结 Edge 夹具先以端口 0 和无鉴权 URL 启动失败，改为有效的空闲端口与启动器提供的 URL 后通过。

## 上板验收顺序

1. 核对 J7 实际运行的 bit/ELF、探针独占状态和目标 ELF。分别用本机代理和浏览器直连核对端点、DAP 握手、时钟请求与实际读回。
2. F103ZE 与 H743 先做身份、运行态内存、暂停、寄存器、四断点轮转与源码步进，核对断开时的断点清理和运行态。烧录先备份目标扇区，再验证擦写、逐字节读回及复位，结束后恢复备份。H743 的 RTT 控制块采用已知 AXI SRAM 夹具。
3. HPM6800EVK 比较内置板型与原版 SDK CFG。核对 TAP、实际 TCK、运行态 SBA、暂停寄存器、硬件断点、NDM reset、RTT 双向及 XPI 扇区读回。其它芯片按实际可用设备逐项验收。
4. 分别从运行中的 WASM 调试器或 RTT Viewer 交接给 RTT 转发、J-Scope 和 ETM，再接回调试器。记录交接、数据质量、原目标状态恢复和实际配对。

本轮未接入硬件，兼容性结论限于配置加载和离线模型。新增跟踪项为 ZL-171。

## ETM 网页控制补齐

上面的首个候选只切换了三项工具。后续候选将内嵌和独立 ETM 页的 SWD 控制也接到同一份 WASM。目标识别、暂停/继续、Flash 校验、CoreSight 配置、入口断点和采后恢复通过物理 MEM-AP0。采用 OpenOCD 的 `mem_ap` 目标类型，避免 Cortex-M 首次检查重写 DEMCR、配置 ITM 和清空 FPB 比较器。ETM 原有的目标识别、寄存器所有权与回读仍由 ETM 页处理。

网页释放 WASM 会话后，原生服务仍负责布防 FPGA 和放行 CPU。采后 WASM 仅重连原探针并沿用所选 SWD 档。离线测试覆盖 250 kHz 的真实 WASM 配置、10 MHz 默认档、1 MHz 对照档、释放失败保留所有权、拒绝用另一支探针恢复，以及 DHCSR 单次放行。旧网页驱动的 HTTP 原子交换、批量内存和寄存器对照开关不用于 WASM 会话。

板验仍需以 F103ZE 和 H743 分别验证 AP0/实际时钟、采集前后 FPB/DEMCR/RCC 状态、起点和配置恢复、完整窗口及数据质量。原生 `trace capture` 的独立入口继续使用 Zynq 原生控制与采集。

新版候选为 `build/openocd-wasm-20261108/windows-etm-candidate/zynq-etm-bridge.exe`，来源 `85fd9cc6c9d90a6a35f7e3e38dda10c10501a3b5`，EXE SHA-256 为 `42d71bbf33e71dbf10ddbc7aa42e93ed44f3703b38d2b6ca90860024871d39c3`。Web 145/145、CLI 62/62、177 个主页面模块语法检查和 ETM 改动模块语法通过。冻结包校验 1841 个文件、两条离线 Trace 记录以及内嵌和独立路径的 WASM 资源。Edge 从冻结 EXE 页面核对了内嵌 ETM 后端，独立路径启动真实 Worker 并返回 `mem_ap`。离线硬件访问保持禁用。

## 所有控制和低速通道核查

以 `85fd9cc6` 的实际入口为准。superlinkPRO 的 `dc3d4e9` 也仍由 J-Scope 调用 `AkaLinkHid.xfer`，其验收报告将 WASM RTT 与探针高速采样分开。两仓均未达到所有控制和低速通道走 WASM 的要求。

| 入口 | 实际控制和数据路径 | 迁移状态 |
|---|---|---|
| 调试器、烧录器、RTT Viewer | `OpenOcdProbe`、WASM Worker、CMSIS-DAP。RTT 上下行经 WASM 读写目标环。烧录后的目标软件复位在 WASM 会话中完成 | 已切换，待实板 |
| ETM 网页目标控制 | `OpenOcdEtmProbe` 的物理 MEM-AP0。读写、暂停/继续、入口与配置恢复均用它 | 已切换，待实板 |
| ETM 联动采集、独立 `trace capture` | 网页移交后，`zynq_la.py` 经原生 DAP 和 EP0 厂商请求布防、放行及查询；`zynq_ddr.py` 管理 DDR 下载；OpenCSD 做离线解码 | 联动控制和独立 CLI 的目标控制待迁移。高速回传单独核算 |
| J-Scope / HSS | `scope/view.js` 的 `hidXfer` 直达 `AkaLinkHid.xfer`。`0x31` 选架构，`0x32` 配置/设时钟/标定/启停/读取状态和计数；固件经 EP7 IN 送样本。调慢采样周期仍走这一条通路 | 控制未迁移，低频采样无 WASM 分支 |
| RTT 转发 | `hid/view.js` 与 `hid/probe.js` 的 `0x31` 控制目标选择、扫描、速率、启停和状态；固件读目标 RTT 环，CDC 送字节 | 私有控制未迁移。RTT Viewer 已迁移 |
| 全局硬复位和复位脚模式 | `flash/target-reset.js` 发原始 CMSIS-DAP `DAP_Connect` 和 `DAP_SWJ_Pins`；复位脚模式经 `hid/probe.js` 的私有 HID | 未迁移 |
| 通用串口 / 终端与原生直调入口 | `serial/session.js` 用 Web Serial 或本机串口；`toolbox probe call` 直达本机 USB/HID/serial 代理，另有原生诊断/验收脚本 | 未迁移，单独列出以明确范围 |

J7 现有 PS 固件在 `probe_stream.c` 接收 HID `0x31/0x32`。现有 CMSIS-DAP 厂商处理器 `DAP_vendor.c` 的 `0x80–0x8d` 没有等效的 HSS／RTT 转发接口。后续需要让 WASM 执行这些私有控制事务并通过受管传输发送，保留同一设备身份、请求/响应关联、失败不重放、HSS 停机排空和尾计数。低频采样需要实际从 WASM 读取目标内存，按实际采样间隔与缺样记录结果。原生 ETM 的布防/放行迁移另验同一所有权下的时序和现场恢复。跟踪 ZL-172。
