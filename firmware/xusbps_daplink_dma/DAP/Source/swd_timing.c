#include "DAP_config.h"
#include "swd_timing.h"

static int present(void) {return swd_read32(SWD_TIMING_VERSION)==SWD_TIMING_SIGNATURE;}
uint32_t swd_timing_fclk(void) {
    uint32_t c=Xil_In32(SLCR_FPGA0_CLK_CTRL),a=(c>>8)&63U,b=(c>>20)&63U;
    return a && b ? IO_PLL_HZ/a/b : 0;
}
int swd_timing_snapshot(uint32_t out[SWD_TIMING_WORDS]) {
    if(!present()) return 0;
    for(unsigned i=0;i<SWD_TIMING_WORDS;i++)out[i]=swd_read32(SWD_TIMING_BASE+i*4U);
    return 1;
}
int swd_timing_enabled(void) {return present() && (swd_read32(SWD_TIMING_BASE)&1U);}
static int valid(const uint32_t *c) {
    uint32_t aq=c[5] ? c[5] : c[1];
    return !(c[0]&~1U) && c[1]>=65536U && c[2]>=65536U &&
        (!c[5] || c[5]>=65536U) && (!c[6] || c[6]>=65536U) &&
        !(c[3]&0xfff80000U) && !(c[4]&0xfff80000U) &&
        ((c[3]&65536U) || (c[3]&65535U)<(aq>>16)) &&
        ((c[4]&65536U) || (c[4]&65535U)<(c[1]>>16)) &&
        !(c[7]&0xf07c000eU);
}
int swd_timing_apply(const uint32_t c[SWD_TIMING_WORDS],uint32_t fclk_hz) {
    if(!present() || !valid(c) || (swd_read32(SWD_TIMING_STATUS)&1U) ||
       (fclk_hz && (fclk_hz<500000U || fclk_hz>120000000U)))return -1;
    uint32_t previous[SWD_TIMING_WORDS],old_clock=Xil_In32(SLCR_FPGA0_CLK_CTRL);
    if(fclk_hz && !swd_timing_snapshot(previous))return -1;
    uint32_t before=swd_read32(SWD_TIMING_STATUS)>>16;
    for(unsigned i=0;i<SWD_TIMING_WORDS;i++)swd_write32(SWD_TIMING_BASE+i*4U,c[i]);
    swd_write32(SWD_TIMING_CMD,1U);
    uint32_t status=swd_read32(SWD_TIMING_STATUS);
    if((status>>16)!=((before+1U)&65535U) || (status&0xff00U))return -1;
    // DAP vendor commands and service setup run serially in the PS main loop.
    // The hardware commit rejected any active packet/sampler/RTT owner above.
    if(fclk_hz && ps_set_fclk0_hz(fclk_hz)<=0) {
        Xil_Out32(0xf8000008U,0xdf0dU);Xil_Out32(SLCR_FPGA0_CLK_CTRL,old_clock);
        Xil_Out32(0xf8000004U,0x767bU);
        (void)swd_timing_apply(previous,0);
        return -1;
    }
    return 0;
}
int swd_timing_disable(void) {
    if(!present() || (swd_read32(SWD_TIMING_STATUS)&1U))return -1;
    uint32_t before=swd_read32(SWD_TIMING_STATUS)>>16;
    swd_write32(SWD_TIMING_CMD,4U);
    uint32_t status=swd_read32(SWD_TIMING_STATUS);
    return (swd_read32(SWD_TIMING_BASE)&1U) || (status&0xff00U) ||
        (status>>16)!=((before+1U)&65535U) ? -1 : 0;
}
int swd_timing_clock(uint32_t hz) {
    uint32_t c[SWD_TIMING_WORDS];
    if(!swd_timing_enabled())return 0;
    uint32_t fclk=swd_timing_fclk();
    if(!hz || !fclk || hz>fclk/2U || !swd_timing_snapshot(c))return -1;
    uint64_t denominator=2ULL*hz;
    uint64_t q=(((uint64_t)fclk<<16)+denominator-1U)/denominator;
    if(q>UINT32_MAX)return -1;
    c[1]=(uint32_t)q;
    return swd_timing_apply(c,0) ? -1 : 1;
}
