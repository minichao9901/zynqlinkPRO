#ifndef ZYNQLINK_PS_FCLK_H
#define ZYNQLINK_PS_FCLK_H
#include <stdint.h>
#ifndef DAP_FIXED_FCLK0_TEST
#define DAP_FIXED_FCLK0_TEST 0
#endif

/* Read-only clock decoding. FCLK SRCSEL 0/1=IO, 2=ARM, 3=DDR.
 * No PLL, CPU/DDR divider or independent FCLK1 register is written here. */
static inline uint32_t ps_fclk0_hz(void) {
    uint32_t c=Xil_In32(0xf8000170U),source=(c>>4)&3U;
    uint32_t a=(c>>8)&63U,b=(c>>20)&63U;
    uint32_t pll=Xil_In32(source<2 ? 0xf8000108U :
                          source==2 ? 0xf8000100U : 0xf8000104U);
    uint32_t bypass=(pll&8U) ? (Xil_In32(0xf800025cU)&16U) : (pll&16U);
    if (!a || !b || (pll&3U)) return 0;
    uint32_t hz=bypass ? 33333333U : 33333333U*((pll>>12)&127U);
    return hz/a/b;
}

#if DAP_FIXED_FCLK0_TEST || (defined(DAP_MAX_SWCLK_HZ) && DAP_MAX_SWCLK_HZ >= 66666666U)
/* Explicit 133MHz profile: fixed-SWD experiment or opt-in RISC-V top rate.
 * Never retune any PLL, CPU/DDR clock or FCLK1. */
static inline int ps_fixed133_select(void) {
    uint32_t pll=Xil_In32(0xf8000100U);
    if (((pll>>12)&127U)!=40U || (pll&0x13U) ||
        ((pll&8U) && (Xil_In32(0xf800025cU)&16U)) ||
        !(Xil_In32(0xf800010cU)&1U)) return -1;
    uint32_t before=Xil_In32(0xf8000170U);
    uint32_t control=(before&~0x03f03f30U)|0x00100a20U;
    if (before!=control) {
        Xil_Out32(0xf8000008U,0xdf0dU);
        Xil_Out32(0xf8000170U,control);
        Xil_Out32(0xf8000004U,0x767bU);
    }
    return (int)ps_fclk0_hz();
}
static inline uint32_t ps_fixed_half_period(uint32_t fclk,uint32_t requested) {
    if (!requested || requested>0x3fffffffU) return 0;
    uint32_t denominator=requested*2U;
    uint32_t half=(fclk+denominator-1U)/denominator;
    return half && half<=256U ? half : 0;
}
#endif
#endif
