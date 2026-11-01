#include <assert.h>
#include <stdint.h>
#include <stdio.h>
uint32_t Xil_In32(uintptr_t);
void Xil_Out32(uintptr_t,uint32_t);
#define DAP_FIXED_FCLK0_TEST 1
#include "../../firmware/xusbps_daplink_dma/DAP/Include/ps_fclk.h"
static uint32_t control,arm=0x28008,ddr=0x20008,io=0x36008,boot;
static unsigned writes;
uint32_t Xil_In32(uintptr_t address) {
    switch(address) {
    case 0xf8000170U:return control;
    case 0xf8000100U:return arm;
    case 0xf8000104U:return ddr;
    case 0xf8000108U:return io;
    case 0xf800025cU:return boot;
    case 0xf800010cU:return 0x3f;
    default:assert(!"Unexpected clock-register read");return 0;
    }
}
void Xil_Out32(uintptr_t address,uint32_t value) {
    assert(address==0xf8000008U || address==0xf8000004U || address==0xf8000170U);
    writes++;
    if(address==0xf8000170U)control=value;
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
    control=(1U<<8)|(15U<<20);
    assert(ps_fixed133_select()==133333332 && writes==3);
    assert(((control>>4)&3)==2);
    assert(ps_fixed133_select()==133333332 && writes==3); /* no clock glitch writes */
    arm|=16;assert(ps_fixed133_select()==-1 && writes==3);arm&=~16U;
    assert(ps_fixed_half_period(133333332,66666666)==1);
    assert(ps_fixed_half_period(133333332,60000000)==2);
    assert(ps_fixed_half_period(133333332,33333333)==2);
    assert(ps_fixed_half_period(133333332,25000000)==3);
    assert(ps_fixed_half_period(133333332,1000000)==67);
    assert(ps_fixed_half_period(133333332,250000)==0);
    assert(ps_fixed_half_period(133333332,0)==0);
    puts("PS clock source/divisor/bypass/invalid-state checks passed");
    return 0;
}
