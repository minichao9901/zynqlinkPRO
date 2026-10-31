# QSPI 固化验收（2026-10-31）

本轮按用户授权固化本次 7020/120MHz 优化配对，后续 ETM 滤波改动未合入。启动拨码由用户切到 QSPI 并重新上电，软件读回 BOOT_MODE=1。

实际烧写包在 [prebuilt/20261031_orbtrace_opt_qspi_7020_120](../../../prebuilt/20261031_orbtrace_opt_qspi_7020_120/README.md)。PL源 `bc9ced69f1f8f81647b8d62eaf74100d53fd883f`，固件配对已在 `742eeca` 验收；加载器与CLI后端源提交 `13caecfcf4b83c92608e6a6d4e994e2a237a2eda`。再次构建的BOOT.bin与实际已烧写文件SHA-256完全一致。构建源文件哈希、选项、BSP、三分区MD5校验和ELF布局在包内build_manifest.json；bit/ELF/BOOT身份由flash_manifest.json绑定。

| 检查 | 结果 |
| --- | --- |
| PS IDCODE / Flash | `23727093`（7020）/ JEDEC `EF4019`，单片32MiB |
| 擦写前原备份 | 整片33554432字节，SHA-256 `eba1c30c082caf617f92177e67030ad5c7a0fd567762957f149f19e913413e19` |
| SDK擦除检查、编程、verify | PASS，见program_flash.log |
| BOOT.bin长度 / 擦写范围 | 4264656字节 / `[0,0x412000)` |
| 独立整片回读 | BOOT.bin逐字节一致；擦写范围外与原备份逐字节一致 |
| BOOT.bin及回读SHA-256 | `389c0d2cd52f6087aae038dc6bf35acfff0f0d65b74b98949fbdb5deab9525eb` |
| 整片新回读SHA-256 | `2500c2b2a9444c6b98b24d2d236e22644c83242984bff762f4abdd459542fe2f` |
| 无暂停软件系统复位 | PASS，不执行fpga/dow/con，由QSPI自主引导 |
| 引导交接 | trace=`53544730,20261031,10008,1,2,600,0,1`，QSPI→DDR加载器→OCM入口0 |
| USB / 时钟 | USB 0D28:0204重新枚举；FCLK读回119999998Hz |
| 固化后SWD60短测 | 2KiB、depth32、64块、2轮：读4.83914 / 写4.74603MB/s，数据/SRAM/RCC恢复PASS |
| CLI实际回读及复位流程 | `toolbox.py probe-flash --verify-only` PASS，见cli_verify_pass |
| 损坏镜像拒绝 | dry-run在访问硬件前拒绝BOOT.bin SHA不符，见negative_manifest_test.json |
| 实体按键/断电重启 | 等待用户完成烧写后的操作；此前用户重上电发生在此次烧写前，不计为此项通过 |

原Flash备份和完整回读保留在本机 `E:/zynqlinkPRO_orbtrace_opt/build/qspi_boot/backup/original_flash_32MiB.bin` 及 `post_program/programmed_flash_32MiB.bin`，不提交公开Git；本目录保留哈希、范围和校验结果。

两个调试问题的原始失败记录保留：

- `debugger_reset_halts` / `initial_reset_failure`：SDK2018.3的`rst -system`明确要求`suspend=1`，在复位向量停住，此时DDR尚未初始化。显式继续后启动成功；正式CLI改为同一XilinxReset服务`suspend=0`，随后在没有JTAG下载或继续指令的情况下读到完整QSPI交接记录。
- `cli_initial_cpu_state_failure`：在正在运行的Thumb应用上直接dow ARM辅助ELF，继承的CPU执行/缓存状态导致异常，辅助程序未就绪。CLI现先`rst -processor`，再初始化PS、加载辅助程序。修复后整个CLI回读/复位流程通过，未再擦写Flash。

只读备份程序的13h命令适配和启动链结构见 [firmware/boot](../../../firmware/boot/README.md)。这次固化没有重编应用或改变USB/DAP队列，也没有烧写F103 Flash。F103的临时时钟/RAM夹具与完整50/60MHz性能对照见 [SOTA复测](../orbtrace-sota-20261031/README.md)。实体复位后将只读核对启动及做短测，不用JTAG重新下载掩盖启动问题。

统一CLI源在独立 `codex/qspi-cli-integration` 工作树实现，并以三处插入接入主目录toolbox.py；反向去掉三处插入后，主文件与另一个AI的原未提交文件逐字节一致，主目录Git索引未操作。`main_integration.json`记录核对结果。主目录CLI文档和新增启动包均已安装；其他AI的ETM/native-engine改动保留。
