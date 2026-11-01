#ifndef ZYNQLINK_PS_FCLK_H
#define ZYNQLINK_PS_FCLK_H
#include <stdint.h>

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
#endif
