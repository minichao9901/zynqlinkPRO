# USB Chapter 9 空指针修复与优化版复验

用户断电重上后，原 QSPI 镜像自主引导、USB 枚举及 SWD/JTAG60 短测通过。额外实时比对发现 OCM 地址零由 ELF 的 `EA000049` 变为 `EA000001`，其余71299字节代码相同。硬件观察点定位到原ELF的 `0xF88A: strb r1,[r6]`，r1=1、r6=0：`XUsbPs_StdDevReq` 的 SET_CONFIGURATION 经空 `UserDataPtr` 写 `CurrentConfig`，实际覆盖复位向量首字节。原记录及定位日志见 `../orbtrace-qspi-20261031/cold_power_cycle/`。不能据此认定此前所有 USB 掉线都来自此缺陷。

修复源提交 `24d6665` + `0ec2e63`：为 USB Chapter 9 提供静态配置上下文，启动及总线复位时清零配置值；初始化失败退出时解除指针，不释放静态对象。没有修改 PL、USB/DAP 队列、采样周期或正常数据传输路径。初版静态上下文的测试保留于 `USB_context/` 和 `sota_peak_rtt/`，最终退出路径修正后的测试在带 `final` 的目录中；交付使用最终版本。

最终60MHz配置ELF SHA-256为 `6684400fd217fdd10f4a6375be48eff1e55560d861eca097470a2b88f0a6ddb7`。代码71268字节，OCM跨度120976字节，DDR静态分配711520字节，16×4096 DAP队列及512KiB USB arena不变。`USB_context_final/` 的四轮 SET_CONFIGURATION/GET_CONFIGURATION 全通过，并在每轮后读回全部可执行字节，与该ELF逐字节一致；复位向量保持 `EA000049`。

PL继续显式复用未变RTL的 `f02a15db0b576f631c08448b19ea3844d1b45ef00ee6801d243caee398960230` bit，源 `bc9ced6`，并非声称此次重新综合。7020/120MHz STA仍为 WNS+0.499ns、WHS+0.020ns、TNS/THS零。完整原生RTL、真实CM3和父版矩阵证据继续适用同一PL；本次针对新固件重新上板验收。

最终60MHz配置的50/60MHz峰值、RTT、30秒soak及HSS使用与原SOTA相同参数重新测量，原始JSON、实际FCLK/TCK、目标96MHz DWT确认及完整恢复记录保存在本目录。默认50MHz配置另行验收。启动空闲FCLK为100MHz；请求60MHz SWCLK/TCK时切到120MHz，不把空闲100MHz误判为时序目标降档。

本修复启动包为 `prebuilt/20261031_orbtrace_opt_qspi_usbfix_7020_120/`。原先含NULL上下文的启动包及其验证数据保留为历史，不作为新的默认固化镜像。QSPI烧写、整片备份/回读、更新后复位及最终冷启动状态以本目录最终结果为准；新ELF不借用旧ELF的冷启动结果。

最终复测结果（十进制MB/s）：

| 链路 | SWD读/写 | JTAG读/写 | SWD RTT | JTAG RTT |
| --- | ---: | ---: | ---: | ---: |
| 50MHz | 4.035 / 3.982 | 2.022 / 2.004 | 4.017 | 1.987 |
| 60MHz | 4.814 / 4.714 | 2.417 / 2.392 | 4.802 | 2.397 |

与前一优化版的12个相同负载中位值变化为−0.81%～+0.27%，逐项对照见 `comparison-table.md`；没有据此宣称每个短窗口数值完全相等。SWD60的30秒连续读写零错误，读中位4.82704、最低4.76799，写中位4.74147、最低4.63939MB/s。完整样本、过载HSS的跳点率均保留，不能把超载有效速率当作零跳点上限。42行HSS逐帧数据、序号和最终样本数全通过，无重复STAT或链路错误。默认50MHz配置单独加载完成四项峰值/RTT测试，时钟和目标状态全部恢复。

`qspi_cli/` 记录总CLI实际执行的完整固化流程：先备份整片32MiB（SHA-256 `2500c2b2a9444c6b98b24d2d236e22644c83242984bff762f4abdd459542fe2f`，即之前旧镜像的整片回读），再SDK编程/verify、独立整片回读和擦写范围外对比，最后无暂停QSPI软件复位。新BOOT.bin及回读SHA-256均为 `ee7116bc71b0c7f0fdbebed75c5c85137e80ec7ef7c1b8cc3db50cebb39f1185`。`post_QSPI_software/` 再次证明四轮USB配置后完整代码与最终ELF相等。原始全片备份/回读留本机 `build/qspi_usb_context_flash/`，不提交公开Git。

最终修复版的实体断电重启当前等待用户操作；软件复位通过不冒充这一项已测。早先用户已断电验证的是原ELF，正是在那次额外代码审计中发现了本缺陷。

`firmware_source_audit.json` 核对最终ELF的36个构建源文件与完整提交指纹，明确区分Git原始字节和CRLF检出。固件修复也以独立提交加入 `codex/qspi-cli-integration`；主目录只安装总CLI、启动包及其记录，未覆盖另一AI的固件源码。7010/100MHz仍沿用原PL静态实现，另配同一修复的50MHz ELF于 `prebuilt/20261031_orbtrace_usbfix_7010_100/`，没有物理7010板测。
