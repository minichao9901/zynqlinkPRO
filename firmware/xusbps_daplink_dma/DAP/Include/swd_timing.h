#ifndef SWD_TIMING_H
#define SWD_TIMING_H
#include <stdint.h>
#define SWD_TIMING_BASE 0x400100d0U
#define SWD_TIMING_CMD 0x400100f0U
#define SWD_TIMING_STATUS 0x400100f4U
#define SWD_TIMING_VERSION 0x400100f8U
#define SWD_TIMING_SIGNATURE 0x53575431U
#define SWD_TIMING_WORDS 8
int swd_timing_snapshot(uint32_t out[SWD_TIMING_WORDS]);
int swd_timing_apply(const uint32_t config[SWD_TIMING_WORDS],uint32_t fclk_hz);
int swd_timing_disable(void);
int swd_timing_enabled(void);
int swd_timing_clock(uint32_t hz); // 0 legacy, 1 handled, -1 rejected
uint32_t swd_timing_fclk(void);
#endif
