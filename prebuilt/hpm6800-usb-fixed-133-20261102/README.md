# HPM6800EVK USB修复配对（133.333MHz约束）

bit复用已验收133.333333MHz/7.5ns文件；新PS修复CLEAR_FEATURE(ENDPOINT_HALT)漏复位DATA0。不是fixed-SWD固件，不替换Golden，也未固化QSPI。CDC缺口修复在本机EXE后台连续接收器，两部分须使用对应版本。

PS e93f1810…/bit106d579b…已实际加载并物理MEM-AP0匹配。100轮首DEF、冻结EXE24步随机、1/3/8通道完整窗口及严格序号流通过。SRAM主窗口约3.435/3.403MB/s；HSS上限波动、span元数据显示警告及原生转Web初连超时分别保留ZL-070/097/098。详见[R23](../../docs/validation/hpm6800-def-cdc-fix-20261102/README.md)、manifest和完整ps-build.json。PS源码基于035b187加报告build-inputs精确覆盖；提交后绑定承载源码提交。
