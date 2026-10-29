$ErrorActionPreference = 'Stop'
$sdkRoot = 'E:\sdk_env_v1.11.0'
$env:HPM_SDK_BASE = Join-Path $sdkRoot 'hpm_sdk'
$env:GNURISCV_TOOLCHAIN_PATH = Join-Path $sdkRoot 'toolchains\rv32imac_zicsr_zifencei_multilib_b_ext-win'
$env:HPM_SDK_TOOLCHAIN_VARIANT = 'gcc'
$env:HPM_BUILD_TYPE = 'ram'
$env:BOARD = 'hpm5301evklite'
$env:PATH = "$sdkRoot\tools\python3;$sdkRoot\tools\cmake\bin;$sdkRoot\tools\ninja;" + $env:PATH
$buildPath = Join-Path $PSScriptRoot 'build'
cmake -G Ninja -DBOARD=hpm5301evklite -DHPM_BUILD_TYPE=ram -DCMAKE_BUILD_TYPE=release -S $PSScriptRoot -B $buildPath
if ($LASTEXITCODE) { throw 'HPM fixture CMake configuration failed' }
cmake --build $buildPath
if ($LASTEXITCODE) { throw 'HPM fixture build failed' }
