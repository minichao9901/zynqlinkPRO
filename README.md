# zynqlinkPRO

Zynq-7020 CMSIS-DAP 探针：PL SWD/JTAG/RTT/HSS 与并行 ETM，PS USB/OCM 固件，配套 Web/CLI 工作台。

**[在线工作台](https://minichao9901.github.io/zynqlinkPRO/) · [工程下载](https://minichao9901.github.io/zynqlinkPRO/#download) · [Windows 完整包](https://github.com/minichao9901/zynqlinkPRO/releases/latest/download/zynq-etm-bridge-win64.zip)**

使用桌面版 Chrome / Edge。ETM 采集、原生解码及离线分析请下载完整包，解压后双击 `zynq-etm-bridge.exe`，无需 Python / Node.js。保留完整目录及 `_internal`；更新前退出旧程序并保留 `data`。本机固定入口为 `dist/zynq-etm-bridge/zynq-etm-bridge.exe`。

## 当前交付

| 内容 | 入口 |
|---|---|
| J7 转接板 bit + Zynq ELF | [release-20261106](prebuilt/release-20261106/README.md) |
| Golden / QSPI 恢复 / 目标 ELF | [正式产物索引](prebuilt/README.md) |
| Windows 工作台 v1.3.0 与 WebUSB | [构建、实板与发布报告](docs/validation/release-20261106/README.md) |
| F103ZE ETMv3 / H743 ETMv4 | [Trace CLI](docs/Trace-CLI使用说明.md)、[H743 报告](docs/validation/h743-comprehensive-20261101/README.md) |
| 飞行记录 / HTML 火焰图 / 报告导出 | [飞行记录](docs/validation/session-flight-recorder-20261105/README.md)、[HTML 导出](docs/flame-html-export.md) |

J7 当前 bit 含五路 ELD1 与原始 SWD 序列修复，默认零 tap。频率、适用目标、实际验收与已知限制以配对 manifest 和[问题索引](docs/项目问题跟踪列表.md)为准。网页提示由浏览器控制；RAM 加载不等于 QSPI 固化。目标 PLL/AHB/APB 由目标固件负责，工作台不自动改频。

## 开发入口

先读 [AGENTS.md](AGENTS.md)、[问题索引](docs/项目问题跟踪列表.md)、[文档导航](docs/README.md)和[CLI 工作台](docs/toolbox-cli-ai.md)。工具经 [toolbox.py](toolbox.py) 发现，依赖见 [构建说明](docs/dependencies.md)。

```powershell
python -X utf8 toolbox.py project list
python -X utf8 toolbox.py trace doctor --offline
python -X utf8 toolbox.py project run web.check
python -X utf8 toolbox.py bridge-build --zip
```

业务 Trace 只保留 [5 份精选记录](docs/retained-records.json)，测试另保留必要固定输入。历史逐轮证据和实验产物已按[归档索引](docs/validation/README.md)退出当前目录；失败与暂停结论仍有效。GitHub Pages 从 `gh-pages` 分支发布，EXE 放 Releases；发布步骤见 [GitHub 发布](docs/github-release.md)。
