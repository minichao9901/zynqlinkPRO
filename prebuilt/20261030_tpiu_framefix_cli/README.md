# TPIU 连续帧/同步与CLI配对

状态：本次新构建，STA通过，待上板验收。保留其它已知配对，不替换根目录默认固件。
源码修改：连续16字节帧、帧内HSYNC移除、FSYNC自动选择字节相位，非法结构传播为loss。
详细源码哈希、构建命令、bit/ELF及PS初始化SHA-256见manifest.json。

FCLK约束验收上限100MHz；setup +0.487ns、hold +0.015ns。ELF由当前源码重新编译，
最大SWCLK/TCK为50MHz。实际运行FCLK/TCK以采集报告为准，不能用这些上限代替实测。

```powershell
python tools/run_xsct.py tools/download_dap_fpga.tcl prebuilt/20261030_tpiu_framefix_cli/zynqdap_orbtrace.elf prebuilt/20261030_tpiu_framefix_cli/zynqdap_orbtrace.bit
python -X utf8 toolbox.py --runtime build/native-web-final serve --port 8882 --bit prebuilt/20261030_tpiu_framefix_cli/zynqdap_orbtrace.bit --zynq-elf prebuilt/20261030_tpiu_framefix_cli/zynqdap_orbtrace.elf
```

打开serve输出的browserUrl，CLI上传目标ELF后调用page etm invoke captureNative。
完整命令见docs/toolbox-cli-ai.md；本轮记录见docs/validation/web-cli-f103ze-20261030/README.md。
当前目标ELF为etm-service/firmware/stm32f103_cdc_trace/fw-ze.elf，SHA-256：
63881ed9f6c1187d56924795ccad3f151a677aea0dfa201823fe44e0cb857522。
