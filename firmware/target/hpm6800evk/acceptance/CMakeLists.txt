cmake_minimum_required(VERSION 3.13)
find_package(hpm-sdk REQUIRED HINTS $ENV{HPM_SDK_BASE})
project(hpm6800evk_acceptance C ASM)

set(shared "${CMAKE_CURRENT_SOURCE_DIR}/../../../target-support/acceptance")
set(debug "${CMAKE_CURRENT_SOURCE_DIR}/../reference")
sdk_inc(${shared})
# The pinned local SDK's Ethernet driver can include this header even for a UART target.
if(EXISTS "$ENV{HPM_SDK_BASE}/samples/lwip/lwip_tcpecho/src/TRACE_LOG")
    sdk_inc($ENV{HPM_SDK_BASE}/samples/lwip/lwip_tcpecho/src/TRACE_LOG)
endif()
sdk_compile_definitions(-DCONFIG_NDEBUG_CONSOLE=1 -DTARGET_HPM
    -DFIXTURE_RING_BYTES=16384 -DFIXTURE_BUILD_MARKER=${FIXTURE_BUILD_MARKER}
    "-DFIXTURE_BUILD_ID=\"hpm6800evk-${FIXTURE_IMAGE}\"")
sdk_compile_options(-g3 -gdwarf-4 -ffunction-sections -fdata-sections)
sdk_app_src(${shared}/hpm_platform.c)

if(FIXTURE_IMAGE MATCHES "^dbg-")
    sdk_compile_definitions(-DFIXTURE_ACCEPTANCE)
    sdk_compile_options(-Og -fasynchronous-unwind-tables)
    sdk_app_src(${debug}/dbgstress/src/main.c ${debug}/dbgstress/src/engine.c
                ${debug}/dbgstress/src/model.c ${debug}/common/dbg_frames.c
                ${shared}/debug_observables.c ${shared}/rtt.c)
elseif(FIXTURE_IMAGE MATCHES "^performance-")
    sdk_compile_options(-O2)
    if(FIXTURE_IMAGE STREQUAL "performance-ahb")
        sdk_compile_definitions(-DFIXTURE_HPM_AHB)
    endif()
    sdk_app_src(${shared}/performance.c ${shared}/rtt.c)
elseif(FIXTURE_IMAGE STREQUAL "uart")
    sdk_compile_options(-O2)
    sdk_app_src(${shared}/uart.c)
else()
    message(FATAL_ERROR "Unknown HPM6800EVK fixture: ${FIXTURE_IMAGE}")
endif()
