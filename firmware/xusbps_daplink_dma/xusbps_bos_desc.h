/******************************************************************************
*
* DAPLink BOS and Microsoft OS 2.0 Descriptors
*
* Based on CherryUSB DAPLink implementation
*
******************************************************************************/

#ifndef XUSBPS_BOS_DESC_H
#define XUSBPS_BOS_DESC_H

#ifdef __cplusplus
extern "C" {
#endif

#include "xil_types.h"

/************************** Constant Definitions *****************************/

/* BOS Descriptor Type */
#define USB_DESC_TYPE_BOS		0x0F
#define USB_DESC_TYPE_DEVICE_CAPABILITY	0x10
#define USB_DESC_TYPE_PLATFORM		0x05

/* Microsoft OS 2.0 Descriptor Request Codes */
#define MS_OS_20_REQUEST_DESCRIPTOR	0x07

/* Vendor Code for Microsoft OS 2.0 Descriptors */
#define MS_OS_20_VENDOR_CODE		0x20

/************************** Type Definitions *********************************/

/* BOS Descriptor Structure */
typedef struct {
	u8  bLength;
	u8  bDescriptorType;
	u16 wTotalLength;
	u8  bNumDeviceCaps;
} __attribute__((packed)) USB_BOS_DESC;

/* Device Capability Descriptor Structure */
typedef struct {
	u8  bLength;
	u8  bDescriptorType;
	u8  bDevCapabilityType;
} __attribute__((packed)) USB_DEV_CAP_DESC;

/* Platform Capability Descriptor Structure */
typedef struct {
	u8  bLength;
	u8  bDescriptorType;
	u8  bDevCapabilityType;
	u8  bReserved;
	u8  PlatformCapabilityUUID[16];
	u32 dwWindowsVersion;
	u16 wMSOSDescriptorSetTotalLength;
	u8  bMS_VendorCode;
	u8  bAltEnumCode;
} __attribute__((packed)) USB_PLATFORM_CAP_DESC;

/************************** Variable Definitions *****************************/

/* Microsoft OS 2.0 Platform Capability GUID */
/* {D8DD60DF-4589-4CC7-9CD2-659D9E648A9F} */
#define MS_OS_20_GUID \
	{ 0xDF, 0x60, 0xDD, 0xD8, 0x89, 0x45, 0xC7, 0x4C, \
	  0x9C, 0xD2, 0x65, 0x9D, 0x9E, 0x64, 0x8A, 0x9F }

/* Windows 8.1 or later */
#define WINDOWS_8_1_VERSION	0x06030000

/* BOS Descriptor Data */
extern const u8 USBD_BinaryObjectStoreDescriptor[];
extern const u32 USBD_BinaryObjectStoreDescriptorLen;

/* Microsoft OS 2.0 Descriptor Set */
extern const u8 USBD_WinUSBDescriptorSetDescriptor[];
extern const u32 USBD_WinUSBDescriptorSetDescriptorLen;

/************************** Function Prototypes ******************************/

u32 XUsbPs_Ch9SetupBosDescReply(u8 *BufPtr, u32 BufLen);
u32 XUsbPs_Ch9SetupMsOs20DescReply(u8 *BufPtr, u32 BufLen);

#ifdef __cplusplus
}
#endif

#endif /* XUSBPS_BOS_DESC_H */
