/* Host model for the endpoint callbacks. The foreground framing, queue and
 * input/reply banks are the production code, including its reset path. */
#include "probe_target_platform.h"
#include "dap_wait.h"
#include "dap_request.h"
#include "selectio_aux.h"
#include "selectio_block.h"
#include "selectio_mode.h"
#include "selectio_combo.h"
#include "probe_stream.h"
#include <string.h>

static int unexpected(void) { abort(); }
#define selectio_mem_port() 0U
#define selectio_mem_active() 0
#define selectio_mem_close() unexpected()
#define selectio_mem_open_at(...) unexpected()
#define selectio_mem_bulk(...) unexpected()
#define selectio_mem_stats(...) unexpected()
#define selectio_combo_active() 0
#define selectio_combo_reset() ((void)0)
#define selectio_combo_poll() ((void)0)
#define selectio_combo_commit(...) unexpected()
#define selectio_combo_frame(...) unexpected()
#define selectio_aux_native_owner() 0
#define selectio_aux_reset() 0
#define selectio_aux_release_native() 0
#define selectio_aux_poll() ((void)0)
#define selectio_aux_consume(n) ((void)(n),unexpected())
#define selectio_aux_frame(...) unexpected()
#define selectio_cdc_bind(...) unexpected()
#define selectio_cdc_reset() ((void)0)
#define selectio_cdc_status(...) unexpected()
#define selectio_live_profile(...) unexpected()
#define probe_native_owns_stream() 0
#define probe_native_abandon() 0
#define probe_native_peek(channel,out,cap,packets) (*(packets)=0,(unsigned)unexpected())
#define probe_native_commit(...) unexpected()
#define probe_native_control(...) unexpected()
#define probe_native_route(...) unexpected()
#define DAP_ValidateCommand(...) unexpected()
#define DAP_ExecuteCommand(...) unexpected()
#define DAP_OK 0
#define dap_wait_begin() ((void)0)
#define dap_wait_command_error() 0
#define probe_target_context_invalid() 0
#define probe_before_dap() unexpected()
#define probe_after_dap() unexpected()
#define SWD_FEATURES 0x40010000U
#define Xil_DCacheFlushRange(p,n) ((void)0)
#include "../../firmware/xusbps_daplink_dma/selectio_usb.c"

static XUsbPs device;
static u8 rx_data[FRAME_SIZE], expected[FRAME_SIZE], *tx_data;
static u32 rx_size, tx_size;
static unsigned released;
uint32_t Xil_In32(uintptr_t addr) { (void)addr; return 0; }
void XTime_GetTime(XTime *value) { static XTime timer; *value=++timer; }
void selectio_usb_resume_rx(XUsbPs *usb) { (void)usb; }
int XUsbPs_EpBufferReceive(XUsbPs *usb,u8 ep,u8 **buffer,u32 *length,u32 *handle) {
    assert(usb==&device && ep==1); *buffer=rx_data; *length=rx_size; *handle=1; return 0;
}
void XUsbPs_EpBufferRelease(u32 handle) { assert(handle==1); released++; }
int XUsbPs_EpBufferSend(XUsbPs *usb,u8 ep,u8 *payload,u32 length) {
    assert(usb==&device && ep==4 && tx_data==NULL); tx_data=payload; tx_size=length; return 0;
}
static void inject(u8 ch,u8 op,u32 seq,const u8 *payload,u32 length) {
    assert(selectio_usb_rx_available() && length<=FRAME_SIZE-17);
    memcpy(rx_data,"ZLK1",4); rx_data[4]=ch; rx_data[5]=op; rx_data[6]=rx_data[7]=0;
    write32(rx_data+8,seq); write32(rx_data+12,length);
    if(length) memcpy(rx_data+16,payload,length);
    rx_size=16+length; if(rx_size%512==0) rx_data[rx_size++]=0;
    selectio_usb_event(&device,1,XUSBPS_EP_EVENT_DATA_RX,NULL);
    memset(rx_data,0xa5,rx_size); /* controller owns the dTD again */
    selectio_usb_poll(&device);
    selectio_usb_poll(&device);
}
static void check(u32 seq,u8 status,u32 length,const u8 *payload) {
    assert(tx_data && read32(tx_data+8)==seq && tx_data[6]==status);
    assert(read32(tx_data+12)==length && tx_size==16+length+((16+length)%512==0));
    if(payload) assert(!memcmp(tx_data+16,payload,length));
}
static void complete(void) {
    u8 *sent=tx_data; assert(sent); tx_data=NULL;
    selectio_usb_event(&device,4,XUSBPS_EP_EVENT_DATA_TX,sent);
    selectio_usb_poll(&device);
}
int main(void) {
    selectio_usb_configured(&device);
    inject(0,0,30,NULL,0);check(30,0,16,NULL);assert(read32(tx_data+28)==FRAME_SIZE);complete();
    for(unsigned i=0;i<sizeof(expected);i++)expected[i]=(u8)(i*37+(i>>3));
    inject(0,1,31,expected,6000);check(31,1,0,NULL);complete();
    /* A malformed length did not consume sequence 31. */
    u8 frame[4];write32(frame,FRAME_SIZE);
    inject(0,8,31,frame,4);check(31,0,4,frame);complete();
    inject(0,1,32,expected,FRAME_SIZE-17);check(32,0,FRAME_SIZE-17,expected);
    inject(0,1,33,expected+2,496);check(32,0,FRAME_SIZE-17,expected);
    inject(0,1,34,expected+7,4079);check(32,0,FRAME_SIZE-17,expected);
    assert(!selectio_usb_rx_available());complete();check(33,0,496,expected+2);
    complete();check(34,0,4079,expected+7);complete();
    /* Use the highest aligned region in the private DDR window. */
    const unsigned bytes=16320;u8 bulk[16+16320]={1};
    bulk[2]=(u8)(bytes/4);bulk[3]=(u8)(bytes/1024);
    write32(bulk+4,0x20010000U-bytes);memcpy(bulk+16,expected,bytes);
    inject(7,6,35,bulk,sizeof(bulk));check(35,0,16,NULL);complete();
    bulk[0]=0;inject(7,6,36,bulk,16);check(36,0,16+bytes,NULL);
    assert(read32(tx_data+16)==bytes/4 && !memcmp(tx_data+32,expected,bytes));complete();
    write32(bulk+4,0x20010004U-bytes);inject(7,6,37,bulk,16);check(37,1,0,NULL);complete();
    inject(0,0,99,NULL,0);check(99,0,16,NULL);complete();
    inject(0,1,100,expected,4080);check(100,1,0,NULL);complete();
    assert(released==11 && !tx_busy && !pending_length);
    puts("PASS IF4 negotiated frames, dTD recycling, three ordered in-flight echoes, DDR bounds and legacy reset");
    return 0;
}
