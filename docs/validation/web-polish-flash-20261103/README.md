# 紧凑 Web 打磨与 HPM WebUSB Flash 实测

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

日期：2026-11-03（Asia/Shanghai）。工作区 `codex/web-ui-compact`，基于 `8a059d6`；最终代码随本报告提交。用户要求保留大工作区、窄边框、导航与状态同排；明确统一 WebUSB、删除工程生成页，并授权空闲 HPM6800EVK 写入测试固件测速。未推送、未合并 main。

## 本轮结果

- ZL-106：修复独立复审 F1/F2。每页独立保存实际采用目标及 ELF 绑定；显式沿用成功推进本地身份，手选目标依此清理旧文件。全局变化不漂移波形/ARM 调试本地身份，沿用时才清空旧符号、变量和地址。泛架构选择不覆盖具体会话板型，未绑定来源 ELF 不冒认全局板型。
- ZL-102：波形空态给出按当前进度变化的主动作，直接沿用目标、载入/复用 ELF、选变量、连接或开始；另有离线回放。主动作展开已收起侧栏并切到变量面板。样本/速率/缓冲/内存常驻，细项计数按需展开；异常时质量按钮突出显示，正常时不声称完整性已验收。保留单行顶栏与窄边框。
- ZL-093：用现有 Zynq RISC-V 虚拟 MEM-AP 的标准 DAP TransferBlock 批量搬运 Flash 算法及缓冲；控制、执行、XIP 读取仍用已有流程。最终冻结 EXE 三轮全流程中位 **5.256s**，本轮旧源码路径 **39.526s**，约 **7.52 倍**提速、耗时降低 **86.7%**。OpenOCD 合理 RISC-V 时钟配置为 **3.002s**，仍约有 1.75 倍差距。
- ZL-108：真实烧录→波形发现手动连接路径漏确认架构，HSS CONFIG=-6、0包。每次真实 START 前发送并核对目标类型 ACK，失败立即中止；修正误导性的“只有位宽非法”解释。最终 EXE 实采 531 点、1kHz、CSV 531 行逐行契约正确，丢失/读错/尾差均0。

这不是广泛板型或商业正式版验收。命名工程配置、拔插/刷新/服务重启后的恢复矩阵、RTT Viewer 批量读和大型 ETM 首屏等待仍需后续工作。优先完成限定板型的跨功能恢复与诊断，再扩展吞吐优化。

## 速度对照方法与边界

同一 HPM6800EVK、同一探针 bit/ELF、同一 SDK scope ELF。实际烧写 47,856B，两个连续区域：`0x80000400+3216`、`0x80003000+44640`。校验均为目标 CPU 读取 XIP 后逐字节比较，包含擦除、编程、完整有效载荷校验和复位运行。所有改动扇区均在首64KiB，事先双读备份，结束独立读回恢复。

Web 计时为鉴权页面调用烧录操作到收到完成结果；包含页面/HTTP控制等待。OpenOCD为独立进程启动到退出，另留内部准备/写入/校验/复位计时。两者全流程边界相近但不完全相同，不能当作同一内部函数基准。串行执行，无并发争用；OpenOCD预热一次，再计三轮，Web各组连续三轮。没有用历史21.905s/2.971s充当本轮实测。

| 路径 | 三轮全流程秒 | 中位秒 | 实际探针 FCLK / TCK（MHz） |
|---|---|---|---|
| 旧 Web 原始 DMI 源码服务 | 40.527 / 39.526 / 37.299 | 39.526 | raw 20 / 10 |
| 新 Web 源码服务 | 5.559 / 5.685 / 5.415 | 5.559 | 控制 raw 20 / 10；批量原生 120 / 10 |
| 最终新冻结 EXE | 5.193 / 5.256 / 5.465 | 5.256 | 控制 raw 20 / 10；批量原生 120 / 10 |
| OpenOCD，raw模式时钟对照 | 9.019 / 8.956 / 9.064 | 9.019 | 20 / 10 |
| OpenOCD，既有 RISC-V 低频 profile | 3.196 / 3.002 / 3.000 | 3.002 | 120 / 10 |

上表频率来自物理 MEM-AP0、PLL/分频寄存器及协议读回计算，**不是外部频率计实测**；实值 raw FCLK=19,999,999Hz/TCK=9,999,999.5Hz，native FCLK=119,999,998Hz/TCK=9,999,999.833Hz。同TCK并不意味着同FCLK，因此保留两个OpenOCD对照。133.333MHz是该bit构建约束，不能当作本轮动态FCLK。

优化仅启用于 HPM6800EVK、请求10MHz、`nativeService`且`dapSynchronized`的日常 EXE 原生USB代理通路；它仍传输 WebUSB 使用的标准DAP协议，不恢复任何 OpenOCD/J-Link 产品后端。只加速 work-area 内>=64B、4B对齐的RAM访问，最大120字/包，保留512B探针限制。其他设备/板型/频率/浏览器直接USB路径继续原流程，未宣称同等加速。每轮206个原生块、算法及缓冲各写/读49,244B；原始JTAG批次从约7,080降至约900（最终三轮892～920）。没有改Flash算法或牺牲校验。

传输核对模式ACK、块长度/完成计数/状态；超时后隔离通道，不重放、不静默退回慢路径。正常收尾清SBA地址缓存，恢复raw IR和10MHz并记录时钟。未修改PL/PS或目标PLL，未写探针QSPI。

## 失败证据与修复链

1. 先前固定目录发布在冻结/离线验收成功后遭WinError32：用户PID30436仍占用 `dist/zynq-etm-bridge/`。未结束用户程序、未替换固定目录；以独立 `dist/zynq-etm-bridge-candidate-20261103/` 成功构建、验收和板测。ZL-107按限制处置。用户原入口仍是旧程序。
2. `frozen-scope.json` 保存初轮CONFIG=-6失败；`scope-initial-refusal.png`只是清理后空画布，错误以JSON为准。定位到原 START 只在自动重连分支补发RISC-V目标类型，手动已连接路径跳过；前一功能已恢复raw IR0e，PS无法接受RISC-V HSS配置。源码修复后 `source-scope-fixed.json` 的497点通过，期间未重载探针配对、未重刷目标固件掩盖失败。最终重新构建EXE后再烧录三轮、切波形实采531点通过。
3. 首次OpenOCD诊断 `openocd.json` 按5个未合并 ELF 段分别读回，不进入主表；最终两组 `openocd-raw-merged.json` / `openocd-riscv-profile.json` 合并为与Web一致的两个区域。早期候选 `frozen-flash.json` 中位6.055s也保留，不冒充最终包数据。

## 验证与交付字节

- `web.check`：10份共享驱动一致、154个模块语法检查通过。共享驱动未修改。
- `test.web`：119/119；包含实际UI初始化器事件组合、泛架构身份、原生内存成功/边界/超时隔离/部分完成拒绝，以及目标架构拒绝/短ACK阻止启动等。`test.cli`：55/55。
- 最终冻结程序自身预检及离线 Trace Web/CLI 验收通过（1796个文件，Python/Node不在子进程PATH，硬件路由禁用），见 `package-verification.json`。
- 最终EXE的禁用硬件实例：8页45步CLI通过，见 `cli-summary.json` / `cli-results.json`。
- 最终EXE真实浏览器F1：F103→沿用RTT的H7→选H743 ELF→手选F103，页面恢复“选择或拖入固件”，见 `f1-firmware-cleared.png`。
- F2：波形采用F103、载入F103 ELF并选SystemCoreClock；RTT改H7后，本地仍F103、ELF/1个勾选保留，沿用启用；点击后ELF和勾选清空。调试页同样保留F103符号并在显式沿用后清除，见 `f2-browser.json` / `f2-debug-browser.json` 及截图。
- 1366×768：设置收起时无横向溢出（scrollWidth=1366），波形画布1350.4×643.2，导航入口27.2高、仍单行。下一步按钮实际打开文件选择、展开侧栏并选中变量页。未测125%/150%缩放、键盘完整流程和其他板型硬件，不作其通过结论。
- 最终构建manifest如实记录baseRevision=`8a059d6`、sourceDirty=true。`source-package-binding.json`核对10个变更新增产品资源与最终包逐字节一致，SHA绑定到本次提交的源码；不改写构建历史为不存在的干净提交。

程序目录必须整体保留（EXE与`_internal`）。固定旧程序仍被用户进程占用，候选程序位于 `dist/zynq-etm-bridge-candidate-20261103/zynq-etm-bridge.exe`；本轮没有替换用户的data或冻结旧入口。

## 板卡身份与恢复交接

实测前显式JTAG/RAM加载已版本管理的 `prebuilt/hpm6800-usb-fixed-133-20261102/` 配对；初始、加载后、最终物理OCM核对均匹配76,420个可执行字节，证据 `initial-ocm.json` / `loaded-ocm.json` / `final-ocm.json`。

- bit SHA-256：`106d579bc1b79c2b873fd1e3eb2609d468892a67613d85a6e41d4dc90c8fc177`
- Zynq ELF SHA-256：`e93f1810d48e77f8d9aa097f643e40e0aaee32bdec1c263c1428f092909e608a`
- 目标scope ELF：`firmware/target/hpm6800_web_validation/scope/fw.elf`，SHA-256 `e5124ca35a872c2c54f210df99c5cfc3ca7a0d8f6a64f1cfa29a907aeb9b73a9`
- TAP IDCODE `0x1000563d`；IDCODE并不能独立区分所有HPM板型，板型以用户确认及配套配置为准。
- 原始Flash首64KiB双读一致，SHA-256 `afdb834a734d0c18f9d2269b28d8a0abe6eacd5d694077657c961521025397d4`；最终重新烧回原字节，再独立CPU progbuf读回，64KiB逐字节一致。私有原始Flash、读回、调试上下文仅留 `build/flash-perf-20261103/backup` / `restore-final`，不提交Git。
- 最终原程序复位后运行；DCSR可写位mask `0xbe17`匹配原值，最终DCSR `0x400006c3`、DMSTATUS `0x430ca2`。这是原程序重新启动，不是恢复测试前PC/GPR的无缝续跑。
- 最终FCLK约20MHz、TCK约10MHz、raw模式，物理采集/DDR/CDMA/packet/SWD观测均空闲，见 `final-physical.json` / `final-clock.json` / `restore-summary.json`。探针QSPI未写、目标PLL未直接修改。
- 本任务浏览器、源码/候选服务均已关闭；用户旧程序PID30436和共享hw_server PID19676保留。
