# ETM C++ 主线集成与固定程序回归

日期：2026-11-03（Asia/Shanghai）。用户授权给旧 main 打 tag、合并候选、更新固定 EXE，并以 F103/H743 已保存记录做完整回归。本轮不操作硬件。

合并前 main 为 `06452f2`，固定 tag 为 `archive/main-before-etm-cpp-20261103`。候选为 `codex/etm-cpp-stage1` 的 `d7db13e`。固定历史流程与保留的 Python 参考路径见 [Golden Reference](../../etm-golden-reference.md)。

已检查另一会话“Review Web界面并提出改进建议”的 `codex/web-ui-compact`（`b181751`）：会话空闲，worktree 无未提交生产改动；只读检查，不修改其分支、不合并其未授权 UI 工作。C++ 候选不修改 Web JS/CSS；共同生产文件 `etm-service/server.py` 中，一方改 `elf_info` 接入原生 DTO，另一方增加教学示例接口，代码位置不同。问题表/编号说明必须按稳定编号保留双方记录，不能整表覆盖。

当前固定程序来源 `035b187` 是旧 main 的祖先，最新 Web 教学/紧凑布局仍在 Web 候选中；此次替换基于 main，不会把该候选偷偷加入固定程序。真实合并仅两处文档冲突，稳定问题行逐项三方比较无内容冲突，保留 main 的编号历史说明并补齐候选新增状态。

主线源码/Web/CLI、固定包验收和全部记录回归进行中。验证完成前，不声明固定 EXE 已验收；最终证据将随此报告补齐。旧源报告保留当时“未合并”结论，不改写历史快照。
