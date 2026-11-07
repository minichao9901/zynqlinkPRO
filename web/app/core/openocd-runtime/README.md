# OpenOCD Wasm runtime

The two runtime files are copied byte for byte from superlinkPRO commit `5fc3cc60570aaa74900171b4b7fbcb4fa8da7dbf`. The build uses Emscripten 4.0.10, Asyncify, the full Flash registry, and the WebUSB CMSIS-DAP v2 browser session. [Corresponding superlinkPRO runtime and integration](https://github.com/minichao9901/superlinkPRO/tree/5fc3cc60570aaa74900171b4b7fbcb4fa8da7dbf/web/app/core/openocd-runtime)

| File | SHA-256 |
|---|---|
| `openocd-core.mjs` | `44014d5b8c29c9acc7e2310e33e314e22e720061e6004b79c7961571ac0e6b09` |
| `openocd-core.wasm` | `5ee31e1e56f89bb9376e120d950de1a769bf3a84a158e9cd0aa6b346d6607b9e` |

Corresponding sources are OpenOCD `9f2d8762b3a75b4d7b2155affcf3d8bb8eb8849a`, its Jim Tcl submodule `d5243a25c488dfe751ef218828f13516e04ea2ba`, and libusb `87a55632db62c9bdc58cd31d3ccfa673f1bb017f`. [OpenOCD source](https://github.com/openocd-org/openocd/tree/9f2d8762b3a75b4d7b2155affcf3d8bb8eb8849a) · [Jim Tcl source](https://github.com/msteveb/jimtcl/tree/d5243a25c488dfe751ef218828f13516e04ea2ba) · [libusb source](https://github.com/libusb/libusb/tree/87a55632db62c9bdc58cd31d3ccfa673f1bb017f)

The [build script](../../../tools/dev/build-openocd-core-wasm.sh) compiles the pinned sources. With MSYS2 Autoconf 2.73, remove the continuation backslashes after `Makefile` and `testing/Makefile` in the OpenOCD checkout's `AC_CONFIG_FILES` before bootstrapping. Link with `--optimization Oz --profile full --browser-session` and pass `--libusb`, `--libusb-source` and `--libusb-build` to the [link script](../../../tools/dev/link-openocd-core-wasm.py). The script applies the browser USB wait, CMSIS-DAP response and RISC-V SBA patches and links the [browser command loop](../../../tools/dev/openocd-browser-loop.c).
