#if DAP_SELECTIO
#include "DAP_config.h"
#include "DAP.h"
#include "selectio_mode.h"
#include "etm_ddr_usb.h"
#include "probe_stream.h"
#include "selectio_aux.h"
#include "xtime_l.h"
#define SREG 0x80010000U
#define JREG 0x80000000U
#define LIVE (SREG+0x24U)
#define PHY_CLOCK_CTL (SREG+0x38U)
#define FCLK1_CTL 0xf8000180U
#define FCLK1_MASK 0x03f03f30U
static uint32_t profile=(33U<<18)|(2U<<14)|(28U<<7)|(24U<<1);
static uint8_t jtap=16, stap=8;

uint32_t selectio_serial_hz(void) {
    return ps_fclk_decode(FCLK1_CTL)*(DAP_SELECTIO_VARIABLE ? 4U : 1U);
}
uint32_t selectio_live_hz(void) {
    return selectio_serial_hz()/((selectio_live_config()&(1U<<26)) ? 4U : 2U);
}

unsigned selectio_clock_divisor(void) {
    if (!DAP_SELECTIO_VARIABLE) return 0;
    uint32_t ctl=Xil_In32(FCLK1_CTL);
    return ((ctl>>8)&63U)*((ctl>>20)&63U);
}

int selectio_clock_plan(uint32_t limit, unsigned *divisor, unsigned *half_rate) {
    *divisor=0;
    *half_rate=limit==50000000U;
    if (!DAP_SELECTIO_VARIABLE)
        return limit==100000000U || (*half_rate && selectio_dual_rate()) ? 0 : -1;
    if (limit<50000000U || limit>100000000U) return -1;
    const uint32_t pll=33333333U*48U;
    uint32_t best=0;
    for (unsigned mode=0;mode<2;mode++) {
        unsigned half=1U-mode;
        for (unsigned d=32;d<=63;d++) {
            uint32_t hz=(pll/d)*(half ? 1U : 2U);
            if (hz<=limit && hz>best) {
                best=hz;
                *divisor=d;
                *half_rate=half;
            }
        }
    }
    return best ? 0 : -1;
}

#if DAP_SELECTIO_VARIABLE
static int wait_clock(unsigned mask, unsigned expected) {
    XTime begin,now;
    XTime_GetTime(&begin);
    do {
        if ((swd_read32(PHY_CLOCK_CTL)&mask)==expected) return 0;
        XTime_GetTime(&now);
    } while (now-begin<COUNTS_PER_SECOND/100U);
    return -1;
}

static int restart_clock(uint32_t control) {
    swd_write32(PHY_CLOCK_CTL,1);
    if (wait_clock(7,1)) return -1;
    swd_write32(PHY_CLOCK_CTL,3);
    if (wait_clock(7,3)) return -1;
    Xil_Out32(XSLCR_UNLOCK_ADDR,XSLCR_UNLOCK_CODE);
    Xil_Out32(FCLK1_CTL,control);
    Xil_Out32(SLCR_LOCK_ADDR,0x767b);
    if (Xil_In32(FCLK1_CTL)!=control) return -1;
    swd_write32(PHY_CLOCK_CTL,0);
    return wait_clock(7,4);
}
#endif

int selectio_clock_apply(unsigned divisor) {
#if DAP_SELECTIO_VARIABLE
    if (divisor<32 || divisor>63) return -1;
    uint32_t old=Xil_In32(FCLK1_CTL);
    uint32_t next=(old&~FCLK1_MASK)|(1U<<20)|(divisor<<8);
    if ((swd_read32(PHY_CLOCK_CTL)>>8)!=0x53494fU) return -1;
    uint32_t pll=Xil_In32(0xf8000108U);
    uint32_t bypass=(pll&8U) ? Xil_In32(0xf800025cU)&16U : pll&16U;
    if (((pll>>12)&127U)!=48U || bypass || (pll&3U) ||
        !(Xil_In32(0xf800010cU)&4U)) return -1;
    if (!(old&0x30U) && selectio_clock_divisor()==divisor) return wait_clock(7,4);
    if (selectio_aux_busy_for_clock() || probe_stream_active() || (swd_read32(SWD_STATUS)&1U) ||
        !(swd_read32(SREG+4U)&0x20U) || (swd_read32(JREG+4U)&8U)) return -1;
    if (restart_clock(next)) {
        (void)restart_clock(old);
        return -1;
    }
    return 0;
#else
    return divisor ? -1 : 0;
#endif
}
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
    unsigned divisor,half_rate;
    if (selectio_clock_plan(hz,&divisor,&half_rate)) return -1;
    if (!selectio_live_available() || etm_ddr_owned() || ps_fixed133_select()<0) return -1;
    if (!(swd_read32(JREG+4U)&4U) || !(swd_read32(SREG+4U)&8U)) return -1;
    if (selectio_clock_apply(divisor)) return -1;
    swd_write32(JREG+12U,jtap);
    swd_write32(SREG+24U,stap);
    return selectio_live_set(profile|1U|(half_rate ? (1U<<26) : 0U));
}
#endif
