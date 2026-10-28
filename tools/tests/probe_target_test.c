#include "probe_target_platform.h"
#include "../../firmware/xusbps_daplink_dma/probe_target.c"
int probe_session_live(void) {return 1;}
DAP_Data_t DAP_Data={.debug_port=1,.clock_delay=7,.fast_clock=0};
static uint32_t clock_reg=0x100a00,cfg=0x20010,ap_csw=0x23000052,ap_tar=0x20000040;
static uint32_t dp_select=0x01000010,posted,blocks,sequences;
static int inject_wait,inject_fault;
static int jtag_present,jtag_calls,idcode_reads;
static uint32_t jtag_regs[8]={3,4,0,0,0,0,4,10};
void DAP_JTAG_ClockChanged(void) {}
int DAP_JTAG_AutoConfigure(void) {
    DAP_Data.jtag_dev.count=2;DAP_Data.jtag_dev.ir_length[0]=4;
    DAP_Data.jtag_dev.ir_length[1]=5;DAP_Data.jtag_dev.ir_after[0]=5;
    DAP_Data.jtag_dev.ir_before[1]=4;return 0;
}
uint32_t Xil_In32(uintptr_t a) {
    if(a==0x4001004c) return jtag_present ? 15 : 7;
    if(a>=JTAG_ROUTE && a<JTAG_RX_DATA) return jtag_regs[(a-JTAG_ROUTE)/4];
    return a==SWD_CFG ? cfg : clock_reg;
}
void Xil_Out32(uintptr_t a,uint32_t d) {
    if(a>=JTAG_ROUTE && a<JTAG_RX_DATA) jtag_regs[(a-JTAG_ROUTE)/4]=d;
    else if(a==SWD_CFG) cfg=d;else if(a==SLCR_FPGA0_CLK_CTRL) clock_reg=d;
}
int DAP_JTAG_Select(uint32_t index) {DAP_Data.jtag_dev.index=(uint8_t)index;return 0;}
uint32_t JTAG_ReadIDCode(void) {idcode_reads++;return 0x4ba00477;}
void JTAG_IR(uint32_t ir) {jtag_regs[7]=ir;}
uint8_t DAP_JTAG_MemTransfer(uint32_t req,uint32_t *data) {jtag_calls++;return SWD_Transfer(req,data);}
static uint32_t memory_word(uint32_t a) {return a^0x12345678;}
uint8_t SWD_Transfer(uint32_t req,uint32_t *d) {
    if(inject_fault) return 4;
    if(inject_wait) {inject_wait--;return 2;}
    uint32_t value=*d;
    switch(req) {
    case 8: dp_select=value;break;
    case 1: ap_csw=value;break;
    case 5: ap_tar=value;break;
    case 3: *d=posted;posted=ap_csw;break;
    case 7: *d=posted;posted=ap_tar;break;
    case 14: *d=posted;break;
    case 13: posted=0;break;
    case 2: *d=0x2ba01477;break;
    case 6: *d=0xa0000000;break;
    default: break;
    }
    probe_target_observe(req,value,1);return 1;
}
uint32_t DAP_ExecuteCommand(const uint8_t *p,uint8_t *q) {
    memset(q,0,1040);q[0]=p[0];
    if(p[0]==0x11) {DAP_Data.clock_delay=1;clock_reg=0x102800;cfg=0x10010;}
    else if(p[0]==2) {q[1]=p[1];DAP_Data.debug_port=p[1];}
    else if(p[0]==0x15) {DAP_Data.jtag_dev.count=p[1];DAP_Data.jtag_dev.ir_length[0]=p[2];}
    else if(p[0]==0x12) sequences++;
    else if(p[0]==6) {
        uint32_t count=p[2]|((uint32_t)p[3]<<8);blocks++;
        assert(count && count<=256 && (ap_tar&1023)+4*count<=1024);
        q[1]=p[2];q[2]=p[3];q[3]=1;
        for(uint32_t i=0;i<count;i++) {uint32_t v=memory_word(ap_tar+4*i);memcpy(q+4+4*i,&v,4);}
        ap_tar=(ap_tar&~1023U)|((ap_tar+4*count)&1023);
    }
    return 0;
}
int main(void) {
    uint8_t data[1024],expected[1028];uint32_t i,old_clock=clock_reg,old_cfg=cfg;
    probe_target_observe(8,dp_select,1);inject_wait=2;
    assert(!probe_target_claim(20000000));
    assert(dp_select==0 && ap_csw==0x23000052 && DAP_Data.clock_delay==1);
    assert(!probe_target_read(0x200003fd,data,1024));
    for(i=0;i<1028;i+=4) {uint32_t v=memory_word(0x200003fc+i);memcpy(expected+i,&v,4);}
    assert(!memcmp(data,expected+1,1024) && blocks==2);
    assert(probe_target_read(0xfffffffc,data,8)==-6);
    assert(!probe_target_write_word(0x20000000,0x89abcdef));
    assert(probe_target_write_word(0x20000001,0)==-4);
    probe_target_release();
    assert(dp_select==0x01000010 && ap_csw==0x23000052 && ap_tar==0x20000040);
    assert(clock_reg==old_clock && cfg==old_cfg && DAP_Data.clock_delay==7);
    // Failed claims restore the host clock/config too.
    inject_fault=1;assert(probe_target_claim(20000000)==-4);
    assert(clock_reg==old_clock && cfg==old_cfg && DAP_Data.clock_delay==7);
    inject_fault=0;probe_target_forget();DAP_Data.debug_port=0;
    assert(!probe_target_claim(20000000));probe_target_release();assert(sequences==1 && DAP_Data.debug_port==0);
    assert(!probe_target_claim(20000000));probe_target_release();assert(sequences==1);
    assert(probe_target_transport(3)==-6 && probe_target_transport(2)==-10);
    jtag_present=1;assert(probe_target_transport(2)==0);DAP_Data.debug_port=1;
    assert(probe_target_claim(20000000)==-7); // Connected SWD host cannot be silently switched.
    DAP_Data.debug_port=0;probe_target_forget();
    assert(!probe_target_claim(20000000) && DAP_Data.debug_port==2 && idcode_reads==1);
    assert(!probe_target_read(0x200003fd,data,1024) && jtag_calls>0);
    probe_target_release();assert(DAP_Data.debug_port==0 && sequences==2);
    assert(!probe_target_claim(20000000));probe_target_release();assert(sequences==2);
    DAP_Data.debug_port=2;jtag_regs[6]=0;assert(probe_target_claim(20000000)==-7);
    puts("PASS production target C: WAIT, unaligned 1KiB split, overflow, SELECT/CSW/TAR/clock restore, independent initialization");
    return 0;
}
