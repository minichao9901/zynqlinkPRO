#!/usr/bin/env pwsh
# prep.ps1 —— 构建前的唯一准备工作：解开 ST 启动文件对 USB 中断的"弱别名锁定"
#
# ┌─ 为什么必须做（实测结论，别删这段注释）──────────────────────────────────────┐
# │ ST 的 startup_stm32f103xb.s / xe.s 对**每一个**中断都写了：                  │
# │     .weak      USB_LP_CAN1_RX0_IRQHandler                                   │
# │     .thumb_set USB_LP_CAN1_RX0_IRQHandler, Default_Handler                  │
# │                                                                             │
# │ 在 GNU as + GNU ld 下实测（arm-none-eabi-gcc 10.3.1）：                     │
# │   · 两条都在   -> startup.o 里是弱定义(W)，向量表指向 Default_Handler；      │
# │                   我们在 usb_glue_st.c 里的强定义**不生效**。               │
# │   · 只留 .weak -> startup.o 里是未定义弱符号(U)，向量表**仍然**指向         │
# │                   Default_Handler（未定义弱符号同样赢过强定义）。           │
# │   · 两条都去掉 -> 符号变成普通未定义(U)，向量表正确解析到我们的强定义 ✓      │
# │                                                                             │
# │ 也试过但**无效**的手段：调整链接顺序、--defsym=名字=名字、                  │
# │                        --defsym=名字=新名字。                               │
# │                                                                             │
# │ 对照：你用 MDK 编出来的 bootloader axf 里是                                 │
# │       0800011a W USB_HP_CAN1_TX_IRQHandler                                 │
# │       080018dc T USB_LP_CAN1_RX0_IRQHandler   ← ARM linker 把 .word 的      │
# │       未定义引用解析到了强定义，所以 MDK 下一切正常。GCC 这条链不一样。      │
# │                                                                             │
# │ 不做的后果：USB 中断永远进不来 → STM32F1 枚举卡在"取设备描述符" →            │
# │            Windows 报「未知 USB 设备(设备描述符请求失败) Code 43」。         │
# └─────────────────────────────────────────────────────────────────────────────┘
#
# 关于 .thumb_set 的一个假设（未验证，仅备注，不影响本脚本的正确性）：
#   ARM 的 `.thumb_set` 会定义符号，某些 GNU as 版本会把"设置过"的符号在
#   对象符号表里标成"已定义"，于是链接期不再接受外部强定义。
#   本脚本的做法是直接把这两条弱别名删掉，不依赖对该行为的任何假设。
#
# 幂等：可重复运行。原文件备份为 *.s.orig。
$ErrorActionPreference = 'Stop'

$sdk = Join-Path $PSScriptRoot '..\sdk\Drivers'
$files = @(
    (Join-Path $sdk 'CMSIS\Device\ST\STM32F1xx\Source\Templates\gcc\startup_stm32f103xb.s'),
    (Join-Path $sdk 'CMSIS\Device\ST\STM32F1xx\Source\Templates\gcc\startup_stm32f103xe.s')
)
$syms = @('USB_HP_CAN1_TX_IRQHandler', 'USB_LP_CAN1_RX0_IRQHandler')

$patched = 0
foreach ($f in $files) {
    if (-not (Test-Path $f)) { Write-Host "  跳过（不存在）: $(Split-Path $f -Leaf)"; continue }
    $bak = "$f.orig"
    if (-not (Test-Path $bak)) { Copy-Item $f $bak }

    $lines = Get-Content $f
    $out = New-Object System.Collections.Generic.List[string]
    $n = 0
    foreach ($line in $lines) {
        $drop = $false
        foreach ($s in $syms) {
            if ($line -match "^\s*\.weak\s+$([regex]::Escape($s))\s*$") { $drop = $true }
            if ($line -match "^\s*\.thumb_set\s+$([regex]::Escape($s))\s*,\s*Default_Handler\s*$") { $drop = $true }
        }
        if ($drop) { $n++; $out.Add("/* [prep.ps1] 已移除弱别名: $($line.Trim()) */") }
        else { $out.Add($line) }
    }
    if ($n -gt 0) {
        Set-Content -Path $f -Value $out -Encoding utf8
        Write-Host "  已补丁 $(Split-Path $f -Leaf)：移除 $n 条弱别名"
        $patched += $n
    } else {
        Write-Host "  无需补丁（可能已处理）: $(Split-Path $f -Leaf)"
    }
}

if ($patched -eq 0) { Write-Host "启动文件已是补丁状态。" }
exit 0
