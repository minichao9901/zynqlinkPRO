# HPM6800EVK Web + 66.667MHz实验配对

PL按133.333333MHz/7.5ns验证，复用R20的bit；PS增加RISC-V最高档、启动诊断及旧HID架构/状态兼容。不是全平台Golden，不固化探针QSPI。

实际Web烧录/RTT/调试及随机切换使用此配对；同配对重载后原生SRAM约3.44/3.40MB/s、RTT3.19MB/s、HSS296.296kS/s对照通过。Web默认烧录实际10MHz。J-Scope跨功能缺首DEF（ZL-005）仍复现，另有随机CDC字节缺口ZL-094，不能称全通过。

见[完整报告](../../docs/validation/hpm6800-web-stress-20261102/README.md)、[manifest](manifest.json)。PS输入为b5bb054加报告build-inputs精确覆盖，完整输入SHA在ps-build.json；提交后source_revision注明承载修正的源码提交。
