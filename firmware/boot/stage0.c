/* OCM stage zero: initialize DDR, relocate the full loader, then leave OCM.
 * The probe application itself is linked at OCM address zero. */
#include "ps7_init.h"
#include "xil_cache.h"
#include "xil_io.h"
#include "xil_printf.h"
#include <stdint.h>
#include <string.h>

#define STAGE2_ADDRESS 0x02000000U
#define TRACE_ADDRESS 0x03FF0000U
extern const unsigned char probe_stage2_start[], probe_stage2_end[];
extern void FsblHandoffExit(unsigned address) __attribute__((noreturn));
volatile unsigned probe_stage0_status = 0x53544730U;

int main(void) {
    unsigned status = ps7_init();
    if (status != PS7_INIT_SUCCESS) {
        probe_stage0_status = 0xBAD00000U | status;
        for (;;) __asm__ volatile("wfe");
    }
    Xil_DCacheDisable();
    unsigned length = (unsigned)(probe_stage2_end - probe_stage2_start);
    volatile uint32_t *trace = (volatile uint32_t *)TRACE_ADDRESS;
    trace[0] = 0x53544730U;
    trace[1] = 0x20261031U;
    trace[2] = length;
    trace[3] = Xil_In32(0xF800025CU) & 15U;
    trace[4] = 1;
    trace[5] = trace[6] = trace[7] = 0;
    memcpy((void *)STAGE2_ADDRESS, probe_stage2_start, length);
    __asm__ volatile("dsb sy" ::: "memory");
    Xil_ICacheInvalidateRange(STAGE2_ADDRESS, length);
    probe_stage0_status = 0x53544731U;
    trace[4] = 2;
    xil_printf("[probe boot] DDR loader ready\r\n");
    FsblHandoffExit(STAGE2_ADDRESS);
}
