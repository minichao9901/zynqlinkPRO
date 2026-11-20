#if DAP_SELECTIO
#include "selectio_aux.h"
#include "DAP_config.h"
#include "DAP.h"
#include "selectio_block.h"
#include "selectio_mode.h"
#include "probe_stream.h"
#include "etm_ddr_usb.h"
#include "xtime_l.h"
#include "xusbps_class_cdc.h"
#include <string.h>

#define AUX 0x80020000U
#define RD(off) swd_read32(AUX+(off))
#define WR(off,value) swd_write32(AUX+(off),(value))
static unsigned active_channel,exclusive,flags,read_only_stop,raw_test;
enum { CMSIS_SWO_CHANNEL=8 };
static uint8_t swo_transport,swo_mode,swo_running;
static uint32_t swo_rate,swo_consumed,swo_drops,swo_errors;
static volatile unsigned cdc_bound,cdc_owns,cdc_baud=115200,cdc_deferred;
static unsigned cdc_running_baud;
static uint8_t bypass_samples[512];
static unsigned bypass_count,raw_half,raw_advance;
static uint8_t cdc_tx_ring[4][4096] __attribute__((aligned(32)));
static uint16_t cdc_tx_length[4];
static volatile unsigned cdc_in,cdc_out,cdc_sending,cdc_ack_bytes,cdc_usb_bytes;
static uint8_t cdc_in_data[2048] __attribute__((aligned(2048)));
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
int selectio_aux_conflict(unsigned port) {return exclusive || ((active_channel==5 || active_channel==CMSIS_SWO_CHANNEL) && port==2);}
static int restore(void) {
    if(!active_channel) return 0;
    if(aux_wait(2,0,400)) return -1;
    WR(8,0);settle();
    if(raw_test) {
        swd_write32(0x80000008U,2);
        settle();
        if(swd_read32(SWD_FEATURES)&0x1000U) swd_write32(0x80000038U,3);
    }
    if(exclusive) {
        if(aux_wait(1,0,20)) return -1;
        Xil_Out32(XSLCR_UNLOCK_ADDR,XSLCR_UNLOCK_CODE);
        Xil_Out32(SLCR_FPGA0_CLK_CTRL,saved_fclk);
        Xil_Out32(SLCR_LOCK_ADDR,0x767b);
        swd_write32(JTAG_ROUTE,saved_route);
    }
    flags=active_channel=exclusive=read_only_stop=raw_test=0;
    return 0;
}
void selectio_swo_reset(void) {
    if(active_channel==CMSIS_SWO_CHANNEL) (void)restore();
    swo_transport=swo_mode=swo_running=0;
    swo_rate=swo_consumed=swo_drops=swo_errors=0;
}
void selectio_aux_reset(void){(void)restore();selectio_swo_reset();}

/* CONFIG payload: codec (0=raw SPI,1=8N1,2=Manchester), claim TX,
 * SPI mode, capture slot, little-endian information rate, input delay tap.
 * SPI may monitor its return line with either serial decoder for pad testing. */
static int run_raw(unsigned words) {
    if(!words || words>512) return -1;
    swd_write32(0x80000008U,1U);
    unsigned timeout=100000;
    while((swd_read32(0x80000004U)&15U)!=15U && --timeout) {}
    if(!timeout) return -1;
    bypass_count=words;
    for(unsigned i=0;i<words;i++) bypass_samples[i]=(uint8_t)swd_read32(0x80002000U+4U*i);
    swd_write32(0x80000008U,0);
    timeout=100000;
    while((swd_read32(0x80000004U)&15U)!=5U && --timeout) {}
    return timeout?0:-1;
}
/* Reinstall BYPASS inside this PHY ownership interval. The two TAPs
 * use 4+5 IR bits. Perform the preamble at 50 MHz with generous setup. */
static int bypass_preamble(void) {
    static const struct {uint8_t n,tms,tdi;} steps[]={
        {8,1,0},{1,0,0},{2,1,0},{2,0,0},{8,0,1},{1,1,1},
        {1,1,0},{1,0,0},{1,1,0},{2,0,0},{2,0,0}};
    unsigned i=0;
    for(unsigned j=0;j<sizeof steps/sizeof steps[0];j++)
        for(unsigned n=0;n<steps[j].n;n++) {
            uint32_t bits=0xf0U|(steps[j].tms?0xff00U:0U)|(steps[j].tdi?0xff0000U:0U);
            if(j+1U==sizeof steps/sizeof steps[0] && n+1U==steps[j].n) bits|=1U<<24;
            swd_write32(0x80001000U+4U*i++,bits);
        }
    return run_raw(i);
}
static int configure(unsigned ch,const uint8_t *p,unsigned size) {
    if((size!=9 && size!=10) || active_channel ||
        (swd_read32(SWD_FEATURES)&0x200U)==0 || RD(0)!=0x41555831U) return -1;
    unsigned codec=p[0],drive=p[1],mode=p[2],sample=p[3],rate=word(p+4),tap=p[8];
    unsigned test=size==10?p[9]:0;
    if(test>7 || ((test&3U) && !(swd_read32(SWD_FEATURES)&0x1000U)) ||
       (test && ch!=4) || (drive==3 && (!(test&2U) || codec!=1))) return -1;
    if(codec>2 || drive>3 || (drive==2 && (ch!=4 || codec==0)) || mode>3 || sample>63 || tap>31 || rate<9600 || rate>100000000U ||
       (ch==5 && !codec) || (ch==5 && drive && codec!=1)) return -1;
    unsigned sideband=!!(swd_read32(SWD_FEATURES)&0x800U);
    unsigned claim=ch==4 || (drive && !sideband);
    if (selectio_mem_port() && (claim || selectio_mem_port()==DAP_PORT_JTAG)) return -1;
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
    if(swd_read32(SWD_FEATURES)&0x1000U) WR(0x30,test&3U);
    raw_test=ch==4 && drive==2;
    raw_advance=(test>>2)&1U;
    raw_half=(codec==2 ? rate*2U : rate)==200000000U ? 1U:2U;
    if(raw_test) {
        if(swd_read32(SWD_FEATURES)&0x1000U) swd_write32(0x80000038U,codec==1?2U:0U);
        swd_write32(0x80000008U,0);
        settle();
        if((swd_read32(0x80000004U)&7U)!=5U || bypass_preamble())goto failed;
    }
    flags=codec|(raw_test?0U:(test&2U)?8U:ch==4?4U:(drive?8U:0U));
    WR(8,flags);settle();read_only_stop=0;
    if(!raw_test && (claim || drive) && aux_wait(1,1,20)) goto failed;
    return 0;
failed:
    (void)restore();return -1;
}
static unsigned peek(uint8_t *out,unsigned capacity) {
    uint32_t ptr=RD(0x20),n=RD(0x24);
    if(n>65536) return 0;
    if(n>capacity) n=capacity;
    unsigned k=0;
    if((ptr&3U) && n) {
        uint32_t first=RD(0x10000U+(ptr&65532U));
        unsigned skip=ptr&3U;
        k=4U-skip;
        if(k>n) k=n;
        memcpy(out,((uint8_t *)&first)+skip,k);
    }
    for(;k+4U<=n;k+=4U) {
        uint32_t v=RD(0x10000U+((ptr+k)&65532U));
        memcpy(out+k,&v,4);
    }
    if(k<n) {
        uint32_t last=RD(0x10000U+((ptr+k)&65532U));
        memcpy(out+k,&last,n-k);
    }
    return n;
}
void selectio_aux_consume(unsigned bytes) {
    if (!active_channel || !bytes) return;
    if(aux_wait(8,0,20)) return;
    WR(0x20,bytes);
    (void)aux_wait(8,0,20);
}
static int transmit_start(const uint8_t *data,unsigned size) {
    if(!size || size>4079 || !(flags&12U) || read_only_stop || aux_wait(3,1,20)) return -1;
    for(unsigned i=0;i<size;i+=4) {
        uint32_t v=0;unsigned take=size-i<4?size-i:4;
        memcpy(&v,data+i,take);WR(0x1000U+i,v);
    }
    WR(0x1c,size);
    return 0;
}
/* Four TCK per octet at 50 MHz. In a prepared TAP BYPASS chain the target
 * drives these bits back on the real TDO/SWO pad for receiver qualification. */
static int bypass_wave(const uint8_t *bytes,unsigned count) {
    unsigned words=count*raw_half*2U;
    if(!words || words>512 || read_only_stop) return -1;
    unsigned step=2U*raw_half;
    for(unsigned i=0;i<words;i++) {
        uint32_t wave=raw_half==1?0xaaU:0xccU;
        for(unsigned j=0;j<8;j++) {
            unsigned bit=(8U*i+j+raw_advance)/step;
            if(bit<count*8 && (bytes[bit/8]&(0x80U>>(bit&7U)))) wave|=1U<<(16U+j);
        }
        if(i+1U==words) wave|=1U<<24;
        swd_write32(0x80001000U+4U*i,wave);
    }
    return run_raw(words);
}
static int transmit(const uint8_t *data,unsigned size) {
    if(raw_test) return bypass_wave(data,size);
    if(transmit_start(data,size)) return -1;
    /* Including an entire 8N1 transaction even at the minimum baud. */
    uint32_t budget=30U+(uint32_t)(((uint64_t)size*10U*RD(0x0c)+102399999U)/102400000U);
    return aux_wait(6,4,budget);
}
int selectio_aux_frame(unsigned ch,unsigned op,const uint8_t *in,unsigned size,
                       uint8_t *out,unsigned capacity,unsigned *length,unsigned *consume) {
    if(cdc_owns) return -1;
    if(op==0) return configure(ch,in,size);
    if(!active_channel || active_channel!=ch) return -1;
    if(op==1 && !size) {*consume=*length=peek(out,capacity);return 0;}
    if(op==8 && raw_test && !read_only_stop && size && size%3U==0 && size<=512U*3U) {
        unsigned words=size/3U;
        for(unsigned i=0;i<words;i++) {
            uint32_t bits=in[3*i]|((uint32_t)in[3*i+1]<<8)|((uint32_t)in[3*i+2]<<16);
            if(i+1==words) bits|=1U<<24;
            swd_write32(0x80001000U+4U*i,bits);
        }
        return run_raw(words);
    }
    if(op==7 && raw_test && !size && capacity>=bypass_count) {
        memcpy(out,bypass_samples,bypass_count);*length=bypass_count;return 0;
    }
    if(op==9 && ch==5) return transmit_start(in,size);
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

/* Standard CMSIS-DAP polled transport. The native interface and CDC use
 * the same hardware receiver and cannot take ownership of a live SWO FIFO. */
uint32_t selectio_swo_command(uint8_t cmd,const uint8_t *p,uint8_t *r) {
    unsigned available=0, status=swo_running?1U:0U, n=0;
    if(cmd==0x1b || cmd==0x1c || cmd==0x1e) {
        if(active_channel==CMSIS_SWO_CHANNEL) {
            WR(0x28,1);
            if(aux_wait(16,0,20)) status|=0x40U;
            else {
                uint32_t drops=RD(0x28),errors=RD(0x2c);
                if(drops!=swo_drops) status|=0x80U;
                if(errors!=swo_errors) status|=0x40U;
                if(cmd!=0x1e || (p[0]&1U)) {swo_drops=drops;swo_errors=errors;}
            }
            available=RD(0x24);
        }
        if(cmd==0x1b) {r[0]=status;put(r+1,available);return 5;}
        if(cmd==0x1e) {
            if(p[0]&1U) r[n++]=status;
            if(p[0]&2U) {put(r+n,available);n+=4;}
            if(p[0]&4U) {
                put(r+n,swo_consumed+available);put(r+n+4,TIMESTAMP_GET());n+=8;
            }
            return (1U<<16)|n;
        }
        unsigned limit=p[0]|((unsigned)p[1]<<8);
        if(limit>DAP_PACKET_SIZE-4U) limit=DAP_PACKET_SIZE-4U;
        if(swo_transport==1 && active_channel==CMSIS_SWO_CHANNEL && available && limit) {
            n=peek(r+3,limit);selectio_aux_consume(n);swo_consumed+=n;
        }
        r[0]=status;r[1]=(uint8_t)n;r[2]=(uint8_t)(n>>8);
        return (2U<<16)|(3U+n);
    }
    r[0]=DAP_ERROR;
    if(cmd==0x19) {
        uint32_t request=word(p);
        uint32_t accepted=0;
        if(!swo_running && request>=9600U && request<=100000000U && (swd_read32(SWD_FEATURES)&0x200U)) {
            uint64_t f=2ULL*ps_fclk_decode(0xf8000180U);
            uint32_t period=(uint32_t)((f*256U+request/2U)/request);
            if(period>=1024U) {swo_rate=request;accepted=(uint32_t)((f*256U+period/2U)/period);}
        }
        put(r,accepted);return (4U<<16)|4U;
    }
    if(cmd==0x17 && !swo_running && p[0]<=1) {
        if(!p[0]) selectio_swo_reset();
        swo_transport=p[0];r[0]=DAP_OK;
    } else if(cmd==0x18 && !swo_running && p[0]<=2) {
        if(active_channel==CMSIS_SWO_CHANNEL && restore()) return (1U<<16)|1U;
        swo_mode=p[0];r[0]=DAP_OK;
    } else if(cmd==0x1a && p[0]<=1) {
        if(p[0]==swo_running) r[0]=DAP_OK;
        else if(!p[0] && active_channel==CMSIS_SWO_CHANNEL) {
            WR(8,0);settle();read_only_stop=1;swo_running=0;r[0]=DAP_OK;
        } else if(p[0] && swo_transport==1 && swo_mode && swo_rate) {
            uint8_t config[9]={swo_mode,0,0,0,0,0,0,0,0};
            if(active_channel==CMSIS_SWO_CHANNEL && restore()) return (1U<<16)|1U;
            put(config+4,swo_rate);
            if(!configure(CMSIS_SWO_CHANNEL,config,sizeof config)) {
                swo_consumed=swo_drops=swo_errors=0;swo_running=1;r[0]=DAP_OK;
            }
        }
    }
    return (1U<<16)|1U;
}

void selectio_cdc_status(uint32_t values[8]) {
    values[0]=cdc_bound;values[1]=cdc_owns;values[2]=cdc_baud;values[3]=usbd_cdc_acm_get_dtr();
    values[4]=cdc_in-cdc_out;values[5]=values[6]=values[7]=0;
    if(cdc_owns) {
        WR(0x28,1);
        if(!aux_wait(16,0,20)) {values[5]=RD(0x28);values[6]=RD(0x2c);}
        values[7]=RD(0x24);
    }
}
int selectio_cdc_bind(unsigned enable) {
    if(enable>1 || (enable && (active_channel || probe_uses_legacy_cdc() || !(swd_read32(SWD_FEATURES)&0x200U)))) return -1;
    cdc_bound=enable;
    return 0;
}
int selectio_cdc_receiving(void){return cdc_bound!=0;}
int selectio_cdc_space(void){
    if(!cdc_bound || cdc_in-cdc_out<4) return 1;
    cdc_deferred=1;return 0;
}
void selectio_cdc_receive(const uint8_t *p,unsigned n) {
    if(!cdc_bound || !n || n>4096 || cdc_in-cdc_out>=4) return;
    unsigned index=cdc_in&3U;
    memcpy(cdc_tx_ring[index],p,n);
    cdc_tx_length[index]=(uint16_t)n;
    __sync_synchronize();cdc_in++;
}
int selectio_cdc_complete(void *data) {
    if(!cdc_usb_bytes || data!=cdc_in_data) return 0;
    cdc_ack_bytes=cdc_usb_bytes;cdc_usb_bytes=0;return 1;
}
void selectio_cdc_line(unsigned baud){cdc_baud=baud;}
void selectio_cdc_reset(void) {
    cdc_bound=cdc_owns=cdc_deferred=cdc_sending=cdc_ack_bytes=cdc_usb_bytes=0;
    cdc_in=cdc_out=0;cdc_baud=115200;
}
void selectio_cdc_poll(XUsbPs *usb) {
    if(!cdc_bound && !cdc_owns) return;
    if(cdc_owns && cdc_ack_bytes) {
        unsigned n=cdc_ack_bytes;cdc_ack_bytes=0;selectio_aux_consume(n);
    }
    if(cdc_owns && cdc_sending && !(RD(4)&2U)) {
        cdc_out++;cdc_sending=0;
        if(cdc_deferred) {
            unsigned f=mfcpsr();mtcpsr(f|0x80U);cdc_deferred=0;
            selectio_cdc_resume_rx(usb);mtcpsr(f);
        }
    }
    if(!cdc_bound || !usbd_cdc_acm_get_dtr() || cdc_baud!=cdc_running_baud) {
        if(cdc_owns && !cdc_sending && !cdc_usb_bytes && !cdc_ack_bytes) {
            if(!restore()) cdc_owns=0;
        }
        if(!cdc_bound || !usbd_cdc_acm_get_dtr()) return;
    }
    if(!cdc_owns) {
        static XTime retry_after;
        XTime now;XTime_GetTime(&now);
        if(now<retry_after)return;
        uint8_t cfg[9]={1,1,0,0,0,0,0,0,0};
        put(cfg+4,cdc_baud);
        if(configure(5,cfg,sizeof cfg)) {retry_after=now+COUNTS_PER_SECOND/20U;return;}
        cdc_running_baud=cdc_baud;cdc_owns=1;
    }
    if(!cdc_sending && cdc_in!=cdc_out) {
        unsigned index=cdc_out&3U;
        if(!transmit_start(cdc_tx_ring[index],cdc_tx_length[index])) cdc_sending=1;
    }
    if(!cdc_usb_bytes && !cdc_ack_bytes) {
        /* Short transfer or explicit ZLP lets the CDC driver publish promptly. */
        unsigned n=peek(cdc_in_data,sizeof cdc_in_data);
        if(n) {
            unsigned f=mfcpsr();mtcpsr(f|0x80U);
            cdc_usb_bytes=n;
            Xil_DCacheFlushRange((UINTPTR)cdc_in_data,(n+31U)&~31U);
            if(XUsbPs_EpBufferSendWithZLT(usb,3,cdc_in_data,n)!=XST_SUCCESS) cdc_usb_bytes=0;
            mtcpsr(f);
        }
    }
}
#endif
