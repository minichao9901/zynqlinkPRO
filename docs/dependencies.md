# 最小依赖与构建

后续PL实现与路由时序验证默认约束133.333333MHz（7.5ns），见根AGENTS.md。历史Golden的120MHz记录保持原样；约束值不等于运行FCLK/TCK，运行时仍按PLL/分频寄存器读回记录。

- Vivado/SDK2018.3安装在项目外，真实CM3加密RTL仅XSim可编译。
- CM3默认目录reference/cortex_m3_on_xc7a100t下的34个RTL/include文件、上游许可证和README已纳入Git；文件身份见cm3-model.json。
- PS默认BSP的include/lib/libsrc、Makefile与system.mss已纳入Git。libxil.a是必要的固定构建输入，其SHA-256与Golden及recovery的原构建清单一致；不提交可再生.o或SDK工作区元数据。
- reference/vexriscv/vexriscv.v和上游许可证已纳入Git，供main已有的真实RISC-V TAP仿真使用。
- hpm6800evk_rtt_kingst、xilinx_msc以及旧示例工程仍仅保留本地，正式构建/CM3仿真不依赖这些目录。HFLink worktree和分支已按用户要求退役，reference/HFLink仅为待手动清理的旧参考副本，不再要求保留。
- docs/required-dependencies.json列出全部869个必需依赖文件及SHA-256；普通git clone即可取得，无需子模块或Git LFS。运行python tools/verify_dependencies.py可严格离线检查完整性。
- etm-service/native、vendor/OpenCSD-1.8.3、CMakeLists.txt及source-provenance保留原生重建源码。
- 完整C++索引/建库另需已纳入Git的 `etm-service/vendor/nlohmann-json-3.11.3/json.hpp`（MIT，固定3.11.3及SHA）；无运行时DLL或联网下载依赖。主机编译器需支持C++17及浮点 `std::to_chars`，本轮使用本机MinGW GCC16.1。
- 原生静态字典固定Capstone5.0.7（与原Python绑定底层版本一致，仅编译ARM）和libdwarf2.3.3；所需源文件及许可证纳入vendor和依赖指纹。Capstone静态链接，libdwarf作为可替换的 `build-native/libdwarf.dll` 分发，冻结包附许可证和重建说明。DLL仅依赖Windows KERNEL32/msvcrt；CMake在builder构建后将DLL复制到同目录。
- etm-service/build-native部署6个当前EXE：etm_decode、etm_frontend、etm_storebuild、etm_index、etm_export、etm_framed，不是CMake缓存。它们的PE直接依赖仅Windows KERNEL32/msvcrt。
- prebuilt/golden/host/openocd保存此前使用的OpenOCD、配套DLL/scripts、GPL许可证及源码补丁。只验证版本启动，未在本轮重新测板。

Python基础环境安装：python -m pip install -r etm-service/requirements.txt。部分构建/分析脚本另外使用pefile、pandas；Node用于Web语法/自测；Icarus/本机C编译器用于快速协议/主机自测。这些工具和Vivado/SDK安装包不放进仓库。

换机时先运行python tools/verify_dependencies.py。Vivado/XSim使用2018.3，安装位置不同时设置XILINX_VIVADO；run_cm3_sim.py和run_vivado.py均支持此变量。PS构建可用--gcc指定SDK2018.3的arm-none-eabi-gcc.exe，run_xsct.py和build_probe_boot.py支持--sdk。仓库依赖路径相对脚本所在仓库解析，不要求clone到E:/zynqlinkPRO。

Golden是已有验收产物。重新构建DMA应用时明确使用--project xusbps_daplink_dma --compact-code --max-swclk-hz 60000000与匹配BSP，生成产物必须重新验收，不能覆盖Golden后沿用旧哈希。PL构建为fpga/build_dma.tcl，完整RAW4/FIFO16、7020(-2)/120MHz；本轮没有执行。

SDK启动缓存与CM3快照默认位于项目外../zynqlinkPRO-work，可用ZYNQLINK_WORK_DIR指定。ETM原生重解按本次受测方式使用项目内临时工作目录，完成后清理；任意外部输出路径未在本轮接受。build/results为可清工作输出，不放唯一正式产物。

H743 Golden的自包含SDK及来源哈希已纳入 `firmware/target/stm32h743_cdc_trace/sdk/`，不再依赖superlinkPRO目录。需要本机ARM GCC；`python toolbox.py project run target.h743-build -- -CoreMHz 60 -TraceR 12 -BannerEveryMs 20 -OutputDir build/h743-new -NoPublish` 只构建，不烧录。CPU60/TRACECLK20是ETM基线，CPU480/TRACECLK20是独立吞吐配置；详见该例程README及本轮综合报告。
