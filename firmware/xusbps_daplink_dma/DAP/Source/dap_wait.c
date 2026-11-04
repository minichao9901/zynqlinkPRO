#include "DAP_config.h"
#include "DAP.h"
#include "dap_wait.h"
#include "swd_dma.h"
#include "xtime_l.h"
extern uint32_t chry_dap_epoch(void);
static uint32_t command_epoch,command_error;
#define SAFETY_DATA __attribute__((section(".dap_trace.safety"),aligned(32)))
volatile uint32_t dap_wait_failures SAFETY_DATA,dap_wait_first_reason SAFETY_DATA,
    dap_wait_first_address SAFETY_DATA,dap_wait_first_status SAFETY_DATA,
    dap_wait_last_reason SAFETY_DATA,dap_wait_recovery_failures SAFETY_DATA;
volatile uint32_t dap_context_snapshot[6] SAFETY_DATA;
#if DAP_VALIDATION_FAULTS
/* Diagnostic ELF only: one-shot injection through physical MEM-AP, no USB
 * interface. These globals and branches are absent in the production ELF. */
volatile uint32_t dap_validation_wait_arm SAFETY_DATA,dap_validation_wait_mask SAFETY_DATA,dap_validation_wait_ms SAFETY_DATA;
volatile uint32_t dap_validation_restore_arm SAFETY_DATA,dap_validation_restore_stage SAFETY_DATA;
#endif
void dap_wait_init(void) {
    dap_wait_failures=dap_wait_first_reason=dap_wait_first_address=dap_wait_first_status=0;
    dap_wait_last_reason=dap_wait_recovery_failures=0;
    for(unsigned i=0;i<6;i++)dap_context_snapshot[i]=0;
#if DAP_VALIDATION_FAULTS
    dap_validation_wait_arm=dap_validation_wait_mask=dap_validation_wait_ms=0;
    dap_validation_restore_arm=dap_validation_restore_stage=0;
#endif
    dap_wait_begin();
}
void dap_context_publish(uint32_t flags,uint32_t failures,uint32_t first_stage,
                          uint32_t select,uint32_t csw,uint32_t tar) {
    dap_context_snapshot[1]=failures;dap_context_snapshot[2]=first_stage;
    dap_context_snapshot[3]=select;dap_context_snapshot[4]=csw;dap_context_snapshot[5]=tar;
    dap_context_snapshot[0]=flags;
}
void dap_wait_begin(void) {
    command_epoch=chry_dap_epoch();command_error=0;DAP_TransferAbort=0;
}
unsigned dap_wait_command_error(void) {
    if(!command_error) {
        uint32_t reason=chry_dap_epoch()!=command_epoch ? DAP_WAIT_EPOCH :
                        DAP_TransferAbort ? DAP_WAIT_CANCEL : 0;
        if(reason) {
            command_error=reason;dap_wait_last_reason=reason;dap_wait_failures++;
            if(!dap_wait_first_reason) {
                dap_wait_first_address=0;dap_wait_first_status=0;dap_wait_first_reason=reason;
            }
        }
    }
    return command_error;
}
int dap_validation_restore_fault(unsigned stage) {
#if DAP_VALIDATION_FAULTS
    if(dap_validation_restore_arm==0x112115a5U && dap_validation_restore_stage==stage) {
        dap_validation_restore_arm=0;return 1;
    }
#else
    (void)stage;
#endif
    return 0;
}
int dap_wait_status(uint32_t address,uint32_t mask,uint32_t expected,
                     uint32_t wire_bits,uint32_t *last) {
    XTime start,now;uint32_t status,n=0,reason=0,test_mask=0,test_ms=0,irq_state;
    uint64_t budget,fclk,half;
    if(command_error){*last=0;return -1;}
#if DAP_VALIDATION_FAULTS
    if(dap_validation_wait_arm==0x112115a5U) {
        dap_validation_wait_arm=0;test_mask=dap_validation_wait_mask&mask;
        test_ms=dap_validation_wait_ms;
        if(test_ms>2000)test_ms=2000;
    }
#endif
    status=swd_read32(address);status=(status&~test_mask)|((~expected)&test_mask);*last=status;
    if(chry_dap_epoch()!=command_epoch){reason=DAP_WAIT_EPOCH;goto failed;}
    if(DAP_TransferAbort){reason=DAP_WAIT_CANCEL;goto failed;}
    if((status&mask)==expected)return 0;
    /* The PS private timer keeps ticking if a PL engine/FCLK stops. Four
     * times the legal wire work plus 20ms margin includes the realized low
     * FCLK/divider, instead of a CPU-dependent iteration count. */
    fclk=ps_fclk0_hz();if(!fclk){reason=DAP_WAIT_TIMEOUT;goto failed;}
    status=swd_read32(SWD_CFG);
    half=1+((status>>13)&15)+(((status>>28)&15)<<4);
    budget=(uint64_t)COUNTS_PER_SECOND/50U+
        ((uint64_t)COUNTS_PER_SECOND*wire_bits*8U*half+fclk-1)/fclk;
    if(test_ms)budget=(uint64_t)COUNTS_PER_SECOND*test_ms/1000U;
    XTime_GetTime(&start);
    for(;;) {
        status=swd_read32(address);status=(status&~test_mask)|((~expected)&test_mask);*last=status;
        if(chry_dap_epoch()!=command_epoch){reason=DAP_WAIT_EPOCH;break;}
        if(DAP_TransferAbort){reason=DAP_WAIT_CANCEL;break;}
        if((status&mask)==expected)return 0;
        if((++n&31U)==0) {
            XTime_GetTime(&now);
            if(now-start>=budget){reason=DAP_WAIT_TIMEOUT;break;}
        }
    }
failed:
    /* RESET IRQ can run between the epoch and Abort reads above. Recheck
     * atomically with the reset decision: an old waiter must never reset a
     * successor session's engine, even if it initially observed Abort. */
    irq_state=mfcpsr();mtcpsr(irq_state|0x80U);
    if(chry_dap_epoch()!=command_epoch)reason=DAP_WAIT_EPOCH;
    command_error=reason;dap_wait_last_reason=reason;dap_wait_failures++;
    if(!dap_wait_first_reason) {
        dap_wait_first_address=address;dap_wait_first_status=*last;dap_wait_first_reason=reason;
    }
    /* A USB reset already aborted the old epoch; do not reset its successor.
     * For BUSY/Abort, require the controller's acknowledged reset, no replay. */
    if(reason!=DAP_WAIT_EPOCH && swd_abort_engines())dap_wait_recovery_failures++;
    mtcpsr(irq_state);
    return -1;
}
