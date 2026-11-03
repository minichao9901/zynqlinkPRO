# 历史研究分支退役与归档

日期：2026-11-03（Asia/Shanghai）。用户根据[四分支审查](../research-branch-review-20261103/README.md)授权先归档有价值内容，再删除四个分支及对应工作目录。

保留安排：

- RISC-V 三个独有提交固定到 annotated tag `archive/20261103/riscv-sba-pipeline`，对应 `a236da6`。这是历史WIP归档，不是已验收版本；BUSY编码和回归失败继续见ZL-128。
- SWD 七个独有提交由既有 tag `swd-timing-generator-rx-events-20261028` 完整保留，未移动该tag。
- FCLK 未提交脚本的原文件和补丁已在 main 的审查报告中保存；删除前再次逐字节核对未发生新修改。已提交部分可从main追溯。
- ETM 已验收配对、24MHz最佳tag、原始记录与失败现场已纳入main。额外筛选本地build中的实验日志、结果、时序报告和采集/内存二进制等资料，以内容SHA去重压缩；所有内容对象解压后重新核对SHA。排除可重建的store/native、实现检查点、冻结运行库和运行时令牌目录。
- 原build中4种未匹配main prebuilt的中间ELF另外保存在本报告 `historical-artifacts/` 并纳入Git，以免唯一原字节随目录丢失。它们是历史快照，来源/配对/验收没有在本轮重新建立，不可替换当前交付或Golden；未修改、编译或加载它们。

额外实验压缩包保留在本机 `E:/zynqlinkPRO/build/research-branch-archive-20261103/etm-research-evidence.zip`，内含 `file-manifest.json`；文件路径与SHA映射在[归档清单](archive-manifest.json)中也纳入Git。Zip中的内容对象使用 `objects/<SHA256>` 命名；按清单恢复原相对路径即可。原始采集/内存快照仅保留在本机压缩包，不重复纳入Git。

已删除并核对的分支：`codex/etm-lane-calibration`、`codex/fclk-timing`、`codex/swd-timing-generator`、`wip/riscv-sba-pipeline`。对应工作目录仅 `E:/zynqlinkPRO_etm_calibration` 和 `E:/zynqlinkPRO_fclk_timing`；先验证绝对路径、分支头、修改与归档，再用Git删除。前两条提交已合入main，后两条仅删除分支名，全部独有历史由上述tag保留。本地开发分支只剩main；远端引用未处理。

两目录移除的文件逻辑大小为24308175805字节，约22.64GiB；归档ZIP为416954000字节，包含4984个源路径、按SHA去重后的2453个内容对象。目录大小不等同于磁盘空闲空间的精确增加量，归档本身也继续占用空间。

main、固定EXE、用户data、Python golden reference tag/worktree和其它未授权目录保留。本轮没有操作硬件、重构建、重新打包或推送。实际删除结果与最终身份核对随归档清单记录。
