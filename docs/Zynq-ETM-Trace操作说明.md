# Zynq ETM

Zynq使用prebuilt/golden的bit/ELF/ps7_init；目标匹配f103ze-cdc48.elf（48MHz CDC应用）。恢复包属于旧已验收版本，不能混称当前Golden。

| F103ZE | Zynq J7 | 信号 |
|---|---|---|
| PE2 | 16 | TRACECLK |
| PE3 | 15 | D0 |
| PE4 | 17 | D1 |
| PE5 | 18 | D2 |
| PE6 | 19 | D3 |
| GND | 14 | 地 |

统一入口为toolbox.py。离线浏览保存记录不需要连接探针。启用native probe、下载、采集或Flash均为独立硬件操作，本轮精简没有执行。

只保留最新有效1s（12MHz TRACECLK）和100ms业务记录，见retained-records.json。记录含gaps/unknownExecution，不把成功解码等同于全部执行已知，也不外推更高TRACECLK均通过。

原始输入、目标ELF、配置和源码必须配套。离线查看/导出：
`python toolbox.py trace --help`、`python toolbox.py project list`。
