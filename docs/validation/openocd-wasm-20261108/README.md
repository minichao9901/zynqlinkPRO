# OpenOCD Wasm 工作台迁移

2026-11-08，北京时间。参考 superlinkPRO `f2fa8ca` 的 Worker、目标脚本和 HPM 验收，以及 `5fc3cc6` 的共用 Flash、RTT、原版 CFG 实现与 F103ZE、H743、HPM6800EVK、RP2350 报告。该仓的板测使用 akaLinkPro。Zynq 工作台验收范围以下表为准。 [运行时指纹与源码](../../../web/app/core/openocd-runtime/README.md)

调试器、烧录器和 RTT Viewer 共用 OpenOCD。浏览器 Worker 通过现有租约向页面请求 USB 操作。本机代理沿用 owner 与 resourceEpoch，仅增加标准 USB 描述符读取。Zynq 的 DAP 为接口 0、OUT2、IN1，保留 IN2 的 ETM 通道和 IN7 的 HSS 通道。正式固件使用 DAP 队列新 epoch 与空闲回读，短于 4096 字节的整 USB 包写入补 ZLP。RTT 转发、J-Scope、ETM 和独立 Trace CLI 使用各自已有的专用数据通路。

| 离线项目 | 范围 |
|---|---|
| WASM 本体 | 运行浏览器版 OpenOCD。注册 F103、H7、HPM、nRF52、RP2350 的目标和 Flash driver，解析含变量与相对依赖的 CFG，拒绝越界目录 |
| Edge 工作台 | 真实页面加载 `.mjs` 和 `.wasm`，导入 CFG 后烧录器和 RTT Viewer 沿用同一核心。另解析 HPM SDK 1.11.0 的原版入口及上游 RP2350 双核 CFG |
| 模拟 USB | 浏览器 Worker 通过描述符选中接口 0、OUT2、IN1，完成 CMSIS-DAP Info 交换。夹具故意返回无 SWD 能力，建链报错后接口与设备均关闭。模型另核对 ZLP、队列 epoch、禁止访问 ETM 端点和原生描述符请求隔离 |
| Flash 安全模型 | 固件所有地址在擦除前预检，保留未覆盖的扇区字节，烧录后比较完整扇区 |
| 既有入口 | Web、CLI、共享驱动检查及 `trace doctor --offline`。Edge 首轮发现 RTT 初始化仍引用旧类名，修正后重新加载通过 |

## 上板验收顺序

1. 核对 J7 实际运行的 bit/ELF、探针独占状态和目标 ELF。分别用本机代理和浏览器直连核对端点、DAP 握手、时钟请求与实际读回。
2. F103ZE 与 H743 先做身份、运行态内存、暂停、寄存器、四断点轮转与源码步进，核对断开时的断点清理和运行态。烧录先备份目标扇区，再验证擦写、逐字节读回及复位，结束后恢复备份。H743 的 RTT 控制块采用已知 AXI SRAM 夹具。
3. HPM6800EVK 比较内置板型与原版 SDK CFG。核对 TAP、实际 TCK、运行态 SBA、暂停寄存器、硬件断点、NDM reset、RTT 双向及 XPI 扇区读回。其它芯片按实际可用设备逐项验收。
4. 分别从运行中的 WASM 调试器或 RTT Viewer 交接给 RTT 转发、J-Scope 和 ETM，再接回调试器。记录交接、数据质量、原目标状态恢复和实际配对。

本轮未接入硬件，兼容性结论限于配置加载和离线模型。新增跟踪项为 ZL-171。
