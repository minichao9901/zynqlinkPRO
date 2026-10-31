# ETM service

当前使用根README、docs/Trace-CLI使用说明.md和docs/Zynq-ETM-Trace操作说明.md。

- native/、vendor/OpenCSD-1.8.3和CMakeLists.txt为可重建源码。
- build-native/只保留当前5个部署EXE，不存CMake中间目录。
- records/只保留清单中的两条F103ZE CDC-ETM记录，含匹配ELF、配置、源码和trace-store。native.bin不是浏览所需，已经离线验证并省略。
- 旧H7/SPI示例固件、业务历史和实验脚本已退出活跃树；历史源在archive/main-before-slim-20261031。
- 离线检查：python toolbox.py trace doctor --offline。不会自动启动服务或枚举探针。
