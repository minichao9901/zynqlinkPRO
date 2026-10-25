#include "stdint.h"
#include "DAP.h"
#include "xusbps.h"
#include "xil_cache.h"
#include "xil_mmu.h"
#include "xil_printf.h"
#include "xtime_l.h"
#include "sleep.h"
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

static volatile uint16_t USB_RequestIndexI;
static volatile uint16_t USB_RequestIndexO;
static volatile uint16_t USB_RequestCountI;
static volatile uint16_t USB_RequestCountO;
static volatile uint8_t USB_RequestIdle=0;

static volatile uint16_t USB_ResponseIndexI;
static volatile uint16_t USB_ResponseIndexO;
static volatile uint16_t USB_ResponseCountI;
static volatile uint16_t USB_ResponseCountO;
static volatile uint8_t USB_ResponseIdle;

// static __attribute__((section(".noncacheable"))) __attribute__((aligned(4))) uint8_t USB_Request[DAP_PACKET_COUNT][DAP_PACKET_SIZE];
// static __attribute__((section(".noncacheable"))) __attribute__((aligned(4))) uint8_t USB_Response[DAP_PACKET_COUNT][DAP_PACKET_SIZE];
static __attribute__((aligned(32))) uint8_t USB_Request[DAP_PACKET_COUNT][DAP_PACKET_SIZE];
static __attribute__((aligned(32))) uint8_t USB_Response[DAP_PACKET_COUNT][DAP_PACKET_SIZE];
static uint16_t USB_RespSize[DAP_PACKET_COUNT];

extern XUsbPs *g_dap_usb_instance;

__attribute__((section(".dap_debug"), aligned(32))) volatile uint32_t
dap_dbg_rtl_writes, dap_dbg_rtl_reads, dap_dbg_last_write_addr,
dap_dbg_last_write_value, dap_dbg_last_read_addr, dap_dbg_last_read_value;
__attribute__((section(".dap_debug"), aligned(32))) volatile uint32_t
dap_dbg_usb_rx, dap_dbg_exec_count;

// volatile struct cdc_line_coding g_cdc_lincoding;
// volatile uint8_t config_uart = 0;
// volatile uint8_t config_uart_transfer = 0;

// static __attribute__((section(".noncacheable"))) __attribute__((aligned(4))) uint8_t uartrx_ringbuffer[(8 * 1024)];
// static __attribute__((section(".noncacheable"))) __attribute__((aligned(4))) uint8_t usbrx_ringbuffer[(8 * 1024)];
// static __attribute__((section(".noncacheable"))) __attribute__((aligned(4))) uint8_t usb_tmpbuffer[512U];

// static volatile uint8_t usbrx_idle_flag = 0;
// static volatile uint8_t usbtx_idle_flag = 0;
// static volatile uint8_t uarttx_idle_flag = 0;

// chry_ringbuffer_t g_uartrx;
// chry_ringbuffer_t g_usbrx;

// extern uint8_t RxBuffer1[512];






void usbd_event_handler(uint8_t event)
{
  // printf("usbd_event_handler: %d\n", event);
  switch (event)
  {
  case 1:
    // usbrx_idle_flag = 0;
    // usbtx_idle_flag = 0;
    // uarttx_idle_flag = 0;
    // config_uart_transfer = 0;
    break;
  case 7:

    USB_RequestIdle = 0U;
    // usbd_ep_start_read(0x02, USB_Request[0], 512U);
    // usbd_ep_start_read(0x04, usb_tmpbuffer, 512U);
    // XUsbPs_EpPrime(g_dap_usb_instance, 2, XUSBPS_EP_DIRECTION_OUT);

    break;

  default:
    break;
  }
}

void debug_blink(uint32_t size, uint8_t led)
{  
  if(size > 512U){ 
    Xil_Out32(0x40000000, Xil_In32(0x40000000) | led);
    Xil_Out32(0x40000000, Xil_In32(0x40000000) & ~led);
    if(led == 0x1U)
    {
      xil_printf("o:%d\n", size);
    }
    else if(led == 0x2U)
    {
      xil_printf("i:%d\n", size);
    }
  }
}

void usbd_dap_bulk_out(XUsbPs *InstancePtr, u8 EpNum, u32 nbytes, u8 *Buffer)
{
  // Xil_Out32(0x40000000, Xil_In32(0x40000000) | 0x1U);
  // Xil_Out32(0x40000000, Xil_In32(0x40000000) & ~0x1U);
  // xil_printf("o:%d\n", nbytes);
  // xil_printf("dap_out_callback: ep=%02x, nbytes=%d\n", EpNum, nbytes);
  // debug_blink(nbytes, 0x1U);
  dap_trace_add(1U, nbytes);
  
  memcpy(USB_Request[USB_RequestIndexI], Buffer, nbytes);
  dap_dbg_usb_rx++;
  if (dap_dbg_usb_rx <= 8U) {
    xil_printf("[DAP] USB OUT ep=%d len=%d cmd=0x%02x\r\n",
               EpNum, nbytes, USB_Request[USB_RequestIndexI][0]);
  }
  if (USB_Request[USB_RequestIndexI][0] == 0x07U)
  {
    DAP_TransferAbort = 1U;
  }
  else
  {
    USB_RequestIndexI++;
    if (USB_RequestIndexI == DAP_PACKET_COUNT)
    {
      USB_RequestIndexI = 0U;
    }
    USB_RequestCountI++;
  }

  if ((uint16_t)(USB_RequestCountI - USB_RequestCountO) != DAP_PACKET_COUNT)
  {
    // usbd_ep_start_read(0x02, USB_Request[USB_RequestIndexI], 512U);
    // XUsbPs_EpPrime(g_dap_usb_instance, 2, XUSBPS_EP_DIRECTION_OUT);
  }
  else
  {
    USB_RequestIdle = 1U;
  }
}

static void dap_start_response(uint16_t idx)
{
  uint16_t len = USB_RespSize[idx];

  dap_trace_add(4U, len);
  /* A bulk IN transfer that ends on an exact max-packet boundary needs a ZLP,
   * otherwise the host keeps waiting for the rest of its buffer.  Responses
   * with 4 + 4*N bytes hit this for N = 127, 255, ... */
  if ((len != 0U) && (len < DAP_PACKET_SIZE) && ((len % 512U) == 0U)) {
    (void)XUsbPs_EpBufferSendWithZLT(g_dap_usb_instance, 1, USB_Response[idx], len);
  } else {
    (void)XUsbPs_EpBufferSend(g_dap_usb_instance, 1, USB_Response[idx], len);
  }
}

void usbd_dap_bulk_in(XUsbPs *InstancePtr, u8 EpNum, u32 nbytes)
{
  // xil_printf("dap_in_callback: ep=%02x, nbytes=%d\n", EpNum, nbytes);
  dap_trace_add(5U, nbytes);
  if (USB_ResponseCountI != USB_ResponseCountO)
  {

    // usbd_ep_start_write(0x82, USB_Response[USB_ResponseIndexO], USB_RespSize[USB_ResponseIndexO]);
    dap_start_response(USB_ResponseIndexO);
    USB_ResponseIndexO++;
    if (USB_ResponseIndexO == DAP_PACKET_COUNT)
    {
      USB_ResponseIndexO = 0U;
    }
    USB_ResponseCountO++;
  }
  else
  {
    USB_ResponseIdle = 1U;
  }
}


static void chry_dap_state_init(void)
{

  USB_RequestIndexI = 0U;
  USB_RequestIndexO = 0U;
  USB_RequestCountI = 0U;
  USB_RequestCountO = 0U;
  USB_RequestIdle = 1U;
  USB_ResponseIndexI = 0U;
  USB_ResponseIndexO = 0U;
  USB_ResponseCountI = 0U;
  USB_ResponseCountO = 0U;
  USB_ResponseIdle = 1U;

  // Xil_MemMap((uint32_t)&USB_Request, DAP_PACKET_COUNT * DAP_PACKET_SIZE, NORM_NONCACHE);
  // Xil_MemMap((uint32_t)&USB_Response, DAP_PACKET_COUNT * DAP_PACKET_SIZE, NORM_NONCACHE);
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
  uint32_t n;

  while (USB_RequestCountI != USB_RequestCountO)
  {

    n = USB_RequestIndexO;
    while (USB_Request[n][0] == 0x7EU)
    {
      USB_Request[n][0] = 0x7FU;
      n++;
      if (n == DAP_PACKET_COUNT)
      {
        n = 0U;
      }
      if (n == USB_RequestIndexI)
      {
      }
    }

    dap_trace_add(2U, USB_Request[USB_RequestIndexO][0]);
    USB_RespSize[USB_ResponseIndexI] =
        (uint16_t)DAP_ExecuteCommand(USB_Request[USB_RequestIndexO], USB_Response[USB_ResponseIndexI]);
    dap_trace_add(3U, USB_RespSize[USB_ResponseIndexI]);

    if (dap_dbg_exec_count < 8U) {
      xil_printf("[DAP] EXEC cmd=0x%02x resp=%d rtlW=%d rtlR=%d lastW=0x%08x lastR=0x%08x\r\n",
                 USB_Request[USB_RequestIndexO][0], USB_RespSize[USB_ResponseIndexI],
                 dap_dbg_rtl_writes, dap_dbg_rtl_reads,
                 dap_dbg_last_write_value, dap_dbg_last_read_value);
    }
    dap_dbg_exec_count++;

    USB_RequestIndexO++;
    if (USB_RequestIndexO == DAP_PACKET_COUNT)
    {
      USB_RequestIndexO = 0U;
    }
    USB_RequestCountO++;

    if (USB_RequestIdle)
    {
      if ((uint16_t)(USB_RequestCountI - USB_RequestCountO) != DAP_PACKET_COUNT)
      {
        USB_RequestIdle = 0U;
        // usbd_ep_start_read(0x02, USB_Request[USB_RequestIndexI], 512U);
        XUsbPs_EpPrime(g_dap_usb_instance, 2, XUSBPS_EP_DIRECTION_OUT);
      }
    }

    USB_ResponseIndexI++;
    if (USB_ResponseIndexI == DAP_PACKET_COUNT)
    {
      USB_ResponseIndexI = 0U;
    }
    USB_ResponseCountI++;

    if (USB_ResponseIdle)
    {
      if (USB_ResponseCountI != USB_ResponseCountO)
      {

        n = USB_ResponseIndexO++;
        if (USB_ResponseIndexO == DAP_PACKET_COUNT)
        {
          USB_ResponseIndexO = 0U;
        }
        USB_ResponseCountO++;
        USB_ResponseIdle = 0U;
        // usbd_ep_start_write(0x82, USB_Response[n], USB_RespSize[n]);
        // XUsbPs_EpBufferSendWithZLT(g_dap_usb_instance, 1, USB_Response[n], USB_RespSize[n]);
        dap_start_response((uint16_t)n);
        // debug_blink(USB_RespSize[n], 0x2U);
      }
    }
  }
}
