#include <assert.h>
#include <stdint.h>
#include <stdio.h>
uint32_t Xil_In32(uintptr_t);
#include "../../firmware/xusbps_daplink_dma/DAP/Include/ps_fclk.h"
static uint32_t control,arm=0x28008,ddr=0x20008,io=0x36008,boot;
uint32_t Xil_In32(uintptr_t address) {
    switch(address) {
    case 0xf8000170U:return control;
    case 0xf8000100U:return arm;
    case 0xf8000104U:return ddr;
    case 0xf8000108U:return io;
    case 0xf800025cU:return boot;
    default:assert(!"Unexpected clock-register read");return 0;
    }
}
int main(void) {
    control=(1U<<8)|(15U<<20);assert(ps_fclk0_hz()==119999998U);
    control|=1U<<4;assert(ps_fclk0_hz()==119999998U);
    control=(2U<<4)|(10U<<8)|(1U<<20);assert(ps_fclk0_hz()==133333332U);
    control=(3U<<4)|(8U<<8)|(1U<<20);assert(ps_fclk0_hz()==133333332U);
    control=(2U<<4)|(1U<<8)|(1U<<20);boot=16;
    assert(ps_fclk0_hz()==33333333U);boot=0;
    arm|=1;assert(ps_fclk0_hz()==0);arm&=~1U;
    control=(2U<<4)|(10U<<8);assert(ps_fclk0_hz()==0);
    puts("PS clock source/divisor/bypass/invalid-state checks passed");
    return 0;
}
