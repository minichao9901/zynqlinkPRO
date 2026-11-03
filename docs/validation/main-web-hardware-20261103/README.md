# main 合并后 F103ZE 真机验收与 HAL 存储 Trace（进行中）

2026-11-03开始，跨至2026-11-04（Asia/Shanghai）。用户授权全部8页、CLI/历史最佳/Web性能比较，追加精英板HAL SPI Flash/EEPROM例程及新旧算法差分。起点main `41e2cee`，原有未跟踪build/保留；不推送、不写探针QSPI。

**尚不能判全部通过。** 已发现普通Web断点解析的合并回归ZL-134，源码/原生修复及离线回归完成，待重建固定EXE后实际按钮复验；HSS尾部排空ZL-130仍待定位。

## 现场和配对

初始无业务USB，JTAG仅DAP30000021/xc7z020，PL读超时。DAP系统复位后BOOT_MODE=0、FPGA_RST=01F33F0F、LVL_SHFTR=0，属于JTAG启动未初始化现场（ZL-060），不能称为已核对运行配对的新失联。

F103最初复位进ROM、RCC_CFGR=10000a、无CDC。用户确认目标未供电并重新插拔电后，CDC COM34枚举、CDC48两段Flash逐字节匹配、RCC_CFGR=51040a、CPU/HCLK48MHz。ROM/供电不足组排除正式比较，失败保留（ZL-129）。原512KiB Flash双读SHA `48f226217497607c696a156addbb363925577499b00ee64f187bd5eea7a94499`；有效加载段原已与CDC48相同。原字节私留build，收尾须核对恢复。

| 实际RAM加载配对 | bit SHA-256 | Zynq ELF SHA-256 | 范围 |
|---|---|---|---|
| hpm6800-usb-fixed-133-20261102 | 106d579bc1b79c2b873fd1e3eb2609d468892a67613d85a6e41d4dc90c8fc177 | e93f1810d48e77f8d9aa097f643e40e0aaee32bdec1c263c1428f092909e608a | ARM SRAM/RTT/HSS，物理76420B匹配；此bit无DDR ETM |
| fclk133-release-20261101 | af1031d3caa0d7bd3b6adffa911d26efdab9e0bfb5223fb18f70dabb70ebeeed | 2137f7d0f507c08574f36223130103c0710645cbfdefb5c1d8c8efb0cfb990a0 | 后续DDR ETM，重载后独立物理OCM核对 |

没有新建/修改PL或PS。133.333MHz是实现约束及release启动点；SWD10/50/60对应实际FCLK约120/100/120MHz，逐轮读回，为寄存器计算而非频率计测量。未由上位机改变MCU PLL/AHB/APB。

## 页面和性能阶段结果

Web均用真实浏览器及公开页内CLI操作实际本机USB/HID/COM。源码工作台、固定EXE普通按钮和Web原生辅助接口分列，按钮投递不代替数据/质量/恢复验证。

| 页面/能力 | 已验证范围 |
|---|---|
| 串口助手 | PING/INFO、3×8192B精确回显/导出 |
| 终端 | 同一实际串口接收PONG、保存 |
| RTT Viewer | 上行3800B、下行31B逐字节，控制块和RAM/核心恢复 |
| RTT转发 | SWD50/60各3轮，文件/递增序列/发布量/moved完全相等，读写错0 |
| 烧录器 | ELF，CLI/Web各3轮擦写/完整有效载荷校验/复位；其他格式待补 |
| 调试器 | ELF/DWARF、16KiB SRAM三轮/恢复、R12恢复、真实单步和cdc_poll硬断点；更多交互待补 |
| J-Scope | CLI多周期1/8变量逐帧/计数；Web低速STOP尾部排空失败，不能判通过 |
| ETM | CLI CDC100ms和HAL读/写、辅助Web采集/解码/首屏；普通固定EXE起点路径ZL-134待重建复验 |

SRAM峰值：512 words、depth32、256 blocks、3重复，另3秒读写soak。历史峰值短测参数相同，历史10/60秒soak不冒称本轮时长。

| 项目 | 本轮CLI中位 | 历史或本轮Web |
|---|---:|---|
| SRAM SWD50读/写 | 4.0492 / 3.9806 MB/s | 历史Golden4.0498 / 3.9824，配对不同 |
| SRAM SWD60读/写 | 4.8315 / 4.7385 MB/s | 历史Golden4.8348 / 4.7479，不推断统计等效 |
| RTT SWD50 / 60，1024B块 | 3.8816 / 4.6437 MB/s | 历史Golden3.8832 / 4.6460；本轮3秒、历史2秒 |
| 控制API SRAM10，16KiB读/写 | 0.6520 / 0.6413 MB/s | Web含HTTP/JSON开销0.1094 / 0.0604 |
| 8192B CDC往返有效吞吐 | 0.2270 MB/s | Web发/接收检查/首屏0.0313，不是USB线速 |
| 约20KiB ELF烧录/校验/复位 | 1.450s | Web2.704s；边界近似，非内部同函数计时 |

RTT转发Web首末非空数据活动段中位3.9795/4.7840MB/s，与CLI硬件计数窗口口径不同，暂不计算严格同口径提速百分比；Web整5秒窗又包含等待/排尾。原计时和数据校验保留，后续正式对照须统一条件。

## 第二个例程：HAL外设读写

[源码/安全运行方法](../../../firmware/target/stm32f103_hal_storage/README.md)，[实际ELF](../../../prebuilt/targets/f103ze-hal-storage-20261104/README.md)。独立于CDC，HAL SPI2/I2C1业务，启动/100ms循环只读，写入需主机备份和一次性arm。

实物JEDEC **EF4018 /16MiB**，EEPROM0x50应答。双读备份NOR `0x00fff000+4096`、EEPROM `0+256`，主机原备份SHA分别 `ec49cab04f685666b5536a49d6a9e0ada6975ebb72087ebf8136b41668f2b49f` / `ba6b09b3804088cb4fc17bdee75f974356a1d9fa30d1c1f4b6e4b7685cdf38af`；原数据不提交。

事务从NOR偏移0xf0跨256B页编程512B，EEPROM从0xdb写29B按8B页拆分，逐字节比较；恢复整个4KiB/256B后，再独立从实际外设双读。CLI与辅助Web各3轮，加功能/源码窗口均恢复核对通过。普通按钮失败轮尚未执行的写入命令已取消，dirty=0。

实际v3 ELF SHA `dbaff7a388bb66fb2d1439f729f60c4f6620ff464c623bda80e2a3f7ef6a4d44`。HAL1.1.10及固定ST官方SPI/I2C补充源码，全部输入/参数/产物SHA见build manifest。ZL-132缺强USB向量、ZL-133初版WFI读回边界保留，不把失败字节当交付。

1秒HAL CLI三轮9.962/9.812/9.777秒；**Web原生辅助接口**10.875/10.798/10.755秒，不是日常联动全部前端控制。每轮约1729～1742万路径，包错/frameDrops/parserErrors/writerError为0，硬件1秒完整；未知执行/起止gap按原值保留，不能据包错0证明全部执行可信。普通按钮性能待修复后测量。

## 新旧差分及合并回归

HAL CLI首轮同一raw和ELF，旧参考tag `archive/main-before-etm-cpp-20261103` /06452f2，参考worktree未改。

- 全函数、DWARF行区间、segments、Web ELF DTO一致。
- 完整执行块、诊断、analysis、默认视图、语义meta及60表dtype/shape/每个值一致。
- 固定Golden实际生成旧库，new direct/binary/rescan/repeat四组完整60表一致，5种真实输入变化拒绝；不以总数相同代替差分。
- 182查询深度DTO一致。断点修复后新编核心再次13专项、三ELF静态、HAL完整60表和182查询通过。

ZL-134：普通Web起点仍调`image.elf.get_section_by_name`，NativeImage无该pyelftools接口。修复由C++按$t/$d/$a映射给出Thumb可断点边界，Python仅解析规格/组DTO；三ELF全部边界与旧参考一致，literal pool/奇地址/无代码行不放宽。HTTP测试同时禁止Python ELF/Capstone入口。普通固定EXE重建及真按钮重验尚未完成。

源码检查160模块、128Web、56CLI通过，不能据自测宣称全部板上功能通过。[原生构建身份](raw/native-build-identity.json)保留源码SHA和前后程序身份。

## 未通过项和进行中状态

ZL-130：Web 1×u32/1kHz停止超时。RAW4389点、缓存4283，独立最终4408，原RAW缺19点；USB/序号错0不足以证明尾部完整。额外夹具HID关闭后仍复现。[原RAW](raw/hss-stop-failure.jsp)可按已知模式独立复验；`hss-after-cleanup.png`仅是清理后界面，不是失败提示截图。

ZL-131：长RAM producer后CDC枚举但端口配置WinError31；已有UsbReconnect短暂拉低/恢复PA12并从原初始化入口恢复，随后CLI/Web精确回显通过，根因仍待定位。

已结束夹具均核对RAM、核心、时钟和运行状态恢复。当前目标运行HAL只读循环，外设dirty=0，私有备份保留；旧固定EXE是本任务PID17380，独立data在build，共享hw_server保留。**最终内部Flash/NVM/进程恢复待收尾更新。**

工作输出 `build/main-web-hardware-20261103/`；[有界公开证据索引](raw/evidence-manifest.json)。令牌、原Flash、SRAM/GPR和外部NVM原字节不入Git。
