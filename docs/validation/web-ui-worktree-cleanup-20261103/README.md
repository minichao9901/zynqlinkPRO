# Web UI worktree 清理（2026-11-03）

用户授权检查保留内容并删除本会话worktree。检查时Web分支头为b181751，已合入main a2b8bc4，组合验收3ae26e6；无独有提交、无未提交已跟踪源码。独立分支指针`codex/web-ui-compact`保留，未推送，未操作硬件，其他worktree未做清理。

## 保留内容

本机归档目录：`E:/zynqlinkPRO/build/worktree-archive/web-ui-compact-20261103/`。保留原相对路径，2419文件/574666127字节（约575MB），全部复制后逐文件SHA-256核对。详细清单在归档目录的`archive-manifest.json`，SHA-256为`f5cf9ddb828abb99cc0d5767c21808957500898382f80a103300fc5bb26120a8`；摘要见archive-summary.json。

- 原`build/web-cli-25-20261103/`：RTT/HSS原始数据、失败及对照窗口、fixture；现按原相对路径位于上述归档下。已按已提交raw-evidence-manifest逐项验证54份原始数据。
- 其余任务build输出：Flash备份/恢复、教学示例/浏览器/CLI验收记录和构建日志；仅排除旧bridge-archive及bridge-package构建缓存。
- `etm-service/records/`及两份dist的本地data，原字节保留，不并入正式用户data。
- 最后一版Web分支候选程序`dist/zynq-etm-bridge-candidate-20261103/`完整保留，用于追溯旧报告身份。当前日常程序仍为主工作区固定EXE，不应把这个历史候选当成合并后的C++版本。

正式源码、报告和产物已在main/Git，不额外重复复制。旧程序归档、打包临时目录及Python缓存已清理；旧缓存里的15个松散F103 ELF均核对为Git中Golden的重复字节。

归档是本地工作输出，不批量纳入Git。内部可能包含已停止服务的旧runtime文件，不作为启动入口，也不分发其中本机鉴权信息。历史报告里的旧绝对路径现按“旧worktree根→上述归档根”定位；Git已跟踪的文件优先从main/Git读取。

## 清理结果与空目录边界

`git worktree remove --force`删除了checkout内容及Git登记，但最后删除根目录时Windows返回占用错误。随后确认目录为空、worktree列表已不含此路径。重置本会话JS内核仍未释放目录；Codex管理接口返回“The task’s primary checkout cannot be removed.”，未强制停止进程或干扰其他会话。

因此当前剩下的只是`C:/Users/Administrator/.codex/worktrees/web-ui-compact/zynqlinkPRO/`空目录，待会话释放后可直接删除。没有未保留数据或仍登记的Web worktree，不能表述为路径本身已不存在。见result.json。
