# ETM C++ 主线集成与固定程序回归

> 2026-11-05整理：本报告保留历史结论；逐轮原始证据/一次性驱动已固定在 Git tag `archive/main-before-cleanup-20261105`。恢复方法和逐文件SHA见[归档索引](../README.md)。历史路径及命令不表示当前可直接执行。

日期：2026-11-03（Asia/Shanghai）。用户授权给旧 main 打 tag、合并候选、更新固定 EXE，并以 F103/H743 已保存记录做完整回归。本轮不操作硬件。

合并前 main 为 `06452f2`，固定 tag 为 `archive/main-before-etm-cpp-20261103`。候选为 `codex/etm-cpp-stage1` 的 `d7db13e`。固定历史流程与保留的 Python 参考路径见 [Golden Reference](../../etm-golden-reference.md)。

已检查另一会话“Review Web界面并提出改进建议”的 `codex/web-ui-compact`（`b181751`）：会话空闲，worktree 无未提交生产改动；只读检查，不修改其分支、不合并其未授权 UI 工作。C++ 候选不修改 Web JS/CSS；共同生产文件 `etm-service/server.py` 中，一方改 `elf_info` 接入原生 DTO，另一方增加教学示例接口，代码位置不同。问题表/编号说明必须按稳定编号保留双方记录，不能整表覆盖。

更新前固定程序来源 `035b187` 是旧 main 的祖先，最新 Web 教学/紧凑布局仍在 Web 候选中。本次固定包使用 main 的前端，Web 候选的合并由该分支单独管理。真实合并仅两处文档冲突，稳定问题行逐项三方比较无内容冲突，保留 main 的编号历史说明并补齐候选新增状态。

主线及固定程序已完成本轮离线回归。合并提交 `56582e0`；修复依赖跟踪缺口 `3175de6`、打包前 Git 跟踪检查 `e61309d`；原生程序重新交付 `2782aa6`。旧报告中的“未合并”属于历史快照，继续保留。

## 最终交付

固定入口：`E:/zynqlinkPRO/dist/zynq-etm-bridge/zynq-etm-bridge.exe`。冻结源码为干净提交 `2782aa6`，原生 builder 内报构建源码 `3175de6bf448`；在新的 `native-clean` 目录从完整已跟踪源码编译成功。SHA、源码字节/Git blob、构建参数和冻结包身份见 [build-manifest.json](build-manifest.json)。decoder/exporter 保持此前已验证的 source77bf1c2 原生程序。

最终更新自动保留 data、归档上一程序到 `build/bridge-archive/20261103-201540-0a261c13/previous`。合并前原程序另保留于 `build/bridge-archive/20261103-142949-b88a0855/previous`。用户 data 的 5 个文件、1664 字节及内容树 SHA 与更新前完全一致：更新前（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-main-integration-20261103/raw/before.json`）、最终核对（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-main-integration-20261103/raw/validation.json`）。未生成 ZIP，未推送提交/tag，未进行任何硬件操作。

## 本轮回归

| 检查 | 结果 |
|---|---|
| 原生/发布/依赖专项 | 38 项通过；包含现有但未被 Git 跟踪的模板注入拒绝、发布回滚及用户数据保留 |
| CLI / Web | 55 / 93 项通过，Web 语法检查及共享驱动一致性通过 |
| 必需依赖 | 865 个文件内容与 Git 跟踪检查全部通过 |
| 完整建库差分 | F103 大记录、H743 1s/2s、F103/H743 尾截断各一组，共 5 组；完整执行块、诊断、analysis、默认视图及 60 张索引表相同 |
| 查询读取 | F103/H743 三种完整记录各 182 场景，共 546 次深度 DTO 对照通过 |
| 静态处理 | 双 ELF 的全部函数、DWARF 行区间、segments 和完整 Web ELF DTO 相同 |
| 协议诊断 | 双协议故障包型注入标签/名称通过；不是损坏 raw 流或硬件容错验收 |
| 固定历史 golden 升级 | 从固定 tag 的原始流程真实生成双协议旧库；新 main 的 binary/direct/rescan/重复切换、每目标 5 种真实输入变更拒绝、旧 native 保留和完整 60 表对照通过 |
| 最终固定 EXE | 双协议冻结导入/查询/HTML/SVG/CLI 验收通过；再次经实际 Web API 升级两种旧库、完整库相等、旧 native 保留，测试服务均退出 |
| 最终固定 EXE CSV | 两种目标均导出 seq900–1700 共 801 条连续记录，通过 |

见 汇总（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-main-integration-20261103/raw/validation.json`）、固定包离线验收（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-main-integration-20261103/raw/fixed-offline.json`）、F103 升级（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-main-integration-20261103/raw/fixed-upgrade-f103.json`）、H743 升级（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-main-integration-20261103/raw/fixed-upgrade-h743.json`）、CSV（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-main-integration-20261103/raw/fixed-csv.json`）；其余完整数组/查询/截断及 golden 升级结果在本目录 `raw/`。本轮构建与功能回归有并发执行，日志中的耗时仅用于定位，不作为新的性能 A/B 或真实采集 E2E 结论。ZL-006 仍为部分解决，不能据此宣称稳定低于 10 秒或与 Ozone 同等。

## 合并与失败证据

只读预演把新 main 与 Web 分支合并时，生产代码无文本冲突，`server.py` 中原生 ELF 与教学接口可自动同时保留；未来仍需逐项解决问题表冲突。Web 分支头始终为 `b181751`，未修改其工作区，未停止其用户程序。见 兼容核对（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-main-integration-20261103/raw/web-compatibility.json`）、问题行三方决策（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-main-integration-20261103/raw/issue-merge-decisions.json`）。本次未实际合并 Web 分支。

ZL-118：候选的 libdwarf `cmake/config.h.in` 被上游 `.gitignore` 忽略，原工作区865通过被本地文件掩盖，合并后的干净 main 仅864通过。现已显式提交与依赖清单一致的上游模板；检查全部声明依赖跟踪情况，增加打包前检查和故障注入；全新目录编译、最终固定 EXE及上述回归通过，限定关闭。首轮失败（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-main-integration-20261103/raw/dependencies-initial.json`）保留。

ZL-119：最终包 v2 的 PyInstaller 隔离扫描子进程在 asyncio 导入阶段崩溃，原因待定位；v3从头打包和离线验收通过不等于查明根因。完整失败见 v2日志（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-main-integration-20261103/raw/fixed-final-build-v2.log`），最终成功见 v3日志（历史归档：`git show archive/main-before-cleanup-20261105:docs/validation/etm-main-integration-20261103/raw/fixed-final-build-v3.log`）。另有本任务主动停止的未提交源码打包尝试：生成来源 manifest 时误把 JSON 的工作区 CRLF 与 Git LF 要求逐字节相等，校正为分别记录两者 SHA 后重新提交、从干净源码打包，未把被停止尝试当作交付。

中断前完成的 F103 检查予以保留，未完成的 H743 进程退出码未算通过；随后在独立输出目录完成全部剩余检查。当前上述结论均对应最终 builder/DLL 和最终固定包；所有本任务验收服务已退出。原 Python 参考实现继续保留，参考 tag 未移动。
