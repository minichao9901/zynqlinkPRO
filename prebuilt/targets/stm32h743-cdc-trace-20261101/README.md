# H743目标Golden与独立性能配置

目标程序，不是Zynq PS ELF。源代码、SDK、许可证和构建/烧录说明见 [例程](../../../firmware/target/stm32h743_cdc_trace/README.md)，逐文件身份、编译参数和验收范围见 [manifest](manifest.json)，实测数据见 [综合报告](../../../docs/validation/h743-comprehensive-20261101/README.md)。

| 目录 | CPU/HCLK/TRACECLK MHz | 使用范围 |
|---|---|---|
| cpu60-trace20 | 60 / 60 / 20 | 默认H743 Golden；10/200/500/1000ms连续ETMv4各三轮真实CDC负载通过 |
| cpu60-trace30 | 60 / 60 / 30 | 失败诊断，accepted=false，17次formatter解析错误 |
| cpu480-trace20 | 480 / 240 / 20 | 独立SRAM/RTT/HSS和调试插入吞吐配置；未验CPU480的一秒ETM |

三个目录均保存本次新构建的fw.elf/bin/hex。GCC10.3-2021.10；默认HSE25MHz、外部VDD33USB、banner20ms，I-cache开/D-cache关。SDK的GNU at属性警告保留，实际RTT控制块为0x24000cf4，g_trace为0x20003000。各档ELF不得交叉绑定。

本轮探针使用已有release及Golden配对，没有重建PL/PS、没有写QSPI。最后运行cpu60-trace20；原H743全Flash备份保存在验收raw目录。GUI首屏/起点/导出与固定dist EXE更新不在本次验收范围。
