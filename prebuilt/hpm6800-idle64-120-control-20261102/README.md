# HPM6800EVK idle64早期120MHz对照

2026-11-02。仅保留用户纠正约束前**实际加载、实测**的研究配对，供追溯，不是当前推荐配对。来源、构建输入及SHA见[manifest.json](manifest.json)，结果见[报告](../../docs/validation/hpm6800-idle-frontier-20261102/README.md)。

fresh120时序setup +0.415ns、hold +0.034ns。60MHz TCK/idle20/mode17随机SRAM、RTT/HSS探索通过；idle64能力已观测。完整业务重验使用另一个[133.333MHz配对](../hpm6800-idle64-133-experimental-20261102/README.md)，不能混淆。

`implemented-constraints.xdc`及`verify-routed-source.tcl`保留当时120MHz输入。当前源码默认已改133.333MHz，重建本对照必须显式恢复对应实验约束；不得以120MHz替代后续默认实现。PS与133配对ELF字节相同，二者timing元数据不同，均显式API cap60MHz。
