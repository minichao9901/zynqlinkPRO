// Bounded PL capture is independent of USB. Only completed immutable DDR
// records can be downloaded. EP2 header binds every range to capture identity.
#include "etm_ddr_usb.h"
#include "etm_stream.h"
#include "xil_io.h"
#include "xil_exception.h"
#include "xil_mmu.h"
#include <string.h>

#define LEGACY_BASE 0x40030000U
#define DDR_CSR 0x40040000U
#define DDR_BASE 0x39c00000U
#define DDR_END 0x40000000U
#define DR(n) Xil_In32(DDR_CSR+4U*(n))
#define DW(n,v) Xil_Out32(DDR_CSR+4U*(n),(v))
#define ACTIVE 1U
#define DONE 2U
#define CHUNK 16384U

static uint32_t available;
static XUsbPs *bound_usb;
static volatile uint32_t claimed,download_phase,usb_busy,usb_epoch;
static volatile uintptr_t inflight_pointer;
static volatile uint32_t inflight_size,inflight_epoch;
static volatile uint32_t transfer_id,range_offset,range_bytes,sent_bytes,submit_errors;
static uint32_t header[128] __attribute__((aligned(32)));

static uint32_t irq_save(void){uint32_t f=mfcpsr();mtcpsr(f|0x80U);return f;}
static void irq_restore(uint32_t f){mtcpsr(f);}

uint32_t etm_ddr_init(void){
  uint32_t address;
  available=0;
  // Older bitstreams have no AXI slave at DDR_CSR. Never speculative-probe it.
  if(Xil_In32(LEGACY_BASE+32U)!=0x45544431U || !(Xil_In32(LEGACY_BASE+72U)&0x100U))return 0;
  if(DR(0)!=0x45444d31U || (DR(11)&7U)!=7U || DR(12)!=DDR_BASE || DR(13)!=DDR_END)return 0;
  // This explicit linker reservation is disposable capture memory. Configure
  // it BEFORE any PL DMA: later USB driver's cache flush cannot overwrite DMA
  // data with old dirty CPU lines. No other CPU-cached alias is used here.
  for(address=DDR_BASE;address<DDR_END;address+=0x100000U)
    Xil_SetTlbAttributes(address,NORM_NONCACHE);
  available=1;
  return 1;
}
unsigned etm_ddr_available(void){return available;}
unsigned etm_ddr_owned(void){return claimed || (available && (DR(2)&ACTIVE));}
void etm_ddr_usb_reset(void){
  usb_epoch++;bound_usb=0;claimed=download_phase=usb_busy=0;
  // Do not stop/reset the autonomous source or erase its record identity.
}
void etm_ddr_usb_configured(XUsbPs *usb){bound_usb=usb;}

void etm_ddr_snapshot(uint32_t reply[ETM_DDR_REPLY_WORDS]){
  unsigned i;
  memset(reply,0,ETM_DDR_REPLY_WORDS*sizeof(uint32_t));
  reply[0]=0x31554445U;reply[1]=1;reply[2]=available;
  if(available)for(i=0;i<34;i++)reply[4+i]=DR(i);
  reply[38]=transfer_id;reply[39]=range_offset;reply[40]=range_bytes;
  reply[41]=sent_bytes;reply[42]=download_phase | (usb_busy<<8) | (claimed<<16);
  reply[43]=submit_errors;
}

static unsigned identity(const uint32_t args[6]){
  return DR(10)==args[0] && DR(31)==args[1] && DR(32)==args[2] && DR(33)==2;
}
static unsigned claim_endpoint(void){
  unsigned prior=claimed;
  claimed=1;
  if(!bound_usb || !etm_stream_claim_ddr(bound_usb)){claimed=prior;return 0;}
  return 1;
}

unsigned etm_ddr_command(unsigned op,const uint32_t args[6],uint32_t reply[ETM_DDR_REPLY_WORDS]){
  unsigned result=0;
  uint32_t total,reference[4],before_id,f;
  if(!available)result=1;
  else if(op==0){ /* read-only snapshot */ }
  else if(op==1){
    // START: ticks, byte_limit, nonce_lo, nonce_hi, reserved, reserved.
    etm_reference_snapshot(reference);
    if(!args[0] || (uint64_t)args[0]>(uint64_t)reference[0]*2U ||
       args[1]!=DDR_END-DDR_BASE || !(args[2]|args[3]) || args[4] || args[5])result=3;
    else if((DR(2)&ACTIVE) || download_phase || usb_busy)result=2;
    else if(!claim_endpoint())result=7;
    else {
      before_id=DR(10);
      DW(3,DDR_BASE);DW(4,args[1]);DW(15,2);DW(16,args[0]);DW(31,args[2]);DW(32,args[3]);DW(1,1);
      if(DR(10)!=before_id+1U || !(DR(2)&ACTIVE))result=5;
    }
  }else if(op==2){
    // STOP: capture_id, nonce_lo, nonce_hi, remaining fields zero.
    if(args[3] || args[4] || args[5])result=3;
    else if(!identity(args))result=4;
    else if(DR(2)&ACTIVE)DW(1,2);
  }else if(op==3){
    // DOWNLOAD: capture_id, nonce_lo, nonce_hi, offset, length, reserved.
    if(args[5])result=3;
    else if(!identity(args))result=4;
    else if((DR(2)&ACTIVE) || !(DR(2)&DONE) || download_phase || usb_busy)result=2;
    else if(DR(3)!=DDR_BASE || DR(28)!=0x46524d31U || DR(7)!=DR(6))result=5;
    else {
      total=DR(7);
      if(total>DDR_END-DDR_BASE || args[3]>total || args[4]>total-args[3])result=6;
      else if(!claim_endpoint())result=7;
      else {
        memset(header,0,sizeof header);
        header[0]=0x3144445aU;header[1]=1;header[2]=++transfer_id;
        header[3]=args[0];header[4]=args[1];header[5]=args[2];
        header[6]=args[3];header[7]=args[4];header[8]=total;header[9]=DR(28);
        header[10]=DR(22);header[11]=DR(18);header[12]=DR(17);header[13]=DR(29);
        header[14]=sizeof header;header[15]=DR(2);
        f=irq_save();range_offset=args[3];range_bytes=args[4];sent_bytes=0;download_phase=1;irq_restore(f);
      }
    }
  }else if(op==4){
    // Release/cancel USB download. An active PL window must be stopped first.
    if(DR(2)&ACTIVE)result=2;
    else if(!identity(args))result=4;
    else if(!claim_endpoint())result=7;
    else {f=irq_save();usb_epoch++;download_phase=usb_busy=claimed=0;irq_restore(f);}
  }else result=3;
  etm_ddr_snapshot(reply);reply[3]=result;
  return result;
}

unsigned etm_ddr_usb_event(u8 ep,u8 event,void *data){
  if(ep!=ETM_BULKIN_EP || event!=XUSBPS_EP_EVENT_DATA_TX || !usb_busy ||
     (uintptr_t)data!=inflight_pointer || inflight_epoch!=usb_epoch)return 0;
  if(download_phase==1)download_phase=range_bytes ? 2U : 0U;
  else if(download_phase==2){sent_bytes+=inflight_size;if(sent_bytes==range_bytes)download_phase=0;}
  usb_busy=0;
  return 1;
}

unsigned etm_ddr_poll(XUsbPs *usb){
  uint32_t f,length;
  uint8_t *data;
  if(!etm_ddr_owned())return 0;
  if(!download_phase || usb!=bound_usb)return 1;
  f=irq_save();
  if(download_phase && !usb_busy){
    if(download_phase==1){data=(uint8_t *)header;length=sizeof header;}
    else {
      length=range_bytes-sent_bytes;if(length>CHUNK)length=CHUNK;
      data=(uint8_t *)(uintptr_t)(DDR_BASE+range_offset+sent_bytes);
    }
    inflight_pointer=(uintptr_t)data;inflight_size=length;inflight_epoch=usb_epoch;usb_busy=1;
    if(XUsbPs_EpBufferSend(usb,ETM_BULKIN_EP,data,length)!=XST_SUCCESS){usb_busy=0;submit_errors++;}
  }
  irq_restore(f);
  return 1;
}
