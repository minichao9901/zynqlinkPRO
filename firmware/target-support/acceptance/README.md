# 三板共用的验收固件代码

STM32 调试压力负载的 `engine.*`、`model.*`、`dbg_frames.c` 和 `arm_debug.c` 源于
SuperLinkPRO 提交 `cf3afa1`，原路径为 `web/tools/target-firmware/stm32f103_dbgstress/src/` 和
`web/tools/target-firmware/common/`。`arm_debug.c` 接入本工程的时钟、RTT、浮点异常栈与验签。
HPM 的调试负载沿用同工作树保留的参考工程。构建入口与板卡接线见 [目标固件总表](../../target/README.md)。
