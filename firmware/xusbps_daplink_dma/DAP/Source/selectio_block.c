#if DAP_SELECTIO
#include "DAP_config.h"
#include "DAP.h"
#include "probe_stream.h"
#include "selectio_block.h"
#include "xtime_l.h"
#include <string.h>

#define JQUEUE 0x80000000U
#define SQUEUE 0x80010000U

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
                     const uint8_t *request, uint8_t *reply, uint32_t *detail) {
    unsigned i;
    swd_write32(SQUEUE+0x18U,request[7]);
    swd_write32(SQUEUE+0x0cU,1U|(request[8]<<2)|(request[8]<<8)|(request[9]<<14));
    swd_descriptor(0,5U,address);
    for (i=0;i<count;i++)
        swd_descriptor(i+1U,write?13U:15U,write?load32(request+11U+4U*i):0U);
    swd_descriptor(count+1U,14U,0U);
    swd_descriptor(count+2U,6U,0U);
    swd_write32(SQUEUE+0x10U,count+3U);
    if (wait_queue(SQUEUE,0x27U,0x25U)) return -1;
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
                      const uint8_t *request, uint8_t *reply, uint32_t *detail) {
    unsigned i;
    swd_write32(JQUEUE+0xcU,request[7]);
    swd_write32(JQUEUE+0x14U,address);
    swd_write32(JQUEUE+0x18U,count);
    swd_write32(JQUEUE+0x1cU,0x780002U|(request[8]<<3)|(request[9]<<10));
    if (write) for(i=0;i<count;i++)
        swd_write32(JQUEUE+0x1004U+4U*i,load32(request+11U+4U*i));
    swd_write32(JQUEUE+8U,write?13U:5U);
    if (wait_queue(JQUEUE,15U,15U)) return -1;
    *detail=swd_read32(JQUEUE+0x20U);
    if (*detail!=1U || swd_read32(JQUEUE+0x2000U)!=(0x10000U|count)) return -1;
    if (!write) for(i=0;i<count;i++) {
        uint32_t value=swd_read32(JQUEUE+0x2004U+4U*i);
        memcpy(reply+4U*i,&value,4);
    }
    return 0;
}

uint32_t selectio_block(const uint8_t *req, uint8_t *rsp) {
    unsigned port=req[0]&0x7fU, write=req[0]>>7, count=req[1]|((unsigned)req[2]<<8);
    uint32_t address=load32(req+3), detail=0;
    unsigned request_len=12U+(write?4U*count:0U), reply_len=6U;
    int result=-1;
    rsp[0]=DAP_ERROR;
    /* The prototype aperture covers 64 KiB of F103 SRAM. Match the JTAG
     * block RTL. Validate every field before issuing a side-effecting AXI write. */
    if ((port!=1 && port!=2) || port!=DAP_Data.debug_port || !count || count>256 ||
        (address&3U) || (address>>16)!=0x2000U ||
        (address&1023U)+4U*count>1024U || req[7]>31 || req[8]>63 || req[10] ||
        (port==1 && req[9]>15) || (port==2 && (req[8]<16 || !(req[9]&1U))) ||
        !(swd_read32(SWD_FEATURES)&0x80U) || !probe_session_live() || probe_target_claimed()) goto done;
    if (port==2 && (DAP_Data.jtag_dev.count!=2 || DAP_Data.jtag_dev.index ||
                    DAP_Data.jtag_dev.ir_length[0]!=4 || DAP_Data.jtag_dev.ir_length[1]!=5)) goto done;
    if (probe_target_claim(0)) goto done;
    uint32_t route=swd_read32(JTAG_ROUTE);
    uint32_t base=port==2?JQUEUE:SQUEUE;
    swd_write32(JTAG_ROUTE,route&~2U);
    if (swd_read32(JTAG_ROUTE)!=(route&~2U)) goto restore_route;
    swd_write32(base+8U,0U);
    if (!wait_queue(base,port==2?7U:0x21U,port==2?5U:0x21U)) {
        result=port==2?jtag_block(write,address,count,req,rsp+5,&detail):
                       swd_block(write,address,count,req,rsp+5,&detail);
    }
    /* Drain even if USB was removed. No failed write is replayed. */
    if ((port==2 && (swd_read32(base+4U)&8U) && wait_queue(base,2U,2U)) ||
        (port==1 && wait_queue(base,0x20U,0x20U))) {
        probe_target_invalidate();
        goto done;
    }
    swd_write32(base+8U,port==2?2U:1U);
    if (wait_queue(base,0x11U,0x10U)) {
        probe_target_invalidate();
        goto done;
    }
restore_route:
    swd_write32(JTAG_ROUTE,route);
    /* Park guard and SERDES latency before starting the legacy AP restore. */
    {
        XTime start,now;
        XTime_GetTime(&start);
        do { XTime_GetTime(&now); } while(now-start < COUNTS_PER_SECOND/1000000U);
    }
    if (probe_target_release()==0 && !result && probe_session_live()) {
        rsp[0]=DAP_OK;
        if (!write) reply_len+=4U*count;
    }
done:
    memcpy(rsp+1,&detail,4);
    return (request_len<<16)|reply_len;
}
#endif
