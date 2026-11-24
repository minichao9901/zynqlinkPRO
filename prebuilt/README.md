# 固件与目标产物

| 配对 | 用途 |
|---|---|
| [RAW4 融合 bit/ELF](selectio-usb-split-raw4-20261123/README.md) | 当前融合分支的 USB ABI 2，JTAG/RAM 临时加载 |
| [融合前一轮 SPI CDC 配对](selectio-spi-cdc-rx-guard-20261123/README.md) | ABI 1 对照和 F103ZE 复测 |
| [主线 RAM 配对](release-20261106/README.md) | `probe-load` 默认的主线回退和 ETM 同板对照 |
| [正式 QSPI 固定包](qspi-release/README.md) | `probe-flash` 与本机 Web 手册使用 |
| [Golden](golden/README.md)、[历史恢复包](recovery/README.md) | 正式配对复测与回退 |
| [H743 CDC Golden](targets/stm32h743-cdc-trace-20261101/README.md) | 当前融合 ETM 验收使用的目标 MCU 固件 |

显式加载融合配对时使用 `python -X utf8 toolbox.py probe-load --pair prebuilt/selectio-usb-split-raw4-20261123`。每套配对的板测范围、时序和 SHA-256 随其清单提供。探针临时加载和 QSPI 实体冷启动各自取证。

[当前验收索引](../docs/validation/README.md) · [融合前产物及验收档案](../docs/validation/README.md#融合前档案)
