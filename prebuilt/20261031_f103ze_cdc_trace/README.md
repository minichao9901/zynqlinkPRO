# F103ZE CDC trace目标：匹配源码与整包echo修复

用户ZIP的提交、归档SHA、GNU Arm构建命令、Flash段及ELF身份见manifest.json。
fw-48.elf为未修补的重新构建基线；fw-48-echo.elf应用cdc-packet-boundary.patch，
将CDC OUT接收长度由512改为MPS64，避免整包等待后续短包。

两者均为HSE8、CPU48MHz、USB48MHz；AHB /4采集时TRACECLK6MHz。
修补版通过真实Web烧录/校验、31～1024字节echo、源码导入、USB初始化与同步CDC echo采集。
证据与限制统一记录在docs/F103ZE-Web-CLI-ETM统一验收-20261031.md。
这里是STM32目标ELF；Zynq probe需另行加载指定的bit/ELF配对，不能互相代替。
