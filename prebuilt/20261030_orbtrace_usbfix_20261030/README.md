# ORBTrace USB-fix 实验配对（2026-10-30）

本配对包含 USB DATA toggle / CoreSight TRCENA 修复，bit 与 native32 版本相同，ELF 为本次源码重新编译。

状态：SWD/DAP/RTT/HSS 实板通过；ETM 已同步且低速捕获可无丢失，但 OpenCSD 仍失败，未宣称 ETM 完整验收。
详见 `docs/validation/orbtrace-board-20261030/summary.json`。
