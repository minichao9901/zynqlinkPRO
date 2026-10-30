# 完整 ETM 页面：从「照搬」改为本项目原生实现

## 结论

`E:\superlinkPRO\web\etm` 的完整工作台依赖它自己的 Python 桥（默认 `127.0.0.1:8899`）：
页面里 `apiBase` 在非 github.io 站点上取 `/api/`，只有由桥自己托管的页面才连得上；
桥的采集侧是 Kingst LA，解码侧是 `build-native/etm_decode.exe`（OpenCSD C++）。
本项目的 ETM 是 FPGA 并行接收（PS bulk-in `0x82`，ZET1 包），既不接 LA，也不该为一个
分析页面引入 Python 运行时，因此**没有把静态副本留在仓库里**（`web/etm/` 已删除）。

改为把这些功能在本项目 Web 里用纯前端实现，数据只来自本仓库的采集或 `.zetm` 记录：

| superlink 能力 | 本项目落点 |
|---|---|
| 执行流 / 历史导航 | `app/etm/view.js` 执行流页签 + 历史导航下拉 |
| 调用统计 | `analysis.js` `callStats()` |
| 火焰图（含 SVG 导出） | `analysis.js` `flameLayout()` / `flameSvg()` |
| 热点 | `callStats()` 前 12 |
| ETM 包视图 | `analysis.js` `packetSummary()` + 原始包表 |
| 可信区段 / 包问题 | `analysis.js` 区段切分与 `issues` |
| 历史调用栈 | `analysis.js` `stackFrames()` |
| 导出 CSV / JSON / 源码执行流 | `executionCsv()`、`summaryJson()`、`sourceFlow()` |
| ELF / 源码载入、目标识别、ETM 配置与恢复 | 沿用原有 ZynqDAP 直连面板，未改 |

## 调用树怎么来的

OpenCSD 对每段指令范围给出 `last_i_type`（`ocsd_instr_type`）和 `last_i_subtype`
（`ocsd_instr_subtype`）。判定规则只用这两个字段，枚举值取自本仓库
`third_party/OpenCSD-1.8.3/decoder/include/opencsd/ocsd_if_types.h`：

- 调用：`lastSubtype == BR_LINK`（Cortex-M3 的 `BL`/`BLX`）。
- 返回：`lastSubtype` 为 `V8_RET` / `V8_ERET` / `V7_IMPLIED_RET`（`BX LR`、`POP {..., PC}`）。
- 其它 `BR` 按 `lastConditional` 分成条件跳转和直接跳转；`BR_INDIRECT` 且无 RET 子类型是
  间接跳转（尾调用就在这里，不能算返回）。

调用目标取「下一条执行范围的起始地址」——ETM 的范围只是起点加长度，目标地址要等下一段
范围才出现。trace 起点的入口函数没有调用者，作为顶层帧挂在根下面；它的最终返回是正常
收尾，计入 `entryReturns`，不报问题。

权重用半字数（`(end-start)/2`），不是指令条数：解码层不逐条拆指令，半字数与执行量单调
相关，够做火焰图的相对宽度。这一点在 UI 和导出里都写明。

## 区段与质量

- 区段按 `TRACE_ON` 与 `NO_SYNC` 切分。`NO_SYNC` 的 `payload` 是 `unsync_info_t`：
  0 UNKNOWN / 1 INIT_DECODER / 2 RESET / 3 OVERFLOW / 4 DISCARD / 5 BAD_PACKET /
  6 BAD_IMAGE / 7 EOT，只有 3～6 计为真实数据缺口。
- 「可信」= 该区段没有数据缺口、并且真的解出了执行数据。地址不可访问 / 地址未知 / 孤立
  返回都进问题列表单独计数（上限 500 条，超出时在 JSON 里标明已截断），但不直接否定整个
  区段——实板上 trace 起点之后出现 `ADDR_UNKNOWN` 是常见现象。
- 异常入口单独记 `exception`，不混进指令范围数，保证各区段 `ranges` 之和等于总范围数。

## 验证

```powershell
node web/tools/check.mjs
node --test web/tests/etm.test.mjs web/tests/etm-analysis.test.mjs
node web/tools/serve.mjs            # 另一个窗口
node web/tools/page-smoke.mjs
```

`etm-analysis.test.mjs` 覆盖调用/返回、尾调用、未同步缺口、可信区段、火焰图布局、CSV/JSON
导出和 60 万范围的性能下限；`page-smoke.mjs` 用 CDP 驱动无头 Edge 点开九个页面，并在 ETM
页依次载入两份样例，跑完「WASM 解码 → 调用树 → 六个视图」。

当前实测：

| 样例 | 结果 |
|---|---|
| `samples/cm3-orbtrace.zetm`（CM3 仿真） | 1948 字节 → 22,036 范围、1 函数、1 区段、3 类包 |
| `samples/f103ze-oversample.zetm`（F103ZE 实板，24 MHz TRACECLK） | 1309 字节 → 6,368 范围、8 函数、253 调用、深度 3、火焰图 261 个节点 |

实板样例的 `main → cdc_poll` 调用（252 次）来自真实 ETM 数据，不是合成流。

## 未完成

- 火焰图目前不做点击缩放/合并同类帧，只做整树静态 SVG。
- 源码执行流需要 ELF 带 DWARF 行表；只带加载段和符号的样例导不出这一项，要另载 ELF。
- 实板 ETM 采集链路本身已在 24 MHz TRACECLK 工作点端到端验收过（见
  `ETM过采样端到端验收-20261030.md`），但那仍是实验模式；默认生产 IDDR 配对没有切换。
