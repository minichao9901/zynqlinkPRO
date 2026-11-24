# 固件与目标产物

| 配对 | 用途 |
|---|---|
| [RAW4 融合 bit/ELF](selectio-usb-split-raw4-20261123/README.md) | 三板功能、性能和极限测试的唯一探针配对，经 JTAG/RAM 临时加载 |
| [融合前一轮 SPI CDC 配对](selectio-spi-cdc-rx-guard-20261123/README.md) | ABI 1 的归档记录 |
| [SPI 三线采样诊断配对](selectio-spi-pad-diag-20261124/README.md) | H743 SPI 输入边沿诊断归档 |
| [主线 RAM 配对](release-20261106/README.md) | `probe-load` 默认的主线回退和 ETM 同板对照 |
| [正式 QSPI 固定包](qspi-release/README.md) | `probe-flash` 与本机 Web 手册使用 |
| [Golden](golden/README.md)、[历史恢复包](recovery/README.md) | 正式配对复测与回退 |
| [H743 CDC Golden](targets/stm32h743-cdc-trace-20261101/README.md) | 当前融合 ETM 验收使用的目标 MCU 固件 |
| [三板目标验收镜像](../firmware/target/README.md) | 每块板的 `images/` 提供 ELF、BIN、HEX 和清单 |

融合验收使用 `python -X utf8 toolbox.py probe-load --selectio`，完整加载参数和回执核对见融合验收手册。每套配对的板测范围、时序和 SHA-256 随其清单提供。 [融合验收手册](../docs/selectio/fusion-acceptance.md)

[用例与依赖](../acceptance-cases.json) · [当前验收索引](../docs/validation/README.md) · [融合前产物及验收档案](../docs/validation/README.md#融合前档案)
