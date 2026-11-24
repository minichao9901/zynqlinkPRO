# zynqlinkPRO SelectIO 融合工程

基于 XC7Z020 和 J7 转接板。一个 bitstream 提供 SWD/JTAG 调试、原生 SRAM、RTT、J-Scope、物理 COM、标准 SWO、四线 SPI 和四位 ETM。PS 通过 USB 传输，ETM 数据在 PS DDR 缓冲后由主机下载。

当前开发分支为 `codex/selectio-efficiency`。默认阅读和测试对象是 [RAW4 融合 bit/ELF 配对](prebuilt/selectio-usb-split-raw4-20261123/README.md)，原生 USB 使用 ABI 2。已验收配对使用 JTAG/RAM 临时加载。[USB 端点](docs/selectio-native.md) · [J7 接线与 CLI](docs/selectio/README.md)

## 开始使用

在仓库根目录执行。先核对输入配对和板卡占用。

```powershell
$pair = 'prebuilt/selectio-usb-split-raw4-20261123'
python -X utf8 toolbox.py probe-load --pair $pair --dry-run
python -X utf8 toolbox.py probe-load --pair $pair --out build/fusion-load
python -X utf8 toolbox.py selectio --serial 12345678 info
python -X utf8 toolbox.py selectio --help
```

ETM 采集时同时声明探针 bit、探针 PS ELF 和目标 MCU ELF。目标 ELF 必须与实际目标固件一致。[Trace CLI](docs/Trace-CLI使用说明.md)

## 当前验收

| 项目 | 已确认范围 |
|---|---|
| H743 ETM | 历史 CDC Golden，TRACECLK 20 MHz，10／200／500／1000 ms 各三轮，12/12 严格通过 |
| H743 SWD | SRAM、独立 RTT、J-Scope 单变量和八变量，以及并发 |
| H743 JTAG | HCLK240 下 72.727 MHz SRAM 交替 3×60 s 通过。独立 RTT 在 50 MHz 跑 60 s 通过，72.727 MHz RTT 和 100 MHz SRAM 留有已登记边界 |
| COM 与 SWO | COM 双向，SWO NRZ 和 Manchester 实板逐字节对拍 |
| SPI | 主机 100 MHz 四模式全双工仿真及独立 MISO 实板检查。全速四模式双向及 ABI 2 从机接收仍待实板 |

[功能验证](docs/validation/h743-cdc-golden-requal-20261123/README.md) · [HCLK 对照及 JTAG 长窗](docs/validation/h743-hclk-ab-20261123/README.md) · [用例编号和判据](docs/selectio/fusion-performance-cases.md) · [当前问题](docs/项目问题跟踪列表.md)

三块 MCU 的验收固件、构建入口、接线与极限测速条件见[目标固件总表](firmware/target/README.md)。

## 开发

```powershell
python -X utf8 toolbox.py project list
python -X utf8 toolbox.py trace doctor --offline
python -X utf8 tools/verify_dependencies.py
python -X utf8 toolbox.py project run test.cli
python -X utf8 toolbox.py project run test.web
```

- 构建、加载与验收从[工程文档](docs/README.md)进入。配对 SHA-256、实施时序和实板范围随产物提供。
- `web/` 和 `etm-service/` 提供 Web 工作台与 Trace 分析。当前融合版实板以 CLI 记录为准，新 Web 的 ABI 2 对接另行验收。
- 固定 EXE、公开 Pages、Release 和 QSPI 包沿用各自的发布配对。对融合固件使用显式 `probe-load --pair`。[发布与交付](docs/github-release.md)
