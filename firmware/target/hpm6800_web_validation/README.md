# HPM6800EVK Web验收靶子

按用户要求参考superlinkPRO，把其已保存的HPM6880目标固件和源码作为精确快照引入，分别用于J-Scope已知波形、RTT阻塞流和调试复杂结构/调用栈测试。来源仓库提交、原文件路径、字节数和SHA-256见[provenance.json](provenance.json)。这是目标MCU ELF，不是Zynq探针ELF。

三个fw.elf为原有产物，不宣称本轮重新构建。SDK v1.11.0及RISC-V工具链仍为环境依赖；源目录与原始build.ps1/CMakeLists保留，dbgstress的共享dbg_frames.c也在common/。构建命令及契约见各子目录README。源码注释中的历史地址、频率和性能不能代替本轮ELF符号与实测。

会写HPM目标XPI Flash并重启目标。验收前备份实际受影响的完整擦除扇区及工作区；恢复结果见本轮验收报告。不要把它们加载成Zynq PS固件。
