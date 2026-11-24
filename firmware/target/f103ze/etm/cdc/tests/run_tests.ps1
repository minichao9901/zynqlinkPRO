param([string]$CC)
$ErrorActionPreference = 'Stop'
if (-not $CC) { $CC = (Get-Command gcc).Source }
$testRoot = Split-Path -Parent $PSScriptRoot
$testBuild = Join-Path $testRoot 'build\tests'
New-Item -ItemType Directory -Path $testBuild -Force | Out-Null
$testExe = Join-Path $testBuild 'cdc_console_test.exe'
& $CC '-std=c11' '-O2' '-Wall' '-Wextra' '-Werror' '-Wpedantic' `
    "-I$testRoot\src" "$testRoot\src\cdc_console.c" `
    "$PSScriptRoot\test_cdc_console.c" -o $testExe
if ($LASTEXITCODE -ne 0) { throw 'CDC 测试编译失败（需要 Windows 本机 C 编译器）' }
& $testExe
if ($LASTEXITCODE -ne 0) { throw 'CDC 回归测试失败' }
