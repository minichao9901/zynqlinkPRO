#ifndef ZYNQLINK_ETM_STREAM_H
#define ZYNQLINK_ETM_STREAM_H
#include "xusbps.h"
#include <stdint.h>
#define ETM_BULKIN_EP 2
uint32_t etm_reference_init(void);
void etm_reference_snapshot(uint32_t reply[4]);
void etm_usb_configured(XUsbPs *usb);
void etm_usb_reset(void);
void etm_usb_event(void *ref,u8 ep,u8 event,void *data);
void etm_poll(XUsbPs *usb);
void etm_control(uint16_t action,uint32_t reply[8]);
#endif
