# Web目标系列/频率策略与CLI高频配置核查

2026-11-03，`codex/web-ui-compact`，基于`2e7acbf`；ZL-109/110。本轮按用户明确要求收敛Web产品频率，不重新操作探针/目标板，不写Flash/QSPI、不改PL/PS。

## 修改

- 烧录页只允许有内置算法的STM32系列及已登记HPM板型；当前为8个STM32系列和10个HPM预设。此前因为算法筛选，实际已无ESP32入口；本轮补显式系列白名单，避免日后算法增加导致其他系列自动进入产品列表。未删除RTT/调试的通用目标能力。
- Web烧录、RTT Viewer、调试器新增25MHz档。HPM只列最高25MHz的选项，其他ARM/RISC-V最高60MHz；切换目标会重建候选、收窄旧高频选中值并更新持久化偏好。切回ARM后恢复高频候选，不自动升回60MHz。
- 执行入口再次按目标限幅，防止旧偏好或程序调用绕过下拉约束；HPM RTT自动档明确下发10MHz，避免沿用研发CLI留在探针上的高频。默认烧录仍10MHz；上一轮原生批量Flash加速的适用范围仍为HPM6800/10MHz，本轮没有将25MHz宣称为新的测速结果。
- 波形ARM及RTT转发ARM增加25MHz并限定请求最高60MHz。RISC-V波形/转发仍沿用独立采样配置，通用SWD频率控件不可用；当前Zynq协议在目标类型确认后将流请求初始化为10MHz。没有把旧HID clockHz/idle字段改造成TCK设置，也没有把采样周期等同TCK。

## 刷新回归中保留的失败与修复

首轮冻结浏览器发现新增25MHz选择刷新后变默认10MHz，`initial-refresh-failure.json`与`initial-refresh-default.png`保留当时证据。原因是恢复偏好时静态下拉还没有新增25MHz选项；改成先补候选，再恢复偏好，最后按目标限幅。RTT/调试也核对这一顺序，并保留仍在限制内的旧自定义频率（例如8MHz）。

同时发现原RTT芯片跨组选择只程序修改目标类型，没有保存`rtt.target`：直接从ARM选择HPM后刷新会恢复旧ARM目标。ZL-110补齐持久化；源码实测三页设25MHz并刷新，RTT恢复HPM6800/RISC-V，三页均选中25MHz且无更高候选。未用清空浏览器偏好规避失败。

## CLI核查

原生研发CLI已经提供完整所需参数，无需把Web高频档重新放出来：

| 工具 | TCK | idle cycles | 采样窗口 |
|---|---|---|---|
| `tools/validate_hpm6800_performance.py` | `--speeds`，Hz逗号列表 | `--idle`，0～64 | `--modes`，0/1/16/17列表 |
| `tools/validate_hpm6800_streams.py` | `--speeds`，Hz列表 | `--idle`，0～64 | `--mode`，单值 |
| `tools/characterize_hpm6800_idle.py` | `--speeds`，Hz列表 | `--idles`，列表 | `--modes`，列表 |

其中stream工具区分`--stage rtt/hss`；HSS的`--periods`单位是24MHz ticks，`--variables`为变量数。不能把这两者当成JTAG频率或idle。

源码核查：`benchmark_hpm5301.setup`以DAP_SWJ_Clock下发TCK并设置采样mode；performance在升频前写TransferConfigure idle并读Vendor13/255核对有效值。高于15拍需要扩展idle配对；66.667MHz需要配套PS频率cap和FCLK策略。历史限定HPM6800EVK的通过点为TCK约66,666,666Hz、idle22、mode17（Q1/previous-bit），见[历史实测](../hpm6800-speed-completion-20261102/README.md)。该范围不能泛化到所有HPM板型或任意持续时间。

本轮实际运行`project describe`、三个入口的帮助/计划核查；`cli-full-dryrun.json`包含完整bit/ELF/out及66,666,667Hz、idle22、mode17参数的**只打印计划**结果，没有运行底层硬件脚本。研发入口保持原能力，Web页面CLI沿用产品限制。完整命令示例已补入[CLI工作台](../../toolbox-cli-ai.md)。

## 验证与程序交付

源码Web检查：10份共享驱动一致，157个模块语法通过；121项Web自测通过，包含目标频率边界、旧60MHz偏好切HPM降25MHz、切回ARM恢复候选。没有修改共享驱动，CLI硬件工具本身未改。

源码真实浏览器已核对烧录18个目标全部属于STM32/HPM，HPM只有<=25MHz选项；RTT和调试从ARM60MHz切HPM后选中25MHz，其他RISC-V恢复60MHz候选。最终冻结EXE自身预检/离线Trace验收通过（1798个文件，硬件禁用、Python/Node不在子进程PATH），8页45步Web CLI通过；最终浏览器复验三页HPM上限/ARM与其他RISC-V候选/25MHz刷新恢复通过，见`final-browser.json`、`hpm-flash-25mhz.png`、`cli-summary.json`。7个变更新增产品资源与最终包逐字节一致，SHA绑定见`source-package-binding.json`。manifest如实保留baseRevision=2e7acbf、sourceDirty=true，不冒称干净提交。固定旧程序的目录占用仍按ZL-107保留，更新独立`dist/zynq-etm-bridge-candidate-20261103/`。

本轮未访问硬件；不得把上一报告的“最后板上状态”当作本轮新核对结果。本任务服务/浏览器结束时关闭，不结束用户旧程序或共享hw_server。
