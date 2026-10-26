#ifndef DAP_METRICS_H
#define DAP_METRICS_H
#include <stdint.h>
#include "xtime_l.h"
#include "swd_dma.h"
enum { MET_EXEC05, MET_EXEC06_READ, MET_EXEC06_WRITE, MET_PACKET_READ,
       MET_PACKET_WRITE, MET_DMA_UPLOAD, MET_DMA_DOWNLOAD, MET_COPY,
       MET_QUEUE_WAIT, MET_USB_IN, MET_USB_SUBMIT, MET_COUNT };
typedef struct { uint64_t ticks; uint32_t calls, bytes; } dap_metric_t;
extern volatile dap_metric_t dap_metrics[MET_COUNT];
static inline XTime dap_metric_start(void) {
 XTime t=0;if(dap_profile.enabled)XTime_GetTime(&t);return t;
}
static inline void dap_metric_end(unsigned id, XTime start, uint32_t bytes) {
 XTime t;if(start && dap_profile.enabled){XTime_GetTime(&t);
 dap_metrics[id].ticks+=t-start;dap_metrics[id].calls++;dap_metrics[id].bytes+=bytes;}
}
#endif
