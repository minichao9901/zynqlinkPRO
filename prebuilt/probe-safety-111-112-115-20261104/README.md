# ZL-111 / 112 / 115 修复配对

`application.elf`为正式镜像，`validation.elf`仅用于本轮受控PS故障注入，不用于日常运行。两者均与本目录实际验收使用的`probe.bit`配对。正式镜像不含故障控制变量，保留只读故障诊断。

bit逐字节复用fclk133-release-20261101的133.333MHz已布线产物，WNS0.319ns/hold0.033ns；未改RTL、未新做PL实现。PS按本轮源码重新构建，输入SHA/选项分别见production-build.json、diagnostic-build.json；文件SHA/限定验收范围见manifest.json。

F103ZE SWD/JTAG正常业务及故障隔离已验收，仅JTAG/RAM加载，未写QSPI或MCU Flash，不替代Golden/QSPI恢复包。历史失败/中间镜像位于独立子目录，accepted=false。

[详细报告](../../docs/validation/probe-safety-111-112-115-20261104/README.md)。

源码与实测产物提交：`4d5bd0130d64d6e033078af3160c40ef55205260`。提交后逐项核对43个编译输入与该提交的Git blob，仅允许CRLF/LF规范化，映射见[构建输入绑定](source-binding.json)；编译时原始b066f1b/dirty/input SHA记录保持不变。
