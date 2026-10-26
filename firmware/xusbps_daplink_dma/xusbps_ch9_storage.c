/******************************************************************************
*
* Copyright (C) 2010 - 2015 Xilinx, Inc.  All rights reserved.
*
* Permission is hereby granted, free of charge, to any person obtaining a copy
* of this software and associated documentation files (the "Software"), to deal
* in the Software without restriction, including without limitation the rights
* to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
* copies of the Software, and to permit persons to whom the Software is
* furnished to do so, subject to the following conditions:
*
* The above copyright notice and this permission notice shall be included in
* all copies or substantial portions of the Software.
*
* THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
* IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
* FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
* XILINX  BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
* WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF
* OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
* SOFTWARE.
*
* Except as contained in this notice, the name of the Xilinx shall not be used
* in advertising or otherwise to promote the sale, use or other dealings in
* this Software without prior written authorization from Xilinx.
*
******************************************************************************/
/*****************************************************************************/
/**
 * @file xusbps_ch9_storage.c
 *
 * This file contains the implementation of DAPLink USB descriptors
 * based on CherryUSB DAPLink implementation.
 *
 ******************************************************************************/

/***************************** Include Files *********************************/

#include <string.h>
#include "probe_stream.h"

#include "xparameters.h"	/* XPAR parameters */
#include "xusbps_endpoint.h"
#include "xusbps.h"		/* USB controller driver */

#include "xusbps_ch9.h"
#include "xusbps_ch9_storage.h"

/************************** Constant Definitions *****************************/

/***************** Macros (Inline Functions) Definitions *********************/

/**************************** Type Definitions *******************************/

#ifdef __ICCARM__
#pragma pack(push, 1)
#endif
typedef struct {
	u8  bLength;
	u8  bDescriptorType;
	u16 bcdUSB;
	u8  bDeviceClass;
	u8  bDeviceSubClass;
	u8  bDeviceProtocol;
	u8  bMaxPacketSize0;
	u16 idVendor;
	u16 idProduct;
	u16 bcdDevice;
	u8  iManufacturer;
	u8  iProduct;
	u8  iSerialNumber;
	u8  bNumConfigurations;
#ifdef __ICCARM__
}USB_STD_DEV_DESC;
#pragma pack(pop)
#else
}__attribute__((__packed__))USB_STD_DEV_DESC;
#endif

#ifdef __ICCARM__
#pragma pack(push, 1)
#endif
typedef struct {
	u8  bLength;
	u8  bDescriptorType;
	u16 wTotalLength;
	u8  bNumInterfaces;
	u8  bConfigurationValue;
	u8  iConfiguration;
	u8  bmAttributes;
	u8  bMaxPower;
#ifdef __ICCARM__
}USB_STD_CFG_DESC;
#pragma pack(pop)
#else
}__attribute__((__packed__))USB_STD_CFG_DESC;
#endif

#ifdef __ICCARM__
#pragma pack(push, 1)
#endif
typedef struct {
	u8  bLength;
	u8  bDescriptorType;
	u8  bInterfaceNumber;
	u8  bAlternateSetting;
	u8  bNumEndPoints;
	u8  bInterfaceClass;
	u8  bInterfaceSubClass;
	u8  bInterfaceProtocol;
	u8  iInterface;
#ifdef __ICCARM__
}USB_STD_IF_DESC;
#pragma pack(pop)
#else
}__attribute__((__packed__))USB_STD_IF_DESC;
#endif

#ifdef __ICCARM__
#pragma pack(push, 1)
#endif
typedef struct {
	u8  bLength;
	u8  bDescriptorType;
	u8  bEndpointAddress;
	u8  bmAttributes;
	u16 wMaxPacketSize;
	u8  bInterval;
#ifdef __ICCARM__
}USB_STD_EP_DESC;
#pragma pack(pop)
#else
}__attribute__((__packed__))USB_STD_EP_DESC;
#endif

#ifdef __ICCARM__
#pragma pack(push, 1)
#endif
typedef struct {
	u8  bLength;
	u8  bDescriptorType;
	u16 wLANGID[1];
#ifdef __ICCARM__
}USB_STD_STRING_DESC;
#pragma pack(pop)
#else
}__attribute__((__packed__))USB_STD_STRING_DESC;
#endif

#ifdef __ICCARM__
#pragma pack(push, 1)
#endif
typedef struct {
	u8  bLength;
	u8  bDescriptorType;
	u8  bFirstInterface;
	u8  bInterfaceCount;
	u8  bFunctionClass;
	u8  bFunctionSubClass;
	u8  bFunctionProtocol;
	u8  iFunction;
#ifdef __ICCARM__
}USB_STD_IAD_DESC;
#pragma pack(pop)
#else
}__attribute__((__packed__))USB_STD_IAD_DESC;
#endif

#ifdef __ICCARM__
#pragma pack(push, 1)
#endif
typedef struct {
	u8  bLength;
	u8  bDescriptorType;
	u8  bDescriptorSubtype;
	u16 bcdCDC;
#ifdef __ICCARM__
}CDC_HEADER_FUNC_DESC;
#pragma pack(pop)
#else
}__attribute__((__packed__))CDC_HEADER_FUNC_DESC;
#endif

#ifdef __ICCARM__
#pragma pack(push, 1)
#endif
typedef struct {
	u8  bLength;
	u8  bDescriptorType;
	u8  bDescriptorSubtype;
	u8  bmCapabilities;
	u8  bDataInterface;
#ifdef __ICCARM__
}CDC_CALL_MGMT_FUNC_DESC;
#pragma pack(pop)
#else
}__attribute__((__packed__))CDC_CALL_MGMT_FUNC_DESC;
#endif

#ifdef __ICCARM__
#pragma pack(push, 1)
#endif
typedef struct {
	u8  bLength;
	u8  bDescriptorType;
	u8  bDescriptorSubtype;
	u8  bmCapabilities;
#ifdef __ICCARM__
}CDC_ACM_FUNC_DESC;
#pragma pack(pop)
#else
}__attribute__((__packed__))CDC_ACM_FUNC_DESC;
#endif

#ifdef __ICCARM__
#pragma pack(push, 1)
#endif
typedef struct {
	u8  bLength;
	u8  bDescriptorType;
	u8  bDescriptorSubtype;
	u8  bMasterInterface;
	u8  bSlaveInterface0;
#ifdef __ICCARM__
}CDC_UNION_FUNC_DESC;
#pragma pack(pop)
#else
}__attribute__((__packed__))CDC_UNION_FUNC_DESC;
#endif

/************************** Function Prototypes ******************************/

/************************** Variable Definitions *****************************/

#define USB_ENDPOINT0_MAXP		0x40

/* DAPLink Endpoint Definitions */
#define DAP_BULKIN_EP			1	/* EP 1 IN for DAP */
#define DAP_BULKOUT_EP			2	/* EP 2 OUT for DAP */

/* CDC ACM Endpoint Definitions */
#define CDC_INT_EP			5	/* EP 5 IN for CDC notifications */
#define CDC_BULKIN_EP			3	/* EP 3 IN for CDC data */
#define CDC_BULKOUT_EP			4	/* EP 4 OUT for CDC data */

#define USB_DEVICE_DESC			0x01
#define USB_CONFIG_DESC			0x02
#define USB_STRING_DESC			0x03
#define USB_INTERFACE_CFG_DESC		0x04
#define USB_ENDPOINT_CFG_DESC		0x05

#define USB_DESC_TYPE_IAD		0x0B
#define USB_DESC_TYPE_CS_INTERFACE	0x24
#define USB_DESC_TYPE_CS_ENDPOINT	0x25

#define USB_CLASS_VENDOR		0xFF
#define USB_CLASS_CDC			0x02
#define USB_CLASS_CDC_DATA		0x0A
#define USB_CLASS_MISC			0xEF
#define USB_SUBCLASS_COMMON		0x02
#define USB_PROTOCOL_IAD		0x01

#define CDC_HEADER_DESC			0x00
#define CDC_CALL_MANAGEMENT_DESC	0x01
#define CDC_ACM_DESC			0x02
#define CDC_UNION_DESC			0x06

/* DAPLink VID/PID - Using CMSIS-DAP standard values */
#define DAPLINK_VID			0x0D28
#define DAPLINK_PID			0x0204

/*****************************************************************************/
/**
*
* This function returns the device descriptor for the DAPLink device.
*
* @param	BufPtr is pointer to the buffer that is to be filled
*		with the descriptor.
* @param	BufLen is the size of the provided buffer.
*
* @return 	Length of the descriptor in the buffer on success.
*		0 on error.
*
******************************************************************************/
u32 XUsbPs_Ch9SetupDevDescReply(u8 *BufPtr, u32 BufLen)
{
	/* DAPLink Device Descriptor */
	USB_STD_DEV_DESC deviceDesc = {
		sizeof(USB_STD_DEV_DESC),	/* bLength */
		USB_DEVICE_DESC,		/* bDescriptorType */
		be2les(0x0210),			/* bcdUSB 2.10 (for BOS support) */
		USB_CLASS_MISC,			/* bDeviceClass: 0xEF (Misc) */
		USB_SUBCLASS_COMMON,		/* bDeviceSubClass: 0x02 (Common) */
		USB_PROTOCOL_IAD,		/* bDeviceProtocol: 0x01 (IAD) */
		USB_ENDPOINT0_MAXP,		/* bMaxPacketSize0: 64 */
		be2les(DAPLINK_VID),		/* idVendor: 0x0D28 (ARM) */
		be2les(DAPLINK_PID),		/* idProduct: 0x0204 (CMSIS-DAP) */
		be2les(0x0101),			/* bcdDevice: 1.00 */
		0x01,				/* iManufacturer */
		0x02,				/* iProduct */
		0x03,				/* iSerialNumber */
		0x01				/* bNumConfigurations: 1 */
	};

	if (!BufPtr) {
		return 0;
	}

	if (BufLen < sizeof(USB_STD_DEV_DESC)) {
		return 0;
	}

	memcpy(BufPtr, &deviceDesc, sizeof(USB_STD_DEV_DESC));

	return sizeof(USB_STD_DEV_DESC);
}

/*****************************************************************************/
/**
*
* This function returns the configuration descriptor for the DAPLink device.
* DAPLink Configuration: DAP Interface + CDC ACM Interface
*
* @param	BufPtr is the pointer to the buffer that is to be filled with
*		the descriptor.
* @param	BufLen is the size of the provided buffer.
*
* @return 	Length of the descriptor in the buffer on success.
*		0 on error.
*
******************************************************************************/
u32 XUsbPs_Ch9SetupCfgDescReply(u8 *BufPtr, u32 BufLen)
{
	/* Configuration descriptor structure for DAPLink
	 * Layout:
	 * - Configuration Descriptor
	 * - DAP Interface Descriptor
	 * - DAP Endpoint Descriptors (Bulk IN EP1, Bulk OUT EP2)
	 * - IAD for CDC
	 * - CDC Communication Interface Descriptor
	 * - CDC Functional Descriptors
	 * - CDC Interrupt Endpoint Descriptor (EP5)
	 * - CDC Data Interface Descriptor
	 * - CDC Bulk Endpoint Descriptors (OUT EP4, IN EP3)
	 */

	u8 configDesc[256];
	u32 offset = 0;
	u16 wTotalLength;

	/* Configuration Descriptor */
	configDesc[offset++] = 0x09;		/* bLength */
	configDesc[offset++] = USB_CONFIG_DESC;	/* bDescriptorType */
	/* wTotalLength - will be updated later */
	u16 totalLengthOffset = offset;
	configDesc[offset++] = 0x00;
	configDesc[offset++] = 0x00;
	configDesc[offset++] = 0x04;		/* bNumInterfaces: 4 */
	configDesc[offset++] = 0x01;		/* bConfigurationValue */
	configDesc[offset++] = 0x00;		/* iConfiguration */
	configDesc[offset++] = 0x80;		/* bmAttributes: Bus powered */
	configDesc[offset++] = 0xFA;		/* bMaxPower: 500mA */

	/* ==================== DAP Interface (Interface 0) ==================== */
	/* Interface Descriptor */
	configDesc[offset++] = 0x09;		/* bLength */
	configDesc[offset++] = USB_INTERFACE_CFG_DESC;	/* bDescriptorType */
	configDesc[offset++] = 0x00;		/* bInterfaceNumber: 0 */
	configDesc[offset++] = 0x00;		/* bAlternateSetting */
	configDesc[offset++] = 0x03;		/* DAP IN/OUT + HSS IN */
	configDesc[offset++] = USB_CLASS_VENDOR;	/* bInterfaceClass: Vendor Specific */
	configDesc[offset++] = 0x00;		/* bInterfaceSubClass */
	configDesc[offset++] = 0x00;		/* bInterfaceProtocol */
	configDesc[offset++] = 0x02;		/* iInterface */

	/* DAP Bulk OUT Endpoint Descriptor (EP 2 OUT: 0x02) */
	configDesc[offset++] = 0x07;		/* bLength */
	configDesc[offset++] = USB_ENDPOINT_CFG_DESC;	/* bDescriptorType */
	configDesc[offset++] = 0x02;		/* bEndpointAddress: OUT EP2 */
	configDesc[offset++] = 0x02;		/* bmAttributes: Bulk */
	configDesc[offset++] = 0x00;		/* wMaxPacketSize LSB: 512 */
	configDesc[offset++] = 0x02;		/* wMaxPacketSize MSB: 512 */
	configDesc[offset++] = 0x00;		/* bInterval */

	/* DAP Bulk IN Endpoint Descriptor (EP 1 IN: 0x81) */
	configDesc[offset++] = 0x07;		/* bLength */
	configDesc[offset++] = USB_ENDPOINT_CFG_DESC;	/* bDescriptorType */
	configDesc[offset++] = 0x81;		/* bEndpointAddress: IN EP1 */
	configDesc[offset++] = 0x02;		/* bmAttributes: Bulk */
	configDesc[offset++] = 0x00;		/* wMaxPacketSize LSB: 512 */
	configDesc[offset++] = 0x02;		/* wMaxPacketSize MSB: 512 */
	configDesc[offset++] = 0x00;		/* bInterval */

    { const u8 hss[] = {7,5,0x87,2,0,2,0};
      memcpy(configDesc+offset,hss,sizeof(hss)); offset+=sizeof(hss); }

	/* ==================== CDC ACM Interface (Interfaces 1 & 2) ==================== */
	/* IAD (Interface Association Descriptor) for CDC */
	configDesc[offset++] = 0x08;		/* bLength */
	configDesc[offset++] = USB_DESC_TYPE_IAD;	/* bDescriptorType */
	configDesc[offset++] = 0x01;		/* bFirstInterface: 1 */
	configDesc[offset++] = 0x02;		/* bInterfaceCount: 2 */
	configDesc[offset++] = USB_CLASS_CDC;	/* bFunctionClass: CDC */
	configDesc[offset++] = 0x02;		/* bFunctionSubClass: ACM */
	configDesc[offset++] = 0x01;		/* bFunctionProtocol: AT commands */
	configDesc[offset++] = 0x00;		/* iFunction */

	/* CDC Communication Interface Descriptor (Interface 1) */
	configDesc[offset++] = 0x09;		/* bLength */
	configDesc[offset++] = USB_INTERFACE_CFG_DESC;	/* bDescriptorType */
	configDesc[offset++] = 0x01;		/* bInterfaceNumber: 1 */
	configDesc[offset++] = 0x00;		/* bAlternateSetting */
	configDesc[offset++] = 0x01;		/* bNumEndpoints: 1 (Interrupt IN) */
	configDesc[offset++] = USB_CLASS_CDC;	/* bInterfaceClass: CDC */
	configDesc[offset++] = 0x02;		/* bInterfaceSubClass: ACM */
	configDesc[offset++] = 0x01;		/* bInterfaceProtocol: AT commands */
	configDesc[offset++] = 0x00;		/* iInterface */

	/* CDC Header Functional Descriptor */
	configDesc[offset++] = 0x05;		/* bLength */
	configDesc[offset++] = USB_DESC_TYPE_CS_INTERFACE;	/* bDescriptorType */
	configDesc[offset++] = CDC_HEADER_DESC;	/* bDescriptorSubtype */
	configDesc[offset++] = 0x10;		/* bcdCDC LSB: 1.10 */
	configDesc[offset++] = 0x01;		/* bcdCDC MSB */

	/* CDC Call Management Functional Descriptor */
	configDesc[offset++] = 0x05;		/* bLength */
	configDesc[offset++] = USB_DESC_TYPE_CS_INTERFACE;	/* bDescriptorType */
	configDesc[offset++] = CDC_CALL_MANAGEMENT_DESC;	/* bDescriptorSubtype */
	configDesc[offset++] = 0x00;		/* bmCapabilities */
	configDesc[offset++] = 0x02;		/* bDataInterface: Interface 2 */

	/* CDC ACM Functional Descriptor */
	configDesc[offset++] = 0x04;		/* bLength */
	configDesc[offset++] = USB_DESC_TYPE_CS_INTERFACE;	/* bDescriptorType */
	configDesc[offset++] = CDC_ACM_DESC;	/* bDescriptorSubtype */
	configDesc[offset++] = 0x02;		/* bmCapabilities: DTR */

	/* CDC Union Functional Descriptor */
	configDesc[offset++] = 0x05;		/* bLength */
	configDesc[offset++] = USB_DESC_TYPE_CS_INTERFACE;	/* bDescriptorType */
	configDesc[offset++] = CDC_UNION_DESC;	/* bDescriptorSubtype */
	configDesc[offset++] = 0x01;		/* bMasterInterface: 1 */
	configDesc[offset++] = 0x02;		/* bSlaveInterface0: 2 */

	/* CDC Interrupt IN Endpoint Descriptor (EP 4 IN: 0x84) */
	configDesc[offset++] = 0x07;		/* bLength */
	configDesc[offset++] = USB_ENDPOINT_CFG_DESC;	/* bDescriptorType */
	configDesc[offset++] = 0x85;		/* bEndpointAddress: IN EP5 */
	configDesc[offset++] = 0x03;		/* bmAttributes: Interrupt */
	configDesc[offset++] = 0x40;		/* wMaxPacketSize LSB: 64 */
	configDesc[offset++] = 0x00;		/* wMaxPacketSize MSB */
	configDesc[offset++] = 0x0A;		/* bInterval: 10ms */

	/* CDC Data Interface Descriptor (Interface 2) */
	configDesc[offset++] = 0x09;		/* bLength */
	configDesc[offset++] = USB_INTERFACE_CFG_DESC;	/* bDescriptorType */
	configDesc[offset++] = 0x02;		/* bInterfaceNumber: 2 */
	configDesc[offset++] = 0x00;		/* bAlternateSetting */
	configDesc[offset++] = 0x02;		/* bNumEndpoints: 2 (Bulk IN/OUT) */
	configDesc[offset++] = USB_CLASS_CDC_DATA;	/* bInterfaceClass: CDC Data */
	configDesc[offset++] = 0x00;		/* bInterfaceSubClass */
	configDesc[offset++] = 0x00;		/* bInterfaceProtocol */
	configDesc[offset++] = 0x00;		/* iInterface */

	/* CDC Bulk OUT Endpoint Descriptor (EP 4 OUT: 0x04) */
	configDesc[offset++] = 0x07;		/* bLength */
	configDesc[offset++] = USB_ENDPOINT_CFG_DESC;	/* bDescriptorType */
	configDesc[offset++] = 0x04;		/* bEndpointAddress: OUT EP4 */
	configDesc[offset++] = 0x02;		/* bmAttributes: Bulk */
	configDesc[offset++] = 0x00;		/* wMaxPacketSize LSB: 512 */
	configDesc[offset++] = 0x02;		/* wMaxPacketSize MSB: 512 */
	configDesc[offset++] = 0x00;		/* bInterval */

	/* CDC Bulk IN Endpoint Descriptor (EP 3 IN: 0x83) */
	configDesc[offset++] = 0x07;		/* bLength */
	configDesc[offset++] = USB_ENDPOINT_CFG_DESC;	/* bDescriptorType */
	configDesc[offset++] = 0x83;		/* bEndpointAddress: IN EP3 */
	configDesc[offset++] = 0x02;		/* bmAttributes: Bulk */
	configDesc[offset++] = 0x00;		/* wMaxPacketSize LSB: 512 */
	configDesc[offset++] = 0x02;		/* wMaxPacketSize MSB: 512 */
	configDesc[offset++] = 0x00;		/* bInterval */

    { const u8 hid[] = {
        9,4,PROBE_HID_INTERFACE,0,2,3,0,0,4,
        9,0x21,0x11,1,0,1,0x22,0,0,
        7,5,0x86,3,64,0,4,
        7,5,0x06,3,64,0,4
      };
      memcpy(configDesc+offset,hid,sizeof(hid));
      configDesc[offset+16]=(u8)probe_hid_report_size;
      configDesc[offset+17]=(u8)(probe_hid_report_size>>8);
      offset+=sizeof(hid); }

	/* Update wTotalLength */
	wTotalLength = offset;
	configDesc[totalLengthOffset] = wTotalLength & 0xFF;
	configDesc[totalLengthOffset + 1] = (wTotalLength >> 8) & 0xFF;

	if (!BufPtr) {
		return 0;
	}

	if (BufLen < offset) {
		return 0;
	}

	memcpy(BufPtr, configDesc, offset);

	return offset;
}

/*****************************************************************************/
/**
*
* This function returns a string descriptor for the given index.
*
* @param	BufPtr is a  pointer to the buffer that is to be filled with
*		the descriptor.
* @param	BufLen is the size of the provided buffer.
* @param	Index is the index of the string for which the descriptor
*		is requested.
*
* @return 	Length of the descriptor in the buffer on success.
*		0 on error.
*
******************************************************************************/
u32 XUsbPs_Ch9SetupStrDescReply(u8 *BufPtr, u32 BufLen, u8 Index)
{
	int i;

	/* DAPLink String Descriptors */
	static char *StringList[] = {
		"UNUSED",
		"CherryUSB",            /* iManufacturer */
		"CMSIS-DAP",            /* iProduct */
		"12345678",             /* iSerialNumber */
        "ZynqLink probe control",
	};
	char *String;
	u32 StringLen;
	u32 DescLen;
	u8 TmpBuf[128];

	USB_STD_STRING_DESC *StringDesc;

	if (!BufPtr) {
		return 0;
	}

	if (Index >= sizeof(StringList) / sizeof(char *)) {
		return 0;
	}

	String = StringList[Index];
	StringLen = strlen(String);

	StringDesc = (USB_STD_STRING_DESC *) TmpBuf;

	/* Index 0 is special - Language ID */
	if (0 == Index) {
		StringDesc->bLength = 4;
		StringDesc->bDescriptorType = USB_STRING_DESC;
		StringDesc->wLANGID[0] = be2les(0x0409); /* English (US) */
	}
	/* All other strings */
	else {
		StringDesc->bLength = StringLen * 2 + 2;
		StringDesc->bDescriptorType = USB_STRING_DESC;

		for (i = 0; i < StringLen; i++) {
			StringDesc->wLANGID[i] = be2les((u16) String[i]);
		}
	}
	DescLen = StringDesc->bLength;

	/* Check if the provided buffer is big enough to hold the descriptor. */
	if (DescLen > BufLen) {
		return 0;
	}

	memcpy(BufPtr, StringDesc, DescLen);

	return DescLen;
}

/*****************************************************************************/
/**
* This function handles a "set configuration" request.
*
* @param	InstancePtr is a pointer to XUsbPs instance of the controller.
* @param	ConfigIdx is the Index of the desired configuration.
*
* @return	None
*
******************************************************************************/
int XUsbPs_DapResetEndpoints(XUsbPs *InstancePtr)
{
    u32 flush = (1U << DAP_BULKOUT_EP) | (1U << (16 + DAP_BULKIN_EP));
    u32 timeout = 1000000U;
    u32 td;
    int engine_status;
    XUsbPs_EpIn *in = &InstancePtr->DeviceConfig.Ep[DAP_BULKIN_EP].In;
    extern int chry_dap_usb_session_reset(void);

    XUsbPs_EpDisable(InstancePtr, DAP_BULKOUT_EP, XUSBPS_EP_DIRECTION_OUT);
    XUsbPs_EpDisable(InstancePtr, DAP_BULKIN_EP, XUSBPS_EP_DIRECTION_IN);
    XUsbPs_WriteReg(InstancePtr->Config.BaseAddress, XUSBPS_EPFLUSH_OFFSET, flush);
    while ((XUsbPs_ReadReg(InstancePtr->Config.BaseAddress,
                          XUSBPS_EPFLUSH_OFFSET) & flush) && --timeout) {}
    if (!timeout) return XST_FAILURE;
    XUsbPs_WriteReg(InstancePtr->Config.BaseAddress, XUSBPS_EPCOMPL_OFFSET, flush);

    /* Flush stops DMA, but does not clear descriptor ACTIVE tokens in DDR.
     * SDK 2018.3 ReconfigureEp only restores IN links/termination. A transfer
     * abandoned by the host would therefore make the next send fail forever.
     * Clear tokens after DMA is quiescent, before rebuilding either ring. */
    for (td = 0; td < InstancePtr->DeviceConfig.EpCfg[DAP_BULKIN_EP].In.NumBufs; ++td) {
        XUsbPs_dTDInvalidateCache(&in->dTDs[td]);
        XUsbPs_WritedTD(&in->dTDs[td], XUSBPS_dTDTOKEN, 0U);
        XUsbPs_dTDFlushCache(&in->dTDs[td]);
    }
    if (XUsbPs_ReconfigureEp(InstancePtr, &InstancePtr->DeviceConfig,
            DAP_BULKOUT_EP, XUSBPS_EP_DIRECTION_OUT, 0) != XST_SUCCESS ||
        XUsbPs_ReconfigureEp(InstancePtr, &InstancePtr->DeviceConfig,
            DAP_BULKIN_EP, XUSBPS_EP_DIRECTION_IN, 0) != XST_SUCCESS)
        return XST_FAILURE;
    XUsbPs_dQHInvalidateCache(in->dQH);
    XUsbPs_WritedQH(in->dQH, XUSBPS_dQHdTDTOKEN, 0U);
    XUsbPs_WritedQH(in->dQH, XUSBPS_dQHdTDNLP, 1U);
    XUsbPs_dQHFlushCache(in->dQH);
    XUsbPs_dQHInvalidateCache(InstancePtr->DeviceConfig.Ep[DAP_BULKOUT_EP].Out.dQH);
    XUsbPs_WritedQH(InstancePtr->DeviceConfig.Ep[DAP_BULKOUT_EP].Out.dQH,
                   XUSBPS_dQHdTDTOKEN, 0U);
    XUsbPs_dQHFlushCache(InstancePtr->DeviceConfig.Ep[DAP_BULKOUT_EP].Out.dQH);
    engine_status=chry_dap_usb_session_reset();
    XUsbPs_EpEnable(InstancePtr, DAP_BULKOUT_EP, XUSBPS_EP_DIRECTION_OUT);
    XUsbPs_EpEnable(InstancePtr, DAP_BULKIN_EP, XUSBPS_EP_DIRECTION_IN);
    XUsbPs_SetBits(InstancePtr, XUSBPS_EPCRn_OFFSET(DAP_BULKOUT_EP), XUSBPS_EPCR_RXR_MASK);
    XUsbPs_SetBits(InstancePtr, XUSBPS_EPCRn_OFFSET(DAP_BULKIN_EP), XUSBPS_EPCR_TXR_MASK);
    XUsbPs_EpPrime(InstancePtr, DAP_BULKOUT_EP, XUSBPS_EP_DIRECTION_OUT);
    return engine_status<0 ? XST_FAILURE : XST_SUCCESS;
}

void XUsbPs_SetConfiguration(XUsbPs *InstancePtr, int ConfigIdx)
{
	Xil_AssertVoid(InstancePtr != NULL);

	if (0 == ConfigIdx) {
        unsigned ep;
        probe_usb_reset();
        for(ep=1;ep<8;ep++) {
            XUsbPs_EpDisable(InstancePtr,ep,XUSBPS_EP_DIRECTION_IN|XUSBPS_EP_DIRECTION_OUT);
            XUsbPs_EpFlush(InstancePtr,ep,XUSBPS_EP_DIRECTION_IN|XUSBPS_EP_DIRECTION_OUT);
        }
        return;
    }
    if(1 != ConfigIdx) return;
    if(XUsbPs_DapResetEndpoints(InstancePtr)!=XST_SUCCESS)return;

	xil_printf("[DAP] SET_CONFIGURATION 1\r\n");

	probe_usb_configured(InstancePtr);
	/* Enable DAP Endpoints */
	XUsbPs_EpEnable(InstancePtr, DAP_BULKOUT_EP, XUSBPS_EP_DIRECTION_OUT);
	XUsbPs_EpEnable(InstancePtr, DAP_BULKIN_EP, XUSBPS_EP_DIRECTION_IN);

	/* Enable CDC Endpoints */
	XUsbPs_EpEnable(InstancePtr, CDC_INT_EP, XUSBPS_EP_DIRECTION_IN);  /* CDC INT EP */
	XUsbPs_EpEnable(InstancePtr, CDC_BULKOUT_EP, XUSBPS_EP_DIRECTION_OUT);
	XUsbPs_EpEnable(InstancePtr, CDC_BULKIN_EP, XUSBPS_EP_DIRECTION_IN);

	/* Configure DAP Bulk OUT Endpoint */
	XUsbPs_SetBits(InstancePtr, XUSBPS_EPCRn_OFFSET(DAP_BULKOUT_EP),
					XUSBPS_EPCR_RXT_BULK_MASK |
					XUSBPS_EPCR_RXR_MASK);

	/* Configure DAP Bulk IN Endpoint */
	XUsbPs_SetBits(InstancePtr, XUSBPS_EPCRn_OFFSET(DAP_BULKIN_EP),
					XUSBPS_EPCR_TXT_BULK_MASK |
					XUSBPS_EPCR_TXR_MASK);

	/* Configure CDC Interrupt IN Endpoint */
	XUsbPs_SetBits(InstancePtr, XUSBPS_EPCRn_OFFSET(CDC_INT_EP),
					XUSBPS_EPCR_TXT_INTR_MASK |
					XUSBPS_EPCR_TXR_MASK);

	/* Configure CDC Bulk OUT Endpoint */
	XUsbPs_SetBits(InstancePtr, XUSBPS_EPCRn_OFFSET(CDC_BULKOUT_EP),
					XUSBPS_EPCR_RXT_BULK_MASK |
					XUSBPS_EPCR_RXR_MASK);

	/* Configure CDC Bulk IN Endpoint */
	XUsbPs_SetBits(InstancePtr, XUSBPS_EPCRn_OFFSET(CDC_BULKIN_EP),
					XUSBPS_EPCR_TXT_BULK_MASK |
					XUSBPS_EPCR_TXR_MASK);

	/* Prime DAP Bulk OUT endpoint for receiving data */
	{
		int ps = XUsbPs_EpPrime(InstancePtr, DAP_BULKOUT_EP, XUSBPS_EP_DIRECTION_OUT);
		xil_printf("[DAP] PRIME ep2=%d epcr2=0x%08x epstat=0x%08x eprdy=0x%08x\r\n",
			ps,
			XUsbPs_ReadReg(InstancePtr->Config.BaseAddress, XUSBPS_EPCRn_OFFSET(2)),
			XUsbPs_ReadReg(InstancePtr->Config.BaseAddress, XUSBPS_EPSTAT_OFFSET),
			XUsbPs_ReadReg(InstancePtr->Config.BaseAddress, XUSBPS_EPRDY_OFFSET));
	}

	/* Prime CDC Bulk OUT endpoint for receiving data */
	XUsbPs_EpPrime(InstancePtr, CDC_BULKOUT_EP, XUSBPS_EP_DIRECTION_OUT);
}
