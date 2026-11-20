#if DAP_SELECTIO
#include "selectio_aux.h"
#include "DAP_config.h"
#include "DAP.h"
#include "selectio_block.h"
#include "selectio_mode.h"
#include "probe_stream.h"
#include "etm_ddr_usb.h"
#include "xtime_l.h"
#include <string.h>

#define AUX 0x80020000U
#define RD(off) swd_read32(AUX+(off))
#define WR(off,value) swd_write32(AUX+(off),(value))
static unsigned active_channel,exclusive,flags,read_only_stop;
static uint32_t saved_route,saved_fclk;
static uint32_t word(const uint8_t *p){uint32_t value;memcpy(&value,p,4);return value;}
static void put(uint8_t *p,uint32_t v){memcpy(p,&v,4);}
static int aux_wait(uint32_t mask,uint32_t expected,uint32_t milliseconds) {
    XTime start,now;
    XTime_GetTime(&start);
    do {
        if ((RD(4)&mask)==expected) return 0;
        XTime_GetTime(&now);
    } while(now-start<(uint64_t)(COUNTS_PER_SECOND/1000U)*milliseconds);
    return -1;
}
static void settle(void) {
    XTime start,now;XTime_GetTime(&start);
    do {XTime_GetTime(&now);} while(now-start<COUNTS_PER_SECOND/500000U);
}
int selectio_aux_exclusive(void){return exclusive!=0;}
static int restore(void) {
    if(!active_channel) return 0;
    if(aux_wait(2,0,400)) return -1;
    WR(8,0);settle();
    if(exclusive) {
        if(aux_wait(1,0,20)) return -1;
        Xil_Out32(XSLCR_UNLOCK_ADDR,XSLCR_UNLOCK_CODE);
        Xil_Out32(SLCR_FPGA0_CLK_CTRL,saved_fclk);
        Xil_Out32(SLCR_LOCK_ADDR,0x767b);
        swd_write32(JTAG_ROUTE,saved_route);
    }
    flags=active_channel=exclusive=read_only_stop=0;
    return 0;
}
void selectio_aux_reset(void){(void)restore();}

/* CONFIG payload: codec (0=raw SPI,1=8N1,2=Manchester), claim TX,
 * SPI mode, capture slot, little-endian information rate, input delay tap.
 * SPI may monitor its return line with either serial decoder for pad testing. */
static int configure(unsigned ch,const uint8_t *p,unsigned size) {
    if(size!=9 || active_channel || selectio_mem_active() ||
        (swd_read32(SWD_FEATURES)&0x200U)==0 || RD(0)!=0x41555831U) return -1;
    unsigned codec=p[0],drive=p[1],mode=p[2],sample=p[3],rate=word(p+4),tap=p[8];
    if(codec>2 || drive>1 || mode>3 || sample>63 || tap>31 || rate<9600 || rate>100000000U ||
       (ch==5 && !codec) || (ch==5 && drive && codec!=1)) return -1;
    unsigned claim=ch==4 || drive;
    uint32_t route=swd_read32(JTAG_ROUTE);
    if((claim && (probe_stream_active() || probe_target_claimed() || etm_ddr_owned())) ||
       (!claim && (route&3U)==3U) || selectio_live_active() && claim) return -1;
    uint32_t ref=ps_fclk_decode(0xf8000180U);
    if(ref<199000000 || ref>201000000) return -1;
    uint64_t sample_hz=2ULL*ref;
    uint32_t period=(uint32_t)((sample_hz*256U+rate/2U)/rate);
    if(period<1024) period=1024;
    active_channel=ch;exclusive=claim;saved_route=route;
    saved_fclk=Xil_In32(SLCR_FPGA0_CLK_CTRL);
    if(claim) {
        swd_write32(JTAG_ROUTE,route&~2U);
        if(swd_read32(JTAG_ROUTE)!=(route&~2U) || ps_fixed133_select()<0) goto failed;
    }
    WR(8,0);settle();
    WR(0x24,1);
    if(aux_wait(8,0,20)) goto failed;
    WR(0xc,period);
    uint32_t minimum=period>>10, threshold=(3U*period+512U)>>10;
    uint32_t maximum=(5U*period+512U)>>10;
    WR(0x10,(threshold<<16)|(minimum?minimum:1));
    WR(0x14,maximum);
    WR(0x18,(sample<<2)|mode);
    if(swd_read32(0x80000004U)&4U) swd_write32(0x8000000cU,tap);
    else goto failed;
    flags=codec|(ch==4?4U:(drive?8U:0U));
    WR(8,flags);settle();read_only_stop=0;
    if(claim && aux_wait(1,1,20)) goto failed;
    return 0;
failed:
    (void)restore();return -1;
}
static unsigned peek(uint8_t *out,unsigned capacity) {
    uint32_t ptr=RD(0x20),n=RD(0x24);
    if(n>65536) return 0;
    if(n>capacity) n=capacity;
    unsigned k=0;
    while(k<n) {
        unsigned offset=(ptr+k)&65535U;
        uint32_t v=RD(0x10000U+(offset&~3U));
        unsigned begin=offset&3U,bytes=4U-begin;
        if(bytes>n-k) bytes=n-k;
        memcpy(out+k,((uint8_t *)&v)+begin,bytes);
        k+=bytes;
    }
    return n;
}
void selectio_aux_consume(unsigned bytes) {
    if (!active_channel || !bytes) return;
    if(aux_wait(8,0,20)) return;
    WR(0x20,bytes);
    (void)aux_wait(8,0,20);
}
static int transmit(const uint8_t *data,unsigned size) {
    if(!size || size>4079 || !exclusive || read_only_stop || aux_wait(2,0,20)) return -1;
    for(unsigned i=0;i<size;i+=4) {
        uint32_t v=0;unsigned take=size-i<4?size-i:4;
        memcpy(&v,data+i,take);WR(0x1000U+i,v);
    }
    WR(0x1c,size);
    /* Including an entire 8N1 transaction even at the minimum baud. */
    uint32_t budget=30U+(uint32_t)(((uint64_t)size*10U*RD(0x0c)+102399999U)/102400000U);
    return aux_wait(6,4,budget);
}
int selectio_aux_frame(unsigned ch,unsigned op,const uint8_t *in,unsigned size,
                       uint8_t *out,unsigned capacity,unsigned *length,unsigned *consume) {
    if(op==0) return configure(ch,in,size);
    if(!active_channel || active_channel!=ch) return -1;
    if(op==1 && !size) {*consume=*length=peek(out,capacity);return 0;}
    if(op==2) return transmit(in,size);
    if(op==3 && !size) {
        if(aux_wait(2,0,400)) return -1;
        WR(8,0);settle();read_only_stop=1;return 0;
    }
    if(op==4 && !size && capacity>=20) {
        WR(0x28,1);if(aux_wait(16,0,20)) return -1;
        put(out,RD(0x24));put(out+4,RD(0x28));put(out+8,RD(0x2c));
        put(out+12,RD(4));put(out+16,RD(0x20));*length=20;return 0;
    }
    if(op==5 && !size) return restore();
    return -1;
}
#endif
