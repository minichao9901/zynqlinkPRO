/*
 * Copyright (c) 2013-2017 ARM Limited. All rights reserved.
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
 * $Date:        1. December 2017
 * $Revision:    V2.0.0
 *
 * Project:      CMSIS-DAP Source
 * Title:        DAP_vendor.c CMSIS-DAP Vendor Commands
 *
 *---------------------------------------------------------------------------*/

#include "DAP_config.h"
#include "DAP.h"
#include "swd_dma.h"
#include "dap_metrics.h"
#include "xtime_l.h"
#include <string.h>

//**************************************************************************************************
/**
\defgroup DAP_Vendor_Adapt_gr Adapt Vendor Commands
\ingroup DAP_Vendor_gr
@{

The file DAP_vendor.c provides template source code for extension of a Debug Unit with
Vendor Commands. Copy this file to the project folder of the Debug Unit and add the
file to the MDK-ARM project under the file group Configuration.
*/

/** Process DAP Vendor Command and prepare Response Data
\param request   pointer to request data
\param response  pointer to response data
\return          number of bytes in response (lower 16 bits)
                 number of bytes in request (upper 16 bits)
*/
uint32_t DAP_ProcessVendorCommand(const uint8_t *request, uint8_t *response) {
  uint32_t num = (1U << 16) | 1U;

  *response++ = *request;        // copy Command ID

  switch (*request++) {          // first byte in request is Command ID
    case ID_DAP_Vendor0:
      { // Sampling diagnostics: phase 0/1, or 255 to query without changing.
        uint32_t cfg = swd_read32(SWD_CFG);
        uint32_t fclk = Xil_In32(SLCR_FPGA0_CLK_CTRL);
        uint32_t div0 = (fclk >> 8) & 63U;
        uint32_t div1 = (fclk >> 20) & 63U;
        uint32_t hz = (div0 && div1) ? IO_PLL_HZ / div0 / div1 : 0;
        uint8_t status = DAP_OK;
        uint32_t i;
        if (*request <= 1U) {
          if ((swd_read32(SWD_BASE_ADDR + 4U) & 1U) ||
              (swd_read32(SWD_BASE_ADDR + 0x34U) & 1U)) status = DAP_ERROR;
          else {
            cfg = (cfg & ~(1U << 17)) | ((uint32_t)*request << 17);
            swd_write32(SWD_CFG, cfg);
          }
        } else if (*request != 255U) status = DAP_ERROR;
        *response++ = status;
        *response++ = (cfg >> 17) & 1U;
        *response++ = 0;
        for (i=0; i<4; ++i) *response++ = (uint8_t)(hz >> (8*i));
        for (i=0; i<4; ++i) *response++ = (uint8_t)(cfg >> (8*i));
        num = (2U << 16) | 12U;
      }
      break;

    case ID_DAP_Vendor1:
      { // Aggregate profiling, default off: 1=clear/start, 0=stop/read, 2=read.
        uint32_t values[14], i;
        uint64_t ticks[3];
        if (*request == 1U) {
          memset((void *)&dap_profile, 0, sizeof dap_profile);
          DAP_SWD_StatsClear();
          memset((void *)dap_metrics,0,sizeof dap_metrics);
          dap_profile.enabled = 1;
        } else if (*request == 0U) dap_profile.enabled = 0;
        *response++ = (*request <= 2U) ? DAP_OK : DAP_ERROR;
        values[0] = COUNTS_PER_SECOND;
        dap_swd_stats_snapshot(values+1);
        values[9] = dap_profile.batch_calls;
        values[10] = dap_profile.upload_calls;
        values[11] = dap_profile.download_calls;
        values[12] = dap_profile.upload_bytes;
        values[13] = dap_profile.download_bytes;
        for (i=0; i<14; ++i) {memcpy(response, values+i, 4); response+=4;}
        ticks[0]=dap_profile.batch_ticks;
        ticks[1]=dap_profile.upload_ticks;
        ticks[2]=dap_profile.download_ticks;
        memcpy(response,ticks,sizeof ticks);
        num = (2U << 16) | 82U;
      }
      break;
    case ID_DAP_Vendor5:
      { // Data receive window: 0=legacy, 1=early, 255=query.
        uint32_t cfg = swd_read32(SWD_CFG);
        uint8_t status = DAP_OK;
        if (*request <= 1U) {
          if ((swd_read32(SWD_BASE_ADDR + 4U) & 1U) ||
              (swd_read32(SWD_BASE_ADDR + 0x34U) & 1U) ||
              (swd_read32(SWD_BASE_ADDR + 0x48U) & 1U)) status = DAP_ERROR;
          else {
            swd_write32(SWD_CFG, (cfg & ~(1U << 28)) | ((uint32_t)*request << 28));
            cfg = swd_read32(SWD_CFG);
          }
        } else if (*request != 255U) status = DAP_ERROR;
        *response++ = status;
        *response++ = (uint8_t)((cfg >> 28) & 1U);
        num = (2U << 16) | 3U;
      }
      break;
    case ID_DAP_Vendor4:
      { // ACK high-phase hold in FCLK cycles (0..7), 255 to query.
        uint32_t cfg = swd_read32(SWD_CFG);
        uint8_t status = DAP_OK;
        if (*request <= 7U) {
          if ((swd_read32(SWD_BASE_ADDR + 4U) & 1U) ||
              (swd_read32(SWD_BASE_ADDR + 0x34U) & 1U) ||
              (swd_read32(SWD_BASE_ADDR + 0x48U) & 1U)) status = DAP_ERROR;
          else {
            cfg = (cfg & ~(0x7U << 25)) | ((uint32_t)*request << 25);
            swd_write32(SWD_CFG, cfg);
            cfg = swd_read32(SWD_CFG);
          }
        } else if (*request != 255U) status = DAP_ERROR;
        *response++ = status;
        *response++ = (uint8_t)((cfg >> 25) & 0x7U);
        num = (2U << 16) | 3U;
      }
      break;
    case ID_DAP_Vendor3:
      { // Extra turnaround cycles before ACK (0..3), 255 to query.
        uint32_t cfg = swd_read32(SWD_CFG);
        uint8_t status = DAP_OK;
        if (*request <= 3U) {
          if ((swd_read32(SWD_BASE_ADDR + 4U) & 1U) ||
              (swd_read32(SWD_BASE_ADDR + 0x34U) & 1U)) status = DAP_ERROR;
          else {
            cfg = (cfg & ~(0x3U << 23)) | ((uint32_t)*request << 23);
            swd_write32(SWD_CFG, cfg);
          }
        } else if (*request != 255U) status = DAP_ERROR;
        *response++ = status;
        *response++ = (uint8_t)((cfg >> 23) & 0x3U);
        num = (2U << 16) | 3U;
      }
      break;
    case ID_DAP_Vendor2:  break;
    case ID_DAP_Vendor6:
      { // v1 stage metrics; record={ticks64,calls32,bytes32}.
        uint32_t hz=COUNTS_PER_SECOND;
        *response++=DAP_OK;*response++=1;*response++=MET_COUNT;
        memcpy(response,&hz,4);response+=4;
        memcpy(response,(const void *)dap_metrics,sizeof dap_metrics);
        num=(1U<<16)|(8U+sizeof dap_metrics);
      }
      break;
    case ID_DAP_Vendor7:
      {
        uint32_t state[12];
        extern void chry_dap_queue_snapshot(uint32_t out[8]);
        chry_dap_queue_snapshot(state);
        state[8]=swd_read32(SWD_STATUS);
        state[9]=swd_read32(SWD_BATCH_STATUS);
        state[10]=swd_read32(SWD_PACKET_STATUS);
        state[11]=swd_read32(SWD_CFG);
        *response++=DAP_OK;memcpy(response,state,sizeof state);
        num=(1U<<16)|(2U+sizeof state);
      }
      break;
    case ID_DAP_Vendor8:
      {
        uint32_t state,i;
        if(*request==1)swd_write32(SWD_BASE_ADDR+0x54U,1U);
        state=swd_read32(SWD_BASE_ADDR+0x54U);
        *response++=DAP_OK;memcpy(response,&state,4);response+=4;
        for(i=0;i<16;i++){
          swd_write32(SWD_BASE_ADDR+0x58U,i);
          state=swd_read32(SWD_BASE_ADDR+0x5cU);
          memcpy(response,&state,4);response+=4;
        }
        num=(2U<<16)|70U;
      }
      break;
    case ID_DAP_Vendor9:  break;
    case ID_DAP_Vendor10: break;
    case ID_DAP_Vendor11: break;
    case ID_DAP_Vendor12: break;
    case ID_DAP_Vendor13: break;
    case ID_DAP_Vendor14: break;
    case ID_DAP_Vendor15: break;
    case ID_DAP_Vendor16: break;
    case ID_DAP_Vendor17: break;
    case ID_DAP_Vendor18: break;
    case ID_DAP_Vendor19: break;
    case ID_DAP_Vendor20: break;
    case ID_DAP_Vendor21: break;
    case ID_DAP_Vendor22: break;
    case ID_DAP_Vendor23: break;
    case ID_DAP_Vendor24: break;
    case ID_DAP_Vendor25: break;
    case ID_DAP_Vendor26: break;
    case ID_DAP_Vendor27: break;
    case ID_DAP_Vendor28: break;
    case ID_DAP_Vendor29: break;
    case ID_DAP_Vendor30: break;
    case ID_DAP_Vendor31: break;
  }

  return (num);
}

///@}
