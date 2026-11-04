#ifndef PROBE_STREAM_H
#define PROBE_STREAM_H
#include "xusbps.h"
#include <stdint.h>
#define PROBE_HID_INTERFACE 3
#define PROBE_HID_EP 6
#define PROBE_HSS_EP 7
extern const uint8_t probe_hid_report[];
extern const uint32_t probe_hid_report_size;
uint32_t probe_hid_descriptor(uint8_t *out, uint32_t capacity, int report);
void probe_usb_event(void *ref, u8 ep, u8 event, void *data);
void probe_usb_configured(XUsbPs *usb);
void probe_usb_reset(void);
int probe_session_live(void);
void probe_poll(XUsbPs *usb);
int probe_before_dap(void);
int probe_prepare_link_change(void);
void probe_after_dap(void);
void probe_target_observe(uint32_t request, uint32_t data, uint8_t ack);
uint32_t probe_target_dp_select(void);
int probe_target_claim(uint32_t hz);
int probe_target_claimed(void);
int probe_target_transport(uint32_t port); // 0 auto, 1 SWD, 2 JTAG
int probe_target_architecture(uint32_t riscv); // Web legacy target selector.
int probe_target_is_riscv(void);
int probe_target_release(void);
int probe_target_context_invalid(void);
void probe_target_invalidate(void);
int probe_target_recover(void); /* Explicit DAP_Connect only; never replays DRW. */
void probe_target_forget(void);
int probe_target_read(uint32_t addr, uint8_t *out, uint32_t size);
int probe_target_write_word(uint32_t addr, uint32_t value);
uint32_t probe_target_fclk(void);
#endif
