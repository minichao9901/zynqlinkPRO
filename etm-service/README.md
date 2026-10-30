# ETM 本地服务（superlinkPRO 页面 + Zynq 采集）

这是 **superlinkPRO 原始 ETM 工作台**（`web/`，四步页面、执行流/调用统计/火焰图/热点/ETM 包/可信区段）在本仓库的本地服务。页面本身不再重写；只把原来的 **Kingst 逻辑分析仪** 采集后端换成 **Zynq FPGA 并行 ETM**，解码仍由原来的 OpenCSD 原生解码器完成。

```
工具箱（web/，superlinkPRO 页面做减法）
  └─ ETM 执行轨迹 tab ──iframe──> http://127.0.0.1:8766/   ← 本服务
                                      ├─ /web             superlinkPRO ETM 页面（原样）
                                      ├─ /api/capture     Zynq EP2 采集（替换 Kingst）
                                      ├─ /api/decode      etm_decode.exe（OpenCSD）
                                      └─ /api/browse/...  记录分页 / 执行流 / 火焰图
```

## 启动

```powershell
cd etm-service
python server.py --port 8766
# 或者双击 start-etm.bat
```

依赖：`Flask`、`pyusb`、`libusb-package`、`pyelftools`、`capstone`、`numpy`（见 `requirements.txt`）。解码器 `build-native/etm_decode.exe` 已随仓库提供，不需要另装 OpenCSD。

打开 <http://127.0.0.1:8766/> 可独立使用；工具箱 `http://127.0.0.1:8898/` 的「ETM 执行轨迹」页会自动 iframe 这个地址。

## 硬件

ZynqDAP（VID 0x0D28 / PID 0x0204，接口 0 必须有 **bulk-in 0x82**）加载配套 bit/ELF：

| 文件 | 路径 |
|---|---|
| FPGA bitstream | `prebuilt/20261030_orbtrace_oversample_parser/orbtrace_oversample_parser.bit` |
| Zynq 固件 | `prebuilt/20261030_orbtrace_oversample_parser/zynqdap_orbtrace.elf` |
| 目标验收固件 | `etm-service/firmware/stm32f103_cdc_trace/fw-ze.elf` |

目标 ETM 线（F103ZE）：

| 目标 | Zynq J7 | 信号 |
|---|---|---|
| PE2 | J7.16 | TRACECLK |
| PE3 | J7.15 | D0 |
| PE4 | J7.17 | D1 |
| PE5 | J7.18 | D2 |
| PE6 | J7.19 | D3 |
| GND | J7.14 | 地 |

四位 DDR、3.3 V、TRACECLK ≤ 50 MHz、source ID 2。SWD 仍然接在 ZynqDAP 上。

## 采集流程

1. 页面「1 调试」载入与目标 Flash 匹配的 ELF，连接探针，选择起点断点。
2. 「2 时钟」核对 HSE / CPU / TRACECLK；「配置并暂停」把 ETM/TPIU 配好（ETM 已使能，CPU 保持暂停）。
3. 「3 采集」选时长（默认 10 ms，上限 1000 ms），点「联动采集」。
   - 页面先释放浏览器 WebUSB 句柄；
   - 本地服务独占 USB：校验 ETM PL 签名/200 MHz 参考时钟 → arm FPGA → 写 DHCSR 恢复 CPU；
   - 读 EP2 的 ZET1 包，按 source ID 2 解复用，写到 `records/<sid>/capture.bin`；
   - 到时或「停止采集」时发 vendor control 2，收结束包，释放 USB；
   - 页面重新认领探针并恢复目标 ETM/断点。
4. 服务调用 `etm_decode.exe` 解码，随后建浏览索引；页面显示执行流、调用统计、火焰图、热点、ETM 包、可信区段。

`/api/status` 会区分探针：只有带 bulk-in `0x82` 的 ZynqDAP 才返回 `zynq.ready=true`；akaLinkPro 会明确提示“没有 ETM bulk-in 0x82”。

## 与 superlinkPRO 的差异

| 部分 | superlinkPRO | 这里 |
|---|---|---|
| 采集 | Kingst VIS / KVDAT / 500 MSa/s / 阈值 / 通道 / 半周期取样 / 软件滤波 | ZynqDAP EP2，ZET1 包，直接得到 source ID 2 的 ETM 字节 |
| 解码 | `etm_decode.exe`（OpenCSD） | 相同 |
| 页面 | 原始 ETM 四步页面 | 相同，只把“② 逻辑分析仪”换成“② Zynq ETM 接收” |
| 记录 | LA 波形 + `capture.kvdat` | `capture.bin`（已解复用 ETM 字节） |

## 验证状态

- 离线：用 F103ZE 实板样例的 1309 字节 ETM，经 `/api/import` → `/api/decode`，页面显示 **6,368 个路径、1,287 个包、1 个中断**，火焰图/调用统计可打开。服务端无 Python 异常。
- 实板采集：等待 ZynqDAP 重新接入（当前总线上只有 akaLinkPro，没有 0x82 端点）。接回后按上面的 bit/ELF 加载，跑 10 ms 采集即可复核。
