// SWD ownership adapter. All calls run in main, including HID requests.
#include "DAP.h"
#include "DAP_config.h"
#include "probe_stream.h"
#include "DAP/Include/jtag_rtl.h"
#include <string.h>
static uint32_t select_shadow, saved_select, saved_csw, saved_tar;
static int claimed, saved, link_ready;
static uint32_t saved_clock, saved_cfg;
static DAP_Data_t saved_dap;
static DAP_Data_t cached_jtag;
static uint8_t preferred_port,link_port=1,has_jtag,saved_ir_valid;
static uint32_t saved_route,saved_ir_config,saved_dr_config,saved_operation,saved_instruction;
static void restore_clock(void) {
    Xil_Out32(XSLCR_UNLOCK_ADDR, XSLCR_UNLOCK_CODE);
    Xil_Out32(SLCR_FPGA0_CLK_CTRL, saved_clock);
    Xil_Out32(SLCR_LOCK_ADDR, 0x767b);
    swd_write32(SWD_CFG, saved_cfg);
    if(has_jtag) {
        swd_write32(JTAG_IR_CONFIG,saved_ir_config);swd_write32(JTAG_DR_CONFIG,saved_dr_config);
        swd_write32(JTAG_OPERATION,saved_operation);swd_write32(JTAG_ROUTE,saved_route);
    }
    DAP_Data = saved_dap;
    if(has_jtag) DAP_JTAG_ClockChanged();
}
int probe_target_transport(uint32_t port) {
    if(port>2) return -6;
    if(claimed) return -7;
    if(port==2 && !(swd_read32(0x4001004cU)&8U)) return -10;
    preferred_port=(uint8_t)port;
    return 0;
}
void probe_target_forget(void) { claimed = saved = link_ready = 0; }
int probe_target_claimed(void) { return claimed && probe_session_live(); }
static uint8_t command[4112] __attribute__((aligned(32)));
static uint8_t response[4112] __attribute__((aligned(32)));
static uint8_t scratch[4096] __attribute__((aligned(32)));
void probe_target_observe(uint32_t req, uint32_t data, uint8_t ack) {
    if (ack == 1 && (req & 15) == 8)
        select_shadow = data;
}
uint32_t probe_target_dp_select(void) {return select_shadow;}
static int xfer(uint32_t req, uint32_t *data) {
    unsigned retry = 64;
    uint8_t ack;
    if (!probe_session_live())
        return -4;
    do {
        ack = DAP_Data.debug_port==DAP_PORT_JTAG ? DAP_JTAG_MemTransfer(req,data) : SWD_Transfer(req, data);
    } while (ack == 2 && retry--);
    if (ack != 1)
        link_ready = 0;
    return ack == 1 ? 0 : -4;
}
static int write_reg(uint32_t req, uint32_t value) { return xfer(req, &value); }
static int read_ap(uint32_t req, uint32_t *value) {
    uint32_t dummy = 0;
    return xfer(req, &dummy) || xfer(14, value) ? -4 : 0;
}
static int clock_set(uint32_t hz) {
    command[0] = 0x11;
    memcpy(command + 1, &hz, 4);
    DAP_ExecuteCommand(command, response);
    return response[1] ? -1 : 0;
}
uint32_t probe_target_fclk(void) {
    uint32_t c = Xil_In32(SLCR_FPGA0_CLK_CTRL);
    uint32_t a = (c >> 8) & 63, b = (c >> 20) & 63;
    return a && b ? IO_PLL_HZ / a / b : 100000000;
}
int probe_target_claim(uint32_t hz) {
    uint32_t v = 0, i;
    if (!probe_session_live())
        return -4;
    if (claimed)
        return 0;
    uint32_t port=preferred_port ? preferred_port : (DAP_Data.debug_port==DAP_PORT_JTAG ? 2U : 1U);
    // Do not silently switch a connected debugger's wire protocol.
    if(DAP_Data.debug_port && DAP_Data.debug_port!=port) return -7;
    has_jtag=(swd_read32(0x4001004cU)&8U)!=0;
    if(port==2 && !has_jtag) return -10;
    if(port==2 && DAP_Data.debug_port==2 && !(swd_read32(JTAG_TIMING)&4U)) return -7;
    saved_dap = DAP_Data;
    saved_clock = Xil_In32(SLCR_FPGA0_CLK_CTRL);
    saved_cfg = swd_read32(SWD_CFG);
    if(has_jtag) {
        saved_route=swd_read32(JTAG_ROUTE);saved_ir_config=swd_read32(JTAG_IR_CONFIG);
        saved_dr_config=swd_read32(JTAG_DR_CONFIG);saved_operation=swd_read32(JTAG_OPERATION);
        saved_instruction=swd_read32(JTAG_CACHED_IR);saved_ir_valid=(swd_read32(JTAG_TIMING)>>2)&1U;
    }
    if (!DAP_Data.debug_port && link_ready && link_port==port) {
        DAP_Data.debug_port = (uint8_t)port;
        if(port==2) memcpy(&DAP_Data.jtag_dev,&cached_jtag.jtag_dev,sizeof(DAP_Data.jtag_dev));
    }
    if(has_jtag) swd_write32(JTAG_ROUTE,port==2 ? DAP_JTAG_RouteWord() : 2);
    if (DAP_Data.debug_port != port) {
        command[0] = 2;
        command[1] = (uint8_t)port;
        DAP_ExecuteCommand(command, response);
        if (response[1] != port || clock_set(hz ? hz : 50000000))
            goto init_failed;
        // Use the same 152-bit activation sequence as the verified host path.
        command[0] = 0x12;
        command[1] = port==2 ? 88 : 152;
        memset(command + 2, 255, 19);
        command[10] = port==2 ? 0x3c : 0x9e;
        command[11] = 0xe7;
        if(port==2) command[12]=0x1f;
        command[20] = 0;
        DAP_ExecuteCommand(command, response);
        if(port==2) {
            if(!DAP_Data.jtag_dev.count && DAP_JTAG_AutoConfigure()) goto init_failed;
            if(DAP_JTAG_Select(DAP_Data.jtag_dev.index)) goto init_failed;
            v=JTAG_ReadIDCode();
            if(v==0 || v==UINT32_MAX) goto init_failed;
        }
        if ((port==1 && xfer(2, &v)) || write_reg(0, 0x1e) || write_reg(4, port==2 ? 0x50000032 : 0x50000000))
            goto init_failed;
        for (i = 0; i < 128; i++) {
            if (xfer(6, &v))
                goto init_failed;
            if ((v & 0xa0000000) == 0xa0000000)
                break;
        }
        if (i == 128)
            goto init_failed;
    } else if (hz && clock_set(hz)) {
        restore_clock();
        return -1;
    }
    if(port==2 && DAP_JTAG_Select(DAP_Data.jtag_dev.index)) goto init_failed;
    link_ready = 1;
    link_port=(uint8_t)port;
    if(port==2) memcpy(&cached_jtag.jtag_dev,&DAP_Data.jtag_dev,sizeof(DAP_Data.jtag_dev));
    saved_select = select_shadow;
    saved = 0;
    if (write_reg(8, 0) || read_ap(3, &saved_csw) || read_ap(7, &saved_tar)) {
        write_reg(8, saved_select);
        if(has_jtag && saved_dap.debug_port==DAP_PORT_JTAG && saved_ir_valid) JTAG_IR(saved_instruction);
        restore_clock();
        return -4;
    }
    saved = 1;
    claimed = 1;
    if (write_reg(1, 0x23000052)) {
        probe_target_release();
        return -4;
    }
    return 0;
init_failed:
    restore_clock();
    link_ready = 0;
    return -2;
}
void probe_target_release(void) {
    if (!probe_session_live()) {
        probe_target_forget();
        return;
    }
    if (claimed && saved) {
        // Restore the debug host's cached AP context before its next command.
        write_reg(8, 0);
        write_reg(1, saved_csw);
        write_reg(5, saved_tar);
        write_reg(8, saved_select);
        if(has_jtag && saved_dap.debug_port==DAP_PORT_JTAG && saved_ir_valid) JTAG_IR(saved_instruction);
    }
    if (claimed)
        restore_clock();
    claimed = 0;
    saved = 0;
}
static int read_words(uint32_t addr, uint8_t *out, uint32_t count) {
    uint32_t n;
    // claim() leaves SELECT/CSW cached for the stream.  Only TAR changes at
    // an AP page boundary; repeating SELECT+CSW here was a major RTT cost.
    if (write_reg(5, addr))
        return -4;
    command[0] = 6;
    command[1] = DAP_Data.debug_port==DAP_PORT_JTAG ? DAP_Data.jtag_dev.index : 0;
    command[2] = (uint8_t)count;
    command[3] = (uint8_t)(count >> 8);
    command[4] = 15;
    DAP_ExecuteCommand(command, response);
    n = (uint32_t)response[1] | ((uint32_t)response[2] << 8);
    if (response[3] != 1 || n != count)
        return -4;
    memcpy(out, response + 4, count * 4);
    return 0;
}
int probe_target_read(uint32_t addr, uint8_t *out, uint32_t size) {
    if (size && addr > UINT32_MAX - (size - 1))
        return -6;
    while (size) {
        uint32_t base = addr & ~3U, off = addr & 3U;
        uint32_t n = 1024 - (base & 1023);
        if (size < n - off)
            n = (size + off + 3) & ~3U;
        if (read_words(base, scratch, n / 4))
            return -4;
        n -= off;
        if (n > size)
            n = size;
        memcpy(out, scratch + off, n);
        addr += n;
        out += n;
        size -= n;
    }
    return 0;
}
int probe_target_write_word(uint32_t addr, uint32_t value) {
    uint32_t dummy = 0;
    return (addr & 3) || write_reg(8, 0) || write_reg(1, 0x23000052) || write_reg(5, addr) ||
                   write_reg(13, value) || xfer(14, &dummy)
               ? -4
               : 0;
}
