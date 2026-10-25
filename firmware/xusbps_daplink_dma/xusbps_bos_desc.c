/******************************************************************************
*
* DAPLink BOS and Microsoft OS 2.0 Descriptors Implementation
*
* Based on CherryUSB DAPLink implementation
*
******************************************************************************/

#include "xusbps_bos_desc.h"
#include <string.h>

/************************** Constant Definitions *****************************/

/* Microsoft OS 2.0 Descriptor Set Header */
#define MS_OS_20_SET_HEADER_DESCRIPTOR_SIZE	10
#define MS_OS_20_SUBSET_HEADER_CONFIGURATION_SIZE	8
#define MS_OS_20_SUBSET_HEADER_FUNCTION_SIZE	8
#define MS_OS_20_FEATURE_COMPATIBLE_ID_SIZE	20
#define MS_OS_20_FEATURE_REG_PROPERTY_SIZE	132

/************************** Variable Definitions *****************************/

/*
 * BOS (Binary Object Store) Descriptor
 * Required for USB 2.1+ devices to support Microsoft OS 2.0 descriptors
 */
const u8 USBD_BinaryObjectStoreDescriptor[] = {
	/* BOS Descriptor Header */
	0x05,				/* bLength */
	USB_DESC_TYPE_BOS,		/* bDescriptorType */
	0x21, 0x00,			/* wTotalLength: 33 bytes */
	0x01,				/* bNumDeviceCaps: 1 */

	/* Platform Capability Descriptor (Microsoft OS 2.0) */
	0x1C,				/* bLength: 28 bytes */
	USB_DESC_TYPE_DEVICE_CAPABILITY,	/* bDescriptorType */
	USB_DESC_TYPE_PLATFORM,		/* bDevCapabilityType: Platform */
	0x00,				/* bReserved */
	/* MS_OS_20_PLATFORM_CAPABILITY_ID: {D8DD60DF-4589-4CC7-9CD2-659D9E648A9F} */
	0xDF, 0x60, 0xDD, 0xD8,		/* UUID bytes 0-3 */
	0x89, 0x45,			/* UUID bytes 4-5 */
	0xC7, 0x4C,			/* UUID bytes 6-7 */
	0x9C, 0xD2,			/* UUID bytes 8-9 */
	0x65, 0x9D, 0x9E, 0x64, 0x8A, 0x9F,	/* UUID bytes 10-15 */
	0x00, 0x00, 0x03, 0x06,		/* dwWindowsVersion: Windows 8.1 (0x06030000) */
	0xB2, 0x00,			/* wMSOSDescriptorSetTotalLength: 178 bytes */
	MS_OS_20_VENDOR_CODE,		/* bMS_VendorCode: 0x20 */
	0x00				/* bAltEnumCode: 0 */
};

const u32 USBD_BinaryObjectStoreDescriptorLen = sizeof(USBD_BinaryObjectStoreDescriptor);

/*
 * Microsoft OS 2.0 Descriptor Set
 * This provides WinUSB compatibility for the DAP interface
 */
const u8 USBD_WinUSBDescriptorSetDescriptor[] = {
	/* Microsoft OS 2.0 Descriptor Set Header */
	0x0A, 0x00,			/* wLength: 10 bytes */
	0x00, 0x00,			/* wDescriptorType: MS_OS_20_SET_HEADER_DESCRIPTOR */
	0x00, 0x00, 0x03, 0x06,		/* dwWindowsVersion: Windows 8.1 (0x06030000) */
	0xB2, 0x00,			/* wTotalLength: 178 bytes */

	/* Microsoft OS 2.0 Configuration Subset Header */
	0x08, 0x00,			/* wLength: 8 bytes */
	0x01, 0x00,			/* wDescriptorType: MS_OS_20_SUBSET_HEADER_CONFIGURATION */
	0x00,				/* bConfigurationValue: 0 */
	0x00,				/* bReserved: 0 */
	0xA8, 0x00,			/* wTotalLength: 168 bytes (subset) */

	/* Microsoft OS 2.0 Function Subset Header (DAP Interface) */
	0x08, 0x00,			/* wLength: 8 bytes */
	0x02, 0x00,			/* wDescriptorType: MS_OS_20_SUBSET_HEADER_FUNCTION */
	0x00,				/* bFirstInterface: 0 (DAP interface) */
	0x00,				/* bReserved: 0 */
	0xA0, 0x00,			/* wSubsetLength: 160 bytes */

	/* Microsoft OS 2.0 Compatible ID Feature Descriptor */
	0x14, 0x00,			/* wLength: 20 bytes */
	0x03, 0x00,			/* wDescriptorType: MS_OS_20_FEATURE_COMPATIBLE_ID */
	'W', 'I', 'N', 'U', 'S', 'B', 0x00, 0x00,	/* CompatibleID: "WINUSB\0\0" */
	0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,	/* SubCompatibleID: empty */

	/* Microsoft OS 2.0 Registry Property Feature Descriptor */
	0x84, 0x00,			/* wLength: 132 bytes */
	0x04, 0x00,			/* wDescriptorType: MS_OS_20_FEATURE_REG_PROPERTY */
	0x07, 0x00,			/* wPropertyDataType: REG_MULTI_SZ */
	0x2A, 0x00,			/* wPropertyNameLength: 42 bytes */
	/* Property Name: "DeviceInterfaceGUID" (Unicode) */
	'D', 0x00, 'e', 0x00, 'v', 0x00, 'i', 0x00,
	'c', 0x00, 'e', 0x00, 'I', 0x00, 'n', 0x00,
	't', 0x00, 'e', 0x00, 'r', 0x00, 'f', 0x00,
	'a', 0x00, 'c', 0x00, 'e', 0x00, 'G', 0x00,
	'U', 0x00, 'I', 0x00, 'D', 0x00, 's', 0x00,
	0x00, 0x00,
	0x50, 0x00,			/* wPropertyDataLength: 80 bytes */
	/* Property Data: CMSIS-DAP GUID (Unicode) */
	'{', 0x00,
	'C', 0x00, 'D', 0x00, 'B', 0x00, '3', 0x00, 'B', 0x00, '5', 0x00, 'A', 0x00, 'D', 0x00,
	'-', 0x00, '2', 0x00, '9', 0x00, '3', 0x00, 'B', 0x00, '-', 0x00,
	'4', 0x00, '6', 0x00, '6', 0x00, '3', 0x00, '-', 0x00,
	'A', 0x00, 'A', 0x00, '3', 0x00, '6', 0x00, '-', 0x00,
	'1', 0x00, 'A', 0x00, 'A', 0x00, 'E', 0x00, '4', 0x00, '6', 0x00, '4', 0x00, '6', 0x00,
	'3', 0x00, '7', 0x00, '7', 0x00, '6', 0x00,
	'}', 0x00,
	0x00, 0x00, 0x00, 0x00
};

const u32 USBD_WinUSBDescriptorSetDescriptorLen = sizeof(USBD_WinUSBDescriptorSetDescriptor);

/************************** Function Definitions *****************************/

/*****************************************************************************/
/**
*
* This function returns the BOS descriptor for the device.
*
* @param	BufPtr is pointer to the buffer that is to be filled
*		with the descriptor.
* @param	BufLen is the size of the provided buffer.
*
* @return 	Length of the descriptor in the buffer on success.
*		0 on error.
*
******************************************************************************/
u32 XUsbPs_Ch9SetupBosDescReply(u8 *BufPtr, u32 BufLen)
{
	if (!BufPtr) {
		return 0;
	}

	if (BufLen < USBD_BinaryObjectStoreDescriptorLen) {
		return 0;
	}

	memcpy(BufPtr, USBD_BinaryObjectStoreDescriptor, USBD_BinaryObjectStoreDescriptorLen);

	return USBD_BinaryObjectStoreDescriptorLen;
}

/*****************************************************************************/
/**
*
* This function returns the Microsoft OS 2.0 Descriptor Set.
*
* @param	BufPtr is pointer to the buffer that is to be filled
*		with the descriptor.
* @param	BufLen is the size of the provided buffer.
*
* @return 	Length of the descriptor in the buffer on success.
*		0 on error.
*
******************************************************************************/
u32 XUsbPs_Ch9SetupMsOs20DescReply(u8 *BufPtr, u32 BufLen)
{
	if (!BufPtr) {
		return 0;
	}

	if (BufLen < USBD_WinUSBDescriptorSetDescriptorLen) {
		return 0;
	}

	memcpy(BufPtr, USBD_WinUSBDescriptorSetDescriptor, USBD_WinUSBDescriptorSetDescriptorLen);

	return USBD_WinUSBDescriptorSetDescriptorLen;
}
