# J7 QSPI 固化与项目主页整理

2026-11-06。用户授权用本项目CLI固化探针QSPI，并将README整理为专业Probe项目主页。本轮没有修改PL或主应用PS，交付沿用已验证的ELD1 / 原始SWD / WebUSB配对。

## 固化结果

使用 `python -X utf8 toolbox.py probe-flash --image-dir prebuilt/qspi-release-20261106 --out build/qspi-release-20261106/flash-bank0`，默认受限辅助器后端。执行前仅共享hw_server存在，取得探针租约；QSPI拨码读回经历0/JTAG、4/NAND，经用户调整并断电重上后确认为1/QSPI，没有伪造或软件覆盖BOOT_MODE。

| 检查 | 结果 |
|---|---|
| Flash | Winbond JEDEC EF4019，32MiB |
| BOOT | 4281040 B，SHA `fd8d0411388767d4ec37aa690b3ae375f7df64c071cd221fd80fa02954dda6bf` |
| bit / 主应用ELF | 与[正式配对](../../../prebuilt/release-20261106/README.md)字节相同，未重新综合或重编 |
| 原始备份 | 六次完整读取SHA均为 `aaefdf33d45219bfe31d1bbd8008039e5239540b8dd834849d6261cd7425ae2d`，原始32MiB文件留本机，[摘要](evidence/backup-digests.json) |
| 擦写范围 | `[0, 4284416)`，逐4KiB blank-check、逐256B编程/读回 |
| 独立验证 | 重新加载只读helper，整片32MiB回读；BOOT SHA相同，范围外全部字节相同 |
| 自主复位 | 无暂停reset，未随后dow/con，BootROM/两阶段FSBL交接成功 |
| 实体冷启动 | 用户断电几秒后重上；未下载bit/ELF，QSPI交接及85844 B OCM执行段匹配，[证据](evidence/cold-ocm.json) |
| 冷启动业务 | WebUSB正常/短读/非法请求STALL及恢复；SWD10/JTAG1/10 IDCODE/4096B只读与恢复；ETMv3 24MHz/100ms通过 |

[完整写入记录](evidence/programmed-result.json) · [验收身份与工具SHA](evidence/acceptance-summary.json) · [正式启动包](../../../prebuilt/qspi-release-20261106/README.md)。冷启动后空闲FCLK读回99999999Hz；10MHz控制/采集后119999998Hz，实际SWCLK约9999999.83Hz；200MHz参考读回199999998Hz。它们来自PLL/分频寄存器，不是外部频率计。PL约束仍为133.333333MHz、setup/hold余量0.067/0.044ns。

冷启动ETM采到119022帧、1904361 formatter B，硬件完整窗100.000001ms，无丢帧/parser/IDELAY ready-loss/writer错误；1808315条解码指令、packetIssues=0，仍保留2 gaps和29628 unknownExecution，不宣称完整执行流。[ETM](evidence/cold-etm.jsonl) · [WebUSB](evidence/cold-webusb.json) · [SWD/JTAG](evidence/cold-target.json)。

最后目标RCC为0x03034e83/0x0051040a（CDC48，TRACECLK24MHz），运行状态与调试控制位恢复，DHCSR=0x01010000；采集、DDR、DMA、RTT/HSS空闲。最终OCM再次物理对拍通过；没有烧录目标MCU Flash或改其PLL。[最终板状态](evidence/final-board.json) · [最终代码](evidence/final-ocm.json)。本任务没有留下运行的烧录或测试进程，保留共享hw_server。

## 构建与失败边界

- ZL-166：USB BSP缺QSPI头文件，不适用于启动helper。新增 `boot.bsp` 从版本管理的启动HDF生成专用BSP，串行make后才检查导出的头和库。SDK 2018.3 bat曾静默返回0且不产BOOT；隔离原生HSI/Bootgen运行库、补齐动态任务/JVM及RDI环境，并校验真实产物。HSI会在HDF旁生成文件，现打开输出目录的HDF副本，源目录保持干净。[BSP复测](evidence/bsp-generation.json)。该干净生成复测与实际loader编译的BSP身份分开记录，后者以启动包build_manifest为准。
- ZL-167：旧SDK写入库在初始化后发生librdi_xicom_hw.dll / 0xc0000005，补全环境仍失败，隔离布局也失败。首次失败后独立整片回读与原始备份一致，后续完整备份也一致。未将重试或替代后端成功当成SDK修复；保留[首次结果](evidence/sdk-first-result.json)、[独立回读](evidence/sdk-independent-readback.json)和[后续失败](evidence/sdk-env-result.json)。
- ZL-168：受限helper首版21h擦除后blank-check拒绝，WEL仍为2，独立首扇区与原始相同，没有进入页编程。芯片修订与控制器指令支持未分离。当前低16MiB方案退出4字节模式、检查扩展地址寄存器为bank0，使用标准20h/02h；13h继续独立读回。不能将此结果泛化为所有EF4019都不支持21h。[失败记录](evidence/four-byte-result.json)。

辅助器在写使能前校验arm key、JEDEC、BOOT头、长度、DDR数据CRC32及保护状态，不做整片擦除或状态寄存器写入。所有busy等待有界；逐扇区/逐页验证失败就停止。C模型执行生产函数，覆盖错误输入、保护/bank拒绝、256B和4KiB边界、busy超时与读回错误；[模型](evidence/programmer-model.txt)及61项[CLI自测](evidence/cli-tests.txt)通过。真正的交付依据仍是板上整片读回、范围外比较及实体冷启动。

引导链stage2载荷SHA仍为 `f18bd49242ad78e3a28d99f7f486377bbe056f904dc6766119a788b3e561ecf8`，与历史已冷启loader相同，但本次BOOT/主应用验收独立进行。构建基线602131d2加工作区新工具/helper源码，实际编译输入及BSP身份保存在启动包build_manifest中；未用旧BOOT冒充本次产物。

## 项目主页

参考superlinkPRO的组织方式，使用本项目的功能、截图和性能证据，重写主页定位、下载入口、功能表、快速开始、ETM链路、性能条件、J7接线及开发导航。66.667MHz实验与60MHz正式档分开；没有复制其他探针的SPI/I2C/SWO等能力或速度。About描述同步为本项目能力，并加入在线站点链接。

首轮GitHub Mermaid富文本显示“Unable to render rich display”，未确认是语法还是远端服务问题（ZL-169）；替换为仓库原生SVG，浏览器确认流程图、四个徽章及工作台截图全部加载。[主页截图](readme-home.jpg) · [流程图截图](readme-flow.jpg)。README已先以c05b8c27/72b6c740推送，后续提交补当前QSPI交付入口与证据。

原始Flash备份和工作输出收尾保留在工程外 `E:/zynqlinkPRO-local-archive-20261106/build/qspi-release-20261106/`；其中 `flash-bank0/original_flash_32MiB.bin` 是完整原Flash，未纳入公开Git。

指令语义参考 [Winbond W25Q256JV SPI 数据手册（Winbond原文，TI托管）](https://e2e.ti.com/cfs-file/__key/communityserver-discussions-components-files/908/W25Q256JV-SPI-RevQ-02072025-Plus.pdf) 与仓库SDK驱动；当前EF4019的具体芯片修订未识别，不以该手册代替本板指令支持验证。
