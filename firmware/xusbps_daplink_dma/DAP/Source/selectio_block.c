#if DAP_SELECTIO
#include "DAP_config.h"
#include "DAP.h"
#include "probe_stream.h"
#include "selectio_block.h"
#include "selectio_mode.h"
#include "dap_wait.h"
#include "xtime_l.h"
#include "swd_dma.h"
#include "etm_ddr_usb.h"
#include <string.h>

#define JQUEUE 0x80000000U
#define SQUEUE 0x80010000U

static struct {
    unsigned port, poisoned, dma,bank,use_dma,jtag_backoffs,jtag_idle,half_rate,previous_divisor;
    uint32_t route,pins,clock;
    uint8_t profile[4];
    unsigned words[2];
    uint64_t bytes[2],queue_ticks[2],total_ticks[2];
} session;
static unsigned swd_leading_op[2];
static uint32_t rtt_live;

unsigned selectio_mem_port(void) {return session.port;}

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
static void swd_prepare(unsigned write, unsigned first_op, uint32_t first_data,
                        unsigned count, const uint8_t *payload) {
    unsigned i;
    unsigned bank=write?2U:1U;
    swd_write32(SQUEUE+0x1cU,bank);
    unsigned old=session.words[write];
    if(!old) {
        for(i=1;i<=256;i++) swd_descriptor(i,write?13U:15U,0);
    }
    if(!old || swd_leading_op[write]!=first_op) {
        swd_descriptor(0,first_op,first_data);
        swd_leading_op[write]=first_op;
    } else if(first_op==5U) swd_write32(SQUEUE+0x1004U,first_data);
    if(old!=count) {
        /* The template contains DRW everywhere except the two current
         * fences. A change of TAR page length repairs at most four entries. */
        if(old) for(i=old+1U;i<=old+2U && i<=256U;i++)
            swd_descriptor(i,write?13U:15U,0);
        swd_descriptor(count+1U,14U,0);
        swd_descriptor(count+2U,6U,0);
        session.words[write]=count;
    }
    if(write && !session.use_dma) for(i=0;i<count;i++)
        swd_write32(SQUEUE+0x100cU+8U*i,load32(payload+4U*i));
}

static int swd_complete(unsigned write, unsigned count, uint8_t *reply, uint32_t *detail, XTime start) {
    XTime stop;
    if (wait_queue(SQUEUE,0x27U,0x25U)) return -1;
    XTime_GetTime(&stop);session.queue_ticks[write]+=stop-start;
    *detail=swd_read32(SQUEUE+0x14U);
    if ((*detail&0xffffU)!=count+3U) return -1;
    if (swd_read32(SQUEUE+0x2000U+4U*(count+2U))&0xb2U) return -1;
    if (!write && !session.use_dma) for(unsigned i=0;i<count;i++) {
        uint32_t value=swd_read32(SQUEUE+0x2008U+4U*i);
        memcpy(reply+4U*i,&value,4);
    }
    return 0;
}

static int swd_block(unsigned write, uint32_t address, unsigned count,
                     const uint8_t *payload, uint8_t *reply, uint32_t *detail) {
    swd_prepare(write,5U,address,count,payload);
    XTime start;XTime_GetTime(&start);
    swd_write32(SQUEUE+0x10U,count+3U);
    return swd_complete(write,count,reply,detail,start);
}

/* The CDMA uses the other page bank while the PHY is running. Never
 * change the active bank or publish a page before its DP fence passes. */
static int swd_aligned_pages(unsigned write,uint32_t address,unsigned pages,
                            const uint8_t *payload,uint8_t *reply,unsigned *completed,uint32_t *detail) {
    const uint32_t tx=0x45002000U,rx=0x45003000U;
    unsigned bank=session.bank++&1U;
    session.use_dma=1;
    if(write && selectio_dma_payload(1,tx+bank*1024U,(uint8_t *)payload,256))return -1;
    for(unsigned page=0;page<pages;page++) {
        if(!probe_session_live())return -1;
        swd_write32(SQUEUE+0x2cU,4U|bank);
        swd_prepare(write,5U,address+page*1024U,256,0);
        XTime start;XTime_GetTime(&start);
        swd_write32(SQUEUE+0x10U,259);
        int dma_ok=0;
        unsigned other=bank^1U;
        if(write && page+1<pages)
            dma_ok=selectio_dma_payload(1,tx+other*1024U,(uint8_t *)payload+(page+1)*1024U,256);
        if(!write && page)
            dma_ok=selectio_dma_payload(0,rx+other*1024U,reply+(page-1)*1024U,256);
        if(!write && page && !dma_ok)*completed+=256;
        int ret=swd_complete(write,256,0,detail,start);
        if(write && !ret)*completed+=256;
        if(ret || dma_ok)return -1;
        bank=other;
    }
    if(!write) {
        if(selectio_dma_payload(0,rx+(bank^1U)*1024U,reply+(pages-1)*1024U,256)) return -1;
        *completed+=256;
    }
    return 0;
}

static int jtag_block(unsigned write, uint32_t address, unsigned count,
                      const uint8_t *payload, uint8_t *reply, uint32_t *detail) {
    unsigned i;
    swd_write32(JQUEUE+0x14U,address);
    swd_write32(JQUEUE+0x18U,count);
    swd_write32(JQUEUE+0x1cU,(session.half_rate ? 0x600004U : 0x780002U)|(session.profile[2]<<3)|(session.jtag_idle<<10));
    if (write && !session.use_dma) for(i=0;i<count;i++)
        swd_write32(JQUEUE+0x1004U+4U*i,load32(payload+4U*i));
    XTime start,stop;XTime_GetTime(&start);
    swd_write32(JQUEUE+8U,write?13U:5U);
    if (wait_queue(JQUEUE,15U,15U)) return -1;
    XTime_GetTime(&stop);session.queue_ticks[write]+=stop-start;
    *detail=swd_read32(JQUEUE+0x20U);
    if (*detail!=1U || swd_read32(JQUEUE+0x2000U)!=(0x10000U|count)) {
        /* DONE leaves RUN asserted; the queue rejects all configuration
         * writes until GO is withdrawn and its completion has drained. */
        swd_write32(JQUEUE+8U,0);
        (void)wait_queue(JQUEUE,15U,5U);
        return -1;
    }
    if (!write && !session.use_dma) for(i=0;i<count;i++) {
        uint32_t value=swd_read32(JQUEUE+0x2004U+4U*i);
        memcpy(reply+4U*i,&value,4);
    }
    swd_write32(JQUEUE+8U,0U);
    return wait_queue(JQUEUE,15U,5U);
}

static void extend_jtag_idle(void) {
    /* Keep the odd RTI count required by the two-slot ARM stream. Small
     * increases avoid paying twice the idle time after a single target WAIT. */
    unsigned step=2U+2U*(session.jtag_idle/32U);
    unsigned idle=session.jtag_idle+step;
    session.jtag_idle=idle>255U?255U:idle;
    session.jtag_backoffs++;
}

static void settle(void) {
    XTime start,now;XTime_GetTime(&start);
    do { XTime_GetTime(&now); } while(now-start<COUNTS_PER_SECOND/500000U);
}

int selectio_swd50_batch_available(void) {
    return !session.port && DAP_Data.debug_port==DAP_PORT_SWD &&
           DAP_Data.swd_conf.turnaround==1 && !DAP_Data.swd_conf.data_phase &&
           (swd_read32(SWD_FEATURES)&0x8400U)==0x8400U &&
           (DAP_SELECTIO_VARIABLE ? selectio_live_active() :
            (selectio_live_config()&0x04000001U)==0x04000001U);
}

static int swd50_queue_take(uint32_t live) {
    unsigned slot=(live>>1)&63U, idle=(live>>14)&15U;
    swd_write32(SQUEUE+0x0cU,((live&(1U<<26)) ? 0U : 1U)|(slot<<2)|(slot<<8)|(idle<<14));
    swd_write32(SQUEUE+8U,0);
    settle();
    return selectio_live_set(live&~1U) || wait_queue(SQUEUE,0x29U,0x29U);
}

static int swd50_queue_release(uint32_t live) {
    if(wait_queue(SQUEUE,0x20U,0x20U) || selectio_live_set(live)) {
        probe_target_invalidate();return -1;
    }
    swd_write32(SQUEUE+8U,1U);
    swd_write32(SQUEUE+0x2cU,0);
    return 0;
}

int selectio_swd50_rtt_attached(void) {return rtt_live!=0;}
int selectio_swd50_rtt_attach(void) {
    if(!selectio_swd50_batch_available() || !probe_target_claimed() ||
       etm_ddr_owned() || (swd_read32(SQUEUE+4U)&0x38U)!=0x38U)return -1;
    uint32_t live=selectio_live_config();
    rtt_live=live;
    session.port=1; session.dma=1; session.half_rate=(live>>26)&1U;
    session.poisoned=0;session.bank=0;
    if(swd50_queue_take(live) || !probe_session_live()) {
        (void)selectio_swd50_rtt_detach();
        return -1;
    }
    return 0;
}
int selectio_swd50_rtt_detach(void) {
    if(!rtt_live)return 0;
    if(swd50_queue_release(rtt_live))return -1;
    rtt_live=0;session.port=0;session.use_dma=0;
    return 0;
}

int selectio_swd50_drw(unsigned request,unsigned count,const uint8_t *input,uint8_t *output,
                     unsigned *completed,unsigned *status) {
    if ((request!=0x0fU && request!=0x0dU) || count<16 || count>1023U ||
        !selectio_swd50_batch_available() || !probe_session_live() || etm_ddr_owned() ||
        (swd_read32(SQUEUE+4U)&0x38U)!=0x38U) return 0;
    const unsigned write=request==0x0dU;
    const uint32_t live=selectio_live_config();
    const uint32_t payload_window=write?0x45002000U:0x45003000U;
    unsigned transferred=0, pending=0, pending_bank=0, bank=0;
    unsigned result=DAP_TRANSFER_ERROR;
    *completed=0;*status=DAP_TRANSFER_ERROR;
    if(dap_wait_command_error())return 1;

    // Both producers use pad owner 3. Request the queue before changing the
    // lane mux; keep SWJ-DP, SELECT, CSW and the host's live TAR untouched.
    if(swd50_queue_take(live))goto release;
    session.use_dma=1;
    unsigned first=count>256U?256U:count;
    if(write && selectio_dma_payload(1,payload_window,(uint8_t *)input,first))goto release;
    while(transferred<count) {
        unsigned words=count-transferred;
        if(words>256U)words=256U;
        if(dap_wait_command_error() || !probe_session_live())break;
        swd_write32(SQUEUE+0x2cU,4U|bank);
        // The leading DP RDBUFF occupies the queue's TAR slot. It never
        // advances TAR. A successful AP read primes the posted pipeline;
        // the final RDBUFF supplies the last requested data word.
        swd_prepare(write,14U,0,words,0);
        swd_write32(SQUEUE+0x10U,words+3U);
        int dma_error=0;
        unsigned next=count-transferred-words;
        if(next>256U)next=256U;
        if(write && next)
            dma_error=selectio_dma_payload(1,payload_window+1024U*(bank^1U),
                                         (uint8_t *)input+4U*(transferred+words),next);
        if(!write && pending) {
            dma_error=selectio_dma_payload(0,payload_window+1024U*pending_bank,
                                         output+4U*(*completed),pending);
            if(!dma_error)*completed+=pending;
            pending=0;
        }
        if(wait_queue(SQUEUE,0x27U,0x25U)) {
            probe_target_invalidate();
            break;
        }
        uint32_t summary=swd_read32(SQUEUE+0x14U);
        unsigned ack=(summary>>10)&7U;
        unsigned retired=summary&1023U;
        unsigned prefix=write?1U:2U;
        unsigned done=retired>prefix?retired-prefix:0U;
        if(done>words)done=words;
        if(write)*completed+=done;
        else if(!dma_error) {pending=done;pending_bank=bank;}
        transferred+=done;
        if(dma_error || dap_wait_command_error() || !probe_session_live())break;
        if(retired!=words+3U || (summary&0xc000U)) {
            result=(summary&0x2000U) || !ack || ack==DAP_TRANSFER_OK ? DAP_TRANSFER_ERROR:ack;
            break;
        }
        if(transferred==count)result=DAP_TRANSFER_OK;
        bank^=1U;
    }
    if(pending) {
        if(selectio_dma_payload(0,payload_window+1024U*pending_bank,output+4U*(*completed),pending))
            result=DAP_TRANSFER_ERROR;
        else
            *completed+=pending;
    }
    *status=result;
release:
    session.use_dma=0;
    if(swd50_queue_release(live))*status=DAP_TRANSFER_ERROR;
    return 1;
}

int selectio_mem_close(void) {
    if(rtt_live)return selectio_swd50_rtt_detach();
    unsigned port=session.port;
    if (!port) return 0;
    uint32_t base=port==2?JQUEUE:SQUEUE;
    if ((port==2 && (swd_read32(base+4U)&8U) && wait_queue(base,2U,2U)) ||
        (port==1 && wait_queue(base,0x20U,0x20U))) {
        session.poisoned=1;
        probe_target_invalidate();return -1;
    }
    swd_write32(base+8U,port==2?2U:1U);
    if (wait_queue(base,port==2?0x1bU:0x33U,port==2?0x10U:0x30U)) {session.poisoned=1;return -1;}
    if(session.dma) swd_write32(base+(port==2?0x34U:0x2cU),0);
    int failed=selectio_clock_apply(session.previous_divisor);
    Xil_Out32(XSLCR_UNLOCK_ADDR,XSLCR_UNLOCK_CODE);
    Xil_Out32(SLCR_FPGA0_CLK_CTRL,session.clock);
    Xil_Out32(SLCR_LOCK_ADDR,0x767b);
    swd_write32(JTAG_ROUTE,session.route);
    settle();
    if (port==1 && !failed) {
        swd_write32(JTAG_PINS,0x101U);settle();
        swd_write32(JTAG_PINS,session.pins&0x300U);
        if (probe_session_live()) {
            static const uint8_t reset_sequence[9]={255,255,255,255,255,255,255,255,0};
            uint32_t id=0;
            SWJ_Sequence(72,reset_sequence);
            failed|=SWD_Transfer(2,&id)!=DAP_TRANSFER_OK || !(id&1U);
        }
    }
    session.port=0;
    if(probe_target_release()) failed=1;
    if(failed) probe_target_invalidate();
    return failed?-1:0;
}

int selectio_mem_open(const uint8_t fields[4]) {return selectio_mem_open_at(fields,100000000U);}
int selectio_mem_open_at(const uint8_t fields[4],unsigned rate_hz) {
    unsigned port=fields[0],tap=fields[1],slot=fields[2],idle=fields[3];
    unsigned divisor,half_rate;
    if ((DAP_SELECTIO_SLICE==1 && port!=2) || (DAP_SELECTIO_SLICE==2 && port!=1)) return -1;
    if (!DAP_SELECTIO_VARIABLE && port==1 && rate_hz==50000000U) {
        divisor=0;half_rate=1;
    } else if (selectio_clock_plan(rate_hz,&divisor,&half_rate)) return -1;
    if ((port!=1 && port!=2) || port!=DAP_Data.debug_port || session.port || selectio_aux_conflict(port) || tap>31 ||
        slot>63 || (port==1 && idle>15) || (port==2 && (slot<16 || !(idle&1))) ||
        !(swd_read32(SWD_FEATURES)&0x80U) || etm_ddr_owned() || !probe_session_live() ||
        probe_stream_active() || probe_target_claimed()) return -1;
    if (port==2 && (DAP_Data.jtag_dev.count!=2 || DAP_Data.jtag_dev.index ||
        DAP_Data.jtag_dev.ir_length[0]!=4 || DAP_Data.jtag_dev.ir_length[1]!=5)) return -1;
    if (probe_target_claim_on(0,port)) return -1;
    session.route=swd_read32(JTAG_ROUTE);
    session.pins=swd_read32(JTAG_PINS);
    session.clock=Xil_In32(SLCR_FPGA0_CLK_CTRL);
    session.half_rate=half_rate;session.previous_divisor=selectio_clock_divisor();session.port=port;session.poisoned=0;session.bank=0;session.use_dma=0;session.jtag_backoffs=0;session.jtag_idle=idle;
    session.dma=!!(swd_read32(SWD_FEATURES)&0x400U);
    session.words[0]=session.words[1]=0;
    memset(session.bytes,0,sizeof session.bytes);
    memset(session.queue_ticks,0,sizeof session.queue_ticks);
    memset(session.total_ticks,0,sizeof session.total_ticks);
    memcpy(session.profile,fields,4);
    if (port==1) swd_write32(JTAG_PINS,0x100U);
    swd_write32(JTAG_ROUTE,session.route&~2U);
    if (swd_read32(JTAG_ROUTE)!=(session.route&~2U) || ps_fixed133_select()<0 || selectio_clock_apply(divisor)) goto failed;
    uint32_t base=port==2?JQUEUE:SQUEUE;
    swd_write32(base+8U,0U);
    if(wait_queue(base,port==2?7U:0x21U,port==2?5U:0x21U)) goto failed;
    swd_write32(base+(port==2?12U:24U),tap);
    if(port==1) swd_write32(base+12U,(!half_rate)|(slot<<2)|(slot<<8)|(idle<<14));
    return 0;
failed:
    (void)selectio_mem_close();return -1;
}

void selectio_mem_stats(uint64_t values[9]) {
    values[0]=COUNTS_PER_SECOND;
    memcpy(values+1,session.bytes,16);
    memcpy(values+3,session.queue_ticks,16);
    memcpy(values+5,session.total_ticks,16);
    values[7]=session.jtag_backoffs;values[8]=session.jtag_idle;
}

/* Continuous host payload, automatically split at the ADIv5 1 KiB TAR
 * boundary. completed counts confirmed earlier chunks on a failed write. */
int selectio_mem_bulk(unsigned write,uint32_t address,unsigned words,const uint8_t *payload,
                     uint8_t *reply,unsigned *completed,uint32_t *detail) {
    *completed=0;*detail=0;
    if(!session.port || session.poisoned || write>1 || !words || words>4088 ||
       (address&3U) ||
       !((address>=0x20000000U && address<0x20010000U && 4U*words<=0x20010000U-address) ||
         (address>=0x24000000U && address<0x24080000U && 4U*words<=0x24080000U-address))) return -1;
    XTime start,stop;XTime_GetTime(&start);
    while(*completed<words) {
        if(!probe_session_live()) {session.poisoned=1;return -1;}
        unsigned pages=(words-*completed)/256U;
        if(session.port==1 && session.dma && pages>=2 && !(address&1023U)) {
            if(swd_aligned_pages(write,address,pages,payload,reply,completed,detail)) {
                session.poisoned=1;return -1;
            }
            address+=1024U*pages;
            if(write)payload+=1024U*pages;else reply+=1024U*pages;
            continue;
        }
        unsigned count=(1024U-(address&1023U))/4U;
        if(count>words-*completed) count=words-*completed;
        unsigned bank=session.bank++&3U;
        unsigned window=0x45000000U+(session.port==1?0x2000U:0U)+bank*1024U;
        session.use_dma=session.dma && count>=16U;
        if(session.dma) {
            swd_write32(session.port==2?JQUEUE+0x34U:SQUEUE+0x2cU,session.use_dma?(4U|bank):0);
            if(session.use_dma && write && selectio_dma_payload(1,window,(uint8_t *)payload,count)) {
                session.poisoned=1;return -1;
            }
        }
        int rc=session.port==2 ? jtag_block(write,address,count,payload,reply,detail):
                                 swd_block(write,address,count,payload,reply,detail);
        /* An AP read may safely be restarted at its original TAR. A write
         * that posted before WAIT never enters this read-only retry path. */
        while(rc && !write && session.port==2 && *detail==2U && session.jtag_idle<255U &&
              (swd_read32(JQUEUE+4U)&15U)==5U) {
            extend_jtag_idle();
            rc=jtag_block(0,address,count,payload,reply,detail);
        }
        if(!rc && session.use_dma && !write) rc=selectio_dma_payload(0,window+0x1000U,reply,count);
        if(rc) {session.poisoned=1;return rc;}
        *completed+=count;
        address+=4U*count;
        if(write) payload+=4U*count;else reply+=4U*count;
    }
    XTime_GetTime(&stop);
    session.bytes[write]+=4U*words;session.total_ticks[write]+=stop-start;
    return 0;
}

/* Only the RTT consumer owns this SRAM RdOff. An ambiguous posted write
 * must be read back before retrying. All other memory writes remain fail-stop. */
int selectio_commit_rtt_offset(uint32_t addr,uint32_t old,uint32_t next,uint32_t *detail) {
    unsigned completed;
    for(unsigned attempt=0;attempt<5;attempt++) {
        int failed=selectio_mem_bulk(1,addr,1,(const uint8_t *)&next,0,&completed,detail);
        if(failed) {
            if(session.port!=2 || *detail!=2U || (swd_read32(JQUEUE+4U)&15U)!=5U) return -1;
            extend_jtag_idle();session.poisoned=0;
        }
        uint32_t actual;
        if(selectio_mem_bulk(0,addr,1,0,(uint8_t *)&actual,&completed,detail))return -1;
        if(actual==next)return 0;
        if(!failed || actual!=old) {session.poisoned=1;*detail=actual;return -1;}
    }
    session.poisoned=1;return -1;
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
