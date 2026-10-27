/*
 * Copyright (c) 2013-2022 ARM Limited. All rights reserved.
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
 * $Date:        26. April 2022
 * $Revision:    V2.1.1
 *
 * Project:      CMSIS-DAP Source
 * Title:        DAP.c CMSIS-DAP Commands
 *
 *---------------------------------------------------------------------------*/

#include <string.h>
#include "DAP_config.h"
#include "DAP.h"
#include "xil_printf.h"
#include "swd_dma.h"
#include "dap_metrics.h"
#include "xtime_l.h"

#define DAP_HOT_CODE __attribute__((section(".ocm_text")))
#define DAP_HOT_BSS  __attribute__((section(".ocm_bss"), aligned(32)))


#if (DAP_PACKET_SIZE < 64U)
#error "Minimum Packet Size is 64!"
#endif
#if (DAP_PACKET_SIZE > 32768U)
#error "Maximum Packet Size is 32768!"
#endif
#if (DAP_PACKET_COUNT < 1U)
#error "Minimum Packet Count is 1!"
#endif
#if (DAP_PACKET_COUNT > 255U)
#error "Maximum Packet Count is 255!"
#endif


// Clock Macros
#define MAX_SWJ_CLOCK(delay_cycles) \
  ((CPU_CLOCK/2U) / (IO_PORT_WRITE_CYCLES + delay_cycles))

#ifndef DAP_FORCE_FAST_CLOCK
#define DAP_FORCE_FAST_CLOCK 0U
#endif


DAP_HOT_BSS DAP_Data_t      DAP_Data;           // DAP Data
DAP_HOT_BSS volatile uint8_t DAP_TransferAbort; // Transfer Abort Flag


static const char DAP_FW_Ver [] = DAP_FW_VER;


// Common clock delay calculation routine
//   clock:    requested SWJ frequency in Hertz
static void Set_Clock_Delay(uint32_t clock) {
  uint32_t delay;

#if (DAP_FORCE_FAST_CLOCK != 0U)
  (void)clock;
  DAP_Data.fast_clock  = 1U;
  DAP_Data.clock_delay = 1U;
  return;
#endif

  if (clock >= MAX_SWJ_CLOCK(DELAY_FAST_CYCLES)) {
    DAP_Data.fast_clock  = 1U;
    DAP_Data.clock_delay = 1U;
  } else {
    DAP_Data.fast_clock  = 0U;

    delay = ((CPU_CLOCK/2U) + (clock - 1U)) / clock;
    if (delay > IO_PORT_WRITE_CYCLES) {
      delay -= IO_PORT_WRITE_CYCLES;
      delay  = (delay + (DELAY_SLOW_CYCLES - 1U)) / DELAY_SLOW_CYCLES;
    } else {
      delay  = 1U;
    }

    DAP_Data.clock_delay = delay;
  }
}


// Get DAP Information
//   id:      info identifier
//   info:    pointer to info data
//   return:  number of bytes in info data
static uint8_t DAP_Info(uint8_t id, uint8_t *info) {
  uint8_t length = 0U;

  switch (id) {
    case DAP_ID_VENDOR:
      length = DAP_GetVendorString((char *)info);
      break;
    case DAP_ID_PRODUCT:
      length = DAP_GetProductString((char *)info);
      break;
    case DAP_ID_SER_NUM:
      length = DAP_GetSerNumString((char *)info);
      break;
    case DAP_ID_DAP_FW_VER:
      length = (uint8_t)sizeof(DAP_FW_Ver);
      memcpy(info, DAP_FW_Ver, length);
      break;
    case DAP_ID_DEVICE_VENDOR:
      length = DAP_GetTargetDeviceVendorString((char *)info);
      break;
    case DAP_ID_DEVICE_NAME:
      length = DAP_GetTargetDeviceNameString((char *)info);
      break;
    case DAP_ID_BOARD_VENDOR:
      length = DAP_GetTargetBoardVendorString((char *)info);
      break;
    case DAP_ID_BOARD_NAME:
      length = DAP_GetTargetBoardNameString((char *)info);
      break;
    case DAP_ID_PRODUCT_FW_VER:
      length = DAP_GetProductFirmwareVersionString((char *)info);
      break;
    case DAP_ID_CAPABILITIES:
      info[0] = ((DAP_SWD  != 0)         ? (1U << 0) : 0U) |
                ((DAP_JTAG != 0)         ? (1U << 1) : 0U) |
                ((SWO_UART != 0)         ? (1U << 2) : 0U) |
                ((SWO_MANCHESTER != 0)   ? (1U << 3) : 0U) |
                /* Atomic Commands  */     (1U << 4)       |
                ((TIMESTAMP_CLOCK != 0U) ? (1U << 5) : 0U) |
                ((SWO_STREAM != 0U)      ? (1U << 6) : 0U) |
                ((DAP_UART != 0U)        ? (1U << 7) : 0U);

      info[1] = ((DAP_UART_USB_COM_PORT != 0) ? (1U << 0) : 0U);
      length = 2U;
      break;
    case DAP_ID_TIMESTAMP_CLOCK:
#if (TIMESTAMP_CLOCK != 0U)
      info[0] = (uint8_t)(TIMESTAMP_CLOCK >>  0);
      info[1] = (uint8_t)(TIMESTAMP_CLOCK >>  8);
      info[2] = (uint8_t)(TIMESTAMP_CLOCK >> 16);
      info[3] = (uint8_t)(TIMESTAMP_CLOCK >> 24);
      length = 4U;
#endif
      break;
    case DAP_ID_UART_RX_BUFFER_SIZE:
#if (DAP_UART != 0)
      info[0] = (uint8_t)(DAP_UART_RX_BUFFER_SIZE >>  0);
      info[1] = (uint8_t)(DAP_UART_RX_BUFFER_SIZE >>  8);
      info[2] = (uint8_t)(DAP_UART_RX_BUFFER_SIZE >> 16);
      info[3] = (uint8_t)(DAP_UART_RX_BUFFER_SIZE >> 24);
      length = 4U;
#endif
      break;
    case DAP_ID_UART_TX_BUFFER_SIZE:
#if (DAP_UART != 0)
      info[0] = (uint8_t)(DAP_UART_TX_BUFFER_SIZE >>  0);
      info[1] = (uint8_t)(DAP_UART_TX_BUFFER_SIZE >>  8);
      info[2] = (uint8_t)(DAP_UART_TX_BUFFER_SIZE >> 16);
      info[3] = (uint8_t)(DAP_UART_TX_BUFFER_SIZE >> 24);
      length = 4U;
#endif
      break;
    case DAP_ID_SWO_BUFFER_SIZE:
#if ((SWO_UART != 0) || (SWO_MANCHESTER != 0))
      info[0] = (uint8_t)(SWO_BUFFER_SIZE >>  0);
      info[1] = (uint8_t)(SWO_BUFFER_SIZE >>  8);
      info[2] = (uint8_t)(SWO_BUFFER_SIZE >> 16);
      info[3] = (uint8_t)(SWO_BUFFER_SIZE >> 24);
      length = 4U;
#endif
      break;
    case DAP_ID_PACKET_SIZE:
      info[0] = (uint8_t)(DAP_PACKET_SIZE >> 0);
      info[1] = (uint8_t)(DAP_PACKET_SIZE >> 8);
      length = 2U;
      break;
    case DAP_ID_PACKET_COUNT:
      info[0] = DAP_PACKET_COUNT;
      length = 1U;
      break;
    default:
      break;
  }

  return (length);
}


// Delay for specified time
//    delay:  delay time in ms
void Delayms(uint32_t delay) {
  delay *= ((CPU_CLOCK/1000U) + (DELAY_SLOW_CYCLES-1U)) / DELAY_SLOW_CYCLES;
  PIN_DELAY_SLOW(delay);
}


// Process Delay command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
static uint32_t DAP_Delay(const uint8_t *request, uint8_t *response) {
  uint32_t delay;

  delay  = (uint32_t)(*(request+0)) |
           (uint32_t)(*(request+1) << 8);
  delay *= ((CPU_CLOCK/1000000U) + (DELAY_SLOW_CYCLES-1U)) / DELAY_SLOW_CYCLES;

  PIN_DELAY_SLOW(delay);

  *response = DAP_OK;
  return ((2U << 16) | 1U);
}


// Process Host Status command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
static uint32_t DAP_HostStatus(const uint8_t *request, uint8_t *response) {

  switch (*request) {
    case DAP_DEBUGGER_CONNECTED:
      LED_CONNECTED_OUT((*(request+1) & 1U));
      break;
    case DAP_TARGET_RUNNING:
      LED_RUNNING_OUT((*(request+1) & 1U));
      break;
    default:
      *response = DAP_ERROR;
      return ((2U << 16) | 1U);
  }

  *response = DAP_OK;
  return ((2U << 16) | 1U);
}


// Process Connect command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
static uint32_t DAP_Connect(const uint8_t *request, uint8_t *response) {
  uint32_t port;

  if (*request == DAP_PORT_AUTODETECT) {
    port = DAP_DEFAULT_PORT;
  } else {
    port = *request;
  }

  switch (port) {
#if (DAP_SWD != 0)
    case DAP_PORT_SWD:
      DAP_Data.debug_port = DAP_PORT_SWD;
      PORT_SWD_SETUP();
      break;
#endif
#if (DAP_JTAG != 0)
    case DAP_PORT_JTAG:
      DAP_Data.debug_port = DAP_PORT_JTAG;
      PORT_JTAG_SETUP();
      break;
#endif
    default:
      port = DAP_PORT_DISABLED;
      break;
  }

  *response = (uint8_t)port;
  return ((1U << 16) | 1U);
}


// Process Disconnect command and prepare response
//   response: pointer to response data
//   return:   number of bytes in response
static uint32_t DAP_Disconnect(uint8_t *response) {

  DAP_Data.debug_port = DAP_PORT_DISABLED;
  PORT_OFF();

  *response = DAP_OK;
  return (1U);
}


// Process Reset Target command and prepare response
//   response: pointer to response data
//   return:   number of bytes in response
static uint32_t DAP_ResetTarget(uint8_t *response) {

  *(response+1) = RESET_TARGET();
  *(response+0) = DAP_OK;
  return (2U);
}


// Process SWJ Pins command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
static uint32_t DAP_SWJ_Pins(const uint8_t *request, uint8_t *response) {
#if ((DAP_SWD != 0) || (DAP_JTAG != 0))
  uint32_t value;
  uint32_t select;
  uint32_t wait;
  uint32_t timestamp;

  value  = (uint32_t) *(request+0);
  select = (uint32_t) *(request+1);
  wait   = (uint32_t)(*(request+2) <<  0) |
           (uint32_t)(*(request+3) <<  8) |
           (uint32_t)(*(request+4) << 16) |
           (uint32_t)(*(request+5) << 24);

  if ((select & (1U << DAP_SWJ_SWCLK_TCK)) != 0U) {
    if ((value & (1U << DAP_SWJ_SWCLK_TCK)) != 0U) {
      PIN_SWCLK_TCK_SET();
    } else {
      PIN_SWCLK_TCK_CLR();
    }
  }
  if ((select & (1U << DAP_SWJ_SWDIO_TMS)) != 0U) {
    if ((value & (1U << DAP_SWJ_SWDIO_TMS)) != 0U) {
      PIN_SWDIO_TMS_SET();
    } else {
      PIN_SWDIO_TMS_CLR();
    }
  }
  if ((select & (1U << DAP_SWJ_TDI)) != 0U) {
    PIN_TDI_OUT(value >> DAP_SWJ_TDI);
  }
  if ((select & (1U << DAP_SWJ_nTRST)) != 0U) {
    PIN_nTRST_OUT(value >> DAP_SWJ_nTRST);
  }
  if ((select & (1U << DAP_SWJ_nRESET)) != 0U){
    PIN_nRESET_OUT(value >> DAP_SWJ_nRESET);
  }

  if (wait != 0U) {
#if (TIMESTAMP_CLOCK != 0U)
    if (wait > 3000000U) {
      wait = 3000000U;
    }
#if (TIMESTAMP_CLOCK >= 1000000U)
    wait *= TIMESTAMP_CLOCK / 1000000U;
#else
    wait /= 1000000U / TIMESTAMP_CLOCK;
#endif
#else
    wait  = 1U;
#endif
    timestamp = TIMESTAMP_GET();
    do {
      if ((select & (1U << DAP_SWJ_SWCLK_TCK)) != 0U) {
        if ((value >> DAP_SWJ_SWCLK_TCK) ^ PIN_SWCLK_TCK_IN()) {
          continue;
        }
      }
      if ((select & (1U << DAP_SWJ_SWDIO_TMS)) != 0U) {
        if ((value >> DAP_SWJ_SWDIO_TMS) ^ PIN_SWDIO_TMS_IN()) {
          continue;
        }
      }
      if ((select & (1U << DAP_SWJ_TDI)) != 0U) {
        if ((value >> DAP_SWJ_TDI) ^ PIN_TDI_IN()) {
          continue;
        }
      }
      if ((select & (1U << DAP_SWJ_nTRST)) != 0U) {
        if ((value >> DAP_SWJ_nTRST) ^ PIN_nTRST_IN()) {
          continue;
        }
      }
      if ((select & (1U << DAP_SWJ_nRESET)) != 0U) {
        if ((value >> DAP_SWJ_nRESET) ^ PIN_nRESET_IN()) {
          continue;
        }
      }
      break;
    } while ((TIMESTAMP_GET() - timestamp) < wait);
  }

  value = (PIN_SWCLK_TCK_IN() << DAP_SWJ_SWCLK_TCK) |
          (PIN_SWDIO_TMS_IN() << DAP_SWJ_SWDIO_TMS) |
          (PIN_TDI_IN()       << DAP_SWJ_TDI)       |
          (PIN_TDO_IN()       << DAP_SWJ_TDO)       |
          (PIN_nTRST_IN()     << DAP_SWJ_nTRST)     |
          (PIN_nRESET_IN()    << DAP_SWJ_nRESET);

  *response = (uint8_t)value;
#else
  *response = 0U;
#endif

  return ((6U << 16) | 1U);
}


// Process SWJ Clock command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
#ifndef DAP_MAX_SWCLK_HZ
#define DAP_MAX_SWCLK_HZ 60000000U
#endif
static uint32_t DAP_SWJ_Clock(const uint8_t *request, uint8_t *response) {
#if ((DAP_SWD != 0) || (DAP_JTAG != 0))
  uint32_t clock;
  uint32_t delay;

  clock = (uint32_t)(*(request+0) <<  0) |
          (uint32_t)(*(request+1) <<  8) |
          (uint32_t)(*(request+2) << 16) |
          (uint32_t)(*(request+3) << 24);

  if (clock == 0U) {
    *response = DAP_ERROR;
    return ((4U << 16) | 1U);
  }

  /* Keep the core's two-beat waveform intact at all rates. Dividing FCLK
   * avoids changing half-cycle step counts. Frequencies above 50 MHz are
   * experimental until timing closure and board validation are complete. */
  if ((clock > DAP_MAX_SWCLK_HZ) || (clock < 250000U)) {
    *response = DAP_ERROR;
    return ((4U << 16) | 1U);
  }
  ps_set_fclk0_hz(clock * 2U);
  /* FCLK runs at 2x SWCLK, so the transfer half-cycle must be one FCLK
   * cycle (delay_fast=0).  The RTL reset value is slow; program it here. */
  swd_write32(SWD_CFG, (swd_read32(SWD_CFG) & ~((0xFU << 13) | (1U << 17))) |
              ((clock <= 35000000U) ? (1U << 17) : 0U));
  Set_Clock_Delay(clock);

  *response = DAP_OK;
#else
  *response = DAP_ERROR;
#endif

  return ((4U << 16) | 1U);
}


// Process SWJ Sequence command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
static uint32_t DAP_SWJ_Sequence(const uint8_t *request, uint8_t *response) {
  uint32_t count;

  count = *request++;
  if (count == 0U) {
    count = 256U;
  }

#if ((DAP_SWD != 0) || (DAP_JTAG != 0))
  SWJ_Sequence(count, request);
  *response = DAP_OK;
#else
  *response = DAP_ERROR;
#endif

  count = (count + 7U) >> 3;

  return (((count + 1U) << 16) | 1U);
}


// Process SWD Configure command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
static uint32_t DAP_SWD_Configure(const uint8_t *request, uint8_t *response) {
#if (DAP_SWD != 0)
  uint8_t value;

  value = *request;
  DAP_Data.swd_conf.turnaround = (value & 0x03U) + 1U;
  DAP_Data.swd_conf.data_phase = (value & 0x04U) ? 1U : 0U;

  *response = DAP_OK;
#else
  *response = DAP_ERROR;
#endif

  return ((1U << 16) | 1U);
}


// Process SWD Sequence command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
static uint32_t DAP_SWD_Sequence(const uint8_t *request, uint8_t *response) {
  uint32_t sequence_info;
  uint32_t sequence_count;
  uint32_t request_count;
  uint32_t response_count;
  uint32_t count;

#if (DAP_SWD != 0)
  *response++ = DAP_OK;
#else
  *response++ = DAP_ERROR;
#endif
  request_count  = 1U;
  response_count = 1U;

  sequence_count = *request++;
  while (sequence_count--) {
    sequence_info = *request++;
    count = sequence_info & SWD_SEQUENCE_CLK;
    if (count == 0U) {
      count = 64U;
    }
    count = (count + 7U) / 8U;
#if (DAP_SWD != 0)
    if ((sequence_info & SWD_SEQUENCE_DIN) != 0U) {
      PIN_SWDIO_OUT_DISABLE();
    } else {
      PIN_SWDIO_OUT_ENABLE();
    }
    SWD_Sequence(sequence_info, request, response);
    if (sequence_count == 0U) {
      PIN_SWDIO_OUT_ENABLE();
    }
#endif
    if ((sequence_info & SWD_SEQUENCE_DIN) != 0U) {
      request_count++;
#if (DAP_SWD != 0)
      response += count;
      response_count += count;
#endif
    } else {
      request += count;
      request_count += count + 1U;
    }
  }

  return ((request_count << 16) | response_count);
}


// Process JTAG Sequence command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
static uint32_t DAP_JTAG_Sequence(const uint8_t *request, uint8_t *response) {
  uint32_t sequence_info;
  uint32_t sequence_count;
  uint32_t request_count;
  uint32_t response_count;
  uint32_t count;

#if (DAP_JTAG != 0)
  *response++ = DAP_OK;
#else
  *response++ = DAP_ERROR;
#endif
  request_count  = 1U;
  response_count = 1U;

  sequence_count = *request++;
  while (sequence_count--) {
    sequence_info = *request++;
    count = sequence_info & JTAG_SEQUENCE_TCK;
    if (count == 0U) {
      count = 64U;
    }
    count = (count + 7U) / 8U;
#if (DAP_JTAG != 0)
    JTAG_Sequence(sequence_info, request, response);
#endif
    request += count;
    request_count += count + 1U;
#if (DAP_JTAG != 0)
    if ((sequence_info & JTAG_SEQUENCE_TDO) != 0U) {
      response += count;
      response_count += count;
    }
#endif
  }

  return ((request_count << 16) | response_count);
}


// Process JTAG Configure command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
static uint32_t DAP_JTAG_Configure(const uint8_t *request, uint8_t *response) {
  uint32_t count;
#if (DAP_JTAG != 0)
  uint32_t length;
  uint32_t bits;
  uint32_t n;

  count = *request++;
  DAP_Data.jtag_dev.count = (uint8_t)count;

  bits = 0U;
  for (n = 0U; n < count; n++) {
    length = *request++;
    DAP_Data.jtag_dev.ir_length[n] =  (uint8_t)length;
    DAP_Data.jtag_dev.ir_before[n] = (uint16_t)bits;
    bits += length;
  }
  for (n = 0U; n < count; n++) {
    bits -= DAP_Data.jtag_dev.ir_length[n];
    DAP_Data.jtag_dev.ir_after[n] = (uint16_t)bits;
  }

  *response = DAP_OK;
#else
  count = *request;
  *response = DAP_ERROR;
#endif

  return (((count + 1U) << 16) | 1U);
}


// Process JTAG IDCODE command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
static uint32_t DAP_JTAG_IDCode(const uint8_t *request, uint8_t *response) {
#if (DAP_JTAG != 0)
  uint32_t data;

  if (DAP_Data.debug_port != DAP_PORT_JTAG) {
    goto id_error;
  }

  // Device index (JTAP TAP)
  DAP_Data.jtag_dev.index = *request;
  if (DAP_Data.jtag_dev.index >= DAP_Data.jtag_dev.count) {
    goto id_error;
  }

  // Select JTAG chain
  JTAG_IR(JTAG_IDCODE);

  // Read IDCODE register
  data = JTAG_ReadIDCode();

  // Store Data
  *(response+0) =  DAP_OK;
  *(response+1) = (uint8_t)(data >>  0);
  *(response+2) = (uint8_t)(data >>  8);
  *(response+3) = (uint8_t)(data >> 16);
  *(response+4) = (uint8_t)(data >> 24);

  return ((1U << 16) | 5U);

id_error:
#endif
  *response = DAP_ERROR;
  return ((1U << 16) | 1U);
}


// Process Transfer Configure command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
static uint32_t DAP_TransferConfigure(const uint8_t *request, uint8_t *response) {

  DAP_Data.transfer.idle_cycles =            *(request+0);
  {
    uint32_t cfg = swd_read32(SWD_CFG);
    uint32_t idle = DAP_Data.transfer.idle_cycles;
    if (idle > 15U) idle = 15U;
    /* Zero idle still fails random F103 blocks. Keep release builds safe;
     * diagnostic builds must explicitly opt into the experiment. */
#if !defined(DAP_ALLOW_ZERO_IDLE) || !DAP_ALLOW_ZERO_IDLE
    if (idle == 0U) idle = 1U;
#endif
    DAP_Data.transfer.idle_cycles = (uint8_t)idle;
    swd_write32(SWD_CFG, (cfg & ~0xF0U) | (idle << 4));
  }
  DAP_Data.transfer.retry_count = (uint16_t) *(request+1) |
                                  (uint16_t)(*(request+2) << 8);
  DAP_Data.transfer.match_retry = (uint16_t) *(request+3) |
                                  (uint16_t)(*(request+4) << 8);

  *response = DAP_OK;
  return ((5U << 16) | 1U);
}


// Process SWD Transfer command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
#if (DAP_SWD != 0)
#define SWD_BATCH_OP_END        0x00U
#define SWD_BATCH_OP_XFER_WRITE 0x02U
#define SWD_BATCH_OP_XFER_READ  0x03U
#define SWD_BATCH_STATUS_BUSY   (1U << 0)
#define SWD_BATCH_STATUS_DONE   (1U << 1)
#define SWD_BATCH_STATUS_ERROR  (1U << 2)

#define SWD_BATCH_RSP_COUNT(status) (((status) >> 14) & 0xFFFFU)
#define SWD_BATCH_LAST_ACK(status)  (((status) >> 3) & 0x7U)

typedef struct {
  uint32_t xfer_batch_simple;
  uint32_t xfer_legacy_multi;
  uint32_t xfer_legacy_flags;
  uint32_t xfer_block_batch;
  uint32_t xfer_block_batch_read_words;
  uint32_t xfer_block_batch_write_words;
  uint32_t xfer_block_legacy_flags;
  uint32_t xfer_block_legacy_depth;
} DAP_SWD_STATS_t;

volatile DAP_SWD_STATS_t DAP_SWD_Stats;

void DAP_SWD_StatsClear(void) {
  memset((void *)&DAP_SWD_Stats, 0, sizeof(DAP_SWD_Stats));
}

void dap_swd_stats_snapshot(uint32_t values[8]) {
  memcpy(values, (const void *)&DAP_SWD_Stats, sizeof DAP_SWD_Stats);
}

static uint32_t DAP_HOT_CODE DAP_SWD_Transfer_Legacy(const uint8_t *request, uint8_t *response);
static uint32_t DAP_SWD_TransferBlock_Legacy(const uint8_t *request, uint8_t *response);

__STATIC_FORCEINLINE uint32_t DAP_SWD_BatchCtrlValue(uint32_t start, uint32_t clear) {
  uint32_t retry;

  retry = DAP_Data.transfer.retry_count;
  if (retry > 0xFFU) {
    retry = 0xFFU;
  }

  return ((retry & 0xFFU) << 8) |
         (clear ? 0x2U : 0U) |
         (start ? 0x1U : 0U);
}

__STATIC_FORCEINLINE void DAP_SWD_BatchSetAddr(uint32_t rsp_sel, uint32_t word_addr) {
  swd_write32(SWD_BATCH_ADDR, ((rsp_sel & 1U) << 16) | (word_addr & 0x3FFU));
}

__STATIC_FORCEINLINE void DAP_SWD_BatchWriteWord(uint32_t value) {
  swd_write32(SWD_BATCH_DATA, value);
}

__STATIC_FORCEINLINE uint32_t DAP_SWD_BatchReadWord(void) {
  return swd_read32(SWD_BATCH_DATA);
}

__STATIC_FORCEINLINE void DAP_SWD_BatchClear(void) {
  swd_write32(SWD_BATCH_CTRL, DAP_SWD_BatchCtrlValue(0U, 1U));
}

static uint32_t DAP_SWD_BatchRun(void) {
  uint32_t status;
  XTime start, end;
  uint32_t profiling=dap_profile.enabled;

  if (profiling) XTime_GetTime(&start);
  swd_write32(SWD_BATCH_CTRL, DAP_SWD_BatchCtrlValue(1U, 1U));
  do {
    status = swd_read32(SWD_BATCH_STATUS);
  } while (((status & 0x2U) == 0U) && !DAP_TransferAbort);

  if (!(status & SWD_BATCH_STATUS_DONE) && DAP_TransferAbort) {
    (void)swd_abort_engines();
    status=SWD_BATCH_STATUS_DONE|SWD_BATCH_STATUS_ERROR;
  }

  if (profiling) {
    XTime_GetTime(&end);
    dap_profile.batch_ticks += end-start;
    dap_profile.batch_calls++;
  }
  return status;
}

/* Plain 0x05 packets can mix TAR/SELECT writes and AP posted reads. Track
 * the result indices so pipeline dummy words never enter the USB response. */
static uint16_t transfer_read_map[255];
static uint32_t transfer_cmd_words, transfer_raw_reads;
static int32_t transfer_read_header, transfer_write_header;

static uint32_t transfer_emit_read(uint32_t req) {
  transfer_write_header = -1;
  if (transfer_read_header >= 0 && (swd_dma_cmd[transfer_read_header] & 0xFFU) == req) {
    swd_dma_cmd[transfer_read_header] += 1U << 8;
  } else {
    transfer_read_header = (int32_t)transfer_cmd_words;
    swd_dma_cmd[transfer_cmd_words++] = (4U << 24) | (1U << 8) | req;
  }
  return transfer_raw_reads++;
}

static void transfer_emit_write(uint32_t req, uint32_t value) {
  transfer_read_header = -1;
  if (transfer_write_header >= 0 &&
      (swd_dma_cmd[transfer_write_header] & 0xFFU) == req) {
    swd_dma_cmd[transfer_write_header] += 1U << 8;
  } else {
    transfer_write_header = (int32_t)transfer_cmd_words;
    swd_dma_cmd[transfer_cmd_words++] = (5U << 24) | (1U << 8) | req;
  }
  swd_dma_cmd[transfer_cmd_words++] = value;
}

static uint32_t DAP_HOT_CODE DAP_SWD_Transfer(const uint8_t *request, uint8_t *response) {
  const uint8_t *p = request + 2;
  uint32_t count = request[1], n, req, value, idx, nr = 0, status, ack;
  uint32_t post = 0, check_write = 0;
  uint8_t *out = response + 2;
  if (count < 8U) goto legacy;
  transfer_cmd_words = transfer_raw_reads = 0;
  transfer_read_header = -1;
  transfer_write_header = -1;
  for (n = 0; n < count; n++) {
    req = *p++;
    if ((req & 15U)==8U) goto legacy; /* Observe SELECT writes for probe ownership. */
    if (req & 0xF0U) goto legacy; /* Match/timestamp semantics retain CMSIS code. */
    if ((req & (DAP_TRANSFER_APnDP | DAP_TRANSFER_RnW)) ==
               (DAP_TRANSFER_APnDP | DAP_TRANSFER_RnW)) {
      idx = transfer_emit_read(req);
      if (post) transfer_read_map[nr++] = (uint16_t)idx;
      post = 1;
      check_write = 0;
    } else {
      if (post) {
        transfer_read_map[nr++] = (uint16_t)transfer_emit_read(DP_RDBUFF | DAP_TRANSFER_RnW);
        post = 0;
      }
      if (req & DAP_TRANSFER_RnW) {
        transfer_read_map[nr++] = (uint16_t)transfer_emit_read(req);
        check_write = 0;
      } else {
        memcpy(&value, p, 4); p += 4;
        transfer_emit_write(req, value);
        check_write = 1;
      }
    }
  }
  if (post) transfer_read_map[nr++] = (uint16_t)transfer_emit_read(DP_RDBUFF | DAP_TRANSFER_RnW);
  else if (check_write) (void)transfer_emit_read(DP_RDBUFF | DAP_TRANSFER_RnW);
  swd_dma_cmd[transfer_cmd_words++] = 0;
  DAP_TransferAbort = 0;
  DAP_SWD_BatchClear();
  ack = DAP_TRANSFER_ERROR;
  if (swd_dma_upload(transfer_cmd_words)) goto failed;
  status = DAP_SWD_BatchRun();
  ack = SWD_BATCH_LAST_ACK(status);
  if ((status & (SWD_BATCH_STATUS_DONE | SWD_BATCH_STATUS_ERROR)) != SWD_BATCH_STATUS_DONE)
    goto failed;
  if (nr && swd_dma_download(0, transfer_raw_reads)) {ack = DAP_TRANSFER_ERROR; goto failed;}
  for (n = 0; n < nr;) {
    uint32_t first = transfer_read_map[n], run = 1;
    while (n+run < nr && transfer_read_map[n+run] == first+run) run++;
    memcpy(out, &swd_dma_rsp[first], run*4U);
    out += run*4U;
    n += run;
  }
  response[0] = (uint8_t)count;
  response[1] = DAP_TRANSFER_OK;
  DAP_SWD_Stats.xfer_batch_simple++;
  return ((uint32_t)(p-request) << 16) | (uint32_t)(out-response);
failed:
  response[0] = 0;
  response[1] = (uint8_t)(ack ? ack : DAP_TRANSFER_ERROR);
  return ((uint32_t)(p-request) << 16) | 2U;
legacy:
  DAP_SWD_Stats.xfer_legacy_multi++;
  return DAP_SWD_Transfer_Legacy(request, response);
}

static uint32_t DAP_HOT_CODE DAP_SWD_Transfer_Legacy(const uint8_t *request, uint8_t *response) {
  const
  uint8_t  *request_head;
  uint32_t  request_count;
  uint32_t  request_value;
  uint8_t  *response_head;
  uint32_t  response_count;
  uint32_t  response_value;
  uint32_t  post_read;
  uint32_t  check_write;
  uint32_t  match_value;
  uint32_t  match_retry;
  uint32_t  retry;
  uint32_t  data;
#if (TIMESTAMP_CLOCK != 0U)
  uint32_t  timestamp;
#endif

  request_head   = request;

  response_count = 0U;
  response_value = 0U;
  response_head  = response;
  response      += 2;

  DAP_TransferAbort = 0U;

  post_read   = 0U;
  check_write = 0U;

  request++;            // Ignore DAP index

  request_count = *request++;

  for (; request_count != 0U; request_count--) {
    request_value = *request++;
    if ((request_value & DAP_TRANSFER_RnW) != 0U) {
      // Read register
      if (post_read) {
        // Read was posted before
        retry = DAP_Data.transfer.retry_count;
        if ((request_value & (DAP_TRANSFER_APnDP | DAP_TRANSFER_MATCH_VALUE)) == DAP_TRANSFER_APnDP) {
          // Read previous AP data and post next AP read
          do {
            response_value = SWD_Transfer(request_value, &data);
          } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
        } else {
          // Read previous AP data
          do {
            response_value = SWD_Transfer(DP_RDBUFF | DAP_TRANSFER_RnW, &data);
          } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
          post_read = 0U;
        }
        if (response_value != DAP_TRANSFER_OK) {
          break;
        }
        // Store previous AP data
        *response++ = (uint8_t) data;
        *response++ = (uint8_t)(data >>  8);
        *response++ = (uint8_t)(data >> 16);
        *response++ = (uint8_t)(data >> 24);
#if (TIMESTAMP_CLOCK != 0U)
        if (post_read) {
          // Store Timestamp of next AP read
          if ((request_value & DAP_TRANSFER_TIMESTAMP) != 0U) {
            timestamp = DAP_Data.timestamp;
            *response++ = (uint8_t) timestamp;
            *response++ = (uint8_t)(timestamp >>  8);
            *response++ = (uint8_t)(timestamp >> 16);
            *response++ = (uint8_t)(timestamp >> 24);
          }
        }
#endif
      }
      if ((request_value & DAP_TRANSFER_MATCH_VALUE) != 0U) {
        // Read with value match
        match_value = (uint32_t)(*(request+0) <<  0) |
                      (uint32_t)(*(request+1) <<  8) |
                      (uint32_t)(*(request+2) << 16) |
                      (uint32_t)(*(request+3) << 24);
        request += 4;
        match_retry = DAP_Data.transfer.match_retry;
        if ((request_value & DAP_TRANSFER_APnDP) != 0U) {
          // Post AP read
          retry = DAP_Data.transfer.retry_count;
          do {
            response_value = SWD_Transfer(request_value, NULL);
          } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
          if (response_value != DAP_TRANSFER_OK) {
            break;
          }
        }
        do {
          // Read register until its value matches or retry counter expires
          retry = DAP_Data.transfer.retry_count;
          do {
            response_value = SWD_Transfer(request_value, &data);
          } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
          if (response_value != DAP_TRANSFER_OK) {
            break;
          }
        } while (((data & DAP_Data.transfer.match_mask) != match_value) && match_retry-- && !DAP_TransferAbort);
        if ((data & DAP_Data.transfer.match_mask) != match_value) {
          response_value |= DAP_TRANSFER_MISMATCH;
        }
        if (response_value != DAP_TRANSFER_OK) {
          break;
        }
      } else {
        // Normal read
        retry = DAP_Data.transfer.retry_count;
        if ((request_value & DAP_TRANSFER_APnDP) != 0U) {
          // Read AP register
          if (post_read == 0U) {
            // Post AP read
            do {
              response_value = SWD_Transfer(request_value, NULL);
            } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
            if (response_value != DAP_TRANSFER_OK) {
              break;
            }
#if (TIMESTAMP_CLOCK != 0U)
            // Store Timestamp
            if ((request_value & DAP_TRANSFER_TIMESTAMP) != 0U) {
              timestamp = DAP_Data.timestamp;
              *response++ = (uint8_t) timestamp;
              *response++ = (uint8_t)(timestamp >>  8);
              *response++ = (uint8_t)(timestamp >> 16);
              *response++ = (uint8_t)(timestamp >> 24);
            }
#endif
            post_read = 1U;
          }
        } else {
          // Read DP register
          do {
            response_value = SWD_Transfer(request_value, &data);
          } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
          if (response_value != DAP_TRANSFER_OK) {
            break;
          }
#if (TIMESTAMP_CLOCK != 0U)
          // Store Timestamp
          if ((request_value & DAP_TRANSFER_TIMESTAMP) != 0U) {
            timestamp = DAP_Data.timestamp;
            *response++ = (uint8_t) timestamp;
            *response++ = (uint8_t)(timestamp >>  8);
            *response++ = (uint8_t)(timestamp >> 16);
            *response++ = (uint8_t)(timestamp >> 24);
          }
#endif
          // Store data
          *response++ = (uint8_t) data;
          *response++ = (uint8_t)(data >>  8);
          *response++ = (uint8_t)(data >> 16);
          *response++ = (uint8_t)(data >> 24);
        }
      }
      check_write = 0U;
    } else {
      // Write register
      if (post_read) {
        // Read previous data
        retry = DAP_Data.transfer.retry_count;
        do {
          response_value = SWD_Transfer(DP_RDBUFF | DAP_TRANSFER_RnW, &data);
        } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
        if (response_value != DAP_TRANSFER_OK) {
          break;
        }
        // Store previous data
        *response++ = (uint8_t) data;
        *response++ = (uint8_t)(data >>  8);
        *response++ = (uint8_t)(data >> 16);
        *response++ = (uint8_t)(data >> 24);
        post_read = 0U;
      }
      // Load data
      data = (uint32_t)(*(request+0) <<  0) |
             (uint32_t)(*(request+1) <<  8) |
             (uint32_t)(*(request+2) << 16) |
             (uint32_t)(*(request+3) << 24);
      request += 4;
      if ((request_value & DAP_TRANSFER_MATCH_MASK) != 0U) {
        // Write match mask
        DAP_Data.transfer.match_mask = data;
        response_value = DAP_TRANSFER_OK;
      } else {
        // Write DP/AP register
        retry = DAP_Data.transfer.retry_count;
        do {
          response_value = SWD_Transfer(request_value, &data);
        } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
        if (response_value != DAP_TRANSFER_OK) {
          break;
        }
#if (TIMESTAMP_CLOCK != 0U)
        // Store Timestamp
        if ((request_value & DAP_TRANSFER_TIMESTAMP) != 0U) {
          timestamp = DAP_Data.timestamp;
          *response++ = (uint8_t) timestamp;
          *response++ = (uint8_t)(timestamp >>  8);
          *response++ = (uint8_t)(timestamp >> 16);
          *response++ = (uint8_t)(timestamp >> 24);
        }
#endif
        check_write = 1U;
      }
    }
    response_count++;
    if (DAP_TransferAbort) {
      break;
    }
  }

  for (; request_count != 0U; request_count--) {
    // Process canceled requests
    request_value = *request++;
    if ((request_value & DAP_TRANSFER_RnW) != 0U) {
      // Read register
      if ((request_value & DAP_TRANSFER_MATCH_VALUE) != 0U) {
        // Read with value match
        request += 4;
      }
    } else {
      // Write register
      request += 4;
    }
  }

  if (response_value == DAP_TRANSFER_OK) {
    if (post_read) {
      // Read previous data
      retry = DAP_Data.transfer.retry_count;
      do {
        response_value = SWD_Transfer(DP_RDBUFF | DAP_TRANSFER_RnW, &data);
      } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
      if (response_value != DAP_TRANSFER_OK) {
        goto end;
      }
      // Store previous data
      *response++ = (uint8_t) data;
      *response++ = (uint8_t)(data >>  8);
      *response++ = (uint8_t)(data >> 16);
      *response++ = (uint8_t)(data >> 24);
    } else if (check_write) {
      // Check last write
      retry = DAP_Data.transfer.retry_count;
      do {
        response_value = SWD_Transfer(DP_RDBUFF | DAP_TRANSFER_RnW, NULL);
      } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
    }
  }

end:
  *(response_head+0) = (uint8_t)response_count;
  *(response_head+1) = (uint8_t)response_value;

  return (((uint32_t)(request - request_head) << 16) | (uint32_t)(response - response_head));
}
#endif


// Process JTAG Transfer command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
#if (DAP_JTAG != 0)
static uint32_t DAP_JTAG_Transfer(const uint8_t *request, uint8_t *response) {
  const
  uint8_t  *request_head;
  uint32_t  request_count;
  uint32_t  request_value;
  uint32_t  request_ir;
  uint8_t  *response_head;
  uint32_t  response_count;
  uint32_t  response_value;
  uint32_t  post_read;
  uint32_t  match_value;
  uint32_t  match_retry;
  uint32_t  retry;
  uint32_t  data;
  uint32_t  ir;
#if (TIMESTAMP_CLOCK != 0U)
  uint32_t  timestamp;
#endif

  request_head   = request;

  response_count = 0U;
  response_value = 0U;
  response_head  = response;
  response      += 2;

  DAP_TransferAbort = 0U;

  ir        = 0U;
  post_read = 0U;

  // Device index (JTAP TAP)
  DAP_Data.jtag_dev.index = *request++;
  if (DAP_Data.jtag_dev.index >= DAP_Data.jtag_dev.count) {
    goto end;
  }

  request_count = *request++;

  for (; request_count != 0U; request_count--) {
    request_value = *request++;
    request_ir = (request_value & DAP_TRANSFER_APnDP) ? JTAG_APACC : JTAG_DPACC;
    if ((request_value & DAP_TRANSFER_RnW) != 0U) {
      // Read register
      if (post_read) {
        // Read was posted before
        retry = DAP_Data.transfer.retry_count;
        if ((ir == request_ir) && ((request_value & DAP_TRANSFER_MATCH_VALUE) == 0U)) {
          // Read previous data and post next read
          do {
            response_value = JTAG_Transfer(request_value, &data);
          } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
        } else {
          // Select JTAG chain
          if (ir != JTAG_DPACC) {
            ir = JTAG_DPACC;
            JTAG_IR(ir);
          }
          // Read previous data
          do {
            response_value = JTAG_Transfer(DP_RDBUFF | DAP_TRANSFER_RnW, &data);
          } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
          post_read = 0U;
        }
        if (response_value != DAP_TRANSFER_OK) {
          break;
        }
        // Store previous data
        *response++ = (uint8_t) data;
        *response++ = (uint8_t)(data >>  8);
        *response++ = (uint8_t)(data >> 16);
        *response++ = (uint8_t)(data >> 24);
#if (TIMESTAMP_CLOCK != 0U)
        if (post_read) {
          // Store Timestamp of next AP read
          if ((request_value & DAP_TRANSFER_TIMESTAMP) != 0U) {
            timestamp = DAP_Data.timestamp;
            *response++ = (uint8_t) timestamp;
            *response++ = (uint8_t)(timestamp >>  8);
            *response++ = (uint8_t)(timestamp >> 16);
            *response++ = (uint8_t)(timestamp >> 24);
          }
        }
#endif
      }
      if ((request_value & DAP_TRANSFER_MATCH_VALUE) != 0U) {
        // Read with value match
        match_value = (uint32_t)(*(request+0) <<  0) |
                      (uint32_t)(*(request+1) <<  8) |
                      (uint32_t)(*(request+2) << 16) |
                      (uint32_t)(*(request+3) << 24);
        request += 4;
        match_retry  = DAP_Data.transfer.match_retry;
        // Select JTAG chain
        if (ir != request_ir) {
          ir = request_ir;
          JTAG_IR(ir);
        }
        // Post DP/AP read
        retry = DAP_Data.transfer.retry_count;
        do {
          response_value = JTAG_Transfer(request_value, NULL);
        } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
        if (response_value != DAP_TRANSFER_OK) {
          break;
        }
        do {
          // Read register until its value matches or retry counter expires
          retry = DAP_Data.transfer.retry_count;
          do {
            response_value = JTAG_Transfer(request_value, &data);
          } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
          if (response_value != DAP_TRANSFER_OK) {
            break;
          }
        } while (((data & DAP_Data.transfer.match_mask) != match_value) && match_retry-- && !DAP_TransferAbort);
        if ((data & DAP_Data.transfer.match_mask) != match_value) {
          response_value |= DAP_TRANSFER_MISMATCH;
        }
        if (response_value != DAP_TRANSFER_OK) {
          break;
        }
      } else {
        // Normal read
        if (post_read == 0U) {
          // Select JTAG chain
          if (ir != request_ir) {
            ir = request_ir;
            JTAG_IR(ir);
          }
          // Post DP/AP read
          retry = DAP_Data.transfer.retry_count;
          do {
            response_value = JTAG_Transfer(request_value, NULL);
          } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
          if (response_value != DAP_TRANSFER_OK) {
            break;
          }
#if (TIMESTAMP_CLOCK != 0U)
          // Store Timestamp
          if ((request_value & DAP_TRANSFER_TIMESTAMP) != 0U) {
            timestamp = DAP_Data.timestamp;
            *response++ = (uint8_t) timestamp;
            *response++ = (uint8_t)(timestamp >>  8);
            *response++ = (uint8_t)(timestamp >> 16);
            *response++ = (uint8_t)(timestamp >> 24);
          }
#endif
          post_read = 1U;
        }
      }
    } else {
      // Write register
      if (post_read) {
        // Select JTAG chain
        if (ir != JTAG_DPACC) {
          ir = JTAG_DPACC;
          JTAG_IR(ir);
        }
        // Read previous data
        retry = DAP_Data.transfer.retry_count;
        do {
          response_value = JTAG_Transfer(DP_RDBUFF | DAP_TRANSFER_RnW, &data);
        } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
        if (response_value != DAP_TRANSFER_OK) {
          break;
        }
        // Store previous data
        *response++ = (uint8_t) data;
        *response++ = (uint8_t)(data >>  8);
        *response++ = (uint8_t)(data >> 16);
        *response++ = (uint8_t)(data >> 24);
        post_read = 0U;
      }
      // Load data
      data = (uint32_t)(*(request+0) <<  0) |
             (uint32_t)(*(request+1) <<  8) |
             (uint32_t)(*(request+2) << 16) |
             (uint32_t)(*(request+3) << 24);
      request += 4;
      if ((request_value & DAP_TRANSFER_MATCH_MASK) != 0U) {
        // Write match mask
        DAP_Data.transfer.match_mask = data;
        response_value = DAP_TRANSFER_OK;
      } else {
        // Select JTAG chain
        if (ir != request_ir) {
          ir = request_ir;
          JTAG_IR(ir);
        }
        // Write DP/AP register
        retry = DAP_Data.transfer.retry_count;
        do {
          response_value = JTAG_Transfer(request_value, &data);
        } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
        if (response_value != DAP_TRANSFER_OK) {
          break;
        }
#if (TIMESTAMP_CLOCK != 0U)
        // Store Timestamp
        if ((request_value & DAP_TRANSFER_TIMESTAMP) != 0U) {
          timestamp = DAP_Data.timestamp;
          *response++ = (uint8_t) timestamp;
          *response++ = (uint8_t)(timestamp >>  8);
          *response++ = (uint8_t)(timestamp >> 16);
          *response++ = (uint8_t)(timestamp >> 24);
        }
#endif
      }
    }
    response_count++;
    if (DAP_TransferAbort) {
      break;
    }
  }

  for (; request_count != 0U; request_count--) {
    // Process canceled requests
    request_value = *request++;
    if ((request_value & DAP_TRANSFER_RnW) != 0U) {
      // Read register
      if ((request_value & DAP_TRANSFER_MATCH_VALUE) != 0U) {
        // Read with value match
        request += 4;
      }
    } else {
      // Write register
      request += 4;
    }
  }

  if (response_value == DAP_TRANSFER_OK) {
    // Select JTAG chain
    if (ir != JTAG_DPACC) {
      ir = JTAG_DPACC;
      JTAG_IR(ir);
    }
    if (post_read) {
      // Read previous data
      retry = DAP_Data.transfer.retry_count;
      do {
        response_value = JTAG_Transfer(DP_RDBUFF | DAP_TRANSFER_RnW, &data);
      } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
      if (response_value != DAP_TRANSFER_OK) {
        goto end;
      }
      // Store previous data
      *response++ = (uint8_t) data;
      *response++ = (uint8_t)(data >>  8);
      *response++ = (uint8_t)(data >> 16);
      *response++ = (uint8_t)(data >> 24);
    } else {
      // Check last write
      retry = DAP_Data.transfer.retry_count;
      do {
        response_value = JTAG_Transfer(DP_RDBUFF | DAP_TRANSFER_RnW, NULL);
      } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
    }
  }

end:
  *(response_head+0) = (uint8_t)response_count;
  *(response_head+1) = (uint8_t)response_value;

  return (((uint32_t)(request - request_head) << 16) | (uint32_t)(response - response_head));
}
#endif


// Process Dummy Transfer command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
static uint32_t DAP_Dummy_Transfer(const uint8_t *request, uint8_t *response) {
  const
  uint8_t  *request_head;
  uint32_t  request_count;
  uint32_t  request_value;

  request_head  =  request;

  request++;            // Ignore DAP index

  request_count = *request++;

  for (; request_count != 0U; request_count--) {
    // Process dummy requests
    request_value = *request++;
    if ((request_value & DAP_TRANSFER_RnW) != 0U) {
      // Read register
      if ((request_value & DAP_TRANSFER_MATCH_VALUE) != 0U) {
        // Read with value match
        request += 4;
      }
    } else {
      // Write register
      request += 4;
    }
  }

  *(response+0) = 0U;   // Response count
  *(response+1) = 0U;   // Response value

  return (((uint32_t)(request - request_head) << 16) | 2U);
}


// Process Transfer command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
static uint32_t DAP_Transfer(const uint8_t *request, uint8_t *response) {
  uint32_t num;

  switch (DAP_Data.debug_port) {
#if (DAP_SWD != 0)
    case DAP_PORT_SWD:
      num = DAP_SWD_Transfer(request, response);
      break;
#endif
#if (DAP_JTAG != 0)
    case DAP_PORT_JTAG:
      num = DAP_JTAG_Transfer(request, response);
      break;
#endif
    default:
      num = DAP_Dummy_Transfer(request, response);
      break;
  }

  return (num);
}


// Process SWD Transfer Block command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response
#if (DAP_SWD != 0)
#include "swd_dma.h"
#include "dap_metrics.h"
#include <string.h>
#include "xil_cache.h"

/* Debug counters for the RTL packet-engine path (readable over JTAG). */
volatile uint32_t dbg_pkt_taken, dbg_pkt_fallback, dbg_pkt_status,
                  dbg_pkt_rsp0, dbg_pkt_req, dbg_pkt_count;

static void dbg_pkt_flush(void)
{
#if DAP_MMIO_DIAGNOSTICS
  Xil_DCacheFlushRange((UINTPTR)&dbg_pkt_req, 128);
#endif
}

static uint32_t DAP_SWD_TransferBlock(const uint8_t *request, uint8_t *response) {
  const uint8_t *head = request;
  uint8_t *out = response + 3;
  uint32_t remaining = request[1] | ((uint32_t)request[2] << 8);
  uint32_t req = request[3], completed = 0, ack = 0;
  uint32_t status, chunk, words, offset;
  request += 4;
  if (req & (DAP_TRANSFER_MATCH_VALUE | DAP_TRANSFER_MATCH_MASK | DAP_TRANSFER_TIMESTAMP))
    return DAP_SWD_TransferBlock_Legacy(head, response);

  /* Fast packet-engine path.  The RTL receives a compact four-byte header
   * {0x06,count_lo,count_hi,request}; the DAP index is fixed to zero by this
   * single-target device.  The old DMA batch path remains the fallback. */
  if (remaining && remaining <= 1023U && ((req & 0xF0U) == 0U) &&
      (req & DAP_TRANSFER_APnDP)) {
    uint8_t *raw = (uint8_t *)swd_dma_cmd;
    uint32_t raw_len = 4U + ((req & DAP_TRANSFER_RnW) ? 0U : remaining * 4U);
    uint32_t words = (raw_len + 3U) / 4U;
    uint32_t pstatus, rsp_words, packet_wait, packet_completed, rsp_header;
    uint32_t *direct_rsp = ((req & DAP_TRANSFER_RnW) &&
                           (((uintptr_t)(response-1) & 31U)==0U)) ?
                           (uint32_t *)(response-1) : NULL;
    XTime metric_start;
    dbg_pkt_taken++;
    dbg_pkt_req = req;
    dbg_pkt_count = remaining;
    raw[0] = ID_DAP_TransferBlock;
    raw[1] = (uint8_t)remaining;
    raw[2] = (uint8_t)(remaining >> 8);
    raw[3] = (uint8_t)req;
    if (!(req & DAP_TRANSFER_RnW)) memcpy(raw + 4, request, remaining * 4U);
    DAP_SWD_BatchClear();
    /* The controller silently drops a launch while the previous packet is
     * still busy, so wait for idle before handing over the new command. */
    packet_wait = 0;
    while (swd_read32(SWD_PACKET_STATUS) & 1U) {
      if (++packet_wait > 2000000U) {
        dbg_pkt_fallback++; dbg_pkt_flush();
        xil_printf("[DAP] PACKET_BUSY_STUCK\r\n");
        goto packet_failed;
      }
    }
    if (swd_dma_upload(words)) { dbg_pkt_fallback++; dbg_pkt_flush(); goto packet_fallback; }
    metric_start=dap_metric_start();
    swd_write32(SWD_PACKET_LEN, raw_len);
    swd_write32(SWD_PACKET_CTRL, 1U);
    packet_wait = 0;
    do {
      pstatus = swd_read32(SWD_PACKET_STATUS);
      if (++packet_wait > 2000000U) {
        dbg_pkt_status = pstatus;
        dbg_pkt_fallback++;
        dbg_pkt_flush();
        xil_printf("[DAP] PACKET_TIMEOUT st=0x%08x len=%d req=0x%02x\r\n",
               (unsigned)pstatus, (int)raw_len, (unsigned)req);
        goto packet_failed;
      }
    } while (pstatus & 1U);
    dap_metric_end((req & DAP_TRANSFER_RnW)?MET_PACKET_READ:MET_PACKET_WRITE, metric_start, remaining*4U);
    dbg_pkt_status = pstatus;
    if (!(pstatus & 2U)) goto packet_failed;
    rsp_words = (pstatus >> 16) & 0xFFFFU;
    if (!rsp_words || rsp_words > 1024U) goto packet_failed;
    if (direct_rsp) {
      // RTL word0 is count/status, followed by the aligned data. DMA the whole
      // result into the USB slot, then replace word0 with the CMSIS-DAP header.
      // Nested ExecuteCommands may be unaligned and retain the private buffer.
      if (swd_dma_download_to(0,rsp_words,direct_rsp)) goto packet_failed;
      rsp_header=direct_rsp[0];
      ((uint8_t *)direct_rsp)[0]=ID_DAP_TransferBlock;
    } else {
      if (swd_dma_download(0,rsp_words)) goto packet_failed;
      rsp_header=swd_dma_rsp[0];
    }
    dbg_pkt_rsp0 = rsp_header;
    dbg_pkt_flush();
    packet_completed = rsp_header & 0xFFFFU;
    if (packet_completed > remaining ||
        rsp_words != ((req & DAP_TRANSFER_RnW) ? packet_completed + 1U : 1U)) goto packet_failed;
    response[0] = (uint8_t)rsp_header;
    response[1] = (uint8_t)(rsp_header >> 8);
    response[2] = (uint8_t)(rsp_header >> 16);
    if ((req & DAP_TRANSFER_RnW) && !direct_rsp) {
      metric_start=dap_metric_start();
      memcpy(response + 3, &swd_dma_rsp[1], packet_completed * 4U);
      dap_metric_end(MET_COPY,metric_start,packet_completed*4U);
    }
    return (uint32_t)(3U + ((req & DAP_TRANSFER_RnW) ? packet_completed * 4U : 0U));
packet_failed:
    (void)swd_abort_engines();
    if (direct_rsp) ((uint8_t *)direct_rsp)[0]=ID_DAP_TransferBlock;
    // After launch the target may have advanced TAR or accepted writes. Never
    // replay the packet from its beginning on the batch path.
    response[0] = response[1] = 0;
    response[2] = DAP_TRANSFER_ERROR;
    return 3U;
packet_fallback:
    ;
  }
  DAP_TransferAbort = 0;
  while (remaining && !DAP_TransferAbort) {
    // One repeat header replaces hundreds of individually written commands.
    // Leave room for posted read, write completion check and END.
    chunk = remaining > 1000U ? 1000U : remaining;
    words = 0;
    DAP_SWD_BatchClear();
    if (req & DAP_TRANSFER_RnW) {
      swd_dma_cmd[words++] = (4U << 24) | (chunk << 8) | (req & 0xFFU);
      offset = (req & DAP_TRANSFER_APnDP) ? 1U : 0U;
      if (offset)
        swd_dma_cmd[words++] = (SWD_BATCH_OP_XFER_READ << 24) | DP_RDBUFF | DAP_TRANSFER_RnW;
    } else {
      offset = 0;
      swd_dma_cmd[words++] = (5U << 24) | (chunk << 8) | (req & 0xFFU);
      memcpy(&swd_dma_cmd[words], request, chunk*4U);
      words += chunk;
      swd_dma_cmd[words++] = (SWD_BATCH_OP_XFER_READ << 24) | DP_RDBUFF | DAP_TRANSFER_RnW;
    }
    swd_dma_cmd[words++] = 0;
    if (swd_dma_upload(words)) {ack = DAP_TRANSFER_ERROR; break;}
    status = DAP_SWD_BatchRun();
    ack = SWD_BATCH_LAST_ACK(status);
    if ((status & (SWD_BATCH_STATUS_DONE | SWD_BATCH_STATUS_ERROR)) != SWD_BATCH_STATUS_DONE) {
      if (!ack) ack = DAP_TRANSFER_ERROR;
      break;
    }
    if (req & DAP_TRANSFER_RnW) {
      if (swd_dma_download(offset, chunk)) {ack = DAP_TRANSFER_ERROR; break;}
      memcpy(out, swd_dma_rsp, chunk*4U);
      out += chunk*4U;
    } else {
      request += chunk*4U;
    }
    completed += chunk;
    remaining -= chunk;
    ack = DAP_TRANSFER_OK;
  }
  DAP_SWD_Stats.xfer_block_batch++;
  if (req & DAP_TRANSFER_RnW) DAP_SWD_Stats.xfer_block_batch_read_words += completed;
  else DAP_SWD_Stats.xfer_block_batch_write_words += completed;
  response[0] = (uint8_t)completed;
  response[1] = (uint8_t)(completed >> 8);
  response[2] = (uint8_t)ack;
  return (uint32_t)(out-response);
}

static uint32_t DAP_SWD_TransferBlock_Legacy(const uint8_t *request, uint8_t *response) {
  uint32_t  request_count;
  uint32_t  request_value;
  uint32_t  response_count;
  uint32_t  response_value;
  uint8_t  *response_head;
  uint32_t  retry;
  uint32_t  data;

  response_count = 0U;
  response_value = 0U;
  response_head  = response;
  response      += 3;

  DAP_TransferAbort = 0U;

  request++;            // Ignore DAP index

  request_count = (uint32_t)(*(request+0) << 0) |
                  (uint32_t)(*(request+1) << 8);
  request += 2;
  if (request_count == 0U) {
    goto end;
  }

  request_value = *request++;
  if ((request_value & DAP_TRANSFER_RnW) != 0U) {
    // Read register block
    if ((request_value & DAP_TRANSFER_APnDP) != 0U) {
      // Post AP read
      retry = DAP_Data.transfer.retry_count;
      do {
        response_value = SWD_Transfer(request_value, NULL);
      } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
      if (response_value != DAP_TRANSFER_OK) {
        goto end;
      }
    }
    while (request_count--) {
      // Read DP/AP register
      if ((request_count == 0U) && ((request_value & DAP_TRANSFER_APnDP) != 0U)) {
        // Last AP read
        request_value = DP_RDBUFF | DAP_TRANSFER_RnW;
      }
      retry = DAP_Data.transfer.retry_count;
      do {
        response_value = SWD_Transfer(request_value, &data);
      } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
      if (response_value != DAP_TRANSFER_OK) {
        goto end;
      }
      // Store data
      *response++ = (uint8_t) data;
      *response++ = (uint8_t)(data >>  8);
      *response++ = (uint8_t)(data >> 16);
      *response++ = (uint8_t)(data >> 24);
      response_count++;
    }
  } else {
    // Write register block
    while (request_count--) {
      // Load data
      data = (uint32_t)(*(request+0) <<  0) |
             (uint32_t)(*(request+1) <<  8) |
             (uint32_t)(*(request+2) << 16) |
             (uint32_t)(*(request+3) << 24);
      request += 4;
      // Write DP/AP register
      retry = DAP_Data.transfer.retry_count;
      do {
        response_value = SWD_Transfer(request_value, &data);
      } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
      if (response_value != DAP_TRANSFER_OK) {
        goto end;
      }
      response_count++;
    }
    // Check last write
    retry = DAP_Data.transfer.retry_count;
    do {
      response_value = SWD_Transfer(DP_RDBUFF | DAP_TRANSFER_RnW, NULL);
    } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
  }

end:
  *(response_head+0) = (uint8_t)(response_count >> 0);
  *(response_head+1) = (uint8_t)(response_count >> 8);
  *(response_head+2) = (uint8_t) response_value;

  return ((uint32_t)(response - response_head));
}
#endif


// Process JTAG Transfer Block command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response
#if (DAP_JTAG != 0)
static uint32_t DAP_JTAG_TransferBlock(const uint8_t *request, uint8_t *response) {
  uint32_t  request_count;
  uint32_t  request_value;
  uint32_t  response_count;
  uint32_t  response_value;
  uint8_t  *response_head;
  uint32_t  retry;
  uint32_t  data;
  uint32_t  ir;

  response_count = 0U;
  response_value = 0U;
  response_head  = response;
  response      += 3;

  DAP_TransferAbort = 0U;

  // Device index (JTAP TAP)
  DAP_Data.jtag_dev.index = *request++;
  if (DAP_Data.jtag_dev.index >= DAP_Data.jtag_dev.count) {
    goto end;
  }

  request_count = (uint32_t)(*(request+0) << 0) |
                  (uint32_t)(*(request+1) << 8);
  request += 2;
  if (request_count == 0U) {
    goto end;
  }

  request_value = *request++;

  // Select JTAG chain
  ir = (request_value & DAP_TRANSFER_APnDP) ? JTAG_APACC : JTAG_DPACC;
  JTAG_IR(ir);

  if ((request_value & DAP_TRANSFER_RnW) != 0U) {
    // Post read
    retry = DAP_Data.transfer.retry_count;
    do {
      response_value = JTAG_Transfer(request_value, NULL);
    } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
    if (response_value != DAP_TRANSFER_OK) {
      goto end;
    }
    // Read register block
    while (request_count--) {
      // Read DP/AP register
      if (request_count == 0U) {
        // Last read
        if (ir != JTAG_DPACC) {
          JTAG_IR(JTAG_DPACC);
        }
        request_value = DP_RDBUFF | DAP_TRANSFER_RnW;
      }
      retry = DAP_Data.transfer.retry_count;
      do {
        response_value = JTAG_Transfer(request_value, &data);
      } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
      if (response_value != DAP_TRANSFER_OK) {
        goto end;
      }
      // Store data
      *response++ = (uint8_t) data;
      *response++ = (uint8_t)(data >>  8);
      *response++ = (uint8_t)(data >> 16);
      *response++ = (uint8_t)(data >> 24);
      response_count++;
    }
  } else {
    // Write register block
    while (request_count--) {
      // Load data
      data = (uint32_t)(*(request+0) <<  0) |
             (uint32_t)(*(request+1) <<  8) |
             (uint32_t)(*(request+2) << 16) |
             (uint32_t)(*(request+3) << 24);
      request += 4;
      // Write DP/AP register
      retry = DAP_Data.transfer.retry_count;
      do {
        response_value = JTAG_Transfer(request_value, &data);
      } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
      if (response_value != DAP_TRANSFER_OK) {
        goto end;
      }
      response_count++;
    }
    // Check last write
    if (ir != JTAG_DPACC) {
      JTAG_IR(JTAG_DPACC);
    }
    retry = DAP_Data.transfer.retry_count;
    do {
      response_value = JTAG_Transfer(DP_RDBUFF | DAP_TRANSFER_RnW, NULL);
    } while ((response_value == DAP_TRANSFER_WAIT) && retry-- && !DAP_TransferAbort);
  }

end:
  *(response_head+0) = (uint8_t)(response_count >> 0);
  *(response_head+1) = (uint8_t)(response_count >> 8);
  *(response_head+2) = (uint8_t) response_value;

  return ((uint32_t)(response - response_head));
}
#endif


// Process Transfer Block command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
static uint32_t DAP_TransferBlock(const uint8_t *request, uint8_t *response) {
  uint32_t num;

  switch (DAP_Data.debug_port) {
#if (DAP_SWD != 0)
    case DAP_PORT_SWD:
      num = DAP_SWD_TransferBlock (request, response);
      break;
#endif
#if (DAP_JTAG != 0)
    case DAP_PORT_JTAG:
      num = DAP_JTAG_TransferBlock(request, response);
      break;
#endif
    default:
      *(response+0) = 0U;       // Response count [7:0]
      *(response+1) = 0U;       // Response count[15:8]
      *(response+2) = 0U;       // Response value
      num = 3U;
      break;
  }

  if ((*(request+3) & DAP_TRANSFER_RnW) != 0U) {
    // Read register block
    num |=  4U << 16;
  } else {
    // Write register block
    num |= (4U + (((uint32_t)(*(request+1)) | (uint32_t)(*(request+2) << 8)) * 4)) << 16;
  }

  return (num);
}


// Process SWD Write ABORT command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response
#if (DAP_SWD != 0)
static uint32_t DAP_SWD_WriteAbort(const uint8_t *request, uint8_t *response) {
  uint32_t data;

  // Load data (Ignore DAP index)
  data = (uint32_t)(*(request+1) <<  0) |
         (uint32_t)(*(request+2) <<  8) |
         (uint32_t)(*(request+3) << 16) |
         (uint32_t)(*(request+4) << 24);

  // Write Abort register
  SWD_Transfer(DP_ABORT, &data);

  *response = DAP_OK;
  return (1U);
}
#endif


// Process JTAG Write ABORT command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response
#if (DAP_JTAG != 0)
static uint32_t DAP_JTAG_WriteAbort(const uint8_t *request, uint8_t *response) {
  uint32_t data;

  // Device index (JTAP TAP)
  DAP_Data.jtag_dev.index = *request;
  if (DAP_Data.jtag_dev.index >= DAP_Data.jtag_dev.count) {
    *response = DAP_ERROR;
    return (1U);
  }

  // Select JTAG chain
  JTAG_IR(JTAG_ABORT);

  // Load data
  data = (uint32_t)(*(request+1) <<  0) |
         (uint32_t)(*(request+2) <<  8) |
         (uint32_t)(*(request+3) << 16) |
         (uint32_t)(*(request+4) << 24);

  // Write Abort register
  JTAG_WriteAbort(data);

  *response = DAP_OK;
  return (1U);
}
#endif


// Process Write ABORT command and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
static uint32_t DAP_WriteAbort(const uint8_t *request, uint8_t *response) {
  uint32_t num;

  switch (DAP_Data.debug_port) {
#if (DAP_SWD != 0)
    case DAP_PORT_SWD:
      num = DAP_SWD_WriteAbort (request, response);
      break;
#endif
#if (DAP_JTAG != 0)
    case DAP_PORT_JTAG:
      num = DAP_JTAG_WriteAbort(request, response);
      break;
#endif
    default:
      *response = DAP_ERROR;
      num = 1U;
      break;
  }
  return ((5U << 16) | num);
}


// Process DAP Vendor command request and prepare response
// Default function (can be overridden)
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
__WEAK uint32_t DAP_ProcessVendorCommand(const uint8_t *request, uint8_t *response) {
  (void)request;
  *response = ID_DAP_Invalid;
  return ((1U << 16) | 1U);
}


// Process DAP command request and prepare response
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
uint32_t DAP_ProcessCommand(const uint8_t *request, uint8_t *response) {
  uint32_t num;

  if ((*request >= ID_DAP_Vendor0) && (*request <= ID_DAP_Vendor31)) {
    return DAP_ProcessVendorCommand(request, response);
  }

  *response++ = *request;

  switch (*request++) {
    case ID_DAP_Info:
      num = DAP_Info(*request, response+1);
      *response = (uint8_t)num;
      return ((2U << 16) + 2U + num);

    case ID_DAP_HostStatus:
      num = DAP_HostStatus(request, response);
      break;

    case ID_DAP_Connect:
      num = DAP_Connect(request, response);
      break;
    case ID_DAP_Disconnect:
      num = DAP_Disconnect(response);
      break;

    case ID_DAP_Delay:
      num = DAP_Delay(request, response);
      break;

    case ID_DAP_ResetTarget:
      num = DAP_ResetTarget(response);
      break;

    case ID_DAP_SWJ_Pins:
      num = DAP_SWJ_Pins(request, response);
      break;
    case ID_DAP_SWJ_Clock:
      num = DAP_SWJ_Clock(request, response);
      break;
    case ID_DAP_SWJ_Sequence:
      num = DAP_SWJ_Sequence(request, response);
      break;

    case ID_DAP_SWD_Configure:
      num = DAP_SWD_Configure(request, response);
      break;
    case ID_DAP_SWD_Sequence:
      num = DAP_SWD_Sequence(request, response);
      break;

    case ID_DAP_JTAG_Sequence:
      num = DAP_JTAG_Sequence(request, response);
      break;
    case ID_DAP_JTAG_Configure:
      num = DAP_JTAG_Configure(request, response);
      break;
    case ID_DAP_JTAG_IDCODE:
      num = DAP_JTAG_IDCode(request, response);
      break;

    case ID_DAP_TransferConfigure:
      num = DAP_TransferConfigure(request, response);
      break;
    case ID_DAP_Transfer:
      num = DAP_Transfer(request, response);
      break;
    case ID_DAP_TransferBlock:
      num = DAP_TransferBlock(request, response);
      break;

    case ID_DAP_WriteABORT:
      num = DAP_WriteAbort(request, response);
      break;

#if ((SWO_UART != 0) || (SWO_MANCHESTER != 0))
    case ID_DAP_SWO_Transport:
      num = SWO_Transport(request, response);
      break;
    case ID_DAP_SWO_Mode:
      num = SWO_Mode(request, response);
      break;
    case ID_DAP_SWO_Baudrate:
      num = SWO_Baudrate(request, response);
      break;
    case ID_DAP_SWO_Control:
      num = SWO_Control(request, response);
      break;
    case ID_DAP_SWO_Status:
      num = SWO_Status(response);
      break;
    case ID_DAP_SWO_ExtendedStatus:
      num = SWO_ExtendedStatus(request, response);
      break;
    case ID_DAP_SWO_Data:
      num = SWO_Data(request, response);
      break;
#endif

#if (DAP_UART != 0)
    case ID_DAP_UART_Transport:
      num = UART_Transport(request, response);
      break;
    case ID_DAP_UART_Configure:
      num = UART_Configure(request, response);
      break;
    case ID_DAP_UART_Control:
      num = UART_Control(request, response);
      break;
    case ID_DAP_UART_Status:
      num = UART_Status(response);
      break;
    case ID_DAP_UART_Transfer:
      num = UART_Transfer(request, response);
      break;
#endif

    default:
      *(response-1) = ID_DAP_Invalid;
      return ((1U << 16) | 1U);
  }

  return ((1U << 16) + 1U + num);
}


// Execute DAP command (process request and prepare response)
//   request:  pointer to request data
//   response: pointer to response data
//   return:   number of bytes in response (lower 16 bits)
//             number of bytes in request (upper 16 bits)
uint32_t DAP_HOT_CODE DAP_ExecuteCommand(const uint8_t *request, uint8_t *response) {
  uint32_t cnt, num, n;

  if (*request == ID_DAP_ExecuteCommands) {
    *response++ = *request++;
    cnt = *request++;
    *response++ = (uint8_t)cnt;
    num = (2U << 16) | 2U;
    while (cnt--) {
      n = DAP_ProcessCommand(request, response);
      num += n;
      request  += (uint16_t)(n >> 16);
      response += (uint16_t) n;
    }
    return (num);
  }

  return DAP_ProcessCommand(request, response);
}


// Setup DAP
void DAP_Setup(void) {

  xil_printf("[DAP] SETUP_BEGIN\r\n");

  // Default settings
  DAP_Data.debug_port  = 0U;
  DAP_Data.transfer.idle_cycles = 0U;
  DAP_Data.transfer.retry_count = 100U;
  DAP_Data.transfer.match_retry = 0U;
  DAP_Data.transfer.match_mask  = 0x00000000U;
  xil_printf("[DAP] SETUP_FIELDS\r\n");
#if (DAP_SWD != 0)
  DAP_Data.swd_conf.turnaround  = 1U;
  DAP_Data.swd_conf.data_phase  = 0U;
#endif
#if (DAP_JTAG != 0)
  DAP_Data.jtag_dev.count = 0U;
#endif

  // Sets DAP_Data.fast_clock and DAP_Data.clock_delay.
  Set_Clock_Delay(DAP_DEFAULT_SWJ_CLOCK);
  xil_printf("[DAP] SETUP_CLOCK\r\n");

  DAP_SETUP();  // Device specific setup
  xil_printf("[DAP] SETUP_DONE\r\n");
}
