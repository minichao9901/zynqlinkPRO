/*
 * Copyright (c) 2013-2021 ARM Limited. All rights reserved.
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Licensed under the Apache License, Version 2.0 (the License); you may
 * not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an AS IS BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * ----------------------------------------------------------------------
 *
 * $Date:        16. June 2021
 * $Revision:    V2.1.0
 *
 * Project:      CMSIS-DAP Configuration
 * Title:        DAP_config.h CMSIS-DAP Configuration File (Template)
 *
 *---------------------------------------------------------------------------*/

#ifndef __DAP_CONFIG_H__
#define __DAP_CONFIG_H__


//**************************************************************************************************
/**
\defgroup DAP_Config_Debug_gr CMSIS-DAP Debug Unit Information
\ingroup DAP_ConfigIO_gr
@{
Provides definitions about the hardware and configuration of the Debug Unit.

This information includes:
 - Definition of Cortex-M processor parameters used in CMSIS-DAP Debug Unit.
 - Debug Unit Identification strings (Vendor, Product, Serial Number).
 - Debug Unit communication packet size.
 - Debug Access Port supported modes and settings (JTAG/SWD and SWO).
 - Optional information about a connected Target Device (for Evaluation Boards).
*/

#include "stdint.h"      
#include "xil_io.h"                       

#ifndef   __STATIC_INLINE
#define __STATIC_INLINE                        static inline
#endif
#ifndef   __STATIC_FORCEINLINE                 
#define __STATIC_FORCEINLINE                   __attribute__((always_inline)) static inline
#endif
#ifndef __WEAK
#define __WEAK __attribute__((weak))
#endif

/// Processor Clock of the Cortex-M MCU used in the Debug Unit.
/// This value is used to calculate the SWD/JTAG clock speed.
#define CPU_CLOCK               667000000U      ///< Specifies the CPU Clock in Hz.

/// Number of processor cycles for I/O Port write operations.
/// This value is used to calculate the SWD/JTAG clock speed that is generated with I/O
/// Port write operations in the Debug Unit by a Cortex-M MCU. Most Cortex-M processors
/// require 2 processor cycles for a I/O Port Write operation.  If the Debug Unit uses
/// a Cortex-M0+ processor with high-speed peripheral I/O only 1 processor cycle might be
/// required.
#define IO_PORT_WRITE_CYCLES    2U              ///< I/O Cycles: 2=default, 1=Cortex-M0+ fast I/0.

/// Indicate that Serial Wire Debug (SWD) communication mode is available at the Debug Access Port.
/// This information is returned by the command \ref DAP_Info as part of <b>Capabilities</b>.
#define DAP_SWD                 1               ///< SWD Mode:  1 = available, 0 = not available.

/// Indicate that JTAG communication mode is available at the Debug Port.
/// This information is returned by the command \ref DAP_Info as part of <b>Capabilities</b>.
#define DAP_JTAG                0               ///< JTAG Mode: 1 = available, 0 = not available.

/// Configure maximum number of JTAG devices on the scan chain connected to the Debug Access Port.
/// This setting impacts the RAM requirements of the Debug Unit. Valid range is 1 .. 255.
#define DAP_JTAG_DEV_CNT        8U              ///< Maximum number of JTAG devices on scan chain.

/// Default communication mode on the Debug Access Port.
/// Used for the command \ref DAP_Connect when Port Default mode is selected.
#define DAP_DEFAULT_PORT        1U              ///< Default JTAG/SWJ Port Mode: 1 = SWD, 2 = JTAG.

/// Default communication speed on the Debug Access Port for SWD and JTAG mode.
/// Used to initialize the default SWD/JTAG clock frequency.
/// The command \ref DAP_SWJ_Clock can be used to overwrite this default setting.
#define DAP_DEFAULT_SWJ_CLOCK   10000000U        ///< Default SWD/JTAG clock frequency in Hz.

/// Maximum Package Size for Command and Response data.
/// This configuration settings is used to optimize the communication performance with the
/// debugger and depends on the USB peripheral. Typical vales are 64 for Full-speed USB HID or WinUSB,
/// 1024 for High-speed USB HID and 512 for High-speed USB WinUSB.
/* 4096 with OpenOCD master: master uses DAP_TransferBlock (16-bit count) and
 * asynchronous bulk transfers, so the v0.12 8-bit count limit does not apply. */
#define DAP_PACKET_SIZE         4096U            ///< Specifies Packet Size in bytes.

/// Maximum Package Buffers for Command and Response data.
/// This configuration settings is used to optimize the communication performance with the
/// debugger and depends on the USB peripheral. For devices with limited RAM or USB buffer the
/// setting can be reduced (valid range is 1 .. 255).
#define DAP_PACKET_COUNT        16U              ///< Specifies number of packets buffered.

/// Indicate that UART Serial Wire Output (SWO) trace is available.
/// This information is returned by the command \ref DAP_Info as part of <b>Capabilities</b>.
#define SWO_UART                0               ///< SWO UART:  1 = available, 0 = not available.

/// USART Driver instance number for the UART SWO.
#define SWO_UART_DRIVER         0               ///< USART Driver instance number (Driver_USART#).

/// Maximum SWO UART Baudrate.
#define SWO_UART_MAX_BAUDRATE   10000000U       ///< SWO UART Maximum Baudrate in Hz.

/// Indicate that Manchester Serial Wire Output (SWO) trace is available.
/// This information is returned by the command \ref DAP_Info as part of <b>Capabilities</b>.
#define SWO_MANCHESTER          0               ///< SWO Manchester:  1 = available, 0 = not available.

/// SWO Trace Buffer Size.
#define SWO_BUFFER_SIZE         4096U           ///< SWO Trace Buffer Size in bytes (must be 2^n).

/// SWO Streaming Trace.
#define SWO_STREAM              0               ///< SWO Streaming Trace: 1 = available, 0 = not available.

/// Clock frequency of the Test Domain Timer. Timer value is returned with \ref TIMESTAMP_GET.
#define TIMESTAMP_CLOCK         100000000U      ///< Timestamp clock in Hz (0 = timestamps not supported).

/// Indicate that UART Communication Port is available.
/// This information is returned by the command \ref DAP_Info as part of <b>Capabilities</b>.
#define DAP_UART                0               ///< DAP UART:  1 = available, 0 = not available.

/// USART Driver instance number for the UART Communication Port.
#define DAP_UART_DRIVER         0               ///< USART Driver instance number (Driver_USART#).

/// UART Receive Buffer Size.
#define DAP_UART_RX_BUFFER_SIZE 1024U           ///< Uart Receive Buffer Size in bytes (must be 2^n).

/// UART Transmit Buffer Size.
#define DAP_UART_TX_BUFFER_SIZE 1024U           ///< Uart Transmit Buffer Size in bytes (must be 2^n).

/// Indicate that UART Communication via USB COM Port is available.
/// This information is returned by the command \ref DAP_Info as part of <b>Capabilities</b>.
#define DAP_UART_USB_COM_PORT   1               ///< USB COM Port:  1 = available, 0 = not available.

/// Debug Unit is connected to fixed Target Device.
/// The Debug Unit may be part of an evaluation board and always connected to a fixed
/// known device. In this case a Device Vendor, Device Name, Board Vendor and Board Name strings
/// are stored and may be used by the debugger or IDE to configure device parameters.
#define TARGET_FIXED            0               ///< Target: 1 = known, 0 = unknown;

#define TARGET_DEVICE_VENDOR    "Arm"           ///< String indicating the Silicon Vendor
#define TARGET_DEVICE_NAME      "Cortex-M"      ///< String indicating the Target Device
#define TARGET_BOARD_VENDOR     "Arm"           ///< String indicating the Board Vendor
#define TARGET_BOARD_NAME       "Arm board"     ///< String indicating the Board Name

#if TARGET_FIXED != 0
#include <string.h>
static const char TargetDeviceVendor [] = TARGET_DEVICE_VENDOR;
static const char TargetDeviceName   [] = TARGET_DEVICE_NAME;
static const char TargetBoardVendor  [] = TARGET_BOARD_VENDOR;
static const char TargetBoardName    [] = TARGET_BOARD_NAME;
#endif

/** Get Vendor Name string.
\param str Pointer to buffer to store the string (max 60 characters).
\return String length (including terminating NULL character) or 0 (no string).
*/
__STATIC_INLINE uint8_t DAP_GetVendorString (char *str) {
  (void)str;
  return (0U);
}

/** Get Product Name string.
\param str Pointer to buffer to store the string (max 60 characters).
\return String length (including terminating NULL character) or 0 (no string).
*/
__STATIC_INLINE uint8_t DAP_GetProductString (char *str) {
  (void)str;
  return (0U);
}

/** Get Serial Number string.
\param str Pointer to buffer to store the string (max 60 characters).
\return String length (including terminating NULL character) or 0 (no string).
*/
__STATIC_INLINE uint8_t DAP_GetSerNumString (char *str) {
  (void)str;
  return (0U);
}

/** Get Target Device Vendor string.
\param str Pointer to buffer to store the string (max 60 characters).
\return String length (including terminating NULL character) or 0 (no string).
*/
__STATIC_INLINE uint8_t DAP_GetTargetDeviceVendorString (char *str) {
#if TARGET_FIXED != 0
  uint8_t len;

  strcpy(str, TargetDeviceVendor);
  len = (uint8_t)(strlen(TargetDeviceVendor) + 1U);
  return (len);
#else
  (void)str;
  return (0U);
#endif
}

/** Get Target Device Name string.
\param str Pointer to buffer to store the string (max 60 characters).
\return String length (including terminating NULL character) or 0 (no string).
*/
__STATIC_INLINE uint8_t DAP_GetTargetDeviceNameString (char *str) {
#if TARGET_FIXED != 0
  uint8_t len;

  strcpy(str, TargetDeviceName);
  len = (uint8_t)(strlen(TargetDeviceName) + 1U);
  return (len);
#else
  (void)str;
  return (0U);
#endif
}

/** Get Target Board Vendor string.
\param str Pointer to buffer to store the string (max 60 characters).
\return String length (including terminating NULL character) or 0 (no string).
*/
__STATIC_INLINE uint8_t DAP_GetTargetBoardVendorString (char *str) {
#if TARGET_FIXED != 0
  uint8_t len;

  strcpy(str, TargetBoardVendor);
  len = (uint8_t)(strlen(TargetBoardVendor) + 1U);
  return (len);
#else
  (void)str;
  return (0U);
#endif
}

/** Get Target Board Name string.
\param str Pointer to buffer to store the string (max 60 characters).
\return String length (including terminating NULL character) or 0 (no string).
*/
__STATIC_INLINE uint8_t DAP_GetTargetBoardNameString (char *str) {
#if TARGET_FIXED != 0
  uint8_t len;

  strcpy(str, TargetBoardName);
  len = (uint8_t)(strlen(TargetBoardName) + 1U);
  return (len);
#else
  (void)str;
  return (0U);
#endif
}

/** Get Product Firmware Version string.
\param str Pointer to buffer to store the string (max 60 characters).
\return String length (including terminating NULL character) or 0 (no string).
*/
__STATIC_INLINE uint8_t DAP_GetProductFirmwareVersionString (char *str) {
  (void)str;
  return (0U);
}

///@}


//**************************************************************************************************
/**
\defgroup DAP_Config_PortIO_gr CMSIS-DAP Hardware I/O Pin Access
\ingroup DAP_ConfigIO_gr
@{

Standard I/O Pins of the CMSIS-DAP Hardware Debug Port support standard JTAG mode
and Serial Wire Debug (SWD) mode. In SWD mode only 2 pins are required to implement the debug
interface of a device. The following I/O Pins are provided:

JTAG I/O Pin                 | SWD I/O Pin          | CMSIS-DAP Hardware pin mode
---------------------------- | -------------------- | ---------------------------------------------
TCK: Test Clock              | SWCLK: Clock         | Output Push/Pull
TMS: Test Mode Select        | SWDIO: Data I/O      | Output Push/Pull; Input (for receiving data)
TDI: Test Data Input         |                      | Output Push/Pull
TDO: Test Data Output        |                      | Input
nTRST: Test Reset (optional) |                      | Output Open Drain with pull-up resistor
nRESET: Device Reset         | nRESET: Device Reset | Output Open Drain with pull-up resistor


DAP Hardware I/O Pin Access Functions
-------------------------------------
The various I/O Pins are accessed by functions that implement the Read, Write, Set, or Clear to
these I/O Pins.

For the SWDIO I/O Pin there are additional functions that are called in SWD I/O mode only.
This functions are provided to achieve faster I/O that is possible with some advanced GPIO
peripherals that can independently write/read a single I/O pin without affecting any other pins
of the same I/O port. The following SWDIO I/O Pin functions are provided:
 - \ref PIN_SWDIO_OUT_ENABLE to enable the output mode from the DAP hardware.
 - \ref PIN_SWDIO_OUT_DISABLE to enable the input mode to the DAP hardware.
 - \ref PIN_SWDIO_IN to read from the SWDIO I/O pin with utmost possible speed.
 - \ref PIN_SWDIO_OUT to write to the SWDIO I/O pin with utmost possible speed.
*/


// Configure DAP I/O pins ------------------------------

/** Setup JTAG I/O pins: TCK, TMS, TDI, TDO, nTRST, and nRESET.
Configures the DAP Hardware I/O pins for JTAG mode:
 - TCK, TMS, TDI, nTRST, nRESET to output mode and set to high level.
 - TDO to input mode.
*/

#define GPIO_BASE      0x40000000U
#define GPIO_DATA      GPIO_BASE
#define GPIO_TRI       (GPIO_BASE + 0x4U)


// 假设基地址通过设备树或参数传入
#define SWD_BASE_ADDR       0x40010000  // 根据实际 Vivado 配置调整

#define SWD_CTRL            (SWD_BASE_ADDR + 0x00)
#define SWD_STATUS          (SWD_BASE_ADDR + 0x04)
#define SWD_CFG             (SWD_BASE_ADDR + 0x08)
#define SWD_SWJ_COUNT       (SWD_BASE_ADDR + 0x0C)
#define SWD_SWJ_DATA0       (SWD_BASE_ADDR + 0x10) 
#define SWD_SWJ_DATA1       (SWD_BASE_ADDR + 0x14)  // 复用 XFER_WDATA
#define SWD_SWJ_DATA2       (SWD_BASE_ADDR + 0x18)  // 复用 XFER_RDATA
#define SWD_SWJ_DATA3       (SWD_BASE_ADDR + 0x1C)
#define SWD_SWJ_DATA4       (SWD_BASE_ADDR + 0x20)
#define SWD_SWJ_DATA5       (SWD_BASE_ADDR + 0x24)
#define SWD_SWJ_DATA6       (SWD_BASE_ADDR + 0x28)
#define SWD_SWJ_DATA7       (SWD_BASE_ADDR + 0x2C)
#define SWD_BATCH_CTRL      (SWD_BASE_ADDR + 0x30)
#define SWD_BATCH_STATUS    (SWD_BASE_ADDR + 0x34)
#define SWD_BATCH_ADDR      (SWD_BASE_ADDR + 0x38)
#define SWD_BATCH_DATA      (SWD_BASE_ADDR + 0x3C)
#define SWD_PACKET_CTRL     (SWD_BASE_ADDR + 0x40)
#define SWD_PACKET_LEN      (SWD_BASE_ADDR + 0x44)
#define SWD_PACKET_STATUS   (SWD_BASE_ADDR + 0x48)
#define SWD_FEATURES        (SWD_BASE_ADDR + 0x4C)
#define SWD_ENGINE_RESET    (SWD_BASE_ADDR + 0x50)

/* Low-rate bring-up counters.  Defined in dap_main.c and deliberately kept
 * separate from the USB DMA buffers so JTAG/UART inspection is harmless. */
extern volatile uint32_t dap_dbg_rtl_writes;
extern volatile uint32_t dap_dbg_rtl_reads;
extern volatile uint32_t dap_dbg_last_write_addr;
extern volatile uint32_t dap_dbg_last_write_value;
extern volatile uint32_t dap_dbg_last_read_addr;
extern volatile uint32_t dap_dbg_last_read_value;

__STATIC_FORCEINLINE void swd_write32(uint32_t addr, uint32_t value) {
  *(volatile uint32_t *)addr = value;
#if DAP_MMIO_DIAGNOSTICS
  dap_dbg_rtl_writes++;
  dap_dbg_last_write_addr = addr;
  dap_dbg_last_write_value = value;
#endif
}

__STATIC_FORCEINLINE uint32_t swd_read32(uint32_t addr) {
  uint32_t value = *(volatile uint32_t *)addr;
#if DAP_MMIO_DIAGNOSTICS
  dap_dbg_rtl_reads++;
  dap_dbg_last_read_addr = addr;
  dap_dbg_last_read_value = value;
#endif
  return value;
}

// 等待操作完成
__STATIC_FORCEINLINE void swd_wait_idle(void) {
  while (swd_read32(SWD_STATUS) & 0x01);
}




#include "xil_io.h"
#include "xil_misc_psreset_api.h"

#define SLCR_LOCK_ADDR        0xF8000004U
#define SLCR_FPGA0_CLK_CTRL   0xF8000170U

#define FCLK_SRC_IO_PLL       0U
#define PS_REF_HZ             33333333U
#define IO_PLL_HZ             (PS_REF_HZ * ((Xil_In32(0xF8000108U) >> 12) & 0x7FU))

static int ps_set_fclk0_hz(u32 target_hz) {
  u32 best_div0 = 0, best_div1 = 0;
  u32 best_hz = 0;
  u32 best_err = 0xFFFFFFFFU;
  u32 div0, div1;
  u32 pll_hz = IO_PLL_HZ;

  if (target_hz == 0) {
    return -1;
  }

  for (div0 = 1; div0 <= 63; div0++) {
    for (div1 = 1; div1 <= 63; div1++) {
      u32 hz = pll_hz / div0 / div1;
      u32 err = (hz > target_hz) ? (hz - target_hz) : (target_hz - hz);

      // DAP_SWJ_Clock specifies a maximum: never round above it.
      if (hz <= target_hz && err < best_err) {
        best_err = err;
        best_hz = hz;
        best_div0 = div0;
        best_div1 = div1;
        if (err <= 1U) {
          goto found;
        }
      }
    }
  }

found:
  Xil_Out32(XSLCR_UNLOCK_ADDR, XSLCR_UNLOCK_CODE);

  Xil_Out32(SLCR_FPGA0_CLK_CTRL,
            (1U << 0) |
            ((FCLK_SRC_IO_PLL & 0x3U) << 4) |
            ((best_div0 & 0x3FU) << 8) |
            ((best_div1 & 0x3FU) << 20));

  Xil_Out32(SLCR_LOCK_ADDR, 0x767BU);

  return (int)best_hz;
}





/*
P0: SWCLK/TCK  - Output, idle HIGH
P1: SWDIO/TMS  - Bidirectional
P2: nRESET     - Output, active LOW
*/

__STATIC_INLINE void PORT_JTAG_SETUP (void) {
  ;
}

/** Setup SWD I/O pins: SWCLK, SWDIO, and nRESET.
Configures the DAP Hardware I/O pins for Serial Wire Debug (SWD) mode:
 - SWCLK, SWDIO, nRESET to output mode and set to default high level.
 - TDI, nTRST to HighZ mode (pins are unused in SWD mode).
*/
__STATIC_INLINE void PORT_SWD_SETUP (void) {
  Xil_Out32(GPIO_TRI, 0x0U);
  Xil_Out32(GPIO_DATA, 0x5U);



  // ADDR_CFG (0x08) bit definition (match current RTL):
  //   [3:0]   turnaround_fixed      SWD turnaround cycles (HW fixed readback=1)
  //   [7:4]   cfg_idle_cycles       SWD idle cycles after transfer
  //   [8]     cfg_data_phase        Enable WAIT/FAULT data phase handling
  //   [12:9]  cfg_clock_delay       SWJ sequence half-cycle delay
  //   [16:13] cfg_delay_fast        Transfer half-cycle delay
  //   [17]    cfg_sample_rise      Input capture phase (Q1/Q2)
  //   [18]    cfg_rx_boundary      1=short-return ACK/data boundary, 0=legacy
  //   [24:23] cfg_turn_extra       Extra low half-cycle steps before ACK
  //   [27:25] cfg_ack_delay        0=legacy; 1..7=ACK hold/capture schedule
    //   [31:29] Reserved
  //
  // Current setup:
  // turnaround=1, idle=1, data_phase=0, clock_delay=5, delay_fast=0
  swd_write32(SWD_CFG,
              (1U << 0)  |  // turnaround_fixed
              (1U << 4)  |  // idle_cycles
              (0U << 8)  |  // data_phase
              (5U << 9)  |  // clock_delay
              (0U << 13) |  // delay_fast
              (0U << 23) |  // turn_extra
              (0U << 25) |  // ack_delay
              (0U << 17));  // late FCLK sample at the default 50 MHz

  ps_set_fclk0_hz(100000000U);  // 100 MHz
}

/** Disable JTAG/SWD I/O Pins.
Disables the DAP Hardware I/O pins which configures:
 - TCK/SWCLK, TMS/SWDIO, TDI, TDO, nTRST, nRESET to High-Z mode.
*/
__STATIC_INLINE void PORT_OFF (void) {
  Xil_Out32(GPIO_DATA, 0x5U);
  Xil_Out32(GPIO_TRI, 0x7U);
}


// SWCLK/TCK I/O pin -------------------------------------

/** SWCLK/TCK I/O pin: Get Input.
\return Current status of the SWCLK/TCK DAP hardware I/O pin.
*/
__STATIC_FORCEINLINE uint32_t PIN_SWCLK_TCK_IN  (void) {
  return (Xil_In32(GPIO_DATA) & 0x1U);
}

/** SWCLK/TCK I/O pin: Set Output to High.
Set the SWCLK/TCK DAP hardware I/O pin to high level.
*/
__STATIC_FORCEINLINE void     PIN_SWCLK_TCK_SET (void) {
  Xil_Out32(GPIO_DATA, Xil_In32(GPIO_DATA) | 0x1U);
}

/** SWCLK/TCK I/O pin: Set Output to Low.
Set the SWCLK/TCK DAP hardware I/O pin to low level.
*/
__STATIC_FORCEINLINE void     PIN_SWCLK_TCK_CLR (void) {
  Xil_Out32(GPIO_DATA, Xil_In32(GPIO_DATA) & ~0x1U);
}


// SWDIO/TMS Pin I/O --------------------------------------

/** SWDIO/TMS I/O pin: Get Input.
\return Current status of the SWDIO/TMS DAP hardware I/O pin.
*/
__STATIC_FORCEINLINE uint32_t PIN_SWDIO_TMS_IN  (void) {
  return (Xil_In32(GPIO_DATA) & 0x2U) >> 1U;
}

/** SWDIO/TMS I/O pin: Set Output to High.
Set the SWDIO/TMS DAP hardware I/O pin to high level.
*/
__STATIC_FORCEINLINE void     PIN_SWDIO_TMS_SET (void) {
  Xil_Out32(GPIO_DATA, Xil_In32(GPIO_DATA) | 0x2U);
}

/** SWDIO/TMS I/O pin: Set Output to Low.
Set the SWDIO/TMS DAP hardware I/O pin to low level.
*/
__STATIC_FORCEINLINE void     PIN_SWDIO_TMS_CLR (void) {
  Xil_Out32(GPIO_DATA, Xil_In32(GPIO_DATA) & ~0x2U);
}

/** SWDIO I/O pin: Get Input (used in SWD mode only).
\return Current status of the SWDIO DAP hardware I/O pin.
*/
__STATIC_FORCEINLINE uint32_t PIN_SWDIO_IN      (void) {
  return (Xil_In32(GPIO_DATA) & 0x2U) >> 1U;
}

/** SWDIO I/O pin: Set Output (used in SWD mode only).
\param bit Output value for the SWDIO DAP hardware I/O pin.
*/
__STATIC_FORCEINLINE void     PIN_SWDIO_OUT     (uint32_t bit) {
    if(bit & 0x01)
    {
      Xil_Out32(GPIO_DATA, Xil_In32(GPIO_DATA) | 0x2U);
    }
    else
    {
      Xil_Out32(GPIO_DATA, Xil_In32(GPIO_DATA) & ~0x2U);
    }
}

/** SWDIO I/O pin: Switch to Output mode (used in SWD mode only).
Configure the SWDIO DAP hardware I/O pin to output mode. This function is
called prior \ref PIN_SWDIO_OUT function calls.
*/
__STATIC_FORCEINLINE void     PIN_SWDIO_OUT_ENABLE  (void) {
  Xil_Out32(GPIO_TRI, Xil_In32(GPIO_TRI) & ~0x2U);
}

/** SWDIO I/O pin: Switch to Input mode (used in SWD mode only).
Configure the SWDIO DAP hardware I/O pin to input mode. This function is
called prior \ref PIN_SWDIO_IN function calls.
*/
__STATIC_FORCEINLINE void     PIN_SWDIO_OUT_DISABLE (void) {
  Xil_Out32(GPIO_TRI, Xil_In32(GPIO_TRI) | 0x2U);
}


// TDI Pin I/O ---------------------------------------------

/** TDI I/O pin: Get Input.
\return Current status of the TDI DAP hardware I/O pin.
*/
__STATIC_FORCEINLINE uint32_t PIN_TDI_IN  (void) {
  return (0U);
}

/** TDI I/O pin: Set Output.
\param bit Output value for the TDI DAP hardware I/O pin.
*/
__STATIC_FORCEINLINE void     PIN_TDI_OUT (uint32_t bit) {
  ;
}


// TDO Pin I/O ---------------------------------------------

/** TDO I/O pin: Get Input.
\return Current status of the TDO DAP hardware I/O pin.
*/
__STATIC_FORCEINLINE uint32_t PIN_TDO_IN  (void) {
  return (0U);
}


// nTRST Pin I/O -------------------------------------------

/** nTRST I/O pin: Get Input.
\return Current status of the nTRST DAP hardware I/O pin.
*/
__STATIC_FORCEINLINE uint32_t PIN_nTRST_IN   (void) {
  return (0U);
}

/** nTRST I/O pin: Set Output.
\param bit JTAG TRST Test Reset pin status:
           - 0: issue a JTAG TRST Test Reset.
           - 1: release JTAG TRST Test Reset.
*/
__STATIC_FORCEINLINE void     PIN_nTRST_OUT  (uint32_t bit) {
  ;
}

// nRESET Pin I/O------------------------------------------

/** nRESET I/O pin: Get Input.
\return Current status of the nRESET DAP hardware I/O pin.
*/
__STATIC_FORCEINLINE uint32_t PIN_nRESET_IN  (void) {
  return (Xil_In32(GPIO_DATA) & 0x4U) >> 2U;  
}

/** nRESET I/O pin: Set Output.
\param bit target device hardware reset pin status:
           - 0: issue a device hardware reset.
           - 1: release device hardware reset.
*/
// extern void swd_set_target_reset(uint8_t asserted);
__STATIC_FORCEINLINE void     PIN_nRESET_OUT (uint32_t bit) {
  if(bit & 0x01)
  {
    Xil_Out32(GPIO_DATA, Xil_In32(GPIO_DATA) | 0x4U);
  }
  else
  {
    Xil_Out32(GPIO_DATA, Xil_In32(GPIO_DATA) & ~0x4U);
    // swd_set_target_reset(0);
  }
}

///@}


//**************************************************************************************************
/**
\defgroup DAP_Config_LEDs_gr CMSIS-DAP Hardware Status LEDs
\ingroup DAP_ConfigIO_gr
@{

CMSIS-DAP Hardware may provide LEDs that indicate the status of the CMSIS-DAP Debug Unit.

It is recommended to provide the following LEDs for status indication:
 - Connect LED: is active when the DAP hardware is connected to a debugger.
 - Running LED: is active when the debugger has put the target device into running state.
*/

/** Debug Unit: Set status of Connected LED.
\param bit status of the Connect LED.
           - 1: Connect LED ON: debugger is connected to CMSIS-DAP Debug Unit.
           - 0: Connect LED OFF: debugger is not connected to CMSIS-DAP Debug Unit.
*/
__STATIC_INLINE void LED_CONNECTED_OUT (uint32_t bit) {}

/** Debug Unit: Set status Target Running LED.
\param bit status of the Target Running LED.
           - 1: Target Running LED ON: program execution in target started.
           - 0: Target Running LED OFF: program execution in target stopped.
*/
__STATIC_INLINE void LED_RUNNING_OUT (uint32_t bit) {}

///@}


//**************************************************************************************************
/**
\defgroup DAP_Config_Timestamp_gr CMSIS-DAP Timestamp
\ingroup DAP_ConfigIO_gr
@{
Access function for Test Domain Timer.

The value of the Test Domain Timer in the Debug Unit is returned by the function \ref TIMESTAMP_GET. By
default, the DWT timer is used.  The frequency of this timer is configured with \ref TIMESTAMP_CLOCK.

*/

/** Get timestamp of Test Domain Timer.
\return Current timestamp value.
*/
__STATIC_INLINE uint32_t TIMESTAMP_GET (void) {
  return 0U;  // TODO: Implement using ZYNQ timer if needed
}

///@}


//**************************************************************************************************
/**
\defgroup DAP_Config_Initialization_gr CMSIS-DAP Initialization
\ingroup DAP_ConfigIO_gr
@{

CMSIS-DAP Hardware I/O and LED Pins are initialized with the function \ref DAP_SETUP.
*/

/** Setup of the Debug Unit I/O pins and LEDs (called when Debug Unit is initialized).
This function performs the initialization of the CMSIS-DAP Hardware I/O Pins and the
Status LEDs. In detail the operation of Hardware I/O and LED pins are enabled and set:
 - I/O clock system enabled.
 - all I/O pins: input buffer enabled, output pins are set to HighZ mode.
 - for nTRST, nRESET a weak pull-up (if available) is enabled.
 - LED output pins are enabled and LEDs are turned off.
*/
__STATIC_INLINE void DAP_SETUP (void) {
  Xil_Out32(GPIO_DATA, 0x5U);
  Xil_Out32(GPIO_TRI, 0x7U);
}

/** Reset Target Device with custom specific I/O pin or command sequence.
This function allows the optional implementation of a device specific reset sequence.
It is called when the command \ref DAP_ResetTarget and is for example required
when a device needs a time-critical unlock sequence that enables the debug port.
\return 0 = no device specific reset sequence is implemented.\n
        1 = a device specific reset sequence is implemented.
*/
__STATIC_INLINE uint8_t RESET_TARGET (void) {
  return (0U);             // change to '1' when a device reset sequence is implemented
}

///@}


#endif /* __DAP_CONFIG_H__ */

