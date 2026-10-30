// The only trace data endpoint is EP2 IN. EP2 OUT remains CMSIS-DAP.
// EP0 requests only enqueue state changes; MMIO draining runs in main.
#include "etm_stream.h"
#include "probe_stream.h"
#include "xil_io.h"
#include "xil_exception.h"
#include "xusbps_endpoint.h"
#include "xtime_l.h"
#include <string.h>
#define ETM_BASE 0x40030000U
#define ER(n) Xil_In32(ETM_BASE+4U*(n))
#define EW(n,v) Xil_Out32(ETM_BASE+4U*(n),(v))
#define QSIZE 8U
#define RECORDS 240U
static uint8_t packets[QSIZE][512] __attribute__((aligned(32)));
static uint16_t lengths[QSIZE];
static volatile uint32_t head,tail,epoch;
static volatile uint8_t configured,busy,busy_zlp,flush_remaining;
static volatile uint16_t pending;
static uint8_t running,ending;
static uint32_t sequence,capture_id;
static volatile uintptr_t active_buffer;
static volatile uint32_t fill_count;
static uint32_t fill_activity;
static uint8_t flush_zero[32] __attribute__((aligned(32)));
static uint32_t now_us(void){XTime t;XTime_GetTime(&t);return (uint32_t)(t/(COUNTS_PER_SECOND/1000000ULL));}
static uint32_t reference_hz;
uint32_t etm_reference_init(void){
  uint32_t pll=Xil_In32(0xf8000108U),locked=Xil_In32(0xf800010cU);
  uint32_t hz=33333333U*((pll>>12)&127U),best=0,error=~0U,a,b,d0=0,d1=0;
  reference_hz=0;
  if((pll&0x13U) || !(locked&4U))return 0;
  for(a=1;a<=63;a++)for(b=1;b<=63;b++){
    uint32_t value=hz/a/b,delta=value>200000000U?value-200000000U:200000000U-value;
    if(value>=190000000U && value<=210000000U && delta<error){best=value;error=delta;d0=a;d1=b;}
  }
  if(!best)return 0;
  // Only FCLK1's divider changes; PLLs, CPU clocks and DAP's FCLK0 are untouched.
  Xil_Out32(0xf8000008U,0xdf0dU);
  Xil_Out32(0xf8000180U,1U|(d0<<8)|(d1<<20));
  Xil_Out32(0xf8000004U,0x767bU);
  reference_hz=best;return best;
}
void etm_reference_snapshot(uint32_t reply[4]){
  reply[0]=reference_hz;reply[1]=Xil_In32(0xf8000180U);
  reply[2]=Xil_In32(0xf8000108U);reply[3]=(ER(2)>>3)&1U;
}
static uint32_t trace_status(void){
  uint32_t cfg=Xil_In32(0x40010008U);
  uint32_t half=1U+((cfg>>13)&15U)+(((cfg>>28)&15U)<<4);
  uint32_t tck_khz=probe_target_fclk()/(2U*half*1000U);
  uint32_t status=ER(2);
  return (status&7U)|((status&8U)<<1)|((tck_khz&65535U)<<16);
}
static void put32(uint8_t *p,uint32_t v){p[0]=v;p[1]=v>>8;p[2]=v>>16;p[3]=v>>24;}
static uint32_t irq_save(void){uint32_t f=mfcpsr();mtcpsr(f|0x80U);return f;}
static void irq_restore(uint32_t f){mtcpsr(f);}
static void reset_endpoint(XUsbPs *usb,unsigned reset_toggle){
  unsigned i;
  XUsbPs_EpFlush(usb,ETM_BULKIN_EP,XUSBPS_EP_DIRECTION_IN);
  XUsbPs_WriteReg(usb->Config.BaseAddress,XUSBPS_EPCOMPL_OFFSET,1U<<(16+ETM_BULKIN_EP));
  for(i=0;i<usb->DeviceConfig.EpCfg[ETM_BULKIN_EP].In.NumBufs;i++){
    XUsbPs_dTD *td=&usb->DeviceConfig.Ep[ETM_BULKIN_EP].In.dTDs[i];
    XUsbPs_dTDInvalidateCache(td);XUsbPs_WritedTD(td,XUSBPS_dTDTOKEN,0);XUsbPs_dTDFlushCache(td);
  }
  XUsbPs_ReconfigureEp(usb,&usb->DeviceConfig,ETM_BULKIN_EP,XUSBPS_EP_DIRECTION_IN,0);
  XUsbPs_dQHInvalidateCache(usb->DeviceConfig.Ep[ETM_BULKIN_EP].In.dQH);
  XUsbPs_WritedQH(usb->DeviceConfig.Ep[ETM_BULKIN_EP].In.dQH,XUSBPS_dQHdTDTOKEN,0);
  XUsbPs_WritedQH(usb->DeviceConfig.Ep[ETM_BULKIN_EP].In.dQH,XUSBPS_dQHdTDNLP,1);
  XUsbPs_dQHFlushCache(usb->DeviceConfig.Ep[ETM_BULKIN_EP].In.dQH);
  XUsbPs_EpEnable(usb,ETM_BULKIN_EP,XUSBPS_EP_DIRECTION_IN);
  // A vendor capture restart does not reset the host's USB DATA0/DATA1 state.
  // Resetting only the device toggle silently discards the first packet when
  // the host expects DATA1. Reset it only for the configuration lifecycle.
  XUsbPs_SetBits(usb,XUSBPS_EPCRn_OFFSET(ETM_BULKIN_EP),XUSBPS_EPCR_TXT_BULK_MASK|
                (reset_toggle ? XUSBPS_EPCR_TXR_MASK : 0U));
  head=tail=busy=busy_zlp=flush_remaining=fill_count=0;
}
void etm_usb_reset(void){configured=0;epoch++;pending=0;running=ending=0;fill_count=flush_remaining=0;EW(1,12);}
void etm_usb_configured(XUsbPs *usb){etm_usb_reset();reset_endpoint(usb,1);configured=1;}
void etm_usb_event(void *ref,u8 ep,u8 event,void *data){
  (void)ref;
  if(ep==ETM_BULKIN_EP && event==XUSBPS_EP_EVENT_DATA_TX && configured && busy && (uintptr_t)data==active_buffer){
    if(busy_zlp){if(flush_remaining)flush_remaining--;busy_zlp=0;}
    else tail++;
    busy=0;
  }
}
void etm_control(uint16_t action,uint32_t reply[8]){
  uint16_t op=action&255U,width=action>>8;
  if(op==1 && width>=1 && width<=3)pending=action;
  else if(op==2 || op==3)pending=action;
  reply[0]=ER(0);reply[1]=trace_status();reply[2]=ER(3);reply[3]=ER(5);
  reply[4]=sequence;reply[5]=capture_id;reply[6]=probe_target_fclk();
  reply[7]=pending;
}
static void kick(XUsbPs *usb){
  uint32_t f=irq_save();
  if(configured && !busy && head!=tail){
    uint8_t *p=packets[tail%QSIZE];
    active_buffer=(uintptr_t)p;busy=1;busy_zlp=0;
    if(XUsbPs_EpBufferSend(usb,ETM_BULKIN_EP,p,lengths[tail%QSIZE])!=XST_SUCCESS)busy=0;
  }else if(configured && !busy && head==tail && !running && !ending && flush_remaining){
    // Retire the browser's outstanding native reads without resetting the
    // shared USB device. A full-size final packet also needs a short terminator.
    active_buffer=(uintptr_t)flush_zero;busy=busy_zlp=1;
    if(XUsbPs_EpBufferSend(usb,ETM_BULKIN_EP,flush_zero,0)!=XST_SUCCESS)busy=busy_zlp=0;
  }
  irq_restore(f);
}
void etm_poll(XUsbPs *usb){
  uint32_t version=epoch,count,i,status,f,base,stamp;
  uint16_t command;
  uint8_t *p;
  if(!configured)return;
  f=irq_save();command=pending;pending=0;irq_restore(f);
  if(command){
    unsigned op=command&255U;
    if(op==1 || op==3){
      f=irq_save();reset_endpoint(usb,0);sequence=0;capture_id++;ending=0;
      running=op==1;
      EW(1,((op==1 ? command>>8 : 3U)<<2)|2U|running);
      irq_restore(f);
    }else if(op==2){EW(1,ER(1)&~1U);running=0;ending=1;flush_remaining=16;}
  }
  kick(usb);
  if((uint32_t)(head-tail)>=QSIZE || (!running && !ending))return;
  base=fill_count;
  count=ER(3);if(count>RECORDS-base)count=RECORDS-base;
  if(!count && !ending && !base)return;
  stamp=now_us();
  if(!count && !ending && (uint32_t)(stamp-fill_activity)<1000)return;
  p=packets[head%QSIZE];
  for(i=0;i<count;i++){
    uint32_t value=ER(4);
    if(value&0x80000000U){count=i;break;}
    p[32+2*(base+i)]=(uint8_t)value;p[33+2*(base+i)]=(uint8_t)(value>>8);
  }
  status=trace_status();
  f=irq_save();
  if(configured && epoch==version){
    fill_count=base+count;if(count)fill_activity=stamp;
    if(fill_count==RECORDS || ending || !count){
      put32(p,0x3154455aU);put32(p+4,sequence);put32(p+8,status|((ending && ER(3)==0)?8U:0U));
      put32(p+12,fill_count);put32(p+16,ER(5));put32(p+20,probe_target_fclk());put32(p+24,capture_id);put32(p+28,1);
      lengths[head%QSIZE]=32+2*fill_count;__sync_synchronize();head++;sequence++;fill_count=0;
      if((status&1U)==0 && ER(3)==0)ending=0;
    }
  }
  irq_restore(f);kick(usb);
}
