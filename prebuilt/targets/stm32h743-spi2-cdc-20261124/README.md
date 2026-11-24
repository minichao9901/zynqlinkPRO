# H743 USB CDC SPI2 夹具

适用正点原子阿波罗 STM32H743，HSE 25 MHz，USB VDD33USB 外供。固件启动后通过 H743 自己的 USB 口枚举 `F055:7432`，序列号 `H743SPI0001`。SPI2 使用 PI0–PI3 的 AF5，空闲释放驱动。命令以换行结束，数据为 8 位、MSB-first，片选低有效。Zynq 使用带 EP10 SPI 的 [RAW4 ABI 2 配对](../../selectio-usb-split-raw4-20261123/README.md)。

| 线 | H743 | ZynqLinkPRO |
|---|---|---|
| NSS | P3-32 / PI0 | J7-31 |
| SCK | P3-33 / PI1 | J7-29 |
| MOSI | P3-25 / PI3 | J7-25 |
| MISO | P3-34 / PI2 | J7-27 |
| GND | P3-1 | GND |

构建使用 `build.ps1 -SpiFixture -CoreMHz 480 -TraceR 24 -BannerEveryMs 0 -NoPublish`。STM32 Flash 从 `0x08000000` 启动。文件哈希与编译选项见 [manifest.json](manifest.json)。实板状态以 [验收记录](../../../docs/validation/h743-spi2-cdc-20261124/README.md) 为准。

## 串口命令

```text
PING
SPI INFO
SPI STATUS
SPI STOP
SPI MASTER TX|FD mode divider bytes frames timeout_ms tx_seed rx_seed
SPI SLAVE RX|FD mode bytes timeout_ms tx_seed rx_seed
SPI STREAM mode divider duration_ms tx_seed
```

从机接收 `SLAVE RX` 只启用 MOSI 接收。`SLAVE FD` 也在 MISO 上返回 `tx_seed` 指定的独立数据。`MASTER TX` 的 `rx_seed` 传 0。主机分频可取 2、4、8、16、32、64、128、256，由 PLL2 的 200 MHz 内核时钟分频得到 100 MHz 到 781.25 kHz。连续 TX 重复同一个 16 KiB DMA 缓冲区。状态中的 `tx_dma` 为送入 SPI 的字节数。连续模式结束时，线上的有效字节以独立接收端的计数为准。`SPI STOP` 或 CDC 关闭时释放 SPI 引脚。

```powershell
python -X utf8 tools/h743_spi_accept.py --cdc-only --out build/h743-spi2-cdc-check.json
python -X utf8 tools/h743_spi_accept.py --out build/h743-spi2-short.json
python -X utf8 tools/h743_spi_accept.py --seconds 60 --repeats 3 --out build/h743-spi2-long.json
```

烧录时 J7 先经 PA13/PA14 运行 SWD。烧录完成并通过 CDC 身份检查后，将 J7-29/31 一次切换到表中的 SPI 接线。同一根 H743 USB 线保留用于切换主从、配置速度和读取校验结果。四模式测试覆盖 J7 原生 SPI 100 MHz → H743 只接收、H743 分档发送 → J7 EP10 接收，以及 J7 原始波形路径的低速双向传输。3.3 V 时 H743 的额定 SPI 从机发送／全双工上限为 31 MHz。 [ST DS12110](https://www.st.com/resource/en/datasheet/DM00387108.pdf)
