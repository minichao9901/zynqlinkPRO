// Production PS stream code with deterministic USB and trace FIFO mocks.
#include "probe_host_platform.h"
#include "../../firmware/xusbps_daplink_dma/etm_stream.c"
static uint16_t fifo[8192];
static uint32_t wr,rd,control_reg,status_reg,total_records;
static uint8_t sent[512];
static uint32_t sent_length,send_calls;
static uintptr_t sent_pointer;
static int fail_send,reset_during_read;
static uint64_t timer;
void XTime_GetTime(XTime *t){*t=timer;}
static uint32_t pll_register=54U<<12,pll_status=4,reference_config;
uint32_t probe_target_fclk(void){return 120000000;}
uint32_t Xil_In32(uintptr_t a){
  if(a==0xf8000108U)return pll_register;
  if(a==0xf800010cU)return pll_status;
  if(a==0xf8000180U)return reference_config;
  switch((a-ETM_BASE)/4){
    case 0:return 0x45544d31;
    case 1:return control_reg;
    case 2:return (status_reg&~1U)|(control_reg&1)|8;
    case 3:return wr-rd;
    case 4:if(reset_during_read){reset_during_read=0;etm_usb_reset();}return rd<wr?fifo[rd++]:0x80000000U;
    case 5:return total_records;
    default:return 0;
  }
}
void Xil_Out32(uintptr_t a,uint32_t value){
  if(a==0xf8000008U||a==0xf8000004U)return;
  if(a==0xf8000180U){reference_config=value;return;}
  assert(a==ETM_BASE+4);control_reg=value&13;
  if(value&2){wr=rd=total_records=status_reg=0;}
}
int XUsbPs_EpBufferSend(XUsbPs *usb,u8 ep,u8 *p,u32 n){
  (void)usb;assert(ep==2 && (n==0 || (n>=32 && n<=512)));send_calls++;
  if(fail_send)return 1;
  memcpy(sent,p,n);sent_length=n;sent_pointer=(uintptr_t)p;return 0;
}
static uint32_t word(unsigned n){return sent[4*n]|((uint32_t)sent[4*n+1]<<8)|((uint32_t)sent[4*n+2]<<16)|((uint32_t)sent[4*n+3]<<24);}
static void complete(XUsbPs *usb){etm_usb_event(usb,2,XUSBPS_EP_EVENT_DATA_TX,(void*)sent_pointer);}
static void append(unsigned n){unsigned i;for(i=0;i<n;i++)fifo[wr++]=(uint16_t)(0x200|(i&255));total_records+=n;status_reg|=2;}
int main(void){
  XUsbPs usb={0};uint32_t reply[8],before;
  assert(etm_reference_init()==199999998U);etm_reference_snapshot(reply);assert(reply[0]==199999998U && reply[1]==reference_config);
  pll_status=0;before=reference_config;assert(!etm_reference_init() && reference_config==before);pll_status=4;assert(etm_reference_init()==199999998U);
  etm_usb_configured(&usb);etm_control(0x301,reply);assert(reply[0]==0x45544d31 && reply[7]==0x301);
  etm_poll(&usb);assert(running && !pending && capture_id==1 && !(head-tail));
  append(300);etm_poll(&usb);assert(word(0)==0x3154455a && word(1)==0 && word(3)==240 && sent_length==512 && sent[33]==2 && (word(2)&16));
  before=tail;etm_usb_event(&usb,7,XUSBPS_EP_EVENT_DATA_TX,(void*)sent_pointer);assert(tail==before);
  etm_usb_event(&usb,2,XUSBPS_EP_EVENT_DATA_TX,(void*)(sent_pointer+32));assert(tail==before);
  // One slot stays owned by USB while the next packet is staged.
  etm_poll(&usb);assert(head==1 && tail==0 && fill_count==60);
  timer+=2000;etm_poll(&usb);assert(head==2 && tail==0 && !fill_count);
  complete(&usb);etm_poll(&usb);assert(word(1)==1 && word(3)==60 && sent_length==152);complete(&usb);
  etm_control(2,reply);etm_poll(&usb);assert(!running && (word(2)&8) && word(3)==0 && sent_length==32);complete(&usb);
  before=tail;for(unsigned i=0;i<16;i++){etm_poll(&usb);assert(busy_zlp && sent_length==0);complete(&usb);}assert(!flush_remaining && tail==before);
  // No-input captures still get a final short packet to release transferIn().
  etm_control(0x301,reply);etm_poll(&usb);etm_control(2,reply);etm_poll(&usb);assert((word(2)&8) && word(1)==0);complete(&usb);
  etm_control(0x301,reply);etm_poll(&usb);append(240);fail_send=1;etm_poll(&usb);assert(!busy && head-tail==1);before=rd;
  etm_poll(&usb);assert(rd==before && head-tail==1);fail_send=0;etm_poll(&usb);assert(busy);complete(&usb);
  // Source loss is sticky in transmitted status; stopping does not hide it.
  status_reg|=4;etm_control(2,reply);etm_poll(&usb);assert((word(2)&12)==12);complete(&usb);
  etm_control(0x301,reply);etm_poll(&usb);append(3000);for(before=0;before<12;before++)etm_poll(&usb);
  assert(head-tail==8 && rd==8*240);before=rd;etm_poll(&usb);assert(rd==before);
  etm_usb_reset();etm_usb_configured(&usb);assert(!head && !tail && !busy && !running);
  // USB reset during MMIO copying must not publish an old capture into the new session.
  etm_control(0x301,reply);etm_poll(&usb);append(4);reset_during_read=1;before=send_calls;etm_poll(&usb);assert(send_calls==before && !configured && !fill_count);
  puts("PASS production ETM USB: EP2 IN isolation, ZET1 framing, empty/end/loss, retry, queue ownership, reset epoch");return 0;
}
