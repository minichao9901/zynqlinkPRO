#ifndef SWD_DMA_H
#define SWD_DMA_H
#include <stdint.h>
/* Aligned, private buffers: cache maintenance cannot touch USB-owned data. */
extern uint32_t swd_dma_cmd[1024];
extern uint32_t swd_dma_rsp[1024];
int swd_dma_upload(uint32_t words);
int swd_dma_download(uint32_t first, uint32_t words);
/* Destination must own the complete cache lines and be 32-byte aligned. */
int swd_dma_download_to(uint32_t first, uint32_t words, uint32_t *destination);
int swd_dma_selftest(void);
typedef struct {
    uint32_t enabled, batch_calls, upload_calls, download_calls;
    uint32_t upload_bytes, download_bytes;
    uint64_t batch_ticks, upload_ticks, download_ticks;
} dap_profile_t;
extern volatile dap_profile_t dap_profile;
void dap_swd_stats_snapshot(uint32_t values[8]);
void DAP_SWD_StatsClear(void);
#endif
