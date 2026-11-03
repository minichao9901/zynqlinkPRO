# F103ZE 精英板：HAL SPI Flash / EEPROM Trace 例程

面向正点原子精英 STM32F103ZE：CPU/HCLK48MHz、TRACECLK24MHz、HSE8MHz。用真实 `HAL_SPI_Transmit/Receive` 和 `HAL_I2C_Mem_Read/Write` 访问存储器，保留 SysTick 中断、状态轮询、错误分支、跨页写入和校验调用栈。上电及空闲循环仅识别/读取，不自动擦写。

这是独立于 CDC 的第二个业务例程；日志用 SEGGER RTT，控制用带符号的 SRAM mailbox。USART、目标 USB 均不使用。探针只配置 Trace，不修改 MCU PLL。

## 板载连接与实物识别

| 设备 | 接线/配置 |
|---|---|
| 25Q128 SPI NOR | SPI2：PB12 CS、PB13 SCK、PB14 MISO、PB15 MOSI；PCLK1=24MHz /16，SCK1.5MHz；Mode0 |
| 24C02 兼容 EEPROM | I2C1：PB6 SCL、PB7 SDA，100kHz，7位地址0x50，8位存储地址；保守8字节页 |
| Trace | PE2 TRACECLK，PE3～PE6 D0～D3；保持与 CDC48 相同接线 |

接线依据正点原子精英板硬件资料；[官方资料入口](https://www.openedv.com/docs/boards/stm32/zdyz_stm32f103_jingyingV2.html)，[原厂编写的精英板指南镜像](https://uploadcdn.oneyac.com/attachments/files/00/00/STM32F1%E5%BC%80%E5%8F%91%E6%8C%87%E5%8D%97%28%E7%B2%BE%E8%8B%B1%E7%89%88%29-%E5%AF%84%E5%AD%98%E5%99%A8%E7%89%88%E6%9C%AC_V1.0.pdf)。共用 SPI2 的无线模块应保持未选中；本次不驱动未确认的无线模块 GPIO。实物只读阶段返回 JEDEC **EF4018 / 16MiB**，I2C地址0x50应答；EEPROM型号依据板型资料，不把应答地址当独立芯片ID。

## 只构建

```powershell
python -X utf8 firmware/target/stm32f103_hal_storage/build.py --out build/hal-storage-new
```

依赖仓库内 `../stm32f103_cdc_trace/` 的已跟踪 CMSIS、HAL、链接脚本和 RTT；没有外部 SDK 绝对路径。新增 SPI/I2C HAL 源码固定到 ST 官方 v1.1.10、提交 `77fbb30b7a1d02533980400083e48c559aae5a4f`，版本与已有 HAL 一致，[来源和哈希](vendor/provenance.json)、[许可证](vendor/LICENSE.md)。构建输出 ELF/BIN/HEX、map、反汇编、符号及源码/编译参数/产物 SHA manifest；构建不会烧录。

## 写入范围与恢复契约

固件只允许擦写识别出的 NOR **最后一个4KiB扇区**；当前16MiB器件为 `0x00fff000..0x01000000`。EEPROM仅使用首256字节。不会解除 NOR 保护位、修改状态寄存器、触碰其他扇区或写探针 QSPI。

`g_storage` 是版本1的状态/mailbox，magic=`0x53544f52`。命令1识别和读取；2双读备份；3执行一次测试并恢复；4从已验证备份恢复。命令3还要求 `arm=0x53545257`，执行时即消费这个授权。只写command而没有授权和有效备份不会进入测试。

测试：擦除该扇区，从偏移0xf0编程512B，覆盖256B页边界，读回逐字节比较；EEPROM从0xdb写29B，按8B页拆分并读回比较；随后恢复整4KiB扇区和整个256B EEPROM，再读回比较。测试失败仍进入恢复；恢复失败保留dirty标志和备份。状态字段的`fnv`是FNV-1a32校验，主机原始备份另用SHA-256，不冒充CRC。

初次运行写入测试前必须把备份读到主机。RAM备份不能跨断电保存。主机备份含用户原有数据，不纳入Git。

## CLI采集一个完整写入事务

先备份目标原固件，再烧录并独立核对本例程 ELF；加载并核对探针 DDR bit/PS ELF。以下假设实际已经加载 `prebuilt/fclk133-release-20261101/`，不会替你加载配对。

```powershell
python -X utf8 tools/hal_storage_fixture.py --stage backup --elf <fw.elf> --out build/storage-backup-new --execute
python -X utf8 tools/hal_storage_fixture.py --stage arm --elf <fw.elf> --backup build/storage-backup-new --out build/storage-arm-new --execute
python -X utf8 toolbox.py trace capture --elf <fw.elf> --bit prebuilt/fclk133-release-20261101/probe.bit --zynq-elf prebuilt/fclk133-release-20261101/application.elf --entry storage_exercise --seconds 1 --swd-khz 10000 --out build/storage-trace-new
python -X utf8 tools/hal_storage_fixture.py --stage verify --elf <fw.elf> --backup build/storage-backup-new --out build/storage-verify-new --execute
```

arm有意暂停核心，供Trace设置起点再继续。verify要求事务已完成、无错误、写入与校验轮数一致、dirty=0；然后重新从实际外设双读，不只检查RAM旧备份。无写入对照直接以 `storage_read_cycle` 为起点采集。

Web载入同一ELF及本目录源码，起点选择 `storage_exercise`，SWD10MHz、1秒；用同一主机备份/arm步骤后再采集，完成后运行verify。新旧算法比较必须对同一份raw记录进行，不能拿不同采集窗口的指令数做差分。

本轮实物证据、差分结果、交付ELF及最终恢复状态见 [主线真机验收报告](../../../docs/validation/main-web-hardware-20261103/README.md)。初次构建/启动失败与不通过的Web HSS均保留，不能从本说明推定全部功能已通过。
