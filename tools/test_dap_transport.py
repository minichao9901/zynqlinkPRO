"""Compile the real transport C with a simulated USB DMA completion driver.

Checks ownership through ZLP completion, response-full backpressure, failed
submissions, counter wrap, and a reset interrupt during command execution.
"""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1];out=root/'build/test_transport';out.mkdir(parents=True,exist_ok=True)
shim=r'''
#ifndef TEST_SHIM_H
#define TEST_SHIM_H
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
typedef uint8_t u8;typedef uint32_t u32;typedef uintptr_t UINTPTR;typedef uint64_t XTime;
typedef struct {int unused;} XUsbPs;
#define DAP_PACKET_SIZE 4096
#define DAP_PACKET_COUNT 16
#define NORM_NONCACHE 0
#define DAP_ENABLE_TRACE 0
#define XST_SUCCESS 0
#define MET_COUNT 12
#define MET_USB_IN 0
#define MET_USB_SUBMIT 1
#define MET_EXEC05 2
#define MET_EXEC06_READ 3
#define MET_EXEC06_WRITE 4
#define MET_QUEUE_WAIT 5
static uint32_t cpsr=0;
static int reset_before_lock;
int chry_dap_usb_session_reset(void);
static inline uint32_t test_cpsr(void){if(reset_before_lock){reset_before_lock=0;chry_dap_usb_session_reset();}return cpsr;}
#define mfcpsr() test_cpsr()
#define mtcpsr(v) (cpsr=(v))
static inline void XTime_GetTime(XTime *t){static XTime ticks=1;*t=ticks++;}
static inline XTime dap_metric_start(void){return 0;}
static inline void dap_metric_end(unsigned i,XTime t,uint32_t n){(void)i;(void)t;(void)n;}
static inline void Xil_DCacheFlushRange(UINTPTR p,uint32_t n){(void)p;(void)n;}
static inline void Xil_SetTlbAttributes(uint32_t p,int n){(void)p;(void)n;}
static inline void sleep(unsigned s){(void)s;}
#define xil_printf(...) ((void)0)
volatile uint8_t DAP_TransferAbort;
static XUsbPs usb;XUsbPs *g_dap_usb_instance=&usb;
static int send_fail=0,submissions=0,reset_in_execute=0;
static void *active_buffer;static unsigned active_len;
static int send_buf(XUsbPs *d,u8 ep,u8 *buf,unsigned len){(void)d;(void)ep;if(send_fail){send_fail=0;return 1;}submissions++;active_buffer=buf;active_len=len;return 0;}
#define XUsbPs_EpBufferSend send_buf
#define XUsbPs_EpBufferSendWithZLT send_buf
void DAP_Setup(void){}
uint32_t DAP_ExecuteCommand(const uint8_t *p,uint8_t *r);
void XUsbPs_DapResumeRx(XUsbPs *i){(void)i;}
int chry_dap_usb_session_reset(void);
int swd_abort_engines(void){return 0;}
#endif
'''
(out/'shim.h').write_text(shim)
for h in ['DAP.h','dap_metrics.h','xusbps.h','xil_cache.h','xil_mmu.h','xil_printf.h','xtime_l.h','sleep.h','xil_exception.h']:(out/h).write_text('#include "shim.h"\n')
source=r'''
#include "shim.h"
#include "../../firmware/xusbps_daplink_dma/dap_main.c"
uint32_t DAP_ExecuteCommand(const uint8_t *p,uint8_t *r){
 unsigned n=p[2]|(p[3]<<8);memset(r,p[1],n);r[0]=p[0];
 if(reset_in_execute){reset_in_execute=0;chry_dap_usb_session_reset();}
 return n;
}
static void put(unsigned tag,unsigned len){uint8_t p[4]={0x80,(uint8_t)tag,len&255,len>>8};usbd_dap_bulk_out(&usb,2,4,p);}
static void finish(void){void *p=active_buffer;unsigned len=active_len;
 uint32_t before=response_out;
 usbd_dap_bulk_in(&usb,1,p);
 if(len && len<4096 && len%512==0){assert(response_out==before);usbd_dap_bulk_in(&usb,1,(uint8_t *)p+len);}
 assert(response_out==before+1);
}
int main(void){
 chry_dap_state_init();
 for(unsigned i=0;i<16;i++)put(i, i==0?512:7);
 chry_dap_handle();assert(response_in-response_out==16);assert(tx_active);
 uint8_t first[512];memcpy(first,active_buffer,512);
 for(unsigned i=16;i<32;i++)put(i,7);
 assert(!chry_dap_rx_ready());chry_dap_handle();
 assert(response_in-response_out==16);assert(request_in-request_out==16);
 assert(!memcmp(first,active_buffer,512));
 for(unsigned i=0;i<32;i++){assert(((uint8_t *)active_buffer)[1]==i);finish();chry_dap_handle();}
 assert(response_in==response_out);assert(!tx_active);assert(request_in==request_out);
 puts("PASS full queues preserve in-flight data and ZLP ownership");
 send_fail=1;put(55,7);chry_dap_handle();assert(!tx_active);assert(response_in-response_out==1);
 chry_dap_handle();assert(tx_active);assert(((uint8_t *)active_buffer)[1]==55);finish();
 puts("PASS failed submission retries without losing response");
 request_in=request_out=response_in=response_out=0xfffffff0U;
 for(unsigned i=0;i<70000;i++){put(i,7);chry_dap_handle();assert(((uint8_t *)active_buffer)[1]==(uint8_t)i);finish();}
 assert(request_in==request_out);assert(response_in==response_out);
 puts("PASS 70,000 completions and 32-bit sequence wrap");
 reset_in_execute=1;put(7,7);chry_dap_handle();assert(response_in==0&&response_out==0&&!tx_active);
 put(9,7);chry_dap_handle();assert(((uint8_t *)active_buffer)[1]==9);finish();
 uint8_t dummy=0;uint32_t count=request_in;usbd_dap_bulk_out(&usb,2,0,&dummy);assert(request_in==count);
 puts("PASS reset epoch discards old execution; OUT ZLP creates no command");
 put(77,7);reset_before_lock=1;chry_dap_handle();assert(request_in==request_out);assert(response_in==response_out);assert(!tx_active);
 puts("PASS reset before consumer lock cannot create phantom commands");
 puts("ALL TRANSPORT TESTS PASSED");return 0;
}
'''
# Location under build/ keeps all native artifacts out of sources.
(out/'test.c').write_text(source.replace('../../firmware/','../../firmware/').replace('#include "../../firmware/', '#include "'+(root/'firmware').as_posix()+'/'))
subprocess.run(['gcc','-std=gnu11','-Wall','-Wextra','-Werror','-I',str(out),str(out/'test.c'),'-o',str(out/'test.exe')],check=True)
subprocess.run([str(out/'test.exe')],check=True)
