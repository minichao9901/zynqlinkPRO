#ifndef ZYNQLINK_USB_PIPES_H
#define ZYNQLINK_USB_PIPES_H

#define USB_DAP_IN 1
#define USB_CDC_OUT 4
#if DAP_SELECTIO
#define USB_DAP_OUT 1
#define USB_SWO_IN 2
#define USB_CDC_NOTIFY 3
#define USB_CDC_IN 4
#define USB_NATIVE_INTERFACE 3
#define USB_NATIVE_CONTROL 5
#define USB_NATIVE_MEMORY 6
#define USB_NATIVE_RTT 7
#define USB_NATIVE_SCOPE 8
#define USB_ETM_IN 9
#define USB_NATIVE_SPI 10
#define USB_ENDPOINT_COUNT 11
#else
#define USB_DAP_OUT 2
#define USB_CDC_NOTIFY 5
#define USB_CDC_IN 3
#define USB_ETM_IN 2
#define USB_ENDPOINT_COUNT 8
#endif

#define USB_IN_ADDRESS(ep) (0x80U | (ep))
#endif
