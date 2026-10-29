#include "probe_target_platform.h"
#include "../../firmware/xusbps_daplink_dma/DAP/Include/jtag_rtl.h"
#define DAP_JTAG 1
#define DAP_JTAG_DEV_CNT 8
#define JTAG_SEQUENCE_TDO 0x80U
#define JTAG_IDCODE 0x0EU
#define DAP_TRANSFER_ERROR 8U
#define SWD_FEATURES 0x4001004cU
#define SWD_SWJ_DATA0 0x40010010U
#define SWD_SWJ_COUNT 0x4001000cU
static int ps_set_fclk0_hz(uint32_t hz);
void JTAG_Sequence(uint32_t,const uint8_t *,uint8_t *);
#include "../../firmware/xusbps_daplink_dma/DAP/Source/JTAG_RTL.c"

DAP_Data_t DAP_Data={.debug_port=2,.jtag_dev={.count=2,.ir_length={4,5},.ir_after={5,0}}};
static uint32_t regs[8]={3,4|(5U<<19),256,0,0,0,0,14};
static uint32_t selected=0x01000030U,posted;
static uint32_t clock_value=(1U<<20)|(10U<<8),csw_value=0x23000052U,tar_value=0x20004a10U;
static unsigned scans,valid_mode=17,mode_seen,ap_reads;
uint32_t Xil_In32(uintptr_t a) {
    if(a==SWD_FEATURES)return 15;
    if(a==SLCR_FPGA0_CLK_CTRL)return clock_value;
    assert(a>=JTAG_ROUTE && a<JTAG_RX_DATA);
    return regs[(a-JTAG_ROUTE)/4] | (a==JTAG_TIMING ? 4U : 0U);
}
void Xil_Out32(uintptr_t a,uint32_t d) {
    if(a==SLCR_FPGA0_CLK_CTRL) {clock_value=d;return;}
    if(a==XSLCR_UNLOCK_ADDR || a==SLCR_LOCK_ADDR)return;
    assert(a>=JTAG_ROUTE && a<JTAG_RX_DATA);regs[(a-JTAG_ROUTE)/4]=d;
}
uint32_t probe_target_dp_select(void) {return selected;}
static int ps_set_fclk0_hz(uint32_t hz) {
    assert(hz==20000000U);clock_value=(1U<<20)|(50U<<8);return (int)hz;
}
uint8_t SWD_Transfer(uint32_t req,uint32_t *data) {
    unsigned mode=regs[6]&17U;
    int good=clock_value==((1U<<20)|(50U<<8)) || mode==valid_mode;
    if(regs[3]==3) {scans++;mode_seen|=1U<<mode;*data=regs[0]&4U ? 0x1000563dU : 0x3ba00477U;return 1;}
    if(regs[3]==2) {assert((regs[0]&4U) && *data==17U);regs[7]=17;return 1;}
    if((regs[0]&4U) && req==4) {assert(*data==1U);return 1;}
    assert(regs[3]==0);
    switch(req) {
    case 4:assert(*data==0x50000032U);break;
    case 8:selected=*data;break;
    case 1:assert(selected==0);csw_value=*data;break;
    case 5:assert(selected==0);tar_value=*data;break;
    case 3:assert(selected==0);posted=csw_value;ap_reads++;break;
    case 7:assert(selected==0);posted=good ? tar_value : tar_value^0x8000U;ap_reads++;break;
    case 15:
        // The only memory read is the read-only CPUID. A RAM read or any
        // DRW write fails, and every AP context field must be restored.
        assert(selected==0 && tar_value==0xe000ed00U && (csw_value&0x3fU)==2);
        posted=good ? 0x411fc231U : 0;ap_reads++;break;
    case 14:*data=posted;break;
    default:assert(!"Calibration must never write target memory");
    }
    return 1;
}
int main(void) {
    assert(DAP_JTAG_Select(0)==0);
    assert(scans==3 && regs[6]==17 && selected==0x01000030U && ap_reads>6);
    assert(csw_value==0x23000052U && tar_value==0x20004a10U && clock_value==((1U<<20)|(10U<<8)));
    assert(mode_seen==((1U<<0)|(1U<<1)|(1U<<17)));
    valid_mode=16;mode_seen=0;DAP_JTAG_ClockChanged();
    assert(DAP_JTAG_Select(0)==0 && regs[6]==16 && selected==0x01000030U);
    assert(csw_value==0x23000052U && tar_value==0x20004a10U);
    assert(mode_seen==((1U<<0)|(1U<<1)|(1U<<17)|(1U<<16)));
    unsigned old_scans=scans;DAP_JTAG_SetTiming(1);
    assert(DAP_JTAG_Select(0)==0 && scans==old_scans && regs[6]==1);
    // Exercise the actual firmware packing, not just core inputs. IDCODE
    // selection must not inject extra IR-after bits into a one-TAP chain.
    DAP_Data.jtag_dev.count=1;DAP_Data.jtag_dev.ir_length[0]=5;
    DAP_Data.jtag_dev.ir_before[0]=DAP_Data.jtag_dev.ir_after[0]=0;
    unsigned old_ap_reads=ap_reads;
    JTAG_SetIDCodeIR(1);DAP_JTAG_ClockChanged();
    assert(DAP_JTAG_Select(0)==0);
    assert(regs[0]==0x0107 && regs[1]==5 && regs[2]==0);
    assert(regs[6]==1 && ap_reads==old_ap_reads);
    assert(JTAG_ReadIDCode()==0x1000563dU && regs[7]==17U);
    puts("PASS production JTAG calibration: all IDDR phases, TAR pattern/CPUID validation, SELECT/CSW/TAR/clock restore, no target memory writes");
    return 0;
}
