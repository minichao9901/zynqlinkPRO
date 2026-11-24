# zynqlinkPRO SelectIO 融合工程

基于 XC7Z020 和 J7 转接板。一个 bitstream 提供 SWD/JTAG 调试、原生 SRAM、RTT、J-Scope、物理 COM、标准 SWO、四线 SPI 和四位 ETM。PS 通过 USB 传输，ETM 数据在 PS DDR 缓冲后由主机下载。

开发分支为 `codex/selectio-efficiency`。融合复验的通用参考为 [RAW4 ABI 2 配对](prebuilt/selectio-usb-split-raw4-20261123/README.md)，经 JTAG/RAM 临时加载。省略配对参数时，`probe-load` 的命令默认值为 [release-20261106](prebuilt/release-20261106/README.md)。融合复验按用例显式指定 `--pair`。 [USB 端点](docs/selectio-native.md) · [J7 接线与 CLI](docs/selectio/README.md)

## 开始使用

在仓库根目录先查用例和预览配对。实际加载前核对已运行的配对、板卡占用和本轮授权。

```powershell
$pair = 'prebuilt/selectio-usb-split-raw4-20261123'
python -X utf8 toolbox.py project cases
python -X utf8 toolbox.py probe-load --pair $pair --dry-run
```

确认本轮允许 JTAG/RAM 临时加载后，执行加载并核对枚举。

```powershell
$pair = 'prebuilt/selectio-usb-split-raw4-20261123'
python -X utf8 toolbox.py probe-load --pair $pair --out build/fusion-load
python -X utf8 toolbox.py selectio --serial 12345678 info
python -X utf8 toolbox.py selectio --help
```

ETM 采集时同时声明探针 bit、探针 PS ELF 和目标 MCU ELF。目标 ELF 必须与实际目标固件一致。[Trace CLI](docs/Trace-CLI使用说明.md)

## 当前验收

| 项目 | 已确认范围 |
|---|---|
| F103ZE | CDC48 用于功能回归和 ETM 基线，按用例核对配对。HCLK128 SRAM/RTT 性能用临时 SRAM 夹具单独取证。 |
| H743 ETM | 历史 CDC Golden，TRACECLK 20 MHz，10／200／500／1000 ms 各三轮，12/12 严格通过 |
| H743 SWD | SRAM、独立 RTT、J-Scope 单变量和八变量，以及并发 |
| H743 JTAG | HCLK240 下 72.727 MHz SRAM 交替 3×60 s 通过。独立 RTT 在 50 MHz 跑 60 s 通过，72.727 MHz RTT 和 100 MHz SRAM 留有已登记边界 |
| COM 与 SWO | COM 双向，SWO NRZ 和 Manchester 实板逐字节对拍 |
| SPI | [新版滤波配对](prebuilt/selectio-spi-pad-filter-v2-20261124/README.md)上，H743 → J7 EP10 在 50 MHz 四模式各 3×60 秒通过，12 轮零错字节、零成帧、零丢弃。同配对约 25 MHz 全双工四模式短测通过。100 MHz 任意数据从机接收仍待验。 |

[新融合配对的三板验收](docs/selectio/fusion-acceptance.md) · [实板证据索引](docs/validation/README.md) · [SPI 四模式长窗](docs/validation/h743-spi2-100mhz-20261124/README.md#50-mhz-持续验收) · [当前问题](docs/项目问题跟踪列表.md)

[用例清单](acceptance-cases.json)关联参数、配对、目标 ELF 和证据。三块 MCU 的已编译镜像、接线与极限测速条件见[目标固件总表](firmware/target/README.md)。

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
