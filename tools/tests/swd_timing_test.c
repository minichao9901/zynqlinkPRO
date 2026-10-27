#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "swd_timing.h"
static uint32_t active[8]={0,65536,393216,65536,65536,0,0,0x20a11},shadow[8];
static uint32_t status,clock_reg=(18U<<20)|(1U<<8),signature=SWD_TIMING_SIGNATURE;
static unsigned writes,clock_writes;
static int fail_clock;
uint32_t Xil_In32(uintptr_t a) {
    if(a==0xf8000170U)return clock_reg;
    if(a==SWD_TIMING_VERSION)return signature;
    if(a==SWD_TIMING_STATUS)return status;
    assert(a>=SWD_TIMING_BASE && a<SWD_TIMING_CMD);
    return active[(a-SWD_TIMING_BASE)/4];
}
void Xil_Out32(uintptr_t a,uint32_t v) {
    if(a==0xf8000170U){clock_reg=v;return;}
    if(a==0xf8000008U || a==0xf8000004U)return;
    writes++;
    if(a==SWD_TIMING_CMD) {
        if(status&1U){status=(status&0xffff0001U)|0x100;return;}
        if(v==1){memcpy(active,shadow,sizeof active);status=((status>>16)+1U)<<16;}
        else if(v==4){active[0]=0;status=((status>>16)+1U)<<16;}
        else assert(0);
    } else {assert(a>=SWD_TIMING_BASE && a<SWD_TIMING_CMD);shadow[(a-SWD_TIMING_BASE)/4]=v;}
}
int ps_set_fclk0_hz(uint32_t hz) {
    clock_writes++;if(fail_clock)return -1;
    uint32_t divisor=(1800000000U+hz-1U)/hz;
    assert(divisor>0 && divisor<=63);clock_reg=(divisor<<20)|(1U<<8);
    return 1800000000U/divisor;
}
int main(void) {
    uint32_t c[8],saved[8];
    assert(swd_timing_snapshot(c));memcpy(saved,c,sizeof c);
    assert(!swd_timing_enabled() && swd_timing_clock(50000000)==0);
    c[0]=1;assert(swd_timing_apply(c,120000000)==0 && swd_timing_enabled());
    assert(swd_timing_fclk()==120000000 && clock_writes==1);
    assert(swd_timing_clock(50000000)==1 && active[1]==78644);
    assert((uint64_t)swd_timing_fclk()*65536 <= 2ULL*50000000*active[1]);
    assert(swd_timing_clock(70000000)==-1);
    memcpy(saved,active,sizeof saved);fail_clock=1;c[1]=131072;
    assert(swd_timing_apply(c,100000000)==-1 && !memcmp(active,saved,sizeof saved));
    fail_clock=0;
    unsigned n=writes,k=clock_writes;status|=1;
    assert(swd_timing_apply(c,100000000)==-1 && writes==n && clock_writes==k);
    assert(swd_timing_disable()==-1 && writes==n);
    status&=~1U;c[1]=65535;
    assert(swd_timing_apply(c,0)==-1 && writes==n);
    c[1]=131072;c[3]=2;
    assert(swd_timing_apply(c,0)==-1);c[3]=1;c[4]=(3U<<17)|65536U;
    assert(swd_timing_apply(c,0)==0 && active[3]==1 && active[4]==c[4]);
    // Save/restore is exactly the operation used by the service context adapter.
    assert(swd_timing_apply(saved,0)==0 && !memcmp(active,saved,sizeof saved));
    assert(swd_timing_disable()==0);
    signature=0;n=writes;
    assert(!swd_timing_snapshot(c) && swd_timing_apply(saved,0)==-1 && writes==n);
    puts("PASS production timing C: profile/clock, ceil-Q16, busy/invalid/old-bit rejection, snapshot/restore");
    return 0;
}
