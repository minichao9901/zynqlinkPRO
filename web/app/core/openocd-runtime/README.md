# OpenOCD Wasm runtime

The runtime files match the Git blobs from superlinkPRO commit `c9454d0c639493946b0b446b51e9dff0f99a3074`, also present at `044af4a`. The runtime reports `0.12.0+dev-g9f2d876-dirty (2026-11-08-19:23)`. This browser build uses Asyncify, a monotonic Emscripten clock, the full Flash registry, and WebUSB CMSIS-DAP v2. [Corresponding superlinkPRO runtime and integration](https://github.com/minichao9901/superlinkPRO/tree/c9454d0c639493946b0b446b51e9dff0f99a3074/web/app/core/openocd-runtime)

| File | SHA-256 |
|---|---|
| `openocd-core.mjs` | `c4e99f080fbf6b50204a01d626fd650ef9b92e90969d5062580c27e589b81279` |
| `openocd-core.wasm` | `098be8c32791c5a24573a605292aec2cfe7d1a7d2d0dacc030006a723b5918dc` |

Corresponding sources are OpenOCD `9f2d8762b3a75b4d7b2155affcf3d8bb8eb8849a`, its Jim Tcl submodule `d5243a25c488dfe751ef218828f13516e04ea2ba`, and libusb `87a55632db62c9bdc58cd31d3ccfa673f1bb017f`. [OpenOCD source](https://github.com/openocd-org/openocd/tree/9f2d8762b3a75b4d7b2155affcf3d8bb8eb8849a) · [Jim Tcl source](https://github.com/msteveb/jimtcl/tree/d5243a25c488dfe751ef218828f13516e04ea2ba) · [libusb source](https://github.com/libusb/libusb/tree/87a55632db62c9bdc58cd31d3ccfa673f1bb017f)

The [build script](../../../tools/dev/build-openocd-core-wasm.sh) compiles the pinned sources. With MSYS2 Autoconf 2.73, remove the continuation backslashes after `Makefile` and `testing/Makefile` in the OpenOCD checkout's `AC_CONFIG_FILES` before bootstrapping. Link with `--optimization Oz --profile full --browser-session` and pass `--libusb`, `--libusb-source` and `--libusb-build` to the [link script](../../../tools/dev/link-openocd-core-wasm.py). The script applies the browser USB wait, CMSIS-DAP response and RISC-V SBA patches and links the [browser command loop](../../../tools/dev/openocd-browser-loop.c).
