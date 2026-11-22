/* Exercise the production CDC endpoint callback with controller return faults. */
#include "probe_host_platform.h"

enum { RECEIVE_OK, RECEIVE_NO_BUFFER };
static XUsbPs device;
static u8 payload[4096];
static unsigned receive_result, receive_length, aux_bound, ep3_claimed;
static unsigned invalidations, invalidation_length, aux_calls, legacy_calls, releases, probe_events;

static void invalidate(UINTPTR address, u32 length)
{
    invalidations++;
    assert(receive_result == RECEIVE_OK);
    assert(address == (UINTPTR)payload);
    invalidation_length = length;
}

#define Xil_DCacheInvalidateRange(address, length) invalidate((UINTPTR)(address), (length))
int selectio_cdc_receiving(void) { return aux_bound; }

int XUsbPs_EpBufferReceive(XUsbPs *usb, u8 ep, u8 **data, u32 *length, u32 *handle)
{
    assert(usb == &device && ep == 4);
    if (receive_result != RECEIVE_OK) // SDK leaves all outputs unset on XST_USB_NO_BUF.
        return XST_FAILURE;
    *data = payload;
    *length = receive_length;
    *handle = 42;
    return XST_SUCCESS;
}

void selectio_cdc_receive(const uint8_t *data, unsigned length)
{
    assert(receive_result == RECEIVE_OK && aux_bound);
    assert(data == payload && length == receive_length && invalidations > releases);
    aux_calls++;
}

void usbd_cdc_acm_bulk_out(XUsbPs *usb, u8 ep, u32 length, u8 *data)
{
    assert(receive_result == RECEIVE_OK && !aux_bound && usb == &device && ep == 4);
    assert(data == payload && length == receive_length && invalidations > releases);
    legacy_calls++;
}

void XUsbPs_EpBufferRelease(u32 handle)
{
    assert(receive_result == RECEIVE_OK && handle == 42);
    assert(releases + 1 == aux_calls + legacy_calls);
    releases++;
}

int selectio_cdc_complete(void *data)
{
    assert(data == payload);
    return ep3_claimed;
}

void probe_usb_event(void *reference, u8 ep, u8 event, void *data)
{
    assert(reference == &device && ep == 3 && event == XUSBPS_EP_EVENT_DATA_TX);
    assert(data == payload && !ep3_claimed);
    probe_events++;
}

#include "cdc_event_under_test.h"

int main(void)
{
    const unsigned lengths[] = {0, 1, 31, 32, 33, 4096};
    const unsigned cases = sizeof(lengths) / sizeof(lengths[0]);
    for (aux_bound = 0; aux_bound <= 1; aux_bound++) {
        receive_result = RECEIVE_NO_BUFFER;
        unsigned before = invalidations;
        XUsbPs_EpCdcEventHandler(&device, 4, XUSBPS_EP_EVENT_DATA_RX, NULL);
        assert(invalidations == before && releases == before);

        receive_result = RECEIVE_OK;
        for (unsigned i = 0; i < cases; i++) {
            receive_length = lengths[i];
            XUsbPs_EpCdcEventHandler(&device, 4, XUSBPS_EP_EVENT_DATA_RX, NULL);
            assert(invalidation_length == ((receive_length + 31U) & ~31U));
        }
    }
    assert(aux_calls == cases && legacy_calls == cases && releases == 2*cases);

    ep3_claimed = 1;
    XUsbPs_EpCdcEventHandler(&device, 3, XUSBPS_EP_EVENT_DATA_TX, payload);
    assert(probe_events == 0);
    ep3_claimed = 0;
    XUsbPs_EpCdcEventHandler(&device, 3, XUSBPS_EP_EVENT_DATA_TX, payload);
    assert(probe_events == 1);
    puts("CDC_EVENT_PASS empty_descriptor=2 RX_lengths=12 TX_routes=2");
    return 0;
}
