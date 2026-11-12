# OpenOCD Wasm runtime

This runtime retains the HPM pipeline from [the headless A/B](../../../../docs/validation/hpm6800-wasm-pipeline-ab-20261109/README.md). It keeps the runtime integration from superlinkPRO commit `c9454d0c639493946b0b446b51e9dff0f99a3074` and reports OpenOCD `0.12.0+dev-g9f2d876-dirty`. This browser build uses Asyncify, a monotonic Emscripten clock, the full Flash registry, and WebUSB CMSIS-DAP v2. [Corresponding superlinkPRO runtime and integration](https://github.com/minichao9901/superlinkPRO/tree/c9454d0c639493946b0b446b51e9dff0f99a3074/web/app/core/openocd-runtime)

| File | SHA-256 |
|---|---|
| `openocd-core.mjs` | `c3e893b054999756781ce1b94c067b04c1bb437e50e48f1d8baef1579f25209f` |
| `openocd-core.wasm` | `d8017a5f31244efbc776cf7b24f1992e95aeb19aa5e9e95f86ce814146a3daf0` |

Corresponding sources are OpenOCD `9f2d8762b3a75b4d7b2155affcf3d8bb8eb8849a`, its Jim Tcl submodule `d5243a25c488dfe751ef218828f13516e04ea2ba`, and libusb `87a55632db62c9bdc58cd31d3ccfa673f1bb017f`. [OpenOCD source](https://github.com/openocd-org/openocd/tree/9f2d8762b3a75b4d7b2155affcf3d8bb8eb8849a) · [Jim Tcl source](https://github.com/msteveb/jimtcl/tree/d5243a25c488dfe751ef218828f13516e04ea2ba) · [libusb source](https://github.com/libusb/libusb/tree/87a55632db62c9bdc58cd31d3ccfa673f1bb017f)

The [build script](../../../tools/dev/build-openocd-core-wasm.sh) compiles the pinned sources. With MSYS2 Autoconf 2.73, remove the continuation backslashes after `Makefile` and `testing/Makefile` in the OpenOCD checkout's `AC_CONFIG_FILES` before bootstrapping. Link with `--optimization Oz --profile full --browser-session` and pass `--libusb`, `--libusb-source` and `--libusb-build` to the [link script](../../../tools/dev/link-openocd-core-wasm.py). The script applies the browser USB wait, CMSIS-DAP response and RISC-V SBA patches and links the [browser command loop](../../../tools/dev/openocd-browser-loop.c).

The [pipeline patch](../../../tools/dev/openocd-pipeline.patch) raises MAX_PENDING_REQUESTS from 4 to 8 and the dump_image/read_memory/write_memory buffers from 4 KiB to 64 KiB. The build script applies it before compiling all transport objects. Use a fresh build directory because their shared CMSIS-DAP struct layout must agree. The existing browser USB adaptation and RISC-V SBA batching remain enabled. HPM/JTAG at 25 MHz passed SRAM readback and restoration in the linked report. ARM/SWD hardware throughput remains a separate validation scope.

The [H7 DBGMCU patch](../../../tools/dev/openocd-h7-dbgmcu.patch) allows both Flash banks in the built-in STM32H7 profile to identify H74x/H75x through a MEM-AP target on the same TAP. It reads the APB DBGMCU ID through AP2 and checks the Flash capacity through the CPU MEM-AP before returning geometry. The workbench temporarily enables the D1 debug bits over AP2 before examining the core and verifies restoration on close or before reset.

This binary was built with Emscripten 4.0.10 using native Windows LLVM archive builds and the linked browser build above. The standard MSYS2 shell was blocked by the session's Windows permissions. The 26 adapter entries, 38 target types and three transports match the previous runtime. The H743 regression uses the shipped Wasm with an emulated CMSIS-DAP target. It covers the old failure with an AP0 ID of zero, both banks through AP2, the existing AP0 path, invalid identity and capacity, and DBGMCU_CR restoration.

The H743 board check reached Flash programming via AP2. The original paused application's MPU configuration rejected instruction fetch from the AXI work area. The workbench now reads MPU_CTRL before erase and selects the driver's direct debug-port writes when the MPU is enabled. The RAM algorithm with independent work-area backup remains available when the MPU is disabled. See the [board results and retest scope](../../../../docs/validation/h743-web-flash-resume-20261112/README.md).
