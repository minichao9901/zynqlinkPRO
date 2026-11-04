# 统一控制与飞行记录验收配对

2026-11-05，accepted=true，限定F103ZE实板范围：统一控制与流中重连、HSS/RTT、ETMv3环形历史、手动/主机Fault轮询触发与后窗。最终冻结工作台1.1.1已验收。仅JTAG/RAM加载，不替代Golden或QSPI恢复包；未验QSPI冷启动、H743/HPM飞行记录、物理GPIO触发或8小时压力。

PL为本轮RAW4+DDR新构建，133.333333MHz约束setup0.153ns/hold0.032ns，SWCLK7ns预算实际6.800ns。PS为本轮重建，最终执行段85652B经物理MEM-AP0核对一致。运行Trace控制时FCLK约120MHz、SWD约10MHz，均为寄存器推算，不是外部频率计实测。

文件SHA和原始构建选项见[manifest](manifest.json)，源码输入绑定到5be7176见[source-binding](source-binding.json)。原构建基线f466935加工作区输入的记录保留；后续2a1b99f只改主机防护及字节属性，未改变本配对。中间配对子目录保留各自身份，不冒充最终PS测试。

完整范围、失败对照、最终EXE身份和恢复证据见[验收报告](../../docs/validation/session-flight-recorder-20261105/README.md)。板上只加载RAM，重新上电后须核对实际配对。
