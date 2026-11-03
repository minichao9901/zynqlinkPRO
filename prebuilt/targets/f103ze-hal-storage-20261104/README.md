# F103ZE 精英板 HAL 存储 Trace 例程

`fw.elf/bin/hex` 是本轮实际烧录、采集使用的 v3 字节；ELF SHA-256 `dbaff7a388bb66fb2d1439f729f60c4f6620ff464c623bda80e2a3f7ef6a4d44`。源码、受控写入和备份/恢复方法见 [例程说明](../../../firmware/target/stm32f103_hal_storage/README.md)。

CPU/HCLK48MHz、TRACECLK24MHz、SPI2 1.5MHz、I2C1 100kHz。实际板载 JEDEC EF4018、EEPROM 0x50应答。上电只读；写入需有效主机备份和一次性arm。只允许 NOR 最后4KiB和 EEPROM 首256B，事务结束逐字节恢复并独立从外设重读。

已完成 CLI、原生辅助Web接口和修复后的固定EXE普通“联动采集”各三轮1秒采集及实际外设恢复。首次普通按钮的ZL-134失败保留，修复后通过；同一实际HAL输入新旧完整60表和182查询一致，最终EXE也已导入并显示该记录。范围和源码绑定见 [acceptance.json](acceptance.json) 与 [主线真机验收报告](../../../docs/validation/main-web-hardware-20261103/README.md)。

`build-manifest.json`如实保存编译时baseRevision=41e2cee、sourceDirty=true及全部输入SHA；后续提交/验证的源码绑定单独记录，不把编译时工作区伪装为干净提交。HAL正式三轮使用已归档 `prebuilt/fclk133-release-20261101/` bit/PS；全页验收后续另建统一PS候选配对，见主线报告。未新做PL实现或写QSPI；最后目标已恢复原CDC48固件。
