# Zynq ETM Trace 操作说明

本文说明本仓库的 Zynq FPGA 并行 ETM 接收链路如何从上板、采集到 OpenCSD 解码和火焰图分析。当前验收对象是 **STM32F103ZE / Cortex-M3 ETMv3**；目标板只需要 SWD 和 ETM，不需要连接目标 JTAG。

## 1. 使用的文件配对

先确认加载的是同一目录下的 bitstream 和 Zynq 固件，不要把其他构建目录里的旧文件混用。

| 文件 | 路径 | SHA-256 |
|---|---|---|
| FPGA bitstream | `prebuilt/20261030_orbtrace_oversample_parser/orbtrace_oversample_parser.bit` | `230531cef335e6a0b81586be16025fa06bfef28a8106553d6fb8f9296ab09c68` |
| Zynq 固件 | `prebuilt/20261030_orbtrace_oversample_parser/zynqdap_orbtrace.elf` | `6419c8b00a71b70a1572a55f84c3478f32b67aae8eda95a3821684dc7b3f1a30` |
| F103ZE 目标 ELF | `E:\superlinkPRO\etm\firmware\stm32f103_cdc_trace\fw-ze.elf` | `63881ed9f6c1187d56924795ccad3f151a677aea0dfa201823fe44e0cb857522` |

在 PowerShell 中可以这样核对：

```powershell
Get-FileHash prebuilt/20261030_orbtrace_oversample_parser/orbtrace_oversample_parser.bit -Algorithm SHA256
Get-FileHash prebuilt/20261030_orbtrace_oversample_parser/zynqdap_orbtrace.elf -Algorithm SHA256
Get-FileHash E:\superlinkPRO\etm\firmware\stm32f103_cdc_trace\fw-ze.elf -Algorithm SHA256
```

## 2. 上板和接线

### 2.1 加载 Zynq bit/ELF

下面的命令通过 **Zynq JTAG** 给 Zynq 芯片加载 bitstream 和 Zynq 固件。这里的 JTAG 是加载 Zynq 本身，不是目标 F103ZE 的 JTAG。

```powershell
python tools/run_xsct.py tools/download_dap_fpga.tcl `
  prebuilt/20261030_orbtrace_oversample_parser/zynqdap_orbtrace.elf `
  prebuilt/20261030_orbtrace_oversample_parser/orbtrace_oversample_parser.bit
```

脚本需要 Xilinx SDK 2018.3 的 XSCT/hw_server 环境，并会使用 `prebuilt/ps7_init.tcl`。加载完成后，ZynqDAP 的 USB 设备应重新枚举；网页中的 ZynqDAP 连接需要重新授权一次。

### 2.2 F103ZE ETM 线

目标板的 ETM 信号连接到 Zynq J7：

| F103ZE | 目标球位 | Zynq J7 | Zynq 球位 | 信号 |
|---|---|---|---|---|
| PE2 | H16 | J7.16 | H16 | TRACECLK |
| PE3 | H15 | J7.15 | H15 | D0 / TRACEDATA[0] |
| PE4 | G15 | J7.17 | G15 | D1 / TRACEDATA[1] |
| PE5 | H17 | J7.18 | H17 | D2 / TRACEDATA[2] |
| PE6 | N15 | J7.19 | N15 | D3 / TRACEDATA[3] |
| GND | — | J7.14 | — | 信号地 |

要求：

- 目标和 Zynq 必须共地；高速 trace 建议至少使用两根地线。
- ETM 为 3.3 V 电平，TRACECLK 当前约束不超过 50 MHz。
- 先确认 PE2～PE6 没有被目标业务代码重新配置成普通 GPIO。
- SWDIO、SWCLK、GND 仍连接到 ZynqDAP；目标 JTAG 线可以不接。

## 3. 网页采集流程

启动静态网页服务：

```powershell
node web/tools/serve.mjs
```

打开 `http://127.0.0.1:8898/`，进入“ETM 执行轨迹”。页面的四步与参考工程一致，但“逻辑分析仪”已经替换为 Zynq FPGA ETM trace。

### 第一步：调试

1. 点击“浏览载入 ELF”，选择与目标 Flash 完全匹配的 `fw-ze.elf`。
2. 点击“连接 ZynqDAP”。首次使用时浏览器会弹出 USB 授权框；之后可直接重连。
3. 如果需要从固定业务函数开始采集，在函数搜索框中添加硬件断点，再选择该函数作为采集起点。断点使用 Cortex-M FPB，不会修改 Flash。
4. 可以使用“运行至起点”“复位并暂停”“暂停”“继续”检查目标状态。

网页开始采集前会逐字节核对目标 Flash 与 ELF 的加载段。ELF 不匹配时会拒绝采集，避免把错误的指令镜像交给 OpenCSD。

### 第二步：时钟

1. 保持“自动配置并恢复 F103ZE ETM”勾选。
2. 先使用默认 TRACECLK 分频；出现信号完整性问题时，优先选择更低的目标 Trace 工作点并重新验证。
3. “读取 Trace 寄存器”用于确认 DEMCR、DBGMCU、ETM、TPIU 和 GPIOE 配置。
4. “读取固件诊断”用于确认目标固件的时钟、运行状态和 ETM 状态。
5. “只配置不采集”只写入 ETM/TPIU 配置，不启动 FPGA 接收；“恢复原 trace 设置”用于撤销这一步的修改。

网页不会替目标修改 PLL/HCLK。需要降低目标 CPU/Trace 频率时，应使用目标固件的低频配置，或使用 CLI 的临时诊断分频；网页中的 Trace 分频只影响 ETM/TPIU 输出配置。

### 第三步：采集

点击“开始采集”。自动流程为：

1. 核对目标 Flash 与 ELF。
2. 暂停目标 CPU。
3. 保存并配置 ETM、TPIU、DBGMCU 和 GPIOE。
4. 让 FPGA ETM 接收端进入采集状态。
5. 启用 ETM 并恢复目标运行。
6. 按设定时长停止，等待 FPGA 的结束包，再恢复目标寄存器和原有断点。

默认采集时长为 10 ms。需要手动结束时把时长设为 0，然后点击“停止”。建议第一次先用 5～10 ms，确认无丢失后再增加窗口。

采集结束后，状态栏至少应满足：

- `ETM 字节` 大于 0；
- `同步 / 完整结束`；
- 没有 `有丢失`、overflow 或包序号缺口；
- source ID 为 2；
- FCLK 通常显示约 100 MHz（取决于实际加载的 Zynq 固件配对）。

### 第四步：文件与分析

页面支持三种入口：

- “载入真实 CM3 仿真样例”：验证网页解码和分析，不需要接板。
- “载入 F103ZE 实板样例”：验证真实 ETM 字节、调用树和火焰图。
- “导入记录”：打开网页保存的 `.zetm` 记录，离线重新解码。

采集或导入后点击“解码 / 重新解码”。解码在浏览器 Worker 中运行 OpenCSD WASM，不依赖 Python 或 Kingst 服务。

## 4. 查看火焰图

解码完成后，右侧分析页签可查看：

- **执行流**：每段指令的 PC 起止、分支类型、调用深度和所属函数。
- **调用统计**：函数调用次数、自身执行量、包含子树执行量和占比。
- **火焰图**：按调用路径折叠，横向宽度表示执行半字数量；重复调用会聚合。
- **热点**：按包含子树执行量排序的热点函数。
- **ETM 包**：包类型、字节数和最近原始包。
- **可信区段**：显示 TRACE_ON、失同步、地址问题和区段可信性。

点击执行流中的一条记录可以查看历史调用栈。载入配套源码后，源码窗格会显示对应文件和行附近内容；没有 DWARF 行表时仍可查看机器码字节和地址。

“导出火焰图 SVG”生成可在浏览器或矢量编辑器中打开的 SVG；“导出分析 JSON”保存区段、问题、函数统计和包样本；“导出执行流 CSV”保存每段执行范围。

## 5. 已验收基线

使用上述 bit/ELF 配对和 F103ZE 接线，已验收工作点为：

- HCLK：48 MHz；
- 目标物理 TRACECLK：24 MHz；
- Zynq FCLK：100 MHz；
- source ID：2；
- ETM 字节：1309；
- 传输记录：1309；
- FIFO 丢失：0；
- OpenCSD 错误码：0；
- 指令范围：6368；
- 函数：8；
- 调用次数：253；
- 最大调用深度：3。

网页样例文件为 `web/samples/f103ze-oversample.zetm`。它可以在没有硬件的情况下复现解码、调用统计和火焰图流程。

## 6. EMI、降频和原始码流排查

### 6.1 先看状态和寄存器

- `0 ETM 字节 · 很多传输记录`：先核对 source ID、ETM Trace ID、目标是否真的运行，以及 PE2～PE6 是否被配置为复用输出。
- 有记录但 `未同步`：优先检查 TRACECLK、地线、J7 针脚和 bit/ELF 配对。
- `有丢失` 或 overflow：说明接收窗口、FIFO 或 USB 排空速度已经超过当前工作点。

### 6.2 降低工作点

怀疑 EMI 或边沿质量时按以下顺序处理：

1. 缩短采集时长，先确认 5～10 ms 无丢失。
2. 降低目标固件的 HCLK/TRACECLK 工作频率；网页不会自动改目标 PLL。
3. 降低 F103 PE2～PE6 的 GPIO 输出速度，重新采集并比较同步、丢失和解码错误。
4. 加强目标与 Zynq 的地线，缩短并行线，避免线缆贴近高速 USB/电源开关节点。
5. 重新读取 Trace 寄存器，确保降频后目标仍输出四位并行 trace。

CLI 可用于一次性的低频/原始码流对照。它不会烧写目标 Flash，会在结束时恢复目标 CoreSight 和时钟寄存器：

```powershell
python tools/test_orbtrace_board.py `
  --target-elf E:\superlinkPRO\etm\firmware\stm32f103_cdc_trace\fw-ze.elf `
  --bit prebuilt/20261030_orbtrace_oversample_parser/orbtrace_oversample_parser.bit `
  --elf prebuilt/20261030_orbtrace_oversample_parser/zynqdap_orbtrace.elf `
  --output build/etm-f103-check `
  --milliseconds 10 `
  --hclk-div 2 `
  --gpio-speed 1
```

其中 `--hclk-div 2/4` 是目标 AHB 的临时诊断分频，`--gpio-speed 1` 是较慢的 PE2～PE6 输出模式；它们不是网页 Trace 分频的同一含义。要抓 FPGA 看到的原始 DDR 字节，可额外加 `--raw`：

```powershell
python tools/test_orbtrace_board.py `
  --target-elf E:\superlinkPRO\etm\firmware\stm32f103_cdc_trace\fw-ze.elf `
  --bit prebuilt/20261030_orbtrace_oversample_parser/orbtrace_oversample_parser.bit `
  --elf prebuilt/20261030_orbtrace_oversample_parser/zynqdap_orbtrace.elf `
  --output build/etm-f103-raw `
  --milliseconds 10 --raw
```

`--raw` 输出的是接收端采样的 DDR 原始字节，不是可以直接交给 OpenCSD 的 ETM 流；正常网页采集则保存解复用后的 source ID 2 ETM 字节。

## 7. 结束和恢复

停止采集后应看到目标 CoreSight 配置恢复，页面断开前再点击“断开”。如果浏览器或 USB 在采集中断开：

1. 先停止网页采集并重新连接 ZynqDAP；
2. 确认目标仍有 SWD 响应；
3. 必要时重新加载 Zynq bit/ELF 配对；
4. 再做一次“读取 Trace 寄存器”确认 DEMCR、ETM 和 TPIU 已恢复；
5. 不要把一次有 overflow 或未同步的记录当成有效火焰图。

## 8. 相关文件

- [ETM 页面移植说明](完整ETM页面移植说明.md)
- [F103ZE ETM 过采样端到端验收](ETM过采样端到端验收-20261030.md)
- [Web 工作台说明](../web/README.md)
- [FPGA/Zynq 产物清单](../prebuilt/20261030_orbtrace_oversample_parser/manifest.json)
- [ETM 接收协议](../web/app/etm/protocol.js)
- [ETM 分析与火焰图](../web/app/etm/analysis.js)
