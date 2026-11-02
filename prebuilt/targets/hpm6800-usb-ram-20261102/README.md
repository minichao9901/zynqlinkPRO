# HPM6800EVK USB序号流RAM夹具

AHB16占用32KiB内的16KiB环；AXI32在0x01240000、pBuffer=0x012400b8、环32KiB，复刻原RTT靶子布局。源/编译参数/实际使用代码SHA见manifest。AXI版要求目标已配置0x01240000..0x0127ffff非缓存PMA，工具不代改PMA。

用`toolbox.py project describe hpm.usb-fixture`发现安装/控制/恢复工具，先核对探针身份与空闲状态。只加载到ILM 0x10000并备份/恢复GPR、DPC/DCSR/mstatus及指定SRAM，不写Flash/PLL，不提供独立启动初始化。用户SRAM备份不可提交Git。每个字节由递增little-endian u32序列确定；发布粒度可为4/13/127/2048B。最终恢复结果及接口验收见[R23](../../../docs/validation/hpm6800-def-cdc-fix-20261102/README.md)。
