# HPM6880 USB完整性RAM夹具

`producer.S`生成可逐字节推导的递增little-endian u32流，按运行时指定的字节数发布到RTT环。默认AHB16环完全位于有效32KiB AHB SRAM；`HPM_USB_AXI_RING=1`为AXI32环，复刻原RTT靶子的CB、缓冲起点和32KiB大小。实际使用的ELF/机器码与编译参数在[prebuilt](../../../prebuilt/targets/hpm6800-usb-ram-20261102/README.md)。

用`python toolbox.py project describe hpm.usb-fixture`和底层`--help`发现入口。安装会暂停目标、备份指定ILM/SRAM及GPR、DPC/DCSR/mstatus，启动无栈RAM程序；`restore`核对恢复已备份状态。不会写Flash或PLL，不是可直接复位启动的固件。AXI模式必须先确认目标PMA把0x01240000..0x0127ffff设为非缓存，工具不会代改PMA；保留的scope/RTT目标ELF具备此映射。不要在其他任务使用同一板卡时执行。

`hpm.cdc-sequence`通过真实Web窗口取数，以STOP ACK和目标发布总量核对所有字节；原始备份保留在新建的build状态目录，不提交Git。初版跨AHB边界的失败与后续修正均记录在[R23](../../../docs/validation/hpm6800-def-cdc-fix-20261102/README.md)，不作为产品丢字证据。
