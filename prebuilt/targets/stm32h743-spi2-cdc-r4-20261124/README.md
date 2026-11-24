# H743 SPI2 夹具修订 4

USB CDC 兼容修订 3。空闲时 `SPI EDGE` 查询驱动速度，`SPI EDGE 3 1 0` 分别设置 SCK、数据线和 NSS。`SPI FILL 0xff` 为主机发送选择固定码型，`SPI FILL PATTERN` 恢复伪随机载荷。复位和 `SPI DRIVE 3` 的默认驱动均为 3。

镜像哈希见 [manifest.json](manifest.json)，上板状态见 [复查记录](../../../docs/validation/h743-spi2-100mhz-20261124/README.md)。
