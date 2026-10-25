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
 * Title:        SW_DP.c CMSIS-DAP SW DP I/O
 *
 *---------------------------------------------------------------------------*/

#include "DAP_config.h"
#include "DAP.h"
#include "xil_io.h"   

#define DAP_HOT_CODE __attribute__((section(".ocm_text")))


// 假设基地址通过设备树或参数传入
#define SWD_BASE_ADDR       0x40010000  // 根据实际 Vivado 配置调整

#define SWD_CTRL            (SWD_BASE_ADDR + 0x00)  // [15:8]=XFER_REQUEST
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

// XFER_CMD_STS register bit fields
#define XFER_CMD_STS_START          (1ULL << 0)
#define XFER_CMD_STS_MODE           (1ULL << 1)
#define XFER_CMD_STS_TIMESTAMP_EN   (1ULL << 2)
#define XFER_CMD_STS_REQUEST        (8)


// // AXI-Lite 读写函数 (使用 /dev/mem 或 mmap)
// static inline void swd_write32(uint32_t addr, uint32_t value) {
//     *(volatile uint32_t *)addr = value;
// }

// static inline uint32_t swd_read32(uint32_t addr) {
//     return *(volatile uint32_t *)addr;
// }

// // 等待操作完成
// static void swd_wait_idle(void) {
//     while (swd_read32(SWD_CTRL) & 0x01);
// }



// SW Macros

#define PIN_SWCLK_SET PIN_SWCLK_TCK_SET
#define PIN_SWCLK_CLR PIN_SWCLK_TCK_CLR

#define SW_CLOCK_CYCLE()                \
  PIN_SWCLK_CLR();                      \
  PIN_DELAY();                          \
  PIN_SWCLK_SET();                      \
  PIN_DELAY()

#define SW_WRITE_BIT(bit)               \
  PIN_SWDIO_OUT(bit);                   \
  PIN_SWCLK_CLR();                      \
  PIN_DELAY();                          \
  PIN_SWCLK_SET();                      \
  PIN_DELAY()

#define SW_READ_BIT(bit)                \
  PIN_SWCLK_CLR();                      \
  PIN_DELAY();                          \
  bit = PIN_SWDIO_IN();                 \
  PIN_SWCLK_SET();                      \
  PIN_DELAY()

#define PIN_DELAY() PIN_DELAY_SLOW(DAP_Data.clock_delay)


// Generate SWJ Sequence
//   count:  sequence bit count
//   data:   pointer to sequence bit data
//   return: none
#if ((DAP_SWD != 0) || (DAP_JTAG != 0))
static void SWJ_SequenceChunk (uint32_t count, const uint8_t *data) {
  uint32_t w0, w1, w2, w3, w4, w5, w6, w7;

  w0 = ((const uint32_t *)data)[0];
  w1 = ((const uint32_t *)data)[1];
  w2 = ((const uint32_t *)data)[2];
  w3 = ((const uint32_t *)data)[3];
  w4 = ((const uint32_t *)data)[4];
  w5 = ((const uint32_t *)data)[5];
  w6 = ((const uint32_t *)data)[6];
  w7 = ((const uint32_t *)data)[7];

  // xil_printf("%d, %08x, %08x, %08x, %08x, %08x, %08x, %08x, %08x\n",
            //  count, w0, w1, w2, w3, w4, w5, w6, w7);

  swd_write32(SWD_SWJ_DATA0, w0);
  swd_write32(SWD_SWJ_DATA1, w1);
  swd_write32(SWD_SWJ_DATA2, w2);
  swd_write32(SWD_SWJ_DATA3, w3);
  swd_write32(SWD_SWJ_DATA4, w4);
  swd_write32(SWD_SWJ_DATA5, w5);
  swd_write32(SWD_SWJ_DATA6, w6);
  swd_write32(SWD_SWJ_DATA7, w7);
  swd_write32(SWD_SWJ_COUNT, count);
  swd_write32(SWD_CTRL, 0x01);
  swd_wait_idle();
}

void SWJ_Sequence (uint32_t count, const uint8_t *data) {
  SWJ_SequenceChunk(count, data);
}
#endif


// Generate SWD Sequence
//   info:   sequence information
//   swdo:   pointer to SWDIO generated data
//   swdi:   pointer to SWDIO captured data
//   return: none
#if (DAP_SWD != 0)
void SWD_Sequence (uint32_t info, const uint8_t *swdo, uint8_t *swdi) {
  uint32_t val;
  uint32_t bit;
  uint32_t n, k;

  n = info & SWD_SEQUENCE_CLK;
  if (n == 0U) {
    n = 64U;
  }

  if (info & SWD_SEQUENCE_DIN) {
    while (n) {
      val = 0U;
      for (k = 8U; k && n; k--, n--) {
        SW_READ_BIT(bit);
        val >>= 1;
        val  |= bit << 7;
      }
      val >>= k;
      *swdi++ = (uint8_t)val;
    }
  } else {
    while (n) {
      val = *swdo++;
      for (k = 8U; k && n; k--, n--) {
        SW_WRITE_BIT(val);
        val >>= 1;
      }
    }
  }
}
#endif


#if (DAP_SWD != 0)


// SWD Transfer I/O
//   request: A[3:2] RnW APnDP
//   data:    DATA[31:0]
//   return:  ACK[2:0]
#define SWD_TransferFunction(speed)     /**/                                    \
static uint8_t SWD_Transfer##speed (uint32_t request, uint32_t *data) {         \
  uint32_t ack;                                                                 \
  uint32_t bit;                                                                 \
  uint32_t val;                                                                 \
  uint32_t parity;                                                              \
                                                                                \
  uint32_t n;                                                                   \
                                                                                \
  /* Packet Request */                                                          \
  parity = 0U;                                                                  \
  SW_WRITE_BIT(1U);                     /* Start Bit */                         \
  bit = request >> 0;                                                           \
  SW_WRITE_BIT(bit);                    /* APnDP Bit */                         \
  parity += bit;                                                                \
  bit = request >> 1;                                                           \
  SW_WRITE_BIT(bit);                    /* RnW Bit */                           \
  parity += bit;                                                                \
  bit = request >> 2;                                                           \
  SW_WRITE_BIT(bit);                    /* A2 Bit */                            \
  parity += bit;                                                                \
  bit = request >> 3;                                                           \
  SW_WRITE_BIT(bit);                    /* A3 Bit */                            \
  parity += bit;                                                                \
  SW_WRITE_BIT(parity);                 /* Parity Bit */                        \
  SW_WRITE_BIT(0U);                     /* Stop Bit */                          \
  SW_WRITE_BIT(1U);                     /* Park Bit */                          \
                                                                                \
  /* Turnaround */                                                              \
  PIN_SWDIO_OUT_DISABLE();                                                      \
  for (n = DAP_Data.swd_conf.turnaround; n; n--) {                              \
    SW_CLOCK_CYCLE();                                                           \
  }                                                                             \
                                                                                \
  /* Acknowledge response */                                                    \
  SW_READ_BIT(bit);                                                             \
  ack  = bit << 0;                                                              \
  SW_READ_BIT(bit);                                                             \
  ack |= bit << 1;                                                              \
  SW_READ_BIT(bit);                                                             \
  ack |= bit << 2;                                                              \
                                                                                \
  if (ack == DAP_TRANSFER_OK) {         /* OK response */                       \
    /* Data transfer */                                                         \
    if (request & DAP_TRANSFER_RnW) {                                           \
      /* Read data */                                                           \
      val = 0U;                                                                 \
      parity = 0U;                                                              \
      for (n = 32U; n; n--) {                                                   \
        SW_READ_BIT(bit);               /* Read RDATA[0:31] */                  \
        parity += bit;                                                          \
        val >>= 1;                                                              \
        val  |= bit << 31;                                                      \
      }                                                                         \
      SW_READ_BIT(bit);                 /* Read Parity */                       \
      if ((parity ^ bit) & 1U) {                                                \
        ack = DAP_TRANSFER_ERROR;                                               \
      }                                                                         \
      if (data) { *data = val; }                                                \
      /* Turnaround */                                                          \
      for (n = DAP_Data.swd_conf.turnaround; n; n--) {                          \
        SW_CLOCK_CYCLE();                                                       \
      }                                                                         \
      PIN_SWDIO_OUT_ENABLE();                                                   \
    } else {                                                                    \
      /* Turnaround */                                                          \
      for (n = DAP_Data.swd_conf.turnaround; n; n--) {                          \
        SW_CLOCK_CYCLE();                                                       \
      }                                                                         \
      PIN_SWDIO_OUT_ENABLE();                                                   \
      /* Write data */                                                          \
      val = *data;                                                              \
      parity = 0U;                                                              \
      for (n = 32U; n; n--) {                                                   \
        SW_WRITE_BIT(val);              /* Write WDATA[0:31] */                 \
        parity += val;                                                          \
        val >>= 1;                                                              \
      }                                                                         \
      SW_WRITE_BIT(parity);             /* Write Parity Bit */                  \
    }                                                                           \
    /* Capture Timestamp */                                                     \
    if (request & DAP_TRANSFER_TIMESTAMP) {                                     \
      DAP_Data.timestamp = TIMESTAMP_GET();                                     \
    }                                                                           \
    /* Idle cycles */                                                           \
    n = DAP_Data.transfer.idle_cycles;                                          \
    if (n) {                                                                    \
      PIN_SWDIO_OUT(0U);                                                        \
      for (; n; n--) {                                                          \
        SW_CLOCK_CYCLE();                                                       \
      }                                                                         \
    }                                                                           \
    PIN_SWDIO_OUT(1U);                                                          \
    return ((uint8_t)ack);                                                      \
  }                                                                             \
                                                                                \
  if ((ack == DAP_TRANSFER_WAIT) || (ack == DAP_TRANSFER_FAULT)) {              \
    /* WAIT or FAULT response */                                                \
    if (DAP_Data.swd_conf.data_phase && ((request & DAP_TRANSFER_RnW) != 0U)) { \
      for (n = 32U+1U; n; n--) {                                                \
        SW_CLOCK_CYCLE();               /* Dummy Read RDATA[0:31] + Parity */   \
      }                                                                         \
    }                                                                           \
    /* Turnaround */                                                            \
    for (n = DAP_Data.swd_conf.turnaround; n; n--) {                            \
      SW_CLOCK_CYCLE();                                                         \
    }                                                                           \
    PIN_SWDIO_OUT_ENABLE();                                                     \
    if (DAP_Data.swd_conf.data_phase && ((request & DAP_TRANSFER_RnW) == 0U)) { \
      PIN_SWDIO_OUT(0U);                                                        \
      for (n = 32U+1U; n; n--) {                                                \
        SW_CLOCK_CYCLE();               /* Dummy Write WDATA[0:31] + Parity */  \
      }                                                                         \
    }                                                                           \
    PIN_SWDIO_OUT(1U);                                                          \
    return ((uint8_t)ack);                                                      \
  }                                                                             \
                                                                                \
  /* Protocol error */                                                          \
  for (n = DAP_Data.swd_conf.turnaround + 32U + 1U; n; n--) {                   \
    SW_CLOCK_CYCLE();                   /* Back off data phase */               \
  }                                                                             \
  PIN_SWDIO_OUT_ENABLE();                                                       \
  PIN_SWDIO_OUT(1U);                                                            \
  return ((uint8_t)ack);                                                        \
}


#undef  PIN_DELAY
#define PIN_DELAY() PIN_DELAY_FAST()
SWD_TransferFunction(Fast)

#undef  PIN_DELAY
#define PIN_DELAY() PIN_DELAY_SLOW(DAP_Data.clock_delay)
SWD_TransferFunction(Slow)


// SWD Transfer I/O
//   request: A[3:2] RnW APnDP
//   data:    DATA[31:0]
//   return:  ACK[2:0]

#if 0
uint8_t DAP_HOT_CODE SWD_Transfer(uint32_t request, uint32_t *data) 
{
  uint32_t cmd;
  uint32_t status;
  uint8_t ack;

  cmd = ((uint32_t)(request & 0xFF) << XFER_CMD_STS_REQUEST) |
          XFER_CMD_STS_MODE |
          XFER_CMD_STS_START;

  // 写数据（如果是写操作）
  if (!(request & 0x02)) {
      swd_write32(SWD_SWJ_DATA1, *data);
  }

  // 启动传输
  swd_write32(SWD_CTRL, cmd);

  // 等待完成并读取状态
  do {
      status = swd_read32(SWD_STATUS);
  } while (status & 0x01);

  ack = (status >> 1) & 0x07;

  // 读数据（如果是成功的读操作）
  if ((ack == 0x01) && (request & 0x02)) {
      *data = swd_read32(SWD_SWJ_DATA2);
  }

  return ack;
}
#endif


uint8_t DAP_HOT_CODE SWD_Transfer(uint32_t request, uint32_t *data) 
{
  register volatile uint32_t *swd_base = (volatile uint32_t *)SWD_BASE_ADDR;
  register uint32_t cmd;
  register uint32_t status;
  register uint8_t ack;

  cmd = ((request & 0xFF) << XFER_CMD_STS_REQUEST) | XFER_CMD_STS_MODE | XFER_CMD_STS_START;

  // 写数据（如果是写操作）
  if (!(request & 0x02)) {
      swd_base[5] = *data;  // SWD_SWJ_DATA1 = base + 0x14
  }

  // 启动传输
  swd_base[0] = cmd;  // SWD_CTRL = base + 0x00

  // 等待完成并读取状态 - 使用数组索引让编译器优化地址计算
  do {
      status = swd_base[1];  // SWD_STATUS = base + 0x04
  } while (__builtin_expect(status & 0x01, 0));

  ack = (status >> 1) & 0x07;

  // 读数据（如果是成功的读操作）
  if (__builtin_expect((ack == 0x01) && (request & 0x02) && data != NULL, 0)) {
      *data = swd_base[6];  // SWD_SWJ_DATA2 = base + 0x18
  }

  if (status & 0x80U) ack = DAP_TRANSFER_ERROR;

  // xil_printf("%x, %x\n", ack, *data);
  return ack;
}

#endif  /* (DAP_SWD != 0) */

