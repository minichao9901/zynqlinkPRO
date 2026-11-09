# J7 ARM JTAG 66.666666 MHz 实验配对

用于 H743 CPU480/HCLK240 单板验收。配对的 bitstream 与 PS 初始化沿用正式 J7 文件，见 [manifest.json](manifest.json)。板测和恢复结果见 [报告](../../docs/validation/h743-jtag66-20261109/README.md)。

重建时在独立源码目录检出 manifest 中的 sourceRevision，应用 arm-jtag66.patch。使用 SDK 2018.3 工具链及仓库 BSP，执行：

    python -X utf8 tools/build_xusbps_daplink.py --compact-code --j7-adapter --max-swclk-hz 66666666 --timing prebuilt/release-20261106/verified_clock.json --out <独立输出目录>

此实验只经 JTAG/RAM 加载。普通发布包仍保持 60 MHz 上限。
