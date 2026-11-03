# 已合并 ETM worktree 清理

日期：2026-11-03（Asia/Shanghai）。用户确认 Web UI 已合并并授权检查、保留有价值内容后删除本任务 worktree。清理前 main 为 `3ae26e6`，固定包来源 `a2b8bc4`。

已删除三个本任务目录：

- `E:/zynqlinkPRO-work/etm-cpp-stage1-20261102`，头提交 `d7db13e`，源码已在 main。
- `E:/zynqlinkPRO-work/etm-index-reference-20261103`，临时对照 `b03275a`。
- `E:/zynqlinkPRO-work/etm-static-query-reference-20261103`，临时对照 `d022623`。

逐目录核对实际绝对路径、Git 顶层目录、头提交、无已跟踪文件修改及提交已可从 main 追溯后，使用 `git worktree remove --force` 清除。没有结束其它会话的程序。删除 38667 个文件，逻辑大小 20128710608 字节，约 18.75 GiB；该数字不是文件系统空闲空间的精确增量。

保留内容：

1. **正式源码、输入与验收**：均已合入 Git，包括 F103/H743 原始输入、目标 ELF、静态/索引/查询回归、失败证据、原生程序及依赖身份。`codex/etm-cpp-stage1` 分支也保留，历史提交可追溯。
2. **Python golden reference**：tag `archive/main-before-etm-cpp-20261103` 与 `E:/zynqlinkPRO-work/etm-golden-main-20261103/` 保留；使用范围见 [Golden Reference](../../etm-golden-reference.md)。另外两个临时性能对照目录不承担 golden 角色。
3. **补充实验资料**：[experiment-evidence.zip](experiment-evidence.zip)，517 个筛选后的日志、结果 JSON、CSV 与临时复现脚本，原始总大小 23089334 字节，压缩后 2815562 字节。已逐项核对 SHA 和 ZIP CRC，并纳入 Git。排除运行时令牌/鉴权信息、重复记录库、原生编译缓存与第三方工具目录；正式报告依旧优先于这些实验输出。
4. **最后一份合并前候选程序**：完整保存在本机 `E:/zynqlinkPRO/build/etm-worktree-archive-20261103/last-cpp-candidate/`，源码 `6b9732c`；复制前后所有 package manifest 文件 SHA 相等。仅供历史差分定位，日常使用固定 `dist/zynq-etm-bridge/`。历史程序包未重复提交到 Git；原生核心二进制与源码仍可从原提交读取。

删除的主要是重复生成的 store/native、各轮完整记录拷贝、临时编译与格式化工具、已被最终固定程序替代的多个冻结包。历史报告中被删除 worktree 的绝对路径不再作为现行入口，其提交、哈希和归档结论继续有效；需要重测时用 Git 重建隔离目录，输入使用已提交的原始记录。

本轮只做归档与目录清理。固定程序 EXE、package manifest、用户 data 内容树 SHA 均与清理前相同，未重新打包、未操作硬件、未推送。详细文件选择、逐文件 SHA、保留程序身份和删除结果见 [archive-manifest.json](archive-manifest.json)。
