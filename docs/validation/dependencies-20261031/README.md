# 必需依赖补全与干净克隆验证

本轮修正精简时对reference/整体忽略的问题。34个真实CM3 RTL/include及上游许可/说明、260个匹配BSP输入、2个VexRiscv模型/许可文件随Git提供，总计298个文件。研究目录仍本地保留，详见../../not-in-git-files.txt。

验证从实际Git干净克隆执行，reference仅有CM3/BSP/VexRiscv，未复制本机研究目录。克隆的文件与Git blob、依赖清单SHA-256全部一致，PS库与原Golden/recovery构建清单一致；运行真实CM3 JTAG完整流水线、真实VexRiscv TAP、45项Python测试。20个正式PS C源文件使用克隆BSP完成-fsyntax-only检查，读取静态库102个成员。工具链安装在项目外。

没有综合PL、生成PS ELF、访问板子或写Flash；没有改变Golden/recovery字节或挪动既有Golden标签。CM3模型仍为原加密模型，VexRiscv保留原生成模型，未重新生成CPU。摘要注明实际测试的源码提交；后续提交仅补充本记录和本机文件清单。
