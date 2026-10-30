# ZynqDAP Web 工作台

本项目自己的静态 Web 上位机，参考 superlinkPRO/Web 的 Apache-2.0 代码移植。
保留串口助手、xterm 终端、RTT 转发、J-Scope、烧录器、调试器、ETM 执行轨迹、工程生成，
另保留通用 RTT Viewer。页面可部署到 HTTPS 静态站点；本地使用 Chrome / Edge：

```powershell
node web/tools/serve.mjs
# 打开 http://127.0.0.1:8898
```

该服务只提供静态文件，没有调试桥或解码后端。Web Serial / WebHID / WebUSB 直接连接
浏览器授权的设备；ETM 在 Worker 内运行 OpenCSD WASM。没有沿用参考项目的 Kingst 采集桥。

## 设备通路

| 功能 | 本项目通路 |
|---|---|
| 串口助手 / 终端 | 标准 Web Serial，共用一个所选 COM 口 |
| RTT Viewer / 烧录器 / 调试器 | CMSIS-DAP，接口 0 的 EP1 IN / EP2 OUT |
| RTT 转发 | HID 控制接口 3，CDC EP3 IN 接收 |
| J-Scope | HID 控制；独立 HSS bulk-in `0x87` |
| ETM | 独立 bulk-in `0x82`，EP0 vendor `0x60` 控制 |
| ETM 解码 / 回放 | 本仓库 ORBTrace 接收数据 + OpenCSD 1.8.3 WASM，匹配 ELF / DWARF |
| 工程生成 | 浏览器解析 Keil `.uvprojx`，预览 / ZIP / 所选目录写入 |

HID RTT 转发与 J-Scope 目前支持 ARM 目标；RISC-V 可使用独立调试器和 RTT Viewer。
J-Scope 触发由浏览器执行，计划标定测量 PS MEM-AP 读回耗时，供保守起始周期参考；它不是
PL 连续采样吞吐或 USB 极限。计数和实际采集质量仍须观察丢样、USB 缺口和读错误。

ETM 自动配置仅支持 STM32F103ZE / Cortex-M3。开始前逐字节核对 ELF 的目标 Flash，
读取实际 ETM 配置，采集后恢复 CoreSight 寄存器与锁。手工模式可输入准确的 ETMv3 配置。
默认采集 10 ms；解码可用“停止”取消。较大记录需考虑浏览器内存和解码时间。

## ETM 分析视图

`ETM 执行轨迹` 页在解码后由 `app/etm/analysis.js` 在浏览器里还原调用树，不依赖任何本地
服务、Python 桥或逻辑分析仪。数据只来自本机的 FPGA 并行 trace（PS bulk-in `0x82`）或
`.zetm` 记录。六个页签和导出都基于同一份 `analyze()` 结果：

| 视图 | 内容 |
|---|---|
| 执行流 | 每段指令的起止、分支性质（调用/返回/条件/间接/屏障）、调用深度、所属函数 |
| 调用统计 | 每个函数的调用次数、自身与包含子树半字数、占比、最大深度 |
| 火焰图 | 按 `BL`/`BX LR` 还原的调用树，列宽为执行半字数；可导出 SVG |
| 热点 | 按包含子树权重排序的前 12 个函数 |
| ETM 包 | 包类型统计与最近 400 条原始包 |
| 可信区段 | 按 `TRACE_ON` / 未同步事件切分的区段，标出缺口、地址问题和可信性 |

历史导航（指令 / 调用 / 返回 / 条件跳转 / 间接跳转 / 异常 / 未执行）用来在长记录里跳到
下一个关心的位置；`历史调用栈` 显示当前范围所处的完整调用链。导出支持执行流 CSV、
火焰图 SVG、分析 JSON（含区段、问题、函数统计和包样本）和源码执行流 CSV。

调用/返回的判定只用 OpenCSD 给出的 `last_i_type` / `last_i_subtype`：只有 `BR_LINK` 算
调用，只有间接分支上的 RET 子类型算返回，尾调用不会被误判成返回。trace 起点的入口函数
没有调用者，会作为顶层帧出现，它的最终返回属于正常收尾，不计为异常。

## ETM 接线

ZYNQ Micro-SYS 的 J7 连续 15–19 脚，电平 3.3 V，另接地：

| J7 | Zynq 球位 | 目标信号 |
|---|---|---|
| 15 | H15 | TRACEDATA[0] |
| 16 | H16（MRCC） | TRACECLK |
| 17 | G15 | TRACEDATA[1] |
| 18 | H17 | TRACEDATA[2] |
| 19 | N15 | TRACEDATA[3] |
| 14 | GND | 目标 GND |

当前约束目标 TRACECLK ≤ 50 MHz、四位 DDR。构建/仿真通过不能替代实际接线后的时序裕量验收。

## 本地记录和质量

`.zetm` 保存 ETM 字节、SHA-256、解码配置、匹配 ELF 或指令镜像、源 ID 和捕获质量。
检测到包序号缺口、PL 溢出、结束包缺失时，不应视作完整捕获。设备包同时携带 PS 实际
FCLK 与 SWD/JTAG TCK（kHz 精度）。仓库里有两份样例，都能一键导入并在浏览器里解码：

| 样例 | 来源 | 解码结果 |
|---|---|---|
| `samples/cm3-orbtrace.zetm` | DesignStart CM3 实际仿真 | 1948 字节、22,036 个指令范围、1 个函数 |
| `samples/f103ze-oversample.zetm` | F103ZE 实板，24 MHz TRACECLK 过采样 parser 路径 | 1309 字节、6368 个指令范围、8 个函数、253 次调用、深度 3 |

实板样例由 `web/tools/make-etm-sample.mjs` 从验收目录的 `etm.bin` + 目标 ELF 生成，
只带 ELF 的加载段和 221 个函数符号（不含 DWARF），ELF 与 ETM 的 SHA-256 都按验收 JSON
核对过，来源见记录里的 `provenance` 字段。

## 检查和重建

```powershell
node web/tools/check.mjs
node --test web/tests/etm.test.mjs web/tests/etm-analysis.test.mjs
node web/tools/page-smoke.mjs      # 需要先跑 node web/tools/serve.mjs，用本机 Edge 无头验收九页
python tools/test_probe_host.py
python tools/build_etm_wasm.py --emsdk build/emsdk
```

`etm-analysis.test.mjs` 用合成的 OpenCSD 元素流覆盖调用/返回、尾调用、未同步、可信区段、
火焰图布局和导出，并跑一遍 60 万范围的性能下限。`page-smoke.mjs` 用 CDP 驱动无头 Edge
逐个点开九个页面，并在 ETM 页里载入 `samples/cm3-orbtrace.zetm` 走完解码→调用树→火焰图，
另外把三个内置模拟目标（调试器 Cortex-M7 模型、J-Scope 假探针、RTT `?backend=mock`）也
真连一遍。接线相关的串口、烧录和实板 ETM 仍需人工上板。

WASM 重建需激活 Emscripten 4.0.10、CMake 和 Ninja。源码位于 `web/etm-native/` 与
`third_party/OpenCSD-1.8.3/`；运行时只需已纳入本项目的 `opencsd.mjs` 和 `opencsd.wasm`。
构建指纹记录于 `app/etm/build-manifest.json`。参考代码来源、许可证见 `LICENSE`、
`etm-native/LICENSE`、`etm-native/EMSCRIPTEN-LICENSE` 与第三方目录。

物理 ETM 线尚未接好，完整实板 trace 验收待完成；具体构建和板级状态以项目验收记录为准。
