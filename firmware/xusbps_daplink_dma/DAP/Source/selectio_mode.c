#if DAP_SELECTIO
#include "DAP_config.h"
#include "DAP.h"
#include "selectio_mode.h"
#include "etm_ddr_usb.h"
#include "xtime_l.h"
#define SREG 0x80010000U
#define JREG 0x80000000U
#define LIVE (SREG+0x24U)
static uint32_t profile=(33U<<18)|(2U<<14)|(28U<<7)|(24U<<1);
static uint8_t jtap=16, stap=8;

uint32_t selectio_live_hz(void) {return ps_fclk_decode(0xf8000180U)/((selectio_live_config()&(1U<<26)) ? 4U : 2U);}
int selectio_dual_rate(void) {return !!(swd_read32(SWD_FEATURES)&0x8000U);}
int selectio_live_available(void) {return !!(swd_read32(SWD_FEATURES)&0x100U);}
uint32_t selectio_live_config(void) {return selectio_live_available()?swd_read32(LIVE):0;}
int selectio_live_active(void) {return selectio_live_config()&1;}
int selectio_live_set(uint32_t config) {
    if (!selectio_live_available()) return config ? -1 : 0;
    swd_write32(LIVE,config);
    if (swd_read32(LIVE)!=config) return -1;
    XTime start,now;
    XTime_GetTime(&start);
    do { XTime_GetTime(&now); } while(now-start<COUNTS_PER_SECOND/500000U);
    return 0;
}
int selectio_live_profile(unsigned port,unsigned tap,unsigned slot,unsigned idle) {
    if (!selectio_live_available() || selectio_live_active() || tap>31 || slot>63) return -1;
    if (port==1 && idle<=15) {
        profile=(profile&~((63U<<1)|(15U<<14)))|(slot<<1)|(idle<<14);stap=tap;
    } else if (port==2 && slot>=16 && idle<=255) {
        profile=(profile&~((127U<<7)|(255U<<18)))|(slot<<7)|(idle<<18);jtap=tap;
    } else return -1;
    return 0;
}
int selectio_live_clock(uint32_t hz) {
    if(hz!=100000000U && !(hz==50000000U && (swd_read32(SWD_FEATURES)&0x8000U)))return -1;
    if (!selectio_live_available() || etm_ddr_owned() || ps_fixed133_select()<0) return -1;
    if (!(swd_read32(JREG+4U)&4U) || !(swd_read32(SREG+4U)&8U)) return -1;
    swd_write32(JREG+12U,jtap);
    swd_write32(SREG+24U,stap);
    return selectio_live_set(profile|1U|(hz==50000000U ? (1U<<26) : 0U));
}
#endif
