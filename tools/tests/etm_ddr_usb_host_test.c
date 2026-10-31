// Production DDR owner, identity/range validation and USB descriptor retirement.
#include "probe_host_platform.h"
#define NORM_NONCACHE 0x11de2U
void Xil_SetTlbAttributes(uint32_t,uint32_t);
#include "../../firmware/xusbps_daplink_dma/etm_ddr_usb.c"
static uint32_t csr[34],legacy_signature=0x45544431U,legacy_caps=0x100U;
static unsigned ddr_reads,mappings,claims,claim_ok=1,send_ok=1,send_calls;
static uint8_t *sent;
static uint32_t sent_length;
uint32_t Xil_In32(uintptr_t address){
  if(address==LEGACY_BASE+32)return legacy_signature;
  if(address==LEGACY_BASE+72)return legacy_caps;
  assert(address>=DDR_CSR && address<DDR_CSR+sizeof csr);
  ddr_reads++;return csr[(address-DDR_CSR)/4];
}
void Xil_Out32(uintptr_t address,uint32_t value){
  unsigned n=(address-DDR_CSR)/4;assert(n<34);
  if(n==1){
    if(value==1){csr[10]++;csr[2]=ACTIVE;csr[31]=csr[31];csr[28]=0x46524d31U;csr[33]=2;}
    else {assert(value==2);csr[2]=DONE;}
  }else csr[n]=value;
}
void Xil_SetTlbAttributes(uint32_t address,uint32_t flags){
  assert(address==DDR_BASE+mappings*0x100000U && flags==NORM_NONCACHE);mappings++;
}
unsigned etm_stream_claim_ddr(XUsbPs *usb){assert(usb);claims++;return claim_ok;}
void etm_reference_snapshot(uint32_t reply[4]){memset(reply,0,16);reply[0]=200000000;}
int XUsbPs_EpBufferSend(XUsbPs *usb,u8 ep,u8 *data,u32 size){
  assert(usb && ep==2 && size<=CHUNK);send_calls++;
  if(!send_ok)return XST_FAILURE;
  sent=data;sent_length=size;return XST_SUCCESS;
}
static void complete(void){assert(etm_ddr_usb_event(2,XUSBPS_EP_EVENT_DATA_TX,sent));}
int main(void){
  XUsbPs usb={0};uint32_t reply[44],args[6]={0},before;
  legacy_caps=0;assert(!etm_ddr_init() && ddr_reads==0 && mappings==0);
  legacy_caps=0x100;csr[0]=0x45444d31;csr[11]=7;csr[12]=DDR_BASE;csr[13]=DDR_END;
  assert(etm_ddr_init() && mappings==512);
  etm_ddr_usb_configured(&usb);
  args[0]=200000000;args[1]=64<<20;args[2]=0x1234;args[3]=0x5678;
  assert(!etm_ddr_command(1,args,reply) && csr[10]==1 && csr[2]==ACTIVE && claimed);
  assert(etm_ddr_owned());before=send_calls;assert(etm_ddr_poll(&usb) && send_calls==before);
  assert(etm_ddr_command(1,args,reply)==2); // no overwrite of active capture
  args[0]=1;args[1]=0x1234;args[2]=0x5678;args[3]=0;args[4]=0;
  assert(etm_ddr_command(3,args,reply)==2); // no download before final B/EOF
  args[0]=2;assert(etm_ddr_command(2,args,reply)==4); // stale capture ID
  args[0]=1;assert(!etm_ddr_command(2,args,reply) && csr[2]==DONE);
  csr[3]=DDR_BASE;csr[6]=csr[7]=CHUNK+3;
  args[3]=CHUNK;args[4]=4;assert(etm_ddr_command(3,args,reply)==6); // bounded suffix
  args[3]=0xffffffff;args[4]=1;assert(etm_ddr_command(3,args,reply)==6); // wraparound
  args[3]=0;args[4]=CHUNK+3;
  assert(!etm_ddr_command(3,args,reply));
  etm_ddr_poll(&usb);assert(usb_busy && sent_length==512 && ((uint32_t*)sent)[0]==0x3144445aU);
  assert(((uint32_t*)sent)[3]==1 && ((uint32_t*)sent)[4]==0x1234 && ((uint32_t*)sent)[7]==CHUNK+3);
  assert(!etm_ddr_usb_event(7,XUSBPS_EP_EVENT_DATA_TX,sent));
  assert(!etm_ddr_usb_event(2,XUSBPS_EP_EVENT_DATA_TX,sent+1));
  before=send_calls;etm_ddr_poll(&usb);assert(send_calls==before); // descriptor still owned
  complete();send_ok=0;etm_ddr_poll(&usb);assert(!usb_busy && sent_bytes==0 && submit_errors==1);
  send_ok=1;etm_ddr_poll(&usb);assert((uintptr_t)sent==DDR_BASE && sent_length==CHUNK && sent_bytes==0);
  complete();assert(sent_bytes==CHUNK && download_phase==2);
  etm_ddr_poll(&usb);assert((uintptr_t)sent==DDR_BASE+CHUNK && sent_length==3);
  complete();assert(sent_bytes==CHUNK+3 && !download_phase && claimed);
  args[3]=args[4]=0;assert(!etm_ddr_command(4,args,reply) && !claimed);
  // USB reset cancels only download; PL capture identity and state survive.
  csr[2]=ACTIVE;before=csr[10];etm_ddr_usb_reset();assert(csr[2]==ACTIVE && csr[10]==before && etm_ddr_owned());
  csr[2]=DONE;etm_ddr_usb_configured(&usb);args[4]=3;
  assert(!etm_ddr_command(3,args,reply));etm_ddr_poll(&usb);assert(usb_busy);
  etm_ddr_usb_reset();assert(!etm_ddr_usb_event(2,XUSBPS_EP_EVENT_DATA_TX,sent) && !download_phase);
  // Reconfiguration can download the retained record without a new START.
  etm_ddr_usb_configured(&usb);args[3]=CHUNK;args[4]=3;assert(!etm_ddr_command(3,args,reply));
  etm_ddr_poll(&usb);complete();etm_ddr_poll(&usb);assert((uintptr_t)sent==DDR_BASE+CHUNK && sent_length==3);complete();
  assert(!etm_ddr_command(4,args,reply));
  args[0]=400000001;args[1]=1;args[2]=1;args[3]=0;args[4]=0;
  assert(etm_ddr_command(1,args,reply)==3);
  puts("PASS DDR USB: capability guard, noncache reservation, identity/range/active guards, descriptor ownership, failed submit, reset-retained record");
  return 0;
}
