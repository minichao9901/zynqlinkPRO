# Zynq ETM Trace 操作说明（superlinkPRO 页面 + 本地服务）

本文说明本仓库的 ETM 执行轨迹流程：**页面是 superlinkPRO 原始工作台**，采集后端从 Kingst 逻辑分析仪换成 **Zynq FPGA 并行 ETM**，解码仍由 OpenCSD。

## 1. 组成

| 部分 | 位置 | 说明 |
|---|---|---|
| 工具箱页面 | `web/` | 从 `E:\superlinkPRO\web` 拷贝后删掉六个功能页；ETM tab 是 iframe |
| ETM 页面 | `etm-service/web/` | superlinkPRO 原始 ETM 四步页面；“② 逻辑分析仪”已换成“② Zynq ETM 接收” |
| 本地服务 | `etm-service/server.py` | 提供页面/API、Zynq 采集、OpenCSD 解码、记录浏览 |
| 采集适配 | `etm-service/tools/zynq_la.py` | 保持 server 的 job/记录接口，把 LA 的 `Vis` 换成 Zynq EP2 |
| 解码器 | `etm-service/build-native/etm_decode.exe` | OpenCSD 原生解码，随仓库提供 |

## 2. 文件配对

| 文件 | 路径 | SHA-256 |
|---|---|---|
| FPGA bitstream | `prebuilt/20261030_orbtrace_oversample_parser/orbtrace_oversample_parser.bit` | `230531cef335e6a0b81586be16025fa06bfef28a8106553d6fb8f9296ab09c68` |
| Zynq 固件 | `prebuilt/20261030_orbtrace_oversample_parser/zynqdap_orbtrace.elf` | `6419c8b00a71b70a1572a55f84c3478f32b67aae8eda95a3821684dc7b3f1a30` |
| F103ZE 目标固件 | `etm-service/firmware/stm32f103_cdc_trace/fw-ze.elf` | `63881ed9f6c1187d56924795ccad3f151a677aea0dfa201823fe44e0cb857522` |

加载 Zynq bit/ELF（通过 Zynq 自己的 JTAG，不是目标 JTAG）：

```powershell
python tools/run_xsct.py tools/download_dap_fpga.tcl `
  prebuilt/20261030_orbtrace_oversample_parser/zynqdap_orbtrace.elf `
  prebuilt/20261030_orbtrace_oversample_parser/orbtrace_oversample_parser.bit
```

目标 Flash 必须是 `fw-ze.elf` 的那个构建；页面采集前会逐字节核对，不匹配会拒绝。

## 3. 接线

| F103ZE | 目标球位 | Zynq J7 | Zynq 球位 | 信号 |
|---|---|---|---|---|
| PE2 | H16 | J7.16 | H16 | TRACECLK |
| PE3 | H15 | J7.15 | H15 | D0 |
| PE4 | G15 | J7.17 | G15 | D1 |
| PE5 | H17 | J7.18 | H17 | D2 |
| PE6 | N15 | J7.19 | N15 | D3 |
| GND | — | J7.14 | — | 地 |

SWDIO / SWCLK / GND 仍接 ZynqDAP；目标 JTAG 可以不接。至少两根地线。

## 4. 启动

```powershell
# 窗口 1：ETM 本地服务（页面 + 采集 + 解码）
cd etm-service
python server.py --port 8766

# 窗口 2：工具箱静态站
node web/tools/serve.mjs      # http://127.0.0.1:8898
```

打开 `http://127.0.0.1:8898/` →「ETM 执行轨迹」。也可以直接打开 `http://127.0.0.1:8766/`。

服务状态：`GET http://127.0.0.1:8766/api/status`。只有带 **bulk-in 0x82** 的 ZynqDAP 才显示 `zynq.ready=true`；akaLinkPro 虽然 VID/PID 相同，但没有 0x82，会明确提示。

## 5. 四步流程

### 5.1 调试

1. 载入与目标 Flash 匹配的 `fw-ze.elf`。
2. 连接探针（WebUSB 授权一次）。
3. 添加硬件断点并选采集起点；建议 `trace_workload_round` 这类业务函数。
4. 「复位并停在起点」或「运行至起点」；采集前目标保持暂停。

### 5.2 时钟

1. 填 HSE（F103 板常见 8 MHz），核对实际 CPU/TRACECLK。
2. 「配置并暂停」写 Trace GPIO / ETM / TPIU；ETM 处于已使能、CPU 暂停的状态，TPIU 同步序列会落在采集窗口里。

### 5.3 采集

1. 时长默认 10 ms，上限 1000 ms；「服务端联动」保持勾选。
2. 点「联动采集」：
   - 页面释放 WebUSB 句柄；
   - 服务独占 USB：校验 ETM 签名/参考时钟 → arm FPGA → 写 DHCSR 恢复 CPU；
   - 读 EP2，按 source ID 2 解复用，写 `etm-service/records/<sid>/capture.bin`；
   - 到时或「停止采集」时发 vendor control 2，收结束包，释放 USB；
   - 页面重新认领探针、恢复 ETM/断点。
3. 状态至少满足：ETM 字节 > 0、同步/完整结束、无丢失、source ID 2、FCLK 约 100 MHz。

### 5.4 文件与分析

- 采集成功会自动解码；也可「单独解码」。
- 右侧页签：执行流、调用统计、火焰图、热点、ETM 包、可信区段。
- 导出：执行流 CSV、火焰图 SVG、分析 JSON、源码执行流。
- 没有硬件时可用历史记录或导入已解复用的 ETM BIN + ELF + session.json。

## 6. 验收基线

离线（当前仓库内可复现）：

| 项目 | 结果 |
|---|---|
| 输入 | F103ZE 样例 1309 ETM 字节 |
| 解码 | 6,368 个执行路径、1,287 个包、1 个中断 |
| 页面 | 执行流/调用统计/火焰图/热点均能打开，无控制台错误 |

实板：F103ZE @ 48 MHz HCLK / 24 MHz TRACECLK，Zynq FCLK 100 MHz，10 ms 窗口。**当前总线上只有 akaLinkPro（没有 0x82），ZynqDAP 需重新接入后复核这一项**；在接回并加载上述 bit/ELF 前，不要把它当成已完成。

## 7. 排障

| 现象 | 处理 |
|---|---|
| `zynq.ready=false`，提示“没有 ETM bulk-in 0x82” | 接的是 akaLinkPro；换 ZynqDAP 并加载配套 bit/ELF |
| `ETM PL 签名不匹配` | bit/ELF 不是同一配对 |
| `参考时钟未初始化到 200 MHz` | PS 初始化未完成或 ELF 不配套 |
| `ETM 采样延时校准未就绪` | 重新加载 bit/ELF；确认 PL 时钟 |
| 采集后页面重连失败 | 服务是否已释放 USB；关掉其它占用探针的页签/工具 |
| 有记录但未同步/有丢失 | 降 TRACECLK、缩短窗口、检查地线和 J7 针脚 |

## 8. 相关文件

- [ETM 本地服务说明](../etm-service/README.md)
- [Web 工作台说明](../web/README.md)
- [采集适配 `zynq_la.py`](../etm-service/tools/zynq_la.py)
- [服务端 `server.py`](../etm-service/server.py)
