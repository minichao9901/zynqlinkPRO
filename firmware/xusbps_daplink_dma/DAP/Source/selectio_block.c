#if DAP_SELECTIO
#include "DAP_config.h"
#include "DAP.h"
#include "probe_stream.h"
#include "selectio_block.h"
#include "xtime_l.h"
#include "etm_ddr_usb.h"
#include <string.h>

#define JQUEUE 0x80000000U
#define SQUEUE 0x80010000U

static struct {
    unsigned port, poisoned;
    uint32_t route,pins,clock;
    uint8_t profile[4];
    unsigned words[2];
    uint64_t bytes[2],queue_ticks[2],total_ticks[2];
} session;

int selectio_mem_active(void) {return session.port!=0;}

static uint32_t load32(const uint8_t *p) {
    uint32_t value;
    memcpy(&value,p,sizeof value);
    return value;
}

static int wait_queue(uint32_t base, uint32_t mask, uint32_t wanted) {
    XTime start, now;
    XTime_GetTime(&start);
    do {
        if ((swd_read32(base+4U)&mask)==wanted) return 0;
        XTime_GetTime(&now);
    } while (now-start < COUNTS_PER_SECOND/4U);
    return -1;
}

static void swd_descriptor(unsigned index, unsigned op, uint32_t data) {
    uint32_t reg=SQUEUE+0x1000U+8U*index;
    swd_write32(reg,op);
    swd_write32(reg+4U,data);
}

/* The caller claims MEM-AP0 and sets CSW before handing the pads over.
 * Include the final posted result and a DP status fence in the batch. */
static int swd_block(unsigned write, uint32_t address, unsigned count,
                     const uint8_t *payload, uint8_t *reply, uint32_t *detail) {
    unsigned i;
    unsigned bank=write?2U:1U;
    swd_write32(SQUEUE+0x1cU,bank);
    if(session.words[write]!=count) {
        swd_descriptor(0,5U,address);
        for(i=0;i<count;i++) swd_descriptor(i+1U,write?13U:15U,0);
        swd_descriptor(count+1U,14U,0);
        swd_descriptor(count+2U,6U,0);
        session.words[write]=count;
    } else swd_write32(SQUEUE+0x1004U,address);
    if(write) for(i=0;i<count;i++)
        swd_write32(SQUEUE+0x100cU+8U*i,load32(payload+4U*i));
    XTime start,stop;XTime_GetTime(&start);
    swd_write32(SQUEUE+0x10U,count+3U);
    if (wait_queue(SQUEUE,0x27U,0x25U)) return -1;
    XTime_GetTime(&stop);session.queue_ticks[write]+=stop-start;
    *detail=swd_read32(SQUEUE+0x14U);
    if ((*detail&0xffffU)!=count+3U) return -1;
    if (swd_read32(SQUEUE+0x2000U+4U*(count+2U))&0xb2U) return -1;
    if (!write) for(i=0;i<count;i++) {
        uint32_t value=swd_read32(SQUEUE+0x2008U+4U*i);
        memcpy(reply+4U*i,&value,4);
    }
    return 0;
}

static int jtag_block(unsigned write, uint32_t address, unsigned count,
                      const uint8_t *payload, uint8_t *reply, uint32_t *detail) {
    unsigned i;
    swd_write32(JQUEUE+0x14U,address);
    swd_write32(JQUEUE+0x18U,count);
    swd_write32(JQUEUE+0x1cU,0x780002U|(session.profile[2]<<3)|(session.profile[3]<<10));
    if (write) for(i=0;i<count;i++)
        swd_write32(JQUEUE+0x1004U+4U*i,load32(payload+4U*i));
    XTime start,stop;XTime_GetTime(&start);
    swd_write32(JQUEUE+8U,write?13U:5U);
    if (wait_queue(JQUEUE,15U,15U)) return -1;
    XTime_GetTime(&stop);session.queue_ticks[write]+=stop-start;
    *detail=swd_read32(JQUEUE+0x20U);
    if (*detail!=1U || swd_read32(JQUEUE+0x2000U)!=(0x10000U|count)) return -1;
    if (!write) for(i=0;i<count;i++) {
        uint32_t value=swd_read32(JQUEUE+0x2004U+4U*i);
        memcpy(reply+4U*i,&value,4);
    }
    swd_write32(JQUEUE+8U,0U);
    return wait_queue(JQUEUE,15U,5U);
}

static void settle(void) {
    XTime start,now;XTime_GetTime(&start);
    do { XTime_GetTime(&now); } while(now-start<COUNTS_PER_SECOND/500000U);
}

int selectio_mem_close(void) {
    unsigned port=session.port;
    if (!port) return 0;
    uint32_t base=port==2?JQUEUE:SQUEUE;
    if ((port==2 && (swd_read32(base+4U)&8U) && wait_queue(base,2U,2U)) ||
        (port==1 && wait_queue(base,0x20U,0x20U))) {
        session.poisoned=1;
        probe_target_invalidate();return -1;
    }
    swd_write32(base+8U,port==2?2U:1U);
    if (wait_queue(base,0x11U,0x10U)) {session.poisoned=1;return -1;}
    Xil_Out32(XSLCR_UNLOCK_ADDR,XSLCR_UNLOCK_CODE);
    Xil_Out32(SLCR_FPGA0_CLK_CTRL,session.clock);
    Xil_Out32(SLCR_LOCK_ADDR,0x767b);
    swd_write32(JTAG_ROUTE,session.route);
    settle();
    int failed=0;
    if (port==1) {
        swd_write32(JTAG_PINS,0x101U);settle();
        swd_write32(JTAG_PINS,session.pins&0x300U);
        if (probe_session_live()) {
            static const uint8_t reset_sequence[9]={255,255,255,255,255,255,255,255,0};
            uint32_t id=0;
            SWJ_Sequence(72,reset_sequence);
            failed=SWD_Transfer(2,&id)!=DAP_TRANSFER_OK || !(id&1U);
        }
    }
    session.port=0;
    if(probe_target_release()) failed=1;
    return failed?-1:0;
}

int selectio_mem_open(const uint8_t fields[4]) {
    unsigned port=fields[0],tap=fields[1],slot=fields[2],idle=fields[3];
    if ((port!=1 && port!=2) || port!=DAP_Data.debug_port || session.port || selectio_aux_conflict(port) || tap>31 ||
        slot>63 || (port==1 && idle>15) || (port==2 && (slot<16 || !(idle&1))) ||
        !(swd_read32(SWD_FEATURES)&0x80U) || etm_ddr_owned() || !probe_session_live() ||
        probe_stream_active() || probe_target_claimed()) return -1;
    if (port==2 && (DAP_Data.jtag_dev.count!=2 || DAP_Data.jtag_dev.index ||
        DAP_Data.jtag_dev.ir_length[0]!=4 || DAP_Data.jtag_dev.ir_length[1]!=5)) return -1;
    if (probe_target_claim(0)) return -1;
    session.route=swd_read32(JTAG_ROUTE);
    session.pins=swd_read32(JTAG_PINS);
    session.clock=Xil_In32(SLCR_FPGA0_CLK_CTRL);
    session.port=port;session.poisoned=0;
    session.words[0]=session.words[1]=0;
    memset(session.bytes,0,sizeof session.bytes);
    memset(session.queue_ticks,0,sizeof session.queue_ticks);
    memset(session.total_ticks,0,sizeof session.total_ticks);
    memcpy(session.profile,fields,4);
    if (port==1) swd_write32(JTAG_PINS,0x100U);
    swd_write32(JTAG_ROUTE,session.route&~2U);
    if (swd_read32(JTAG_ROUTE)!=(session.route&~2U) || ps_fixed133_select()<0) goto failed;
    uint32_t base=port==2?JQUEUE:SQUEUE;
    swd_write32(base+8U,0U);
    if(wait_queue(base,port==2?7U:0x21U,port==2?5U:0x21U)) goto failed;
    swd_write32(base+(port==2?12U:24U),tap);
    if(port==1) swd_write32(base+12U,1U|(slot<<2)|(slot<<8)|(idle<<14));
    return 0;
failed:
    (void)selectio_mem_close();return -1;
}

void selectio_mem_stats(uint64_t values[7]) {
    values[0]=COUNTS_PER_SECOND;
    memcpy(values+1,session.bytes,16);
    memcpy(values+3,session.queue_ticks,16);
    memcpy(values+5,session.total_ticks,16);
}

/* Continuous host payload, automatically split at the ADIv5 1 KiB TAR
 * boundary. completed counts confirmed earlier chunks on a failed write. */
int selectio_mem_bulk(unsigned write,uint32_t address,unsigned words,const uint8_t *payload,
                     uint8_t *reply,unsigned *completed,uint32_t *detail) {
    *completed=0;*detail=0;
    if(!session.port || session.poisoned || write>1 || !words || words>1008 ||
       (address&3U) || (address>>16)!=0x2000U || 4U*words>0x20010000U-address) return -1;
    XTime start,stop;XTime_GetTime(&start);
    while(*completed<words) {
        unsigned count=(1024U-(address&1023U))/4U;
        if(count>words-*completed) count=words-*completed;
        int rc=session.port==2 ? jtag_block(write,address,count,payload,reply,detail):
                                 swd_block(write,address,count,payload,reply,detail);
        if(rc) {session.poisoned=1;return rc;}
        *completed+=count;
        address+=4U*count;
        if(write) payload+=4U*count;else reply+=4U*count;
    }
    XTime_GetTime(&stop);
    session.bytes[write]+=4U*words;session.total_ticks[write]+=stop-start;
    return 0;
}

uint32_t selectio_block(const uint8_t *req, uint8_t *rsp) {
    unsigned port=req[0]&0x7fU, write=req[0]>>7, count=req[1]|((unsigned)req[2]<<8);
    uint32_t address=load32(req+3), detail=0;
    unsigned request_len=12U+(write?4U*count:0U), reply_len=6U;
    uint8_t fields[4]={(uint8_t)port,req[7],req[8],req[9]};
    int temporary=!session.port;
    rsp[0]=DAP_ERROR;
    if(!count || count>256 || (address&3U) || (address>>16)!=0x2000U ||
       (address&1023U)+4U*count>1024U || req[10]) goto done;
    if(temporary && selectio_mem_open(fields)) goto done;
    if(session.poisoned || memcmp(session.profile,fields,4)) goto done;
    unsigned completed=0;
    int rc=selectio_mem_bulk(write,address,count,req+11,rsp+5,&completed,&detail);
    if(temporary && selectio_mem_close()) rc=-1;
    if(!rc && probe_session_live()) {rsp[0]=DAP_OK;if(!write) reply_len+=4U*count;}
done:
    memcpy(rsp+1,&detail,4);
    return (request_len<<16)|reply_len;
}
#endif
