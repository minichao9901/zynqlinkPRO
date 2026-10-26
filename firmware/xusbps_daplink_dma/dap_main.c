#include "stdint.h"
#include "DAP.h"
#include "dap_metrics.h"
#include "xusbps.h"
#include "xil_cache.h"
#include "xil_mmu.h"
#include "xil_printf.h"
#include "xtime_l.h"
#include "sleep.h"
#include "xil_exception.h"
// #include "ch32h417_usbhs_device.h"

/* Timing trace for USB/SWD bottleneck analysis.  The buffer lives in a
 * dedicated 1 MiB non-cacheable DDR section (0x3F000000) so JTAG reads see
 * every entry without cache flushes. */
#define DAP_TRACE_MAX 4096U
typedef struct {
  uint32_t lo, hi, ev, arg;
} dap_trace_ent_t;
__attribute__((section(".dap_trace"), aligned(64))) volatile dap_trace_ent_t dap_trace_buf[DAP_TRACE_MAX];
__attribute__((section(".dap_trace"))) volatile uint32_t dap_trace_count;
__attribute__((section(".dap_trace"))) volatile uint32_t dap_trace_hz;

static inline void dap_trace_add(uint32_t ev, uint32_t arg)
{
#if DAP_ENABLE_TRACE
  uint32_t i = dap_trace_count;
  XTime t;

  if (i >= DAP_TRACE_MAX) {
    return;
  }
  XTime_GetTime(&t);
  dap_trace_buf[i].lo = (uint32_t)t;
  dap_trace_buf[i].hi = (uint32_t)(t >> 32);
  dap_trace_buf[i].ev = ev;
  dap_trace_buf[i].arg = arg;
  dap_trace_count = i + 1U;
#else
  (void)ev; (void)arg;
#endif
}

/* Raw CMSIS-DAP payload snapshots. Events 16..31 are request words and
 * 32..47 are response words. Keeping the first 64 bytes is enough to decode
 * DAP_Transfer/TransferBlock initialization commands without blowing the
 * small noncached trace ring. */
static inline void dap_trace_bytes(uint32_t event_base, const uint8_t *data,
                                   uint32_t len)
{
#if DAP_ENABLE_TRACE
  uint32_t words = (len + 3U) / 4U;
  uint32_t i;
  if (words > 16U) words = 16U;
  for (i = 0; i < words; ++i) {
    uint32_t value = 0U;
    uint32_t left = len - i * 4U;
    if (left > 4U) left = 4U;
    memcpy(&value, data + i * 4U, left);
    dap_trace_add(event_base + i, value);
  }
#else
  (void)event_base; (void)data; (void)len;
#endif
}

/* Request producer: USB IRQ; request consumer: main loop.
 * Response producer: main loop; response consumer: final USB dTD completion.
 * Slots remain owned until DMA completes, including a terminating ZLP. */
static volatile uint32_t request_in, request_out, response_in, response_out;
static volatile uint32_t session_epoch;
static volatile uint8_t tx_active;
static uint8_t USB_Request[DAP_PACKET_COUNT][DAP_PACKET_SIZE] __attribute__((aligned(32)));
static uint8_t USB_Response[DAP_PACKET_COUNT][DAP_PACKET_SIZE] __attribute__((aligned(32)));
static uint16_t USB_RespSize[DAP_PACKET_COUNT], request_size[DAP_PACKET_COUNT];
static uint8_t execute_request[DAP_PACKET_SIZE] __attribute__((aligned(32)));
static XTime request_time[DAP_PACKET_COUNT], in_start;
static volatile uintptr_t tx_final_buffer;
volatile uint32_t dap_rx_deferred;
volatile uint32_t dap_queue_backpressure, dap_tx_submit_errors, dap_tx_extra_callbacks;
static uint32_t irq_save(void) {uint32_t s=mfcpsr();mtcpsr(s|0x80U);return s;}
static void irq_restore(uint32_t s) {mtcpsr(s);}
static void barrier(void) {
#ifdef __arm__
    __asm__ volatile("dmb sy" ::: "memory");
#else
    __sync_synchronize();
#endif
}
int chry_dap_rx_ready(void) {return (uint32_t)(request_in-request_out)<DAP_PACKET_COUNT;}
extern void XUsbPs_DapResumeRx(XUsbPs *instance);

extern XUsbPs *g_dap_usb_instance;

__attribute__((section(".dap_debug"), aligned(32))) volatile uint32_t
dap_dbg_rtl_writes, dap_dbg_rtl_reads, dap_dbg_last_write_addr,
dap_dbg_last_write_value, dap_dbg_last_read_addr, dap_dbg_last_read_value;
__attribute__((section(".dap_debug"), aligned(32))) volatile uint32_t
dap_dbg_usb_rx, dap_dbg_exec_count;

void usbd_dap_bulk_out(XUsbPs *instance, u8 ep, u32 nbytes, u8 *buffer)
{
    uint32_t slot=request_in % DAP_PACKET_COUNT;
    (void)instance;(void)ep;
    // A ZLP terminates the preceding USB OUT; it is not a new DAP command.
    if(!nbytes || nbytes>DAP_PACKET_SIZE)return;
    if(buffer[0]==0x07U){DAP_TransferAbort=1U;return;}
    if(!chry_dap_rx_ready()){dap_queue_backpressure++;return;}
    request_time[slot]=dap_metric_start();dap_trace_add(1U,nbytes);
    memcpy(USB_Request[slot],buffer,nbytes);request_size[slot]=(uint16_t)nbytes;
    dap_trace_bytes(16U,buffer,nbytes);dap_dbg_usb_rx++;
    barrier();request_in++;
}

static void dap_service_tx(void)
{
    uint32_t slot,flags;uint16_t len;int status;XTime t;
    if(tx_active || response_in==response_out)return;
    flags=irq_save();
    if(tx_active || response_in==response_out){irq_restore(flags);return;}
    slot=response_out % DAP_PACKET_COUNT;len=USB_RespSize[slot];
    t=dap_metric_start();
    // XUsbPs_EpQueueRequest flushes the payload before publishing its dTD.
    // Serialize publication/submission against the completion ISR. Failed
    // submissions keep ownership and are retried by the main loop.

    tx_final_buffer=(uintptr_t)USB_Response[slot];
    if(len && len<DAP_PACKET_SIZE && len%512U==0U)tx_final_buffer+=len;
    tx_active=1;in_start=t;barrier();
    if(tx_final_buffer!=(uintptr_t)USB_Response[slot])
        status=XUsbPs_EpBufferSendWithZLT(g_dap_usb_instance,1,USB_Response[slot],len);
    else status=XUsbPs_EpBufferSend(g_dap_usb_instance,1,USB_Response[slot],len);
    if(status!=XST_SUCCESS){tx_active=0;dap_tx_submit_errors++;}
    else dap_trace_add(4U,len);
    irq_restore(flags);dap_metric_end(MET_USB_SUBMIT,t,len);
}

void usbd_dap_bulk_in(XUsbPs *instance, u8 ep, void *buffer)
{
    (void)instance;(void)ep;
    // The BSP reports EVERY completed dTD. Only the final dTD releases
    // the application slot; the data callback of a ZLP transfer is ignored.
    if(!tx_active || (uintptr_t)buffer!=tx_final_buffer){dap_tx_extra_callbacks++;return;}
    dap_metric_end(MET_USB_IN,in_start,USB_RespSize[response_out%DAP_PACKET_COUNT]);
    dap_trace_add(5U,USB_RespSize[response_out%DAP_PACKET_COUNT]);
    barrier();response_out++;tx_active=0;
    dap_service_tx();
}

static void chry_dap_state_init(void)
{
    request_in=request_out=response_in=response_out=0;
    tx_active=0;tx_final_buffer=0;dap_rx_deferred=0;
    memset(USB_RespSize,0,sizeof USB_RespSize);
}

void chry_dap_queue_snapshot(uint32_t out[8])
{
    uint32_t flags=irq_save();
    out[0]=request_in-request_out;out[1]=response_in-response_out;
    out[2]=tx_active;out[3]=session_epoch;out[4]=dap_queue_backpressure;
    out[5]=dap_tx_submit_errors;out[6]=dap_tx_extra_callbacks;out[7]=dap_rx_deferred;
    irq_restore(flags);
}

void chry_dap_usb_session_reset(void)
{
    session_epoch++;
    DAP_TransferAbort=1;
    chry_dap_state_init();
}

void chry_dap_init(void)
{
  XTime t0, t1;

  /* The trace buffer sits at 0x3F000000 in DDR; keep it non-cacheable so
   * JTAG reads observe every entry. */
  Xil_SetTlbAttributes(0x3F000000U, NORM_NONCACHE);

  XTime_GetTime(&t0);
  sleep(1);
  XTime_GetTime(&t1);
  dap_trace_hz = (uint32_t)(t1 - t0);
  dap_trace_count = 0U;

  // chry_ringbuffer_init(&g_uartrx, uartrx_ringbuffer, (8 * 1024));
  // chry_ringbuffer_init(&g_usbrx, usbrx_ringbuffer, (8 * 1024));

  DAP_Setup();
  chry_dap_state_init();
}

void chry_dap_handle(void)
{
    uint32_t req_slot,rsp_slot,epoch,flags,metric_id;
    XTime t;
    dap_service_tx();
    if(dap_rx_deferred && chry_dap_rx_ready()){
        flags=irq_save();dap_rx_deferred=0;
        XUsbPs_DapResumeRx(g_dap_usb_instance);irq_restore(flags);
    }
    while(request_in!=request_out){
        if((uint32_t)(response_in-response_out)>=DAP_PACKET_COUNT){
            dap_queue_backpressure++;break;
        }
        flags=irq_save();
        // RESET may preempt the while/full checks before this critical section.
        // Revalidate against the new session before consuming any slot.
        if(request_in==request_out ||
           (uint32_t)(response_in-response_out)>=DAP_PACKET_COUNT){
            irq_restore(flags);break;
        }
        epoch=session_epoch;req_slot=request_out%DAP_PACKET_COUNT;
        if(USB_Request[req_slot][0]==0x7eU){
            uint32_t q=request_out;
            while(q!=request_in && USB_Request[q%DAP_PACKET_COUNT][0]==0x7eU)q++;
            if(q==request_in){irq_restore(flags);break;}
        }
        memcpy(execute_request,USB_Request[req_slot],request_size[req_slot]);
        if(execute_request[0]==0x7eU)execute_request[0]=0x7fU;
        rsp_slot=response_in%DAP_PACKET_COUNT;
        irq_restore(flags);
        t=dap_metric_start();
        metric_id=execute_request[0]==6 ?
            ((execute_request[4]&2)?MET_EXEC06_READ:MET_EXEC06_WRITE):MET_EXEC05;
        dap_metric_end(MET_QUEUE_WAIT,request_time[req_slot],0);
        dap_trace_add(2U,execute_request[0]);
        USB_RespSize[rsp_slot]=(uint16_t)DAP_ExecuteCommand(execute_request,USB_Response[rsp_slot]);
        dap_metric_end(metric_id,t,USB_RespSize[rsp_slot]);
        dap_trace_bytes(32U,USB_Response[rsp_slot],USB_RespSize[rsp_slot]);
        dap_trace_add(3U,USB_RespSize[rsp_slot]);dap_dbg_exec_count++;
        flags=irq_save();
        // A bus reset may occur during SWD execution. Discard its old result
        // instead of inserting it into the newly configured USB session.
        if(epoch==session_epoch){barrier();request_out++;response_in++;}
        irq_restore(flags);
        if(epoch!=session_epoch)break;
        dap_service_tx();
        if(dap_rx_deferred && chry_dap_rx_ready()){
            flags=irq_save();dap_rx_deferred=0;
            XUsbPs_DapResumeRx(g_dap_usb_instance);irq_restore(flags);
        }
    }
}
