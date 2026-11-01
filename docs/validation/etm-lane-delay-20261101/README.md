# 逐线输入延迟阶段证据

| 目录 | 范围与结果 |
|---|---|
| failed-first-build | 0de5712首轮直接旁路/延迟并行方案，RTSTAT-2部分未布线，未生成/加载新bit |
| simulation | 首轮数字功能仿真，不能替代该轮失败的物理实现 |
| simulation-v2-zero-tap | e18dd7e单输入路径、启动零tap及故障恢复仿真通过；原9项DDR边界各跑两种参数 |
| implementation/second-build | 单路径重新实现，后置检查对局部网络段误报unused；保留完整日志 |
| implementation/repair | 同一网表AggressiveExplore/route优化，120MHz setup +0.013、hold +0.010，生成新bit，DRC 0错误 |
| implementation/fanout-inspection | 沿跨层级all_fanout确认5条DATAOUT到5个独立pad_meta_reg/D |
| implementation/verification | 226bcb2严格端点、时序、bitgen产物复核；父构建、DCP、bit和验证脚本SHA绑定 |
| implementation/ps-build.log | 配套PS ELF本次实际重新编译的完整日志 |
| board | 实际JTAG加载、OCM代码身份、两轮DDR模式、独立tap实读/归零 |
| zero-tap-24mhz | 100ms/1s真实Flash函数入口采集、原生解码、CDC及可重放记录，通过 |
| scan36-first | 36MHz首次自动扫描，110点无通过点，第111点DAP清理失败，保留111份坏点zip；它们不是通过的etmrecord |
| web-100cycles | 构建并行运行期间，旧已知配对100次Web打开/关闭通过；不冒充新配对的Web验收 |

新的实际加载配对为prebuilt/etm-lane-delay-raw4-20261101，bit SHA eac5a263…，PS ELF SHA 1d55b321…。Golden及上一已知配对不变。新配对只证明上述已测项目；36MHz、自动校准、H743及新配对的Web压力尚未通过。

第111点的遗留断言没有保留不匹配的DAP响应字节，无法从现有证据判断ACK、队列或电气根因。已按首个非采样质量故障停止，没有继续扫描或重试；外层通过原Flash字节及RCC验证恢复，输入tap归零。后续须先补齐响应现场，再决定是否修改会话边界或接收结构。
