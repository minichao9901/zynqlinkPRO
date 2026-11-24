#pragma once
#include <stdbool.h>
#include <stdint.h>

#ifdef TARGET_HPM
#include "hpm_common.h"
#define SHARED ATTR_PLACE_AT_NONCACHEABLE_BSS_WITH_ALIGNMENT(32)
static inline void publish(void) { __asm__ volatile ("fence rw,rw" ::: "memory"); }
#else
#define SHARED __attribute__((aligned(32)))
static inline void publish(void) { __asm__ volatile ("dmb" ::: "memory"); }
#endif

extern volatile uint32_t g_cpu_hz, g_hclk_hz, g_clock_error, g_fixture_ready;
uint32_t target_clock_init(void);
uint32_t target_tick(void);
uint32_t target_tick_hz(void);
void rtt_init(void);
void rtt_terminal_poll(void);
void rtt_produce(void);
void debug_observables_init(void);
void debug_observables_poll(void);
