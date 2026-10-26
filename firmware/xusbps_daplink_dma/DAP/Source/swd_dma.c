#include "swd_dma.h"
#include "dap_metrics.h"
#include "xil_io.h"
#include "xil_cache.h"
#include "xtime_l.h"

#define CDMA 0x40020000U
#define CMD_RAM 0x42000000U
#define RSP_RAM 0x42010000U
#define CR 0x00U
#define SR 0x04U
#define SA 0x18U
#define DA 0x20U
#define BTT 0x28U
#define IDLE 0x2U
#define ERRORS 0x70U

/* AXI BRAM is uncached device memory. Tiny headers/status words cost less
 * as a few direct accesses than setting up an entire CDMA transaction. */
#define PIO_MAX_WORDS 8U

uint32_t swd_dma_cmd[1024] __attribute__((aligned(32)));
uint32_t swd_dma_rsp[1024] __attribute__((aligned(32)));
volatile uint32_t swd_dma_errors, swd_dma_last_status;
volatile dap_profile_t dap_profile;

static int copy(uint32_t src, uint32_t dst, uint32_t bytes) {
    XTime start, now;
    uint32_t status;
    if (bytes == 0U) return 0;
    XTime_GetTime(&start);
    do {
        status = Xil_In32(CDMA + SR);
        if (status & ERRORS) goto fail;
        XTime_GetTime(&now);
        if (now-start > COUNTS_PER_SECOND/10U) goto fail;
    } while (!(status & IDLE));
    Xil_Out32(CDMA + SR, 0x7000U);
    Xil_Out32(CDMA + SA, src);
    Xil_Out32(CDMA + DA, dst);
    __asm__ volatile("dsb sy" ::: "memory");
    Xil_Out32(CDMA + BTT, bytes);
    do {
        status = Xil_In32(CDMA + SR);
        if (status & ERRORS) goto fail;
        XTime_GetTime(&now);
        if (now-start > COUNTS_PER_SECOND/10U) goto fail;
    } while (!(status & IDLE));
    __asm__ volatile("dsb sy" ::: "memory");
    return 0;
fail:
    swd_dma_errors++;
    swd_dma_last_status = status;
    Xil_Out32(CDMA + CR, 4U);
    return -1;
}

int swd_dma_upload(uint32_t words) {
    XTime start, end;
    XTime metric_start=dap_metric_start();
    uint32_t profiling=dap_profile.enabled;
    int rc;
    if (words > 1024U) return -1;
    if (profiling) XTime_GetTime(&start);
    if (words <= PIO_MAX_WORDS) {
        uint32_t n;
        for (n=0; n<words; ++n) Xil_Out32(CMD_RAM+n*4U,swd_dma_cmd[n]);
        __asm__ volatile("dsb sy" ::: "memory");
        rc=0;
    } else {
        Xil_DCacheFlushRange((UINTPTR)swd_dma_cmd, words*4U);
        rc=copy((uint32_t)swd_dma_cmd, CMD_RAM, words*4U);
    }
    if (profiling) {
        XTime_GetTime(&end);
        dap_profile.upload_ticks += end-start;
        dap_profile.upload_calls++;
        dap_profile.upload_bytes += words*4U;
    }
    dap_metric_end(MET_DMA_UPLOAD, metric_start, words*4U);
    return rc;
}

int swd_dma_download_to(uint32_t first, uint32_t words, uint32_t *destination) {
    int rc;
    XTime start, end;
    XTime metric_start=dap_metric_start();
    uint32_t profiling=dap_profile.enabled;
    if (first > 1024U || words > 1024U-first || ((UINTPTR)destination & 31U)) return -1;
    if (profiling) XTime_GetTime(&start);
    if (words <= PIO_MAX_WORDS) {
        uint32_t n;
        for (n=0; n<words; ++n) destination[n]=Xil_In32(RSP_RAM+(first+n)*4U);
        rc=0;
    } else {
        Xil_DCacheFlushRange((UINTPTR)destination, words*4U);
        rc = copy(RSP_RAM + first*4U, (uint32_t)destination, words*4U);
        Xil_DCacheInvalidateRange((UINTPTR)destination, words*4U);
    }
    if (profiling) {
        XTime_GetTime(&end);
        dap_profile.download_ticks += end-start;
        dap_profile.download_calls++;
        dap_profile.download_bytes += words*4U;
    }
    dap_metric_end(MET_DMA_DOWNLOAD, metric_start, words*4U);
    return rc;
}

int swd_dma_download(uint32_t first, uint32_t words) {
    return swd_dma_download_to(first,words,swd_dma_rsp);
}

int swd_dma_selftest(void) {
    uint32_t n;
    for (n=0; n<1024U; n++) swd_dma_cmd[n] = 0xCDA00000U ^ (n*0x10203U);
    if (swd_dma_upload(1024U)) return -1;
    Xil_DCacheFlushRange((UINTPTR)swd_dma_rsp, sizeof swd_dma_rsp);
    if (copy(CMD_RAM, (uint32_t)swd_dma_rsp, sizeof swd_dma_rsp)) return -2;
    Xil_DCacheInvalidateRange((UINTPTR)swd_dma_rsp, sizeof swd_dma_rsp);
    for (n=0; n<1024U; n++) if (swd_dma_rsp[n] != swd_dma_cmd[n]) return -3;
    if (copy((uint32_t)swd_dma_cmd, RSP_RAM, sizeof swd_dma_cmd)) return -4;
    if (swd_dma_download(0U, 1024U)) return -5;
    for (n=0; n<1024U; n++) if (swd_dma_rsp[n] != swd_dma_cmd[n]) return -6;
    return 0;
}
