# F103ZE 精英板 HAL 存储 Trace 例程

`fw.elf/bin/hex` 是本轮实际烧录、采集使用的 v3 字节；ELF SHA-256 `dbaff7a388bb66fb2d1439f729f60c4f6620ff464c623bda80e2a3f7ef6a4d44`。源码、受控写入和备份/恢复方法见 [例程说明](../../../firmware/target/stm32f103_hal_storage/README.md)。

CPU/HCLK48MHz、TRACECLK24MHz、SPI2 1.5MHz、I2C1 100kHz。实际板载 JEDEC EF4018、EEPROM 0x50应答。上电只读；写入需有效主机备份和一次性arm。只允许 NOR 最后4KiB和 EEPROM 首256B，事务结束逐字节恢复并独立从外设重读。

已完成 CLI 和原生辅助Web接口各三轮1秒采集、完整外设恢复及新旧算法差分。首次固定EXE普通“联动采集”被ZL-134阻塞，故本说明不提前宣称普通按钮流程通过；最终结果以 [主线真机验收报告](../../../docs/validation/main-web-hardware-20261103/README.md) 及本目录验收manifest为准。

`build-manifest.json`如实保存编译时baseRevision=41e2cee、sourceDirty=true及全部输入SHA；后续提交/验证的源码绑定单独记录，不把编译时工作区伪装为干净提交。探针配对使用已归档 `prebuilt/fclk133-release-20261101/`，没有重建PL/PS或写QSPI。
