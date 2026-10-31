# 优化回合主工作分支：合并交接（2026-10-31）

用户要求本次只合并，保留另一AI的ETM改动，等另一AI的工作也合入之后统一综合与回归。本次不调用Vivado/SDK构建、仿真、主机回归或板卡；只做Git合并、内容/哈希和静态完整性检查。用户这一明确指示优先于仓库“交付前构建”的一般流程，故不把历史bit/ELF冒充合并头产物。

合并来源：

- 主工作分支 `feature/superlink-zynq-web`，起点 `2eac159`，共同祖先 `00b9f2f`。
- 优化分支 `codex/orbtrace-7010-120mhz-ocm` / `a2082f1`。
- 总CLI集成分支 `codex/qspi-cli-integration` / `df0dac7`。

合并包含PL的诊断裁剪、采样FIFO BRAM化、流引擎LUTRAM/故障释放路径、7010实现选项，以及PS紧凑构建、SWJ非对齐修复、HSS停止计数、USB Chapter9上下文修复。USB/DAP仍为16×4096、USB arena仍为512KiB，没有缩队列。

保留主分支的ETM并行采样、样本采集、TPIU/五线滤波、RAW_DIAGNOSTIC模式0..4、64K FIFO选择和独立FCLK1参考；相应RTL/BD及ETM/Web工具不回退到旧优化分支版本。另一AI尚未提交的native-engine/ETM/CLI修改保留在主工作目录，不混入本次合并提交，不临时stash或清空其文件。

当前`prebuilt/20261031_orbtrace_opt_qspi_usbfix_7020_120/`、`prebuilt/20261031_orbtrace_usbfix_7010_100/`等仍是原优化线明确版本的验收/静态产物。它们的SHA、source revision和原始日志继续有效，但**不是这次ETM+优化合并头的新产物**。原120MHz/7010余2个Slice/OCM数值不可直接当成合并头已验证结论。板卡和QSPI保持不动。

## 删除旧worktree前保留的脚本与数据

可运行工具均已进入Git，使用仓库相对路径及显式参数：

| 用途 | 入口 |
| --- | --- |
| SRAM/RTT/HSS两协议性能 | `tools/benchmark_sram_matrix.py`、`benchmark_rtt_forward.py`、`benchmark_probe_stream.py`、`benchmark_hss_matrix.py` |
| F103时钟/引脚/运行状态备份恢复 | `tools/run_f103_clock_fixture.py`、`run_f103_jtag_fixture.py` |
| 原50/60MHz SOTA计划 | `tools/run_sota_regression.py --dry-run`；该工具不负责加载配对或设置目标时钟 |
| 实时OCM代码比对（不下载/复位） | `tools/verify_probe_ocm_code.py` |
| CM3仿真/采样矩阵/匹配负载 | `tools/run_cm3_sim.py`、`run_cm3_matrix.py`、`benchmark_cm3_transport.py` |
| PS构建及OCM布局 | `tools/build_xusbps_daplink.py`、`report_ocm_elf.py` |
| QSPI加载器构建、打包、固化 | `tools/build_probe_boot.py`、`package_probe_boot.py`、`toolbox.py probe-flash` |
| 未来工程导出QSPI PS配置 | `tools/generate_qspi_boot_hw.tcl`（参数化原build目录脚本；本次未执行） |

额外保留35份原build目录中的手写测试驱动、基线/候选对照、诊断观察点、CM3相位扫描和QSPI生成源于 `as_run_helpers/`，原始SHA见 `helper_inventory.json`。这些保留为 `.py.txt/.tcl.txt`，因为含旧绝对路径、旧配对及历史操作，不能盲目执行。优先使用上表入口，并在测前显式加载/核对未来新构建的bit/ELF/PS init。

原完整Flash备份和回读已按SHA去重复制到主工作目录 `E:/zynqlinkPRO/build/preserved_orbtrace_20261031/flash/`，共3份32MiB私有镜像；来源到新路径的对应关系和SHA见 `private_backup_migration.json`。这些数据不提交公开Git。删除优化worktree后仍在主目录，须一并保留该私有归档。SDK/BSP、授权CM3 RTL仍使用主目录的只读reference或外部安装；不把第三方授权RTL复制进Git。

`optimization_handoff.json`是旧优化验收完成时的历史交接，不代表合并后的验证完成。公开日志中的旧绝对路径属于当时运行证据；实际bit/ELF/BOOT、验收JSON、SHA索引和可复用工具已纳入主分支历史，删除旧worktree不会丢失其Git对象。本次不删除任何worktree。

## 后续统一构建/验收

等另一AI也合入后，针对最终合并头重新生成bit与紧凑ELF，重新检查120MHz setup/hold、7010资源、OCM、SWD/JTAG SRAM/RTT/HSS及ETM。保留原已知配对，记录新文件SHA与实际FCLK/TCK，验收后再更新默认产物。

如PS配置变化，先从最终Vivado工程导出匹配的QSPI HDF/init，不能直接假设历史 `firmware/boot/hardware/` 与新工程匹配。未来明确执行示例（本次未执行）：

```powershell
vivado -mode batch -source tools/generate_qspi_boot_hw.tcl -tclargs <FINAL_PROJECT.xpr> firmware/boot/hardware
# 然后按firmware/boot/README.md生成/串行编译BSP，构建匹配的加载器/BOOT.bin。
python tools/package_probe_boot.py --loader-dir <LOADER_OUTPUT> --bit <NEW_BIT> --elf <NEW_ELF> --ps-init firmware/boot/hardware/ps7_init.tcl --output-dir <NEW_PACKAGE>
```

新增打包入口只校对现有文件/分区MD5并生成hash清单，不构建、不加载、不烧写，初始验收状态始终为NOT PERFORMED。实际编程仍经总CLI，完成板测后记录验收。原BIF保留作构建证据，额外相对路径`rebuild.bif`用于迁移后的打包目录。
