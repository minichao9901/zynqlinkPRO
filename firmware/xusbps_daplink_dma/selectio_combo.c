#if DAP_SELECTIO
#include "selectio_combo.h"
#include "selectio_block.h"
#include "probe_stream.h"
#include "dap_wait.h"
#include "xtime_l.h"
#include <stdint.h>
#include <string.h>

/* One AP owner schedules complete sample groups and bounded RTT bursts.
 * These FIFOs are in PS DDR. RTT RdOff is committed only after the bytes
 * are in private storage. USB IOC advances the independent host tails. */
#define RTT_CAPACITY 16384U
#define GROUP_CAPACITY 1024U
#define MAX_RTT_CHUNK 1024U
#define RTT_ONLY_CHUNK 4096U
static uint32_t rtt_payload[RTT_ONLY_CHUNK/4U+1U] __attribute__((aligned(32)));
static unsigned burst_limit;
static uint8_t rtt_bytes[RTT_CAPACITY] __attribute__((aligned(32)));
static uint32_t groups[GROUP_CAPACITY][9] __attribute__((aligned(32)));
static uint32_t addresses[8],nvars,ring,size,rd,descriptor,period_ticks;
static uint32_t skip_count,fail_stage,rhead,ghead,diagnostic[8];
static volatile uint32_t rtail,gtail;
static unsigned running,opened;
static XTime origin,deadline,period,last_rtt,rtt_cost;
static uint32_t get_u32(const uint8_t *p){uint32_t v;memcpy(&v,p,4);return v;}
static int sram(uint32_t addr,uint32_t bytes) {
    return bytes && addr>=0x20000000U && addr<0x20010000U && bytes<=0x20010000U-addr;
}
static int read_words(uint32_t addr,unsigned words,void *data) {
    unsigned count;uint32_t details;
    int rc=selectio_mem_bulk(0,addr,words,0,data,&count,&details);
    if(rc) {diagnostic[0]=1;diagnostic[1]=addr;diagnostic[2]=words;diagnostic[3]=count;diagnostic[4]=details;}
    return rc;
}
static int write_offset(uint32_t v) {
    uint32_t detail=0;
    int rc;
    if(nvars) rc=selectio_commit_rtt_offset(descriptor+16U,rd,v,&detail);
    else {
        /* Standalone SWD has an unambiguous ACK and the memory queue
         * already verifies the posted write with RDBUFF and CTRL/STAT. */
        unsigned completed;
        rc=selectio_mem_bulk(1,descriptor+16U,1,(const uint8_t *)&v,0,&completed,&detail);
    }
    if(rc) {diagnostic[0]=2;diagnostic[1]=descriptor+16U;diagnostic[2]=1;diagnostic[4]=detail;diagnostic[5]=v;}
    return rc;
}
int selectio_combo_active(void){return opened!=0;}
int selectio_combo_stop(void) {
    running=0;
    if(!opened) return 0;
    return selectio_mem_close();
}
void selectio_combo_reset(void) {running=opened=0;rhead=rtail=ghead=gtail=0;}
static int start(const uint8_t *p,unsigned bytes) {
    if(opened || bytes<16 || selectio_mem_active()) return -1;
    unsigned n=p[12],channel=p[13];
    unsigned plan_bytes=16U+4U*n;
    uint32_t cb=get_u32(p+4),ticks=get_u32(p+8);
    if(n>8 || (bytes!=plan_bytes && (bytes!=plan_bytes+4U || !n)) ||
       channel>=16 || p[14]>1 || p[15] ||
       (n ? (!ticks || ticks>24000000U) : (ticks || p[0]!=1 || !p[14])) ||
       (cb&3U) || !sram(cb,24U+(channel+1U)*24U)) return -1;
    uint32_t clock=bytes==plan_bytes ? (p[14]?50000000U:100000000U) : get_u32(p+plan_bytes);
    if(clock<50000000U || clock>100000000U) return -1;
    for(unsigned i=0;i<n;i++) {
        addresses[i]=get_u32(p+16+4U*i);
        if((addresses[i]&3U) || !sram(addresses[i],4)) return -1;
    }
    if(selectio_mem_open_at(p,clock)) return -1;
    memset(diagnostic,0,sizeof diagnostic);opened=1;fail_stage=1;
    uint32_t head[6],up[6];
    descriptor=cb+24U+24U*channel;
    if(read_words(cb,6,head) || memcmp(head,"SEGGER RTT",10) ||
       head[4]<=channel || head[4]>64 || read_words(descriptor,6,up)) goto failed;
    ring=up[1];size=up[2];rd=up[4];
    if(size<2 || !sram(ring,size) || rd>=size || up[3]>=size) goto failed;
    nvars=n;period_ticks=ticks;
    /* Keep transfers short for high-rate sampling, use a full MEM-AP
     * page when the period has room for a longer contiguous read. */
    burst_limit=ticks/16U;
    if(burst_limit<16U) burst_limit=16U;
    if(burst_limit>MAX_RTT_CHUNK) burst_limit=MAX_RTT_CHUNK;
    if(!n)burst_limit=RTT_ONLY_CHUNK;
    period=((uint64_t)ticks*COUNTS_PER_SECOND+12000000U)/24000000U;
    rhead=rtail=ghead=gtail=skip_count=0;fail_stage=0;
    XTime_GetTime(&origin);deadline=origin;last_rtt=origin;
    rtt_cost=COUNTS_PER_SECOND/20000U;running=1;return 0;
failed:
    (void)selectio_combo_stop();opened=0;return -1;
}
static int sample(XTime now) {
    if(ghead-gtail>=GROUP_CAPACITY) {skip_count++;return 0;}
    uint32_t *group=groups[ghead%GROUP_CAPACITY];
    group[0]=(uint32_t)(((now-origin)*24000000ULL)/COUNTS_PER_SECOND);
    for(unsigned i=0;i<nvars;) {
        unsigned count=1;
        while(i+count<nvars && addresses[i+count]==addresses[i]+4U*count) count++;
        if(read_words(addresses[i],count,group+i+1)) return -1;
        i+=count;
    }
    __sync_synchronize();ghead++;return 0;
}
static int drain_rtt(void) {
    uint32_t wr,available,space=RTT_CAPACITY-(rhead-rtail);
    if(!space) return 0;
    if(read_words(descriptor+12U,1,&wr)) return -1;
    if(wr>=size) {diagnostic[0]=3;diagnostic[5]=size;diagnostic[6]=wr;return -1;}
    if(wr==rd) return 0;
    available=wr>rd?wr-rd:size-rd;
    if(available>space) available=space;
    if(available>burst_limit) available=burst_limit;
    uint32_t at=ring+rd,first=at&~3U;
    unsigned prefix=at-first,words=(available+prefix+3U)/4U;
    if(read_words(first,words,rtt_payload)) return -1;
    unsigned index=rhead%RTT_CAPACITY;
    unsigned part=RTT_CAPACITY-index;
    if(part>available) part=available;
    memcpy(rtt_bytes+index,(uint8_t *)rtt_payload+prefix,part);
    memcpy(rtt_bytes,(uint8_t *)rtt_payload+prefix+part,available-part);
    uint32_t next=rd+available;
    if(next==size) next=0;
    __sync_synchronize();
    if(write_offset(next)) return -1;
    rd=next;__sync_synchronize();rhead+=available;return 0;
}
void selectio_combo_poll(void) {
    if(!running) return;
    if(!nvars) {
        if(drain_rtt()) {fail_stage=3;running=0;}
        return;
    }
    XTime now;XTime_GetTime(&now);
    if(now>=deadline) {
        XTime missed=(now-deadline)/period;
        skip_count+=(uint32_t)missed;deadline+=(missed+1)*period;
        if(sample(now)) {fail_stage=2;running=0;return;}
        XTime_GetTime(&now);
    }
    /* Reserve the next sampling deadline when there is slack. Under
     * saturation still service RTT at least once per ms and count lateness. */
    if((deadline>now && deadline-now>rtt_cost) || now-last_rtt>=COUNTS_PER_SECOND/1000U) {
        last_rtt=now;
        if(drain_rtt()) {fail_stage=3;running=0;return;}
        XTime_GetTime(&now);
        XTime elapsed=now-last_rtt;
        rtt_cost=elapsed>rtt_cost?elapsed:(15*rtt_cost+elapsed)/16;
    }
}
void selectio_combo_commit(unsigned source,unsigned n) {
    if(source==6 && n<=rhead-rtail) rtail+=n;
    if(source==7 && n<=ghead-gtail) gtail+=n;
}
int selectio_combo_frame(unsigned op,const uint8_t *request,unsigned bytes,uint8_t *out,
                         unsigned capacity,unsigned *length,unsigned *consume,unsigned *source) {
    if(op==0) {dap_wait_begin();return start(request,bytes);}
    if(!opened || bytes) return -1;
    if(op==1) {
        unsigned n=rhead-rtail;if(n>capacity)n=capacity;
        unsigned index=rtail%RTT_CAPACITY,part=RTT_CAPACITY-index;if(part>n)part=n;
        memcpy(out,rtt_bytes+index,part);memcpy(out+part,rtt_bytes,n-part);
        *length=*consume=n;*source=6;return 0;
    }
    if(op==2) {
        unsigned stride=4U*(1+nvars),n=ghead-gtail;
        if(n>capacity/stride) n=capacity/stride;
        for(unsigned i=0;i<n;i++) memcpy(out+i*stride,groups[(gtail+i)%GROUP_CAPACITY],stride);
        *length=n*stride;*consume=n;*source=7;return 0;
    }
    if(op==3) {dap_wait_begin();return selectio_combo_stop();}
    if(op==6 && capacity>=32) {memcpy(out,diagnostic,32);*length=32;return 0;}
    if(op==4 && capacity>=32) {
        uint32_t stats[]={running,fail_stage,period_ticks,rhead,rtail,ghead,gtail,skip_count};
        memcpy(out,stats,sizeof stats);*length=sizeof stats;return 0;
    }
    if(op==5 && !running && !selectio_mem_active() && rtail==rhead && gtail==ghead) {
        selectio_combo_reset();return 0;
    }
    return -1;
}
#endif
