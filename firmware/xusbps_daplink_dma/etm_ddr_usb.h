#ifndef ZYNQLINK_ETM_DDR_USB_H
#define ZYNQLINK_ETM_DDR_USB_H
#include "xusbps.h"
#include <stdint.h>
#define ETM_DDR_REPLY_WORDS 44U
uint32_t etm_ddr_init(void);
unsigned etm_ddr_available(void);
unsigned etm_ddr_owned(void);
void etm_ddr_usb_reset(void);
void etm_ddr_usb_configured(XUsbPs *usb);
unsigned etm_ddr_usb_event(u8 ep,u8 event,void *data);
unsigned etm_ddr_poll(XUsbPs *usb);
void etm_ddr_snapshot(uint32_t reply[ETM_DDR_REPLY_WORDS]);
unsigned etm_ddr_command(unsigned op,const uint32_t args[6],uint32_t reply[ETM_DDR_REPLY_WORDS]);
/* Shared EP2 ownership; main-context only, never resets the host data toggle. */
unsigned etm_stream_claim_ddr(XUsbPs *usb);
#endif
