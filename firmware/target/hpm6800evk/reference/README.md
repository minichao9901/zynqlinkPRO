# HPM6800EVK Web验收靶子

按用户要求参考superlinkPRO，把其已保存的HPM6880目标固件和源码作为精确快照引入，分别用于J-Scope已知波形、RTT阻塞流和调试复杂结构/调用栈测试。来源仓库提交、原文件路径、字节数和SHA-256见[provenance.json](provenance.json)。这是目标MCU ELF，不是Zynq探针ELF。

三个原始 ELF 已迁入 [历史产物目录](../../../../prebuilt/targets/hpm6800-web-reference/README.md)。SDK v1.11.0 及 RISC-V 工具链仍为环境依赖。参考工程保留原始 build.ps1、CMakeLists 和 dbgstress 的共享 dbg_frames.c。新三板验收构建见[总表](../../README.md)。实板使用实际 ELF 符号核对地址和时钟。

会写HPM目标XPI Flash并重启目标。验收前备份实际受影响的完整擦除扇区及工作区；恢复结果见本轮验收报告。不要把它们加载成Zynq PS固件。
