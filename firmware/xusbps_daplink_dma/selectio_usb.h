#ifndef SELECTIO_USB_H
#define SELECTIO_USB_H
#ifndef DAP_SELECTIO
#define DAP_SELECTIO 0
#endif
#if DAP_SELECTIO
#include "xusbps.h"
void selectio_usb_configured(XUsbPs *usb);
void selectio_usb_reset(void);
int selectio_usb_rx_available(void);
void selectio_usb_resume_rx(XUsbPs *usb);
void selectio_usb_poll(XUsbPs *usb);
void selectio_usb_event(void *ref,u8 ep,u8 event,void *data);
#endif
#endif
