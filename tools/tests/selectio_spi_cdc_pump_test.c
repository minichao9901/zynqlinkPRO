/* Exercise the production SPI-to-CDC pump with an event-driven AXI/USB model. */
#include "probe_target_platform.h"
#include <string.h>

#define DAP_PACKET_SIZE 512
#define DAP_OK 0
#define DAP_ERROR 0xffU
#define TIMESTAMP_GET() 0U
#define SWD_FEATURES 0x40010044U
#define JTAG_ROUTE 0x43c00020U
#define Xil_DCacheFlushRange(address, bytes) ((void)(address), (void)(bytes))
#include "../../firmware/xusbps_daplink_dma/selectio_aux.c"

enum { PL_RING_BYTES = 65536, SPI_BYTES_PER_POLL = 100, POLL_US = 8 };
static const uint32_t initial_clock = 0x00100a00, initial_route = 2;
static uint32_t clock_control, route, spi_configuration, input_tap, aux_flags;
static XTime clock_us, poll_clock_us, completion_time, blocked_until;
static XUsbPs device;
static uint8_t pl_ring[PL_RING_BYTES];
static uint32_t produced, acknowledged, delivered, in_flight_size;
static uint32_t peak_ddr, failed_submissions, submissions, short_packets, selected_divisor;
static unsigned dtr;

static uint8_t pattern(uint32_t offset)
{
    return (uint8_t)(offset ^ (offset >> 7) ^ (offset >> 19));
}

uint32_t Xil_In32(uintptr_t address)
{
    if (address >= AUX+0x10000U && address < AUX+0x20000U) {
        unsigned offset = (unsigned)(address - AUX - 0x10000U);
        uint32_t word;
        memcpy(&word, pl_ring+offset, sizeof word);
        return word;
    }
    switch (address) {
    case AUX: return 0x41555831U;
    case AUX+4: return aux_flags ? 1U : 0;
    case AUX+8: return aux_flags;
    case AUX+0x20: return acknowledged & 0x1ffffU;
    case AUX+0x24: return produced - acknowledged;
    case AUX+0x28:
    case AUX+0x2c: return 0;
    case AUX+0x34: return 0x53504952U;
    case SWD_FEATURES: return 0x200U;
    case JTAG_ROUTE: return route;
    case 0x80000004U: return 4;
    case 0xf8000100U: return 40U << 12;
    case 0xf800010cU: return 1;
    case SLCR_FPGA0_CLK_CTRL: return clock_control;
    default: assert(!"unexpected production register read"); return 0;
    }
}

void Xil_Out32(uintptr_t address, uint32_t value)
{
    switch (address) {
    case AUX+8: aux_flags = value; break;
    case AUX+0x0c:
    case AUX+0x10:
    case AUX+0x14:
    case AUX+0x28:
    case XSLCR_UNLOCK_ADDR:
    case SLCR_LOCK_ADDR: break;
    case AUX+0x18: spi_configuration = value; break;
    case AUX+0x20:
        assert(value <= produced-acknowledged);
        acknowledged += value;
        break;
    case AUX+0x24: produced = acknowledged = 0; break;
    case 0x8000000cU: input_tap = value; break;
    case JTAG_ROUTE: route = value; break;
    case SLCR_FPGA0_CLK_CTRL: clock_control = value; break;
    default: assert(!"unexpected production register write"); break;
    }
}

void XTime_GetTime(XTime *time) { *time = ++clock_us; }
u8 usbd_cdc_acm_get_dtr(void) { return (u8)dtr; }
unsigned selectio_mem_port(void) { return 0; }
int probe_stream_active(void) { return 0; }
int probe_target_claimed(void) { return 0; }
int probe_uses_legacy_cdc(void) { return 0; }
int selectio_live_active(void) { return 0; }
unsigned etm_ddr_owned(void) { return 0; }
uint32_t selectio_serial_hz(void) { return 200000000U; }
int selectio_clock_apply(unsigned divisor)
{
    selected_divisor = divisor;
    return 0;
}

void selectio_cdc_resume_rx(XUsbPs *usb) { (void)usb; assert(!"SPI receive has no deferred TX"); }

int XUsbPs_EpBufferSendWithZLT(XUsbPs *usb, u8 endpoint, u8 *data, u32 length)
{
    assert(usb == &device && endpoint == 3 && data == cdc_in_data);
    assert(!in_flight_size && length && length <= sizeof cdc_in_data);
    for (uint32_t i = 0; i < length; i++)
        assert(data[i] == pattern(delivered+i));
    submissions++;
    if (submissions % 97U == 0) {
        failed_submissions++;
        return XST_FAILURE;
    }
    if (length < sizeof cdc_in_data)
        short_packets++;
    in_flight_size = length;
    completion_time = clock_us + 160;
    return XST_SUCCESS;
}

static void complete_usb(void)
{
    if (!in_flight_size || clock_us < completion_time || clock_us < blocked_until)
        return;
    for (uint32_t i = 0; i < in_flight_size; i++)
        assert(cdc_in_data[i] == pattern(delivered+i));
    assert(selectio_cdc_complete(cdc_in_data));
    assert(!selectio_cdc_complete(cdc_in_data));
    delivered += in_flight_size;
    in_flight_size = 0;
}

static void tick(void)
{
    poll_clock_us += POLL_US;
    clock_us = poll_clock_us;
    complete_usb();
    selectio_aux_poll();
    selectio_cdc_poll(&device);
    if (rx_head-rx_tail > peak_ddr)
        peak_ddr = rx_head-rx_tail;
}

static void feed(uint32_t length)
{
    assert(length <= PL_RING_BYTES-(produced-acknowledged));
    for (uint32_t i = 0; i < length; i++, produced++)
        pl_ring[produced % PL_RING_BYTES] = pattern(produced);
}

static void arm(unsigned mode, unsigned tap)
{
    uint32_t status[8];
    assert(selectio_cdc_bind_spi(mode,tap) == 0);
    tick();
    selectio_cdc_status(status);
    assert(status[0]==CDC_SPI_RX && !status[1] && !status[3]);
    dtr = 1;
    tick();
    selectio_cdc_status(status);
    assert(status[1] && status[3] && !status[5] && !status[6] && !status[7]);
    assert(selected_divisor==32 && spi_configuration==mode && input_tap==tap && aux_flags==7);
    selectio_cdc_receive((const uint8_t *)"do not drive MOSI", 17);
    assert(cdc_in==cdc_out);
}

static void drain(uint32_t length)
{
    uint32_t status[8];
    for (unsigned cycles = 0; delivered != length && cycles < 100000; cycles++)
        tick();
    tick();
    assert(delivered==length && delivered==acknowledged && !in_flight_size);
    selectio_cdc_status(status);
    assert(status[1] && !status[5] && !status[6] && !status[7]);
}

static void close_com(void)
{
    dtr = 0;
    tick();
    assert(!cdc_owns && !aux_flags && route == initial_route && clock_control == initial_clock);
    assert(selectio_cdc_bind(0) == 0);
}

int main(void)
{
    const uint32_t bytes = 2U*SELECTIO_SERIAL_DDR_BYTES + 37U;
    clock_control = initial_clock;
    route = initial_route;
    selectio_cdc_reset();
    arm(0, 7);
    /* A delayed first completion lets most of the DDR ring fill while input
       keeps advancing, then the model resumes at the normal bulk service rate. */
    blocked_until = clock_us + 150000;
    while (produced < bytes) {
        uint32_t remaining = bytes-produced;
        feed(remaining < SPI_BYTES_PER_POLL ? remaining : SPI_BYTES_PER_POLL);
        tick();
    }
    drain(bytes);
    assert(peak_ddr > SELECTIO_SERIAL_DDR_BYTES-262144U);
    assert(failed_submissions > 0 && short_packets > 0);
    close_com();
    printf("SPI_CDC_PUMP_PASS bytes=%lu peak_ddr=%lu submit_retries=%lu short_packets=%lu\n",
           (unsigned long)bytes, (unsigned long)peak_ddr, (unsigned long)failed_submissions,
           (unsigned long)short_packets);

    delivered = 0;
    arm(3, 12);
    feed(3);
    drain(3);
    close_com();
    puts("SPI_CDC_PUMP_REARM_PASS mode=3 bytes=3");
    return 0;
}
