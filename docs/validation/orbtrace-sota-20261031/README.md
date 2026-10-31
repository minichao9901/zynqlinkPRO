# F103ZE 50/60MHz SOTA 复测（2026-10-31）

结论：已重现 2026-10-29 记录的主要吞吐和 HSS 档位。旧配对也重新加载复测，优化版与它的块吞吐、RTT 中位数差异为 −0.65%～+0.46%；所有数据校验、SRAM 恢复通过。30 秒 soak 的最低瞬时速率存在差异，不能声称每个最低值完全重现。

参考：[原测速记录](../../F103ZE测速-20261029.md)，文档 SHA-256 和参数见 [reference.json](reference.json)。此前的硬件报告以最近的 filtered-TPIU 配对、48MHz 目标和 1024 字节 RTT chunk 为对照；那组结果与本报告的 SOTA 参数不同，不能直接比较数字。

实际加载配对：

| 版本 | bit SHA-256 | ELF SHA-256 |
| --- | --- | --- |
| 原 SOTA 配对 | `62ce682ef3302941d109b0af7479010ac88e8856f32764f60cdeb5d869259ce3` | `5893bdd4248dfd3c9f26c729f36159ad4bc3feadf2b38f6ebb9cb9fc12c4a842` |
| 本次优化 60MHz 配置 | `f02a15db0b576f631c08448b19ea3844d1b45ef00ee6801d243caee398960230` | `4fbf5f7816644ea946a684e1ff3f30425e57eea6e5b64cd0d0d6839f284e6bdb` |
| 本次优化默认 50MHz 配置 | 同上 | `de61421deea6f7bf81810cc9cd1e5fc1024df21ccaf3805bb10f21dd7d2d9957` |

优化 RTL 提交 `bc9ced69f1f8f81647b8d62eaf74100d53fd883f`；固件包含 `f5c938e` 的 Thumb SWJ 非对齐修复和 `cbedca2` 的 HSS STOP 最终计数刷新。产物源信息、OCM 布局、120MHz 时序报告见 [7020 配对](../../../prebuilt/20261031_orbtrace_opt_7020_120_candidate/README.md)。后续 ETM 滤波改动未合入。

测试条件：目标临时切换 HSE8MHz×12，DWT 实测约 96.03MHz；结束后恢复原 RCC、Flash 等待周期、USB 时钟开关、SRAM 和 CPU 寄存器及运行/暂停状态。没有烧写或复位 F103。块吞吐为 halt、512 字、主机 depth32、256 块、3 次中位；探针 USB/DAP 内部仍为原来的 16 队列，未缩小。RTT 使用 8KiB 环、2048 字节 chunk、3 秒×2次。50MHz 请求的实际 FCLK 为 99,999,999Hz、TCK/SWCLK 为 49,999,999.5Hz；60MHz 为 119,999,998Hz / 59,999,999Hz，均有运行时寄存器读回。

本轮使用保留现有目标应用的临时时钟及 RAM 测试夹具，没有重刷原记录的 scope 固件。因此已复现相应链路/夹具测试，未声称重跑 scope 应用及其 SysTick。文档中的旧烧录步骤只作背景参考。

主要结果（MB/s，十进制）：

| 模式 | SWD 读/写 | JTAG 读/写 | SWD RTT | JTAG RTT |
| --- | ---: | ---: | ---: | ---: |
| 50MHz | 4.054 / 3.979 | 2.024 / 2.009 | 4.006 | 1.989 |
| 60MHz | 4.840 / 4.752 | 2.423 / 2.400 | 4.803 | 2.394 |

旧配对本次实测和逐项变化见 [comparison-table.md](comparison-table.md)，可运行 `python docs/validation/orbtrace-sota-20261031/compare_results.py` 从原始 JSON 重新生成。默认 50MHz ELF 单独复测：SWD 读/写 4.045/3.981，JTAG 2.021/2.007，RTT SWD 3.995、JTAG 2.005，均通过数据/恢复校验。

HSS 共 42 行严格验证：每个数据帧逐字节正确，控制/数据帧序号有效，结束计数一致，无重复统计帧，无链路错误。SWD 单变量 1MHz，两档各三次零跳点；8变量 50MHz period236≈101695Hz、60MHz period197≈121827Hz，各三次零跳点。JTAG 单变量零跳点约269663/324324Hz，带约0.79%跳点的峰值约396826/595239Hz；8变量零跳点约45368/54299Hz。period195 等过载点的跳点仍保留在原始数据中。没有重新跑旧配对 HSS；这里与原记录中的 HSS 表比较。

30秒 SWD60 soak 均为零错误：首次优化版读/写中位4.83870/4.75340，但出现4.24925/2.96203的瞬时低点；原配对本次为4.82603/4.74846，最低4.78641/4.71976。随后不并行运行其他工具的优化版复测中位4.83740/4.75233、最低4.79914/4.53061。原记录最低4.76/4.57，因此写最低值仍约低0.9%。复测后探针 DMA/提交错误、兜底和队列背压计数均为零，但这些证据不足以唯一确定瞬时延迟来源。没有把最低值筛掉或承诺固定吞吐下限。

原始日志按 `optimized/`、`historical/`、`optimized_default50/`、`optimized_quiet_soak/` 保存；`restored/` 记录用户断电后的恢复和诊断。临时 SRAM 备份 `.bin` 留在本地，不纳入 Git；恢复 SHA-256 和核对结果在 JSON 中。正式复现入口是 `tools/run_sota_regression.py`，先用 `--dry-run` 查看参数；它不负责加载探针对或切换目标时钟，需要外层 `run_f103_clock_fixture.py` 和 `run_f103_jtag_fixture.py`。本次初始执行用的等价临时驱动命令已保存在 `*_runs.json` 与 `clock_*.json`。
