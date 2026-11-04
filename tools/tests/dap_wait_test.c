#define DAP_VALIDATION_FAULTS 1
#include "probe_target_platform.h"
#include <string.h>
#define SWD_STATUS 0x40010004U
#include "dap_wait.h"
volatile uint8_t DAP_TransferAbort;
static uint32_t test_epoch=1,mmio_status=0,reads,clear_at,cancel_at,epoch_at,resets,reset_bad,epoch_race;
static uint32_t clock_ctl=(1U<<8)|(1U<<20),clock_cfg;
static XTime ticks,time_step=50;
static uint32_t scalar_regs[40];
uint32_t chry_dap_epoch(void) {
    uint32_t value=test_epoch;
    if(epoch_race){epoch_race=0;test_epoch++;DAP_TransferAbort=1;}
    return value;
}
int swd_abort_engines(void) {resets++;return reset_bad?-1:0;}
void XTime_GetTime(XTime *p) {ticks+=time_step;*p=ticks;}
uint32_t Xil_In32(uintptr_t a) {
    if(a==0xf8000108U)return 30U<<12;
    if(a==SLCR_FPGA0_CLK_CTRL)return clock_ctl;
    if(a==SWD_CFG)return clock_cfg;
    if(a==SWD_STATUS) {
        reads++;
        if(clear_at && reads>=clear_at)mmio_status=0;
        if(cancel_at && reads>=cancel_at)DAP_TransferAbort=1;
        if(epoch_at && reads>=epoch_at){test_epoch++;epoch_at=0;}
        return mmio_status;
    }
    return 0;
}
void Xil_Out32(uintptr_t a,uint32_t v) {
    if(a>=0x40010000U && a<0x400100a0U)scalar_regs[(a-0x40010000U)/4]=v;
}
#include "../../firmware/xusbps_daplink_dma/DAP/Source/dap_wait.c"
void probe_target_observe(uint32_t a,uint32_t b,uint8_t c) {(void)a;(void)b;(void)c;}
#define SWD_BASE_ADDR ((uintptr_t)scalar_regs)
#define SWD_SWJ_DATA0 0x40010010U
#define SWD_SWJ_COUNT 0x4001000cU
#define SWD_CTRL 0x40010000U
#define DAP_HOT_CODE
#define DAP_TRANSFER_ERROR 8U
#define XFER_CMD_STS_REQUEST 8U
#define XFER_CMD_STS_MODE 2U
#define XFER_CMD_STS_START 1U
static int swd_wait_idle(void) {uint32_t s;return dap_wait_status(SWD_STATUS,1,0,512,&s);}
#include "dap_scalar_under_test.h"
static void fresh(void) {
    reads=clear_at=cancel_at=epoch_at=resets=reset_bad=mmio_status=0;ticks=0;time_step=50;
    clock_ctl=(1U<<8)|(1U<<20);clock_cfg=0;dap_wait_begin();
}
int main(void) {
    uint32_t s,data=0;
    fresh();assert(!dap_wait_status(SWD_STATUS,1,0,512,&s));assert(!ticks&&!resets);
    fresh();mmio_status=1;clear_at=10;assert(!dap_wait_status(SWD_STATUS,1,0,512,&s));
    fresh();mmio_status=1;assert(dap_wait_status(SWD_STATUS,1,0,512,&s));
    assert(dap_wait_last_reason==DAP_WAIT_TIMEOUT && resets==1 && ticks>=20000 && ticks<21000);
    uint32_t first=dap_wait_first_reason;
    fresh();mmio_status=1;cancel_at=10;assert(dap_wait_status(SWD_STATUS,1,0,512,&s));
    assert(dap_wait_last_reason==DAP_WAIT_CANCEL && resets==1 && dap_wait_first_reason==first);
    fresh();mmio_status=1;epoch_at=10;assert(dap_wait_status(SWD_STATUS,1,0,512,&s));
    assert(dap_wait_last_reason==DAP_WAIT_EPOCH && resets==0);
    fresh();mmio_status=1;epoch_race=1;
    assert(dap_wait_status(SWD_STATUS,1,0,512,&s));
    assert(dap_wait_last_reason==DAP_WAIT_EPOCH && resets==0);
    fresh();mmio_status=1;reset_bad=1;assert(dap_wait_status(SWD_STATUS,1,0,512,&s));assert(dap_wait_recovery_failures);
    fresh();clock_ctl=(63U<<8)|(63U<<20);clock_cfg=(15U<<13)|(15U<<28);time_step=10000;
    mmio_status=1;assert(dap_wait_status(SWD_STATUS,1,0,512,&s));assert(ticks>4000000);
    fresh();mmio_status=1;assert(SWD_Transfer(2,&data)==8 && resets==1);
    uint32_t start=scalar_regs[0];assert(SWD_Transfer(13,&data)==8 && scalar_regs[0]==start);
    fresh();mmio_status=1;uint8_t ones[32];memset(ones,255,sizeof ones);
    SWJ_SequenceChunk(256,ones);assert(dap_wait_command_error()==DAP_WAIT_TIMEOUT && resets==1);
    fresh();dap_validation_wait_mask=1;dap_validation_wait_arm=0x112115a5U;
    assert(dap_wait_status(SWD_STATUS,1,0,512,&s));assert(!dap_validation_wait_arm);
    dap_wait_begin();assert(!dap_wait_status(SWD_STATUS,1,0,512,&s));
    dap_validation_restore_stage=3;dap_validation_restore_arm=0x112115a5U;
    assert(!dap_validation_restore_fault(2));assert(dap_validation_restore_fault(3));assert(!dap_validation_restore_fault(3));
    puts("PASS production wait/scalar/SWJ: ready, timeout, Abort, USB epoch, failed reset, low-rate budget, no replay and one-shot diagnostic injection");
}
