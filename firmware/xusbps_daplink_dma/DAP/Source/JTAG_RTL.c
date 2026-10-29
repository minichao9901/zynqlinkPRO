// CMSIS-DAP JTAG glue. All TCK/TMS/TDI/TDO cycles execute in PL.
#include "DAP_config.h"
#include "DAP.h"
#include "jtag_rtl.h"
#include <string.h>

#if DAP_JTAG
static uint8_t timing_dirty=1;
static uint8_t run(uint32_t op,uint32_t request,uint32_t *value);
void DAP_JTAG_ClockChanged(void) {timing_dirty=1;}
/* Bit0: IDDR Q2=0 / Q1=1. Bit4: previous DR bit window. */
void DAP_JTAG_SetTiming(uint32_t value) {swd_write32(JTAG_TIMING,value&0x11U);timing_dirty=0;}
/* FCLK currently driving the PL, recomputed from the SLCR dividers. */
static uint32_t fclk_now(void) {
    uint32_t reg=Xil_In32(SLCR_FPGA0_CLK_CTRL);
    uint32_t d0=(reg>>8)&63U,d1=(reg>>20)&63U;
    return (d0 && d1) ? IO_PLL_HZ/d0/d1 : 0U;
}
/* Exercise DP/AP IR transitions with saved/restored CSW and TAR patterns,
 * plus reads of the read-only CPUID. SELECT is write-only on DPv0: preserve
 * its observed shadow. Calibration must never write through AP DRW. */
static int reg_write(uint32_t req,uint32_t value) {return run(0,req,&value)==1;}
static int ap_read(uint32_t req,uint32_t *value) {
    return run(0,req,value)==1 && run(0,14,value)==1;
}
static void clock_restore(uint32_t value) {
    Xil_Out32(XSLCR_UNLOCK_ADDR,XSLCR_UNLOCK_CODE);
    Xil_Out32(SLCR_FPGA0_CLK_CTRL,value);
    Xil_Out32(SLCR_LOCK_ADDR,0x767bU);
}
typedef struct {uint32_t clock,safe_clock,select,csw,tar,cpuid;unsigned saved;} timing_context;
static int context_restore(timing_context *c) {
    clock_restore(c->safe_clock);swd_write32(JTAG_TIMING,0);
    int ok=reg_write(4,0x50000032U) && reg_write(8,0);
    if(c->saved) ok=reg_write(1,c->csw) && reg_write(5,c->tar) && ok;
    uint32_t dummy=0;
    if(c->saved) ok=run(0,14,&dummy)==1 && ok;
    return reg_write(8,c->select) && ok;
}
static int context_capture(timing_context *c) {
    extern uint32_t probe_target_dp_select(void);
    memset(c,0,sizeof(*c));c->clock=Xil_In32(SLCR_FPGA0_CLK_CTRL);c->select=probe_target_dp_select();
    uint32_t hz=fclk_now();ps_set_fclk0_hz(hz<20000000U ? hz : 20000000U);
    c->safe_clock=Xil_In32(SLCR_FPGA0_CLK_CTRL);swd_write32(JTAG_TIMING,0);
    swd_write32(JTAG_PINS,swd_read32(JTAG_PINS));
    int ok=reg_write(4,0x50000032U) && reg_write(8,0) && ap_read(3,&c->csw) && ap_read(7,&c->tar);
    if(ok) {
        c->saved=1;
        ok=reg_write(1,(c->csw&~0x3fU)|2U) && reg_write(5,0xe000ed00U) && ap_read(15,&c->cpuid);
        ok=ok && (c->cpuid&0xff000000U)==0x41000000U;
    }
    int restored=context_restore(c);clock_restore(c->clock);
    return ok && restored;
}
static int dp_roundtrip_ok(const timing_context *c) {
    uint32_t value=0,patterns[4]={0x200003fcU,0x20004000U,0xa5a55a58U,0x5a5aa5a4U};
    uint32_t csw=(c->csw&~0x3fU)|2U;
    if(!reg_write(4,0x50000032U) || !reg_write(8,0) || !reg_write(1,csw)) return 0;
    if(!ap_read(3,&value) || (value&0xff00003fU)!=(csw&0xff00003fU)) return 0;
    for(unsigned i=0;i<4;i++)
        if(!reg_write(5,patterns[i]) || !ap_read(7,&value) || value!=patterns[i]) return 0;
    if(!reg_write(5,0xe000ed00U) || !ap_read(7,&value) || value!=0xe000ed00U) return 0;
    for(unsigned i=0;i<4;i++) if(!ap_read(15,&value) || value!=c->cpuid) return 0;
    return 1;
}
/* TDO arrives back through a fixed physical delay, so at TCK = FCLK/2 only
 * some FCLK settings can capture it. Verify both the IDCODE and a data
 * round trip, and if neither sampling mode works step the clock to the next
 * lower achievable FCLK until one does. Clocks are a maximum, so a lower
 * validated rate is acceptable; stepping one divider at a time keeps the
 * fallback as close to the request as the hardware allows. */
/* IDCODE instruction loaded by operation 3. 0x0E is ARM ADIv5; a RISC-V DTM
 * uses 0x01. Route[15:8] is independent of IR chain lengths. Route bit2
 * selects the PL RISC-V SBA memory frontend for the packet/RTT/HSS engines. */
static uint32_t idcode_ir = JTAG_IDCODE;
void JTAG_SetIDCodeIR(uint32_t value) { idcode_ir = value & 0xFFU; }
uint32_t JTAG_IDCodeIR(void) { return idcode_ir; }
uint32_t DAP_JTAG_RouteWord(void) {
    return 3U | (idcode_ir<<8) | (idcode_ir==1U ? 4U : 0U);
}
/* HPM's DTM needs a TAP reset between IDCODE/DTMCS and DMI. Merely
 * replacing IR leaves DMI unresponsive, even though the IR cache says 0x11.
 * Reset through the PL and select DMI before handing it to memory/streams. */
static int prime_riscv(void) {
    if(idcode_ir!=1U) return 1;
    uint32_t ir=17U;
    swd_write32(JTAG_PINS,swd_read32(JTAG_PINS));
    int ok=run(2,0,&ir)==1;
    /* A new stream claim may calibrate after the host activated the DM.
     * Re-establish dmactive after TLR, before autonomous SBA starts. */
    uint32_t active=1U;
    if(ok) ok=run(0,4,&active)==1;
    swd_write32(JTAG_OPERATION,0);
    return ok;
}
#define JTAG_VALIDATE_ATTEMPTS 16U
#define JTAG_VALIDATE_FLOOR_HZ 500000U
static int calibrate(void) {
    timing_context context;
    uint32_t expect_ir=idcode_ir;
    int generic = expect_ir!=(uint32_t)JTAG_IDCODE;   /* RISC-V DTM, not ADIv5 */
    if(!generic) {
        if(!context_capture(&context)) {swd_write32(JTAG_OPERATION,0);return -1;}
    } else {
        memset(&context,0,sizeof context);
    }
    const uint32_t modes[4]={0U,1U,17U,16U};
    uint32_t preferred=generic ? (swd_read32(JTAG_TIMING)&17U) : 0U;
    for(unsigned attempt=0;attempt<JTAG_VALIDATE_ATTEMPTS;attempt++) {
        for(unsigned mode=0;mode<4;mode++) {
            uint32_t chosen=modes[mode]^preferred;
            uint32_t value=0U,again=0U;
            swd_write32(JTAG_TIMING,chosen);
            if((swd_read32(JTAG_TIMING)&17U)!=chosen) continue;
            /* A pins write invalidates the IR cache, forcing a TAP reset
             * before the scan: clock changes can leave the TAP mid-scan. */
            swd_write32(JTAG_PINS,swd_read32(JTAG_PINS));
            if(run(3,2,&value)!=1) continue;
            if(!generic) {
                if((value&0x0fff0fffU)!=0x0ba00477U) continue;
                if(dp_roundtrip_ok(&context)) {
                    uint32_t clock=Xil_In32(SLCR_FPGA0_CLK_CTRL);
                    int restored=context_restore(&context);
                    clock_restore(clock);swd_write32(JTAG_TIMING,chosen);
                    timing_dirty=!restored;swd_write32(JTAG_OPERATION,0);return restored ? 0 : -1;
                }
                continue;
            }
            /* No ADIv5 DP/AP on this target: accept a stable, non-degenerate
             * IDCODE instead of the ARM one and skip the DP/AP round trip. */
            if(value==0U || value==0xffffffffU) continue;
            if(run(3,2,&again)!=1 || again!=value) continue;
            swd_write32(JTAG_TIMING,chosen);
            if(!prime_riscv()) continue;
            timing_dirty=0;swd_write32(JTAG_OPERATION,0);return 0;
        }
        /* A non-ADIv5 target has no DP/AP round trip to gain from a slower
         * clock, and walking the divider down would leave the link slow for
         * every later scan: stop after the four sampling modes. */
        if(generic) break;
        uint32_t fclk=fclk_now();
        if(!fclk || fclk<=JTAG_VALIDATE_FLOOR_HZ) break;
        /* Ask for anything below the current rate: ps_set_fclk0_hz returns the
         * highest achievable value not above the target, i.e. one divider step. */
        ps_set_fclk0_hz(fclk-1U);
    }
    if(!generic) {(void)context_restore(&context);clock_restore(context.clock);}
    swd_write32(JTAG_TIMING,0);swd_write32(JTAG_OPERATION,0);return -1;
}

int DAP_JTAG_Select(uint32_t index) {
    if(!(swd_read32(SWD_FEATURES)&8U) || !DAP_Data.jtag_dev.count ||
       DAP_Data.jtag_dev.count>DAP_JTAG_DEV_CNT || index>=DAP_Data.jtag_dev.count) return -1;
    uint32_t len=DAP_Data.jtag_dev.ir_length[index];
    if(!len || len>32) return -1;
    uint32_t ir=len|((uint32_t)DAP_Data.jtag_dev.ir_before[index]<<8)|
                ((uint32_t)DAP_Data.jtag_dev.ir_after[index]<<19);
    uint32_t dr=index|((uint32_t)(DAP_Data.jtag_dev.count-index-1U)<<8);
    uint32_t route=DAP_JTAG_RouteWord();
    if(swd_read32(JTAG_ROUTE)!=route) {swd_write32(JTAG_ROUTE,route);timing_dirty=1;}
    if(swd_read32(JTAG_IR_CONFIG)!=ir) {swd_write32(JTAG_IR_CONFIG,ir);timing_dirty=1;}
    if(swd_read32(JTAG_DR_CONFIG)!=dr) {swd_write32(JTAG_DR_CONFIG,dr);timing_dirty=1;}
    DAP_Data.jtag_dev.index=(uint8_t)index;
    swd_write32(JTAG_OPERATION,0);
    return timing_dirty ? calibrate() : 0;
}
static uint8_t run(uint32_t op,uint32_t request,uint32_t *value) {
    swd_write32(JTAG_OPERATION,op);
    return SWD_Transfer(request,value);
}
int DAP_JTAG_AutoConfigure(void) {
    uint8_t ones[8],zero=0,ids[8]={0};
    memset(ones,255,sizeof(ones));
    JTAG_Sequence(0x46,ones,ids); // TAP reset.
    JTAG_Sequence(1,&zero,ids);  // Idle.
    JTAG_Sequence(0x41,ones,ids);JTAG_Sequence(2,&zero,ids);
    JTAG_Sequence(0x80,ones,ids); // Both default IDCODEs, independent of IR lengths.
    uint32_t first=0,second=0;memcpy(&first,ids,4);memcpy(&second,ids+4,4);
    JTAG_Sequence(0x42,ones,ids);JTAG_Sequence(1,&zero,ids);
    if((first&0x0fff0fffU)!=0x0ba00477U) return -1;
    unsigned n=second==UINT32_MAX ? 1U : (second&0x0fffffffU)==0x06410041U ? 2U : 0U;
    if(!n) return -1; // Unknown chains require explicit CMSIS JTAG_Configure.
    DAP_Data.jtag_dev.count=(uint8_t)n;DAP_Data.jtag_dev.index=0;
    DAP_Data.jtag_dev.ir_length[0]=4;DAP_Data.jtag_dev.ir_before[0]=0;DAP_Data.jtag_dev.ir_after[0]=n==2 ? 5 : 0;
    if(n==2) {DAP_Data.jtag_dev.ir_length[1]=5;DAP_Data.jtag_dev.ir_before[1]=4;DAP_Data.jtag_dev.ir_after[1]=0;}
    timing_dirty=1;return 0;
}
void JTAG_Sequence(uint32_t info,const uint8_t *tdi,uint8_t *tdo) {
    uint32_t n=info&63U,words[8]={0},value=0;
    if(!n) n=64;
    memcpy(words,tdi,(n+7U)/8U);
    for(unsigned i=0;i<8;i++) swd_write32(SWD_SWJ_DATA0+4*i,words[i]);
    swd_write32(SWD_SWJ_COUNT,n);
    swd_write32(JTAG_SEQ_TMS_REG,(info>>6)&1U);
    uint8_t ack=run(5,2,&value);
    if(info & JTAG_SEQUENCE_TDO) {
        for(unsigned i=0;i<(n+31U)/32U;i++) words[i]=swd_read32(JTAG_RX_DATA+4*i);
        if(ack==1) memcpy(tdo,words,(n+7U)/8U);
        else memset(tdo,0,(n+7U)/8U);
    }
    swd_write32(JTAG_OPERATION,0);
}
void JTAG_IR(uint32_t ir) {
    if(DAP_JTAG_Select(DAP_Data.jtag_dev.index)) return;
    (void)run(2,0,&ir);
    swd_write32(JTAG_OPERATION,0);
}
uint32_t JTAG_ReadIDCode(void) {
    uint32_t value=0;
    if(DAP_JTAG_Select(DAP_Data.jtag_dev.index)) return 0;
    /* IDCODE queries switch away from an already active HPM DMI. Start the
     * observation from TLR too, then prime DMI again for the next transfer. */
    if(idcode_ir==1U) swd_write32(JTAG_PINS,swd_read32(JTAG_PINS));
    if(run(3,2,&value)!=1) value=0;
    if(!prime_riscv()) value=0;
    swd_write32(JTAG_OPERATION,0);
    return value;
}
void JTAG_WriteAbort(uint32_t data) {
    if(DAP_JTAG_Select(DAP_Data.jtag_dev.index)) return;
    (void)run(4,0,&data);
    swd_write32(JTAG_OPERATION,0);
}
uint8_t JTAG_Transfer(uint32_t request,uint32_t *data) {
    uint32_t scratch=0;
    if(DAP_JTAG_Select(DAP_Data.jtag_dev.index)) return DAP_TRANSFER_ERROR;
    uint8_t ack=run(1,request,data ? data : &scratch);
    swd_write32(JTAG_OPERATION,0);
    return ack;
}
uint8_t DAP_JTAG_MemTransfer(uint32_t request,uint32_t *data) {
    swd_write32(JTAG_OPERATION,0);
    return SWD_Transfer(request,data);
}
#endif
