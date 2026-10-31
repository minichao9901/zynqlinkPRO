# 最小依赖与构建

- Vivado/SDK2018.3安装在项目外，真实CM3加密RTL仅XSim可编译。
- CM3默认目录reference/cortex_m3_on_xc7a100t下的34个RTL/include文件、上游许可证和README已纳入Git；文件身份见cm3-model.json。
- PS默认BSP的include/lib/libsrc、Makefile与system.mss已纳入Git。libxil.a是必要的固定构建输入，其SHA-256与Golden及recovery的原构建清单一致；不提交可再生.o或SDK工作区元数据。
- reference/vexriscv/vexriscv.v和上游许可证已纳入Git，供main已有的真实RISC-V TAP仿真使用。
- reference/HFLink、hpm6800evk_rtt_kingst、xilinx_msc以及旧示例工程仍仅保留本地，正式构建/CM3仿真不依赖这些目录。
- docs/required-dependencies.json列出全部298个必需依赖文件及SHA-256；普通git clone即可取得，无需子模块或Git LFS。运行python tools/verify_dependencies.py可严格离线检查完整性。
- etm-service/native、vendor/OpenCSD-1.8.3、CMakeLists.txt及source-provenance保留原生重建源码。
- etm-service/build-native仅部署5个当前EXE，不是CMake缓存。它们的PE直接依赖仅Windows KERNEL32/msvcrt。
- prebuilt/golden/host/openocd保存此前使用的OpenOCD、配套DLL/scripts、GPL许可证及源码补丁。只验证版本启动，未在本轮重新测板。

Python基础环境安装：python -m pip install -r etm-service/requirements.txt。部分构建/分析脚本另外使用pefile、pandas；Node用于Web语法/自测；Icarus/本机C编译器用于快速协议/主机自测。这些工具和Vivado/SDK安装包不放进仓库。

换机时先运行python tools/verify_dependencies.py。Vivado/XSim使用2018.3，安装位置不同时设置XILINX_VIVADO；run_cm3_sim.py和run_vivado.py均支持此变量。PS构建可用--gcc指定SDK2018.3的arm-none-eabi-gcc.exe，run_xsct.py和build_probe_boot.py支持--sdk。仓库依赖路径相对脚本所在仓库解析，不要求clone到E:/zynqlinkPRO。

Golden是已有验收产物。重新构建DMA应用时明确使用--project xusbps_daplink_dma --compact-code --max-swclk-hz 60000000与匹配BSP，生成产物必须重新验收，不能覆盖Golden后沿用旧哈希。PL构建为fpga/build_dma.tcl，完整RAW4/FIFO16、7020(-2)/120MHz；本轮没有执行。

SDK启动缓存与CM3快照默认位于项目外../zynqlinkPRO-work，可用ZYNQLINK_WORK_DIR指定。ETM原生重解按本次受测方式使用项目内临时工作目录，完成后清理；任意外部输出路径未在本轮接受。build/results为可清工作输出，不放唯一正式产物。
