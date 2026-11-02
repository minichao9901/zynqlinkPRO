# 旧ETM decoder的候选工作树输出失败

日期2026-11-03（Asia/Shanghai），ZL-116，待定位。处理ZL-107升级回归时观察到：相同100ms输入及配置，main旧etm_decode.exe输出到main/build成功（exit0），输出到候选worktree/build失败（Cannot write，exit1）；Python可写该目录，候选etm_decode.exe亦成功。具体路径与结果见control.json。本轮不预判权限、路径长度或CRT根因，未修改旧程序。

这发生在main生成基准阶段，早于升级验证；改用main/build全新任务目录后，main→候选同目录升级、模式切换及真实输入变更校验已通过。该处置不算修复本路径边界，也不删除失败记录。未操作硬件、未改目标/探针固件。待独立定位旧程序实际I/O失败原因及路径覆盖。
