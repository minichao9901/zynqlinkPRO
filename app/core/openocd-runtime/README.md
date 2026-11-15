# OpenOCD Wasm runtime

This runtime retains the HPM pipeline from [the headless A/B](../../../../docs/validation/hpm6800-wasm-pipeline-ab-20261109/README.md). It keeps the runtime integration from superlinkPRO commit `c9454d0c639493946b0b446b51e9dff0f99a3074` and reports OpenOCD `0.12.0+dev-g9f2d876-dirty`. This browser build uses Asyncify, a monotonic Emscripten clock, the full Flash registry, and WebUSB CMSIS-DAP v2. [Corresponding superlinkPRO runtime and integration](https://github.com/minichao9901/superlinkPRO/tree/c9454d0c639493946b0b446b51e9dff0f99a3074/web/app/core/openocd-runtime)

| File | SHA-256 |
|---|---|
| `openocd-core.mjs` | `5a55691c948f503d13bc233902d4a74782bee82e7276d9ad7d52d8394053700a` |
| `openocd-core.wasm` | `1977164ce62a8595753be9dfa741751c0b3f2459a95aa6bd03f25afe72d554fe` |

Corresponding sources are OpenOCD `9f2d8762b3a75b4d7b2155affcf3d8bb8eb8849a`, its Jim Tcl submodule `d5243a25c488dfe751ef218828f13516e04ea2ba`, and libusb `87a55632db62c9bdc58cd31d3ccfa673f1bb017f`. [OpenOCD source](https://github.com/openocd-org/openocd/tree/9f2d8762b3a75b4d7b2155affcf3d8bb8eb8849a) · [Jim Tcl source](https://github.com/msteveb/jimtcl/tree/d5243a25c488dfe751ef218828f13516e04ea2ba) · [libusb source](https://github.com/libusb/libusb/tree/87a55632db62c9bdc58cd31d3ccfa673f1bb017f)

The [build script](../../../tools/dev/build-openocd-core-wasm.sh) compiles the pinned sources. With MSYS2 Autoconf 2.73, remove the continuation backslashes after `Makefile` and `testing/Makefile` in the OpenOCD checkout's `AC_CONFIG_FILES` before bootstrapping. Link with `--optimization Oz --profile full --browser-session` and pass `--libusb`, `--libusb-source` and `--libusb-build` to the [link script](../../../tools/dev/link-openocd-core-wasm.py). The script applies the browser USB wait, CMSIS-DAP response and RISC-V SBA patches and links the [browser command loop](../../../tools/dev/openocd-browser-loop.c).

The [pipeline patch](../../../tools/dev/openocd-pipeline.patch) raises MAX_PENDING_REQUESTS from 4 to 8 and the dump_image/read_memory/write_memory buffers from 4 KiB to 64 KiB. The build script applies it before compiling all transport objects. Use a fresh build directory because their shared CMSIS-DAP struct layout must agree. The existing browser USB adaptation and RISC-V SBA batching remain enabled. HPM/JTAG at 25 MHz passed SRAM readback and restoration in the linked report. ARM/SWD hardware throughput remains a separate validation scope.

The runtime uses the upstream `stm32h7x` Flash driver. The built-in Flash list loads the pinned upstream CFGs through the same parser as user imports. The H743 comparison used the upstream CFG to set up debug over AP2 and the upstream driver to read the device ID. The Flash workflow retains direct debug-port programming when an enabled MPU could prevent instruction fetch from the RAM work area. [H743 board comparison and migration](../../../../docs/validation/h743-web-flash-resume-20261112/README.md#openocd-原版-cfg-对照与内置列表迁移)
