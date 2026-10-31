# 最小依赖与构建

- Vivado/SDK2018.3安装在项目外，真实CM3加密RTL仅XSim可编译。
- CM3本机默认目录和许可证保留于reference/cortex_m3_on_xc7a100t；文件身份见cm3-model.json。
- PS构建仍使用reference/legacy_zynq/.../usb_bsp/ps7_cortexa9_0的include/lib/libsrc；不要把BSP当编译垃圾删掉。
- reference/HFLink被HFLink研究worktree通过共享reference引用；reference/vexriscv用于真实RISC-V仿真，均保留。
- etm-service/native、vendor/OpenCSD-1.8.3、CMakeLists.txt及source-provenance保留原生重建源码。
- etm-service/build-native仅部署5个当前EXE，不是CMake缓存。它们的PE直接依赖仅Windows KERNEL32/msvcrt。
- prebuilt/golden/host/openocd保存此前使用的OpenOCD、配套DLL/scripts、GPL许可证及源码补丁。只验证版本启动，未在本轮重新测板。

Python需要Flask、numpy、pandas、pyelftools、capstone、pyusb、libusb-package、pyserial、hidapi、pefile；Node用于Web语法/自测；Icarus/本机C编译器用于快速协议/主机自测。

Golden是已有验收产物。重新构建DMA应用时明确使用--project xusbps_daplink_dma --compact-code --max-swclk-hz60000000与匹配BSP，生成产物必须重新验收，不能覆盖Golden后沿用旧哈希。PL构建为fpga/build_dma.tcl，完整RAW4/FIFO16、7020(-2)/120MHz；本轮没有执行。

SDK启动缓存与CM3快照默认位于项目外../zynqlinkPRO-work，可用ZYNQLINK_WORK_DIR指定。ETM原生重解按本次受测方式使用项目内临时工作目录，完成后清理；任意外部输出路径未在本轮接受。build/results为可清工作输出，不放唯一正式产物。
