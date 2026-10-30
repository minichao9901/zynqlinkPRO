# Zynq ETM CLI 使用说明

> 2026-10-30复测：旧parser配对在50 ms窗口也会出现OpenCSD BAD_SEQUENCE；下文历史成功
> 记录不代表稳定验收。已定位并正在构建TPIU连续帧/HSYNC修复，当前进展见
> [本轮记录](validation/web-cli-f103ze-20261030/README.md)。Web统一入口为根目录toolbox.py。

本仓库的 ETM CLI 参考 superlinkPRO 的 `etm/trace.py`（原说明：`E:\superlinkPRO\docs\trace-cli-ai.md`），但采集端换成了 **Zynq FPGA 并行 ETM**。入口：

```powershell
python -X utf8 etm-service/trace.py ...
```

输出契约与 superlinkPRO 一致：stdout 只有一份 JSON，进度写 stderr，`protocol` 为 `trace-cli/1`。全局退出码：

| 退出码 | 含义 |
|---|---|
| 0 | 成功（仍要看 quality / gaps） |
| 2 | 参数或前置条件不符 |
| 3 | 缺依赖/原生程序 |
| 4 | USB、设备、IO 或恢复错误 |
| 5 | 采集/解码质量不通过 |

## 1. 环境

- Python 3.10+，依赖见 `requirements.txt`（Flask、pyusb、libusb-package、pyelftools、capstone、numpy）。
- 原生解码器：`etm-service/build-native/etm_decode.exe` 等五个 exe，已随仓库提供。
- ZynqDAP：VID `0x0D28` / PID `0x0204`，接口 0 必须有 **bulk-in `0x82`**。akaLinkPro 没有该端点，CLI 会明确拒绝。
- 加载配套 bit/ELF：`prebuilt/20261030_orbtrace_oversample_parser/`。

CLI 采集会独占探针。运行前关闭占用同一 ZynqDAP 的 ETM 网页、调试器或其它 Python 进程，否则报 `Access denied`。

## 2. 命令

### doctor

```powershell
python -X utf8 etm-service/trace.py doctor
```

检查 Python 依赖、五个原生 exe、ZynqDAP 的 `0x82`、本地 ETM 服务（8766）以及默认 ELF/bit。全部就绪返回 0。

### capture

```powershell
python -X utf8 etm-service/trace.py capture `
  --elf etm-service/firmware/stm32f103_cdc_trace/fw-ze.elf `
  --out build/cli-capture-001 `
  --seconds 0.05
```

流程：

1. 用 `tools/test_orbtrace_board.py` 校验目标 Flash 与 ELF，暂停 CPU，保存并配置 ETM/TPIU；
2. arm Zynq FPGA，读 EP2 的 ZET1 包，按 source ID 解复用；
3. 停止时收结束包，恢复 CoreSight/GPIO/RCC，再恢复目标运行状态；
4. 写记录：`capture.bin`、`firmware.elf`、`session.json`、`target-before.json`、`acceptance.json`；
5. 调用原生 `decode_stream` 生成 `decoded.json`。

常用参数：

| 参数 | 说明 |
|---|---|
| `--seconds` | 0..1 s，必须大于0，默认 **0.05**；短窗不能掩盖解码错误 |
| `--trace-id` | 默认 2 |
| `--swd-khz` | 目标控制SWD时钟，默认1000 kHz，与TRACECLK独立 |
| `--hclk-div` | 默认 **4**；当前 parser bit 在 48 MHz HCLK / 24 MHz TRACECLK 下收不到 source 2，`/4` 是已验证工作点 |
| `--gpio-speed` | 默认 1（10 MHz）；与 `/4` 配套 |
| `--no-decode` | 只采集，不跑解码 |
| `--json-out` | 另存结果 JSON（拒绝覆盖） |

示例（200 ms）：

```powershell
python -X utf8 etm-service/trace.py capture `
  --elf etm-service/firmware/stm32f103_cdc_trace/fw-ze.elf `
  --out build/cli-capture-200 --seconds 0.2
```

返回 `result.summary`（packets/ranges/functions）、`quality`（loss/synced/ended/FCLK）和 `record` 路径。

### 离线命令（委托给 superlinkPRO CLI）

以下命令由 `tools/trace_cli.py` 原样执行，JSON/退出码规则不变：

```powershell
python -X utf8 etm-service/trace.py elf inspect --elf ... --search trace_workload
python -X utf8 etm-service/trace.py decode --record build/cli-capture-050 --out build/redecode-050
python -X utf8 etm-service/trace.py query --record build/cli-capture-050 --view summary
python -X utf8 etm-service/trace.py query --record build/cli-capture-050 --view flame
python -X utf8 etm-service/trace.py verify --record build/cli-capture-050
python -X utf8 etm-service/trace.py record list --root build
python -X utf8 etm-service/trace.py record info --record build/cli-capture-050
python -X utf8 etm-service/trace.py export --record build/cli-capture-050 --format csv --out build/flow.csv
python -X utf8 etm-service/trace.py import-record --input x.etmrecord --out build/imported
```

注意：

- 包装器会把 `TEMP/TMP` 指到 `build/tmp-long`。原生 `etm_storebuild` 在 Windows 8.3 临时路径（`ADMINI~1`）下无法创建结果 JSON，直接调用 inherited CLI 会报“打不开 JSON 输出”。
- `decode/query/export` 默认走 native 路径；200 ms 记录解码约 20 s（见性能说明）。
- `verify` 沿用 superlinkPRO 的严格质量规则：任何 `gaps` 都会导致 `ok=false`。实板 50 ms 记录可能有 1–2 个 gap，属于正常边界；要看 `query` 的 `packetIssues/overflow/lastError` 再判断。

## 3. 与 superlinkPRO CLI 的差异

| 能力 | superlinkPRO | 本仓库 |
|---|---|---|
| 采集 | Kingst LA（CSV/KVDAT，500 MSa/s，阈值/通道/相位/滤波） | Zynq EP2（ZET1，source ID 2，直接 ETM 字节） |
| 目标控制 | `web` 运行时 + Node WebUSB + `TargetBridge` | `capture` 内部调用 `test_orbtrace_board.py` 的 SWD 配置/恢复 |
| 烧录 | `web flash` | 未接入（用网页烧录器或 `build/flash_f103ze.py`） |
| 断点起点 | `--entry/--reset-to-entry` | **暂不支持**；从当前暂停位置连续采集 |
| 解码/查询/导出 | C++ native + TraceStore | 同 superlinkPRO 原生路径（未启用 trace-store 融合写出） |
| 服务/网页 | LA 服务 + 页面 worker | ETM 页面 + `server.py` 的 `/api/*` |

## 4. 当前限制与实测

- **24 MHz TRACECLK 工作点**：加载 `orbtrace_oversample_parser.bit` 后，HCLK 48 MHz / TRACECLK 24 MHz 连续 10 ms 采集只有 source 0x7F（未同步）；`--hclk-div 4 --gpio-speed 1`（HCLK 12 MHz / TRACECLK 6 MHz）能稳定收到 source 2。CLI 默认按后者执行，采集结束会恢复 RCC。
- 10 ms 短窗可能触发 OpenCSD `Decode stopped ... response 9`（起始失同步/边界不足）；建议 50 ms 起。
- 200 ms 记录：222 KB ETM、588k ranges，默认 native 解码约 20 s，`gaps` 可能上万；这是解码器边界统计，不代表 USB 丢包（`quality.loss=false`）。
- 1 s 采集参数允许，但默认 Python 解码会非常慢（约 100 s 量级），且页面/CLI 内存增长明显；需要 trace-store/C++ 融合路径后再作为可用工作点。
- 没有 LA 的 `--rate/--threshold/--fraction/--glitch-ns`，这些参数已从 CLI 采集面移除。
- `target`/`web` 子命令仍是 superlinkPRO 的浏览器/LA 运行时，未适配 Zynq，暂不使用。

## 5. 已验证命令

| 命令 | 结果 |
|---|---|
| `doctor` | 全部 ok，Zynq `0x82` 存在 |
| `capture --seconds 0.05` | 56,271 ETM 字节、277,517 ranges、`loss=false`、`gaps=2` |
| `capture --seconds 0.2` | 222,426 ETM 字节、588,906 ranges、`loss=false`、`gaps=50953` |
| `query --view summary` | 返回 packets/ranges/functions/quality |
| `decode --record` | native 重解成功（质量严格检查可能因 gaps 返回 5） |

