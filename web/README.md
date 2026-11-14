# zynqlinkPRO Web 工作台

工作台以 ES 模块组织，提供串口助手、终端、RTT Viewer、RTT 转发、J-Scope 波形、烧录器、调试器和 ETM 执行轨迹。另有工程下载入口，本机工作台可打开可执行手册。

## 启动

- [线上工作台](https://minichao9901.github.io/zynqlinkPRO/)支持 Chrome 和 Edge 的浏览器设备接口。[工程下载](https://minichao9901.github.io/zynqlinkPRO/#download)提供 Windows 便携包。
- Windows 日常启动 `dist/zynq-etm-bridge/zynq-etm-bridge.exe`。程序提供本机探针通路、ETM 采集与解码和可执行手册。手册依赖本机仓库和 Python。
- 从源码启动完整工作台，用 `python -X utf8 toolbox.py --runtime build/workbench-new serve --port 0 --open-browser`。有本机探针需求时按 [CLI 工作台](../docs/toolbox-cli-ai.md#启动与操作-web)配置。
- 只预览静态前端，用 `node web/tools/serve.mjs`，默认地址 `http://127.0.0.1:8898`。ETM 页嵌入本机服务，完整工作台在同源 `/etm` 提供该服务，静态前端也可连接独立 ETM 服务。

## 设备通路

| 功能 | 通路 |
|---|---|
| 串口助手、终端 | Web Serial 或本机桥接，共用串口会话 |
| RTT Viewer、烧录、调试 | OpenOCD Wasm 经 CMSIS-DAP；J7 的 HPM6800EVK Viewer 符合 SRAM 条件时使用探针 SBA 块传输 |
| RTT 转发 | 探针 HID 控制，CDC 串口接收 |
| J-Scope | 探针 HID 控制及 HSS Bulk，或 OpenOCD Wasm 主机轮询 |
| ETM | 本机服务接管探针采集，执行解码、索引和导出 |

J7 的 CLI 与本机 Web 手册共用[正式 QSPI 固定目录](../prebuilt/qspi-release/README.md)。安装包和 Pages 版本见[发布记录](../docs/github-release.md)。

## 验收

开发检查运行 `python -X utf8 toolbox.py project run web.check` 和 `python -X utf8 toolbox.py project run test.web`。实板覆盖及边界见 [H743 Web／JTAG 与 ETM](../docs/validation/h743-workbench-acceptance-20261109/README.md)、[HPM6800EVK 端到端验收](../docs/validation/hpm6800-e2e-20261114/README.md)和 [RTT Viewer 与转发复测](../docs/validation/hpm6800-rtt-viewer-20261114/README.md)。待验项以[问题索引](../docs/项目问题跟踪列表.md)为准。
