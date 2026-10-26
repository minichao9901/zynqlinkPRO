#ifndef PROBE_TARGET_PLATFORM_H
#define PROBE_TARGET_PLATFORM_H
#include "probe_host_platform.h"
#define DAP_PORT_SWD 1
#define DAP_PORT_JTAG 2
#define XSLCR_UNLOCK_ADDR 0xf8000008U
#define XSLCR_UNLOCK_CODE 0xdf0dU
#define SLCR_FPGA0_CLK_CTRL 0xf8000170U
#define SLCR_LOCK_ADDR 0xf8000004U
#define SWD_CFG 0x40010008U
#define IO_PLL_HZ 1000000000U
typedef struct {uint32_t debug_port,clock_delay,fast_clock;} DAP_Data_t;
extern DAP_Data_t DAP_Data;
static inline uint32_t swd_read32(uintptr_t a) {return Xil_In32(a);}
static inline void swd_write32(uintptr_t a,uint32_t d) {Xil_Out32(a,d);}
uint8_t SWD_Transfer(uint32_t,uint32_t *);
uint32_t DAP_ExecuteCommand(const uint8_t *,uint8_t *);
#endif
