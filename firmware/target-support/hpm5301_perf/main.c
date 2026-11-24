// SRAM-only performance fixture. Does not touch the SoC JTAG pin mux or flash.
#include "board.h"
#include "hpm_clock_drv.h"
#include "hpm_mchtmr_drv.h"
#include <stdint.h>

#define STATE ((volatile uint32_t *)0xF0400000U)
#define RTT ((volatile uint32_t *)0xF0400200U)
#define RING ((volatile uint32_t *)0xF0401000U)

static inline uint32_t cycles(void) {
    uint32_t v;
    __asm__ volatile("csrr %0, mcycle" : "=r"(v));
    return v;
}

int main(void) {
    __asm__ volatile("csrw mie, zero\ncsrci mstatus, 8" ::: "memory");
    board_init_clock(); // SDK: CPU 360 MHz, AHB 120 MHz, mchtmr 24 MHz.
    STATE[0] = 0x48504D50U;
    STATE[1] = clock_get_frequency(clock_cpu0);
    STATE[2] = clock_get_frequency(clock_ahb);
    STATE[3] = clock_get_frequency(clock_mchtmr0);
    STATE[4] = 0;
    STATE[5] = 0;
    STATE[6] = 0;
    STATE[16] = 0; // Producer enable, controlled through SBA.
    STATE[17] = 0; // Stop acknowledgement: producer is between complete publishes.
    uint32_t next = 0;
    uint64_t t0 = mchtmr_get_count(HPM_MCHTMR);
    uint32_t c0 = cycles();
    for (;;) {
        if (STATE[16]) {
            STATE[17] = 0;
            uint32_t wr = RTT[9];
            uint32_t after = (wr + 4U) & 8191U;
            if (after != RTT[10]) {
                RING[wr >> 2] = next++;
                __asm__ volatile("fence rw,w" ::: "memory");
                RTT[9] = after;
                STATE[6] = next;
            }
        } else {
            STATE[17] = 1;
            next = 0;
        }
        STATE[4]++;
        uint64_t now = mchtmr_get_count(HPM_MCHTMR);
        if (now - t0 >= 240000U) {
            uint32_t c1 = cycles();
            STATE[5] = (uint32_t)(((uint64_t)(c1 - c0) * STATE[3]) / (now - t0));
            t0 = now;
            c0 = c1;
        }
    }
}
