#include <stdint.h>
#include <string.h>
#include <assert.h>
#include <stdio.h>
#include "dap_request.h"
#define DAP_ValidateCommand dap_validate_real
#include "../../firmware/xusbps_daplink_dma/DAP/Source/dap_request.c"
#undef DAP_ValidateCommand
#include "../../firmware/xusbps_daplink_dma/dap_main.c"
volatile uint8_t DAP_TransferAbort;
XUsbPs *g_dap_usb_instance;
static unsigned effects,before_calls,after_calls,recover_calls,begins,reset_after_validate,before_fail;
uint32_t dap_info_response_size(uint8_t id) {(void)id;return 4;}
int dap_vendor_bounds(uint8_t id,dap_request_plan *p) {(void)id;(void)p;return 0;}
int DAP_ValidateCommand(const uint8_t *p,uint32_t n,uint32_t cap,dap_request_plan *plan) {
    int result=dap_validate_real(p,n,cap,plan);
    if(reset_after_validate){reset_after_validate=0;chry_dap_usb_session_reset();}
    return result;
}
void DAP_Setup(void) {}
void dap_wait_begin(void) {begins++;}
void dap_wait_init(void) {}
unsigned dap_wait_command_error(void) {return 0;}
int probe_before_dap(void) {before_calls++;return before_fail?-4:0;}
void probe_after_dap(void) {after_calls++;}
void probe_target_invalidate(void) {}
int probe_target_recover(void) {recover_calls++;return 0;}
void XUsbPs_DapResumeRx(XUsbPs *p) {(void)p;}
int swd_abort_engines(void) {return 0;}
int XUsbPs_EpBufferSend(XUsbPs *p,u8 ep,u8 *data,u32 n) {(void)p;(void)ep;(void)data;(void)n;return 0;}
int XUsbPs_EpBufferSendWithZLT(XUsbPs *p,u8 ep,u8 *data,u32 n) {return XUsbPs_EpBufferSend(p,ep,data,n);}
uint32_t DAP_ExecuteCommand(const uint8_t *p,uint32_t n,uint8_t *q,uint32_t cap) {
    assert(n>=1 && cap==4096);effects++;q[0]=p[0];q[1]=0;return 2;
}
static void fresh(void) {
    chry_dap_state_init();effects=before_calls=after_calls=recover_calls=begins=before_fail=0;
}
int main(void) {
    uint8_t full[]={17,128,150,152,0},short_clock[]={17};
    fresh();usbd_dap_bulk_out(0,1,sizeof full,full);chry_dap_handle();assert(effects==1);
    usbd_dap_bulk_in(0,1,(void *)tx_final_buffer);unsigned previous=before_calls;
    usbd_dap_bulk_out(0,1,sizeof short_clock,short_clock);chry_dap_handle();
    assert(effects==1 && before_calls==previous && USB_RespSize[1]==1 && USB_Response[1][0]==255);
    fresh();uint8_t compound[]={127,2,17,128,150,152,0,6,0,0,4,2};
    usbd_dap_bulk_out(0,1,sizeof compound,compound);chry_dap_handle();assert(!effects && !before_calls);
    fresh();reset_after_validate=1;
    usbd_dap_bulk_out(0,1,sizeof full,full);chry_dap_handle();
    assert(!effects && !begins && !before_calls && response_in==response_out);
    fresh();before_fail=1;uint8_t read[]={5,0,1,15};
    usbd_dap_bulk_out(0,1,sizeof read,read);chry_dap_handle();assert(!effects && !after_calls && USB_Response[0][0]==255);
    fresh();before_fail=1;uint8_t connect[]={2,1};
    usbd_dap_bulk_out(0,1,sizeof connect,connect);chry_dap_handle();assert(effects==1 && recover_calls==1 && after_calls==1);
    puts("PASS production DAP ingress: stale short tail rejected before handoff, compound atomic preflight, reset between validation/start drops old action, context quarantine and explicit Connect recovery");
}
