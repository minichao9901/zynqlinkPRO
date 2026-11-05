# WebUSB 单后端收敛

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

2026-11-02（Asia/Shanghai），分支codex/web-ui-compact，基于defd04a。关联ZL-103、ZL-104。

用户要求仅保留WebUSB，且明确选择移除整个工程生成页。本轮实现：

- 删除烧录/RTT的J-Link、OpenOCD选择及对应客户端实现；删除WebSocket桥服务、启动脚本、cfg选择器。
- 烧录必须选择或拖入固件文件，不再接受任意磁盘路径，不再自动转到其它后端。列表仅显示现有WebUSB算法与HPM板卡，移除仅依赖已退役后端的目标及自定义cfg入口。
- 删除工程生成页、所有配套模板/桥包生成模块与其导航入口，页面数从9变为8。同步Web CLI/工具目录，移除toolbox bridge入口。
- 旧flash.backend/rtt.backend偏好不再读取；原有芯片、频率、校验、ELF等设置继续使用，退役custom芯片回到有效默认。ARM RTT芯片新偏好兼容读取旧rtt.ocdTarget，以免丢失既有芯片选择；它只作为芯片ID，不再启动外部工具。
- WebUSB底层驱动、共享副本和原生USB/ETM本机服务保持原实现；bridge-build仍为本机工作台EXE构建入口。HID配置、Web Serial串口/CDC仍用于既有功能，不是额外调试后端。
- 历史报告、SDK中OpenOCD板级配置来源及独立硬件验收工具保留取证，不作为产品后端提供。

## 验证

- web.check：10份共享文件一致，142模块语法通过。
- test.web：94/94通过。比上一批少的2项仅为已删除的外部桥专用测试；原有WebUSB/控制队列/调试/记录测试保留。
- test.cli：55/55通过，目录断言改为8页，确认烧录/RTT目录不再暴露后端选择。
- [实际Web CLI验收](cli-acceptance.json)：8页45步通过，包含页内描述、状态/控件、ETM方法发现和真实目标ELF上传；未连接硬件。原生成器的下载步骤随功能退役。
- 首轮验收暴露驱动仍引用退役ELF路径，保留[原失败](cli-first-failure.json)。改为prebuilt/golden/f103ze-cdc48.elf复验通过（ZL-104）。首次实现期间，未暂存删除时工具目录仍看到旧桥脚本；暂存删除后按当前索引正常发现，不作为产品失败。
- 浏览器1280×720：8个入口，烧录无后端/路径输入，RTT直接展示WebUSB连接；无未处理脚本错误。截图：烧录（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/webusb-only-20261102/flash-webusb.png`）、RTT（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/webusb-only-20261102/rtt-webusb.png`）。

本轮只有离线及模拟检查，没有枚举/连接真实探针、目标复位、烧录或采集。能力边界变化属于用户授权的移除，不将主机通过称为实板回归。

下一步建议先补串口/RTT共享的日志查找、过滤与高亮，搜索条按需出现；再做目标/ELF上下文复用。前者对日常定位最直接，后者涉及会话交接，需单独验证。

## 独立EXE

本worktree内`dist/zynq-etm-bridge/zynq-etm-bridge.exe`已重建，旧程序归档并保留data；原E盘工作区程序未替换。EXE SHA-256为`ef877db916ac831876b9f140c3f74a8dcdaba18a78ca6c0074f4e0edfda662fd`。

[冻结程序验收](frozen-verification.json)通过：1790个包文件核对，禁用硬件路由，F103ZE/H743离线解码/索引、Web/CLI HTML导出一致及重复启动复用通过。[源码/包核对](source-package-match.json)确认10个修改前端文件逐字节相同，9个删除模块不在包内。构建记录为defd04a基线加sourceDirty=true，以文件SHA绑定本次实际源码。

额外验证内置模拟RTT：配置与fixture一致的ARM RAM后，控制块0x20001000、约226B/s接收及下行发送成功，错误栏为空；模拟初次沿用HPM范围时未就绪，修正测试配置后通过，不作为真实探针证据。浏览器控制台无error，测试后恢复原HPM选择/地址。已关闭测试页及源码服务，PID24016不存在、8898无监听；冻结验收结果keptRunning=false，无本任务后台服务。
