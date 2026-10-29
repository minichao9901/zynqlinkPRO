#ifndef JTAG_RTL_H
#define JTAG_RTL_H
#include <stdint.h>
#define JTAG_ROUTE 0x40010080U
#define JTAG_IR_CONFIG 0x40010084U
#define JTAG_DR_CONFIG 0x40010088U
#define JTAG_OPERATION 0x4001008cU
#define JTAG_SEQ_TMS_REG 0x40010090U
#define JTAG_PINS 0x40010094U
#define JTAG_TIMING 0x40010098U
#define JTAG_CACHED_IR 0x4001009cU
#define JTAG_RX_DATA 0x400100a0U
#define JTAG_STAT_CYCLES 0x400100c0U
#define JTAG_STAT_BITS 0x400100c4U
#define JTAG_STAT_TRANSFERS 0x400100c8U
int DAP_JTAG_Select(uint32_t index);
int DAP_JTAG_AutoConfigure(void);
void DAP_JTAG_ClockChanged(void);
void DAP_JTAG_SetTiming(uint32_t value);
uint8_t DAP_JTAG_MemTransfer(uint32_t request,uint32_t *data);
uint32_t DAP_JTAG_RouteWord(void);
#endif
