// Compile the production state machine with deterministic USB/SWD/MMIO mocks.
#include "probe_host_platform.h"
#include "../../firmware/xusbps_daplink_dma/probe_stream.c"
static uint8_t memory[4096],rx_packet[64];
static uint32_t regs[8],timer,read_calls,write_calls,claim_calls,release_calls;
static uint32_t sample_fifo[1024],sample_read,sample_write;
static unsigned samples,remaining;
static int fail_send,fail_read,fail_write,host_dtr=1;
static uintptr_t sent_buffer[8];
static uint32_t sent_len[8];
static uint32_t packet_regs[16],dma_calls,packet_acks;
static int fail_dma,reset_in_dma;
int swd_dma_packet_to(uint32_t bank,uint32_t bytes,uint8_t *destination) {
    assert(bank<8 && bytes<=2048);dma_calls++;
    if(fail_dma) return -1;
    if(reset_in_dma) probe_usb_reset();
    memset(destination,0xa5,bytes);return 0;
}
void XTime_GetTime(XTime *p) {*p=timer;}
uint32_t Xil_In32(uintptr_t addr) {
    if(addr>=0x42020000U && addr<0x42020040U) return packet_regs[(addr-0x42020000U)/4];
    unsigned n=(unsigned)((addr-0x40010060U)/4);
    if(n==0) return 0x48530000|regs[0];
    if(n==1) return (samples<<16)|(regs[0]&1);
    if(n==5) {
        uint32_t x=sample_fifo[sample_read++];
        if(--remaining==0) {samples--;remaining=nwords+1;}
        return x;
    }
    return n<8 ? regs[n] : 3;
}
void Xil_Out32(uintptr_t addr,uint32_t value) {
    if(addr>=0x42020000U && addr<0x42020040U) {
        unsigned r=(unsigned)((addr-0x42020000U)/4);
        if(r==3 && value==1) {packet_acks++;if(mode!=1) packet_regs[2]=0;}
        else packet_regs[r]=value;
        return;
    }
    unsigned n=(unsigned)((addr-0x40010060U)/4);
    if(n<7) regs[n]=value;
    if(n==0 && (value&2)) {samples=sample_read=sample_write=0;}
}
int XUsbPs_EpBufferSend(XUsbPs *u,u8 ep,u8 *p,u32 n) {
    (void)u;if(fail_send) return 1;sent_buffer[ep]=(uintptr_t)p;sent_len[ep]=n;return 0;
}
int XUsbPs_EpBufferSendWithZLT(XUsbPs *u,u8 ep,u8 *p,u32 n) {return XUsbPs_EpBufferSend(u,ep,p,n);}
int XUsbPs_EpBufferReceive(XUsbPs *u,u8 ep,u8 **p,u32 *n,u32 *h) {(void)u;(void)ep;*p=rx_packet;*n=64;*h=0;return 0;}
void XUsbPs_EpBufferRelease(u32 x) {(void)x;}
u8 usbd_cdc_acm_get_dtr(void) {return (u8)host_dtr;}
int probe_target_claim(uint32_t hz) {(void)hz;claim_calls++;return 0;}
int probe_target_transport(uint32_t port) {return port<=2 ? 0 : -6;}
void probe_target_release(void) {release_calls++;}
void probe_target_forget(void) {release_calls++;}
uint32_t probe_target_fclk(void) {return 100000000;}
int probe_target_read(uint32_t addr,uint8_t *p,uint32_t n) {
    read_calls++;if(fail_read) return -4;assert(addr>=0x20000000 && addr+n<=0x20001000);
    memcpy(p,memory+addr-0x20000000,n);return 0;
}
int probe_target_write_word(uint32_t addr,uint32_t value) {
    write_calls++;if(fail_write) return -4;
    assert(addr>=0x20000000 && addr+4<=0x20001000);put32(memory+addr-0x20000000,value);return 0;
}
static void command_req(uint8_t *req,uint8_t cmd,uint8_t act,unsigned len) {
    memset(req,0,64);req[0]=1;req[1]=(uint8_t)len;req[2]=cmd;req[3]=act;
}
static void queue_sample(uint32_t stamp,uint32_t value) {
    assert(nwords==1);sample_fifo[sample_write++]=stamp;sample_fifo[sample_write++]=value;
    if(!samples) remaining=2;samples++;
}
int main(void) {
    XUsbPs usb={0};uint8_t req[64],res[64],*p;uint32_t out[12],before;unsigned i;
    configured=1;reset_pending=0;current_epoch=epoch;
    // Validate USB report contract, exact request lengths and unsupported actions.
    assert(probe_hid_descriptor(res,64,1)==29);
    command_req(req,0x31,1,2);control(req,res);assert((int8_t)res[3]==-6 && mode==0);
    command_req(req,0x32,99,2);control(req,res);assert((int8_t)res[3]==-9);
    // Eight wide, unaligned variables fit 24 aligned word descriptors and 64-byte frames.
    command_req(req,0x32,10,56);put32(req+4,48);req[9]=8;
    for(i=0;i<8;i++) {put32(req+10+6*i,0x20000001+16*i);req[14+6*i]=8;req[15+6*i]=7;}
    control(req,res);assert(res[3]==0 && nvars==8 && nwords==24 && frame_size==64 && version==2);
    req[14]=255;control(req,res);assert((int8_t)res[3]==-6);
    // One u32 plan: DEF is queued before DATA; timestamp gaps stay in the
    // fixed-period packet and are accounted for by the STAT skipped counter.
    command_req(req,0x32,10,14);put32(req+4,48);req[9]=1;put32(req+10,0x20000100);req[14]=4;req[15]=4;
    control(req,res);assert(res[3]==0 && nwords==1);
    command_req(req,0x32,1,2);control(req,res);assert(mode==2 && hss.in==1);
    p=hss.data[0];assert(p[3]==1 && p[2]==2 && get32(p+20)==48 && p[26]==1);
    queue_sample(1000,0x12345678);queue_sample(1048,0xabcdef01);queue_sample(1144,0x76543210);
    hss_poll();assert(hss.in==1 && fill_count==3 && produced==3);
    timer+=11000;hss_poll();assert(hss.in==2 && fill_count==0);
    p=hss.data[1];assert(p[3]==2 && get32(p+8)==1000 && p[12]==3 && get32(p+16)==0x12345678 && get32(p+20)==0xabcdef01 && get32(p+24)==0x76543210);
    // FIFO remains untouched with a blocked USB queue.
    hss.in=hss.out+QSIZE;queue_sample(1192,0x55555555);before=sample_read;hss_poll();assert(sample_read==before);
    hss.out=hss.in;samples=0;sample_read=sample_write=0;
    probe_before_dap();assert(release_calls && !regs[0]);probe_after_dap();assert(regs[0]&1);
    command_req(req,0x32,0,2);control(req,res);assert(mode==0);
    // RTT ring wrapping, RdOff commit and retry: no consumption without queue space.
    cdc.in=cdc.out=0;memcpy(memory+0xf0,"SEGGER RTT",10);put32(memory+0x100,1);put32(memory+0x104,0);
    put32(memory+0x10c,0x20000300);put32(memory+0x110,16);put32(memory+0x114,3);put32(memory+0x118,12);
    for(i=0;i<16;i++) memory[0x300+i]=(uint8_t)i;
    command_req(req,0x31,1,11);put32(req+4,0x20000000);put32(req+8,4096);control(req,res);assert(mode==1);
    for(i=0;i<4 && !cb;i++) rtt_poll();assert(cb==0x200000f0 && up==0x20000108);
    fail_write=1;rtt_poll();assert(pending_len==4 && cdc.in==0 && get32(memory+0x118)==12);
    fail_write=0;timer+=11000;before=read_calls;rtt_poll();assert(read_calls==before && pending_len==0 && cdc.in==1 && get32(memory+0x118)==0);
    assert(!memcmp(cdc.data[0],memory+0x30c,4));
    rtt_poll();assert(cdc.in==2 && get32(memory+0x118)==3 && !memcmp(cdc.data[1],memory+0x300,3));
    cdc.in=cdc.out+QSIZE;before=read_calls;rtt_poll();assert(read_calls==before);
    cdc.out=cdc.in;host_dtr=0;rtt_poll();assert(read_calls==before);host_dtr=1;
    // Submission failure retains a slot; CDC stream chunks no longer carry a
    // per-chunk ZLP, so the data completion releases the slot immediately.
    mode=0;cdc.in=1;cdc.out=0;cdc.busy=0;cdc.len[0]=512;
    fail_send=1;kick(&usb,&cdc);assert(!cdc.busy && cdc.out==0);
    fail_send=0;kick(&usb,&cdc);assert(cdc.busy && sent_len[3]==512);
    probe_usb_event(&usb,3,XUSBPS_EP_EVENT_DATA_TX,(void *)sent_buffer[3]);assert(!cdc.busy && cdc.out==1);
    probe_usb_event(&usb,3,XUSBPS_EP_EVENT_DATA_TX,(void *)(sent_buffer[3]+512));assert(!cdc.busy && cdc.out==1);
    kick(&usb,&cdc);assert(!cdc.busy && sent_len[3]==512); // No per-chunk ZLP.
    timer+=2000;kick(&usb,&cdc);assert(cdc.busy && cdc.zlp && sent_len[3]==0 && cdc.out==1);
    probe_usb_event(&usb,3,XUSBPS_EP_EVENT_DATA_TX,(void *)sent_buffer[3]);
    assert(!cdc.busy && !cdc_needs_zlp && cdc.out==1); // ZLP owns no payload slot.
    // Reset invalidates every old queue and stops sampling, including late completions.
    probe_usb_reset();probe_poll(&usb);assert(mode==0 && cdc.in==cdc.out && hss.in==hss.out && pending_len==0);
    probe_usb_event(&usb,3,XUSBPS_EP_EVENT_DATA_TX,(void *)(sent_buffer[3]+512));assert(cdc.out==0);
    configured=1;current_epoch=epoch;status(0x32,out,1);assert(out[0]==0x31535348 && out[2]==24000000);
    // Real DMA path: failed copies keep PL ownership. A successful RTT copy
    // is held out of USB until RdOff completion changes the PL tail index.
    pl_packets=1;mode=1;discard=0;cdc.in=cdc.out=0;
    packet_regs[2]=0x01000000U|512;packet_regs[3]=10;fail_dma=1;
    packet_poll();assert(dma_calls==1 && packet_acks==0 && !dma_pending && cdc.in==0);
    fail_dma=0;packet_poll();assert(dma_pending && packet_acks==1 && cdc.in==0);
    packet_poll();assert(dma_calls==2 && cdc.in==0); // No second DMA while committing.
    packet_regs[3]++;packet_regs[2]=0;packet_poll();
    assert(!dma_pending && cdc.in==1 && cdc.len[0]==512 && cdc.data[0][0]==0xa5);
    // HSS hands the DMA destination directly to USB and never edits a slot
    // still in the USB queue, even if a second PL packet is ready.
    mode=2;flags=0;hss.in=hss.out=0;packet_regs[2]=(3U<<16)|512;
    packet_poll();assert(hss.in==1 && hss.data[0][0]==0xa5 && packet_acks==2);
    hss.in=hss.out+QSIZE;packet_regs[2]=512;before=dma_calls;packet_poll();assert(dma_calls==before && packet_acks==2);
    hss.in=hss.out=0;reset_in_dma=1;packet_poll();
    assert(reset_pending && hss.in==0 && packet_acks==2); // Reset during copy cannot ACK/consume.
    puts("PASS production probe C: HID, 8 variables, HSS DEF/DATA/gaps, backpressure, RTT wrap/RdOff retry, DAP handoff, ZLP, reset");
    return 0;
}
