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
******************************************************************************/
/*****************************************************************************/
/**
 *
 * @file xusbps_class_cdc.h
 *
 * This file contains definitions for CDC ACM class.
 *
 ******************************************************************************/

#ifndef XUSBPS_CLASS_CDC_H
#define XUSBPS_CLASS_CDC_H

#ifdef __cplusplus
extern "C" {
#endif

#include "xil_types.h"
#include "xusbps.h"

#define CDC_SEND_ENCAPSULATED_COMMAND	0x00
#define CDC_GET_ENCAPSULATED_RESPONSE	0x01
#define CDC_SET_COMM_FEATURE			0x02
#define CDC_GET_COMM_FEATURE			0x03
#define CDC_CLEAR_COMM_FEATURE			0x04
#define CDC_SET_LINE_CODING				0x20
#define CDC_GET_LINE_CODING				0x21
#define CDC_SET_CONTROL_LINE_STATE		0x22
#define CDC_SEND_BREAK					0x23

#define CDC_LINE_CODING_SIZE			7

typedef struct {
	u32 dwDTERate;
	u8  bCharFormat;
	u8  bParityType;
	u8  bDataBits;
} CDC_LineCoding;

void XUsbPs_ClassReq(XUsbPs *InstancePtr, void *SetupDataPtr);
void usbd_cdc_acm_set_dtr(XUsbPs *InstancePtr, u8 intf, u8 dtr);
void usbd_cdc_acm_bulk_out(XUsbPs *InstancePtr, u8 EpNum, u32 nbytes, u8 *Buffer);
void usbd_cdc_acm_bulk_in(XUsbPs *InstancePtr, u8 EpNum, u32 nbytes);
u8 usbd_cdc_acm_get_dtr(void);
u32 usbd_cdc_acm_get_rx_data(u8 *buffer, u32 max_len);
int usbd_cdc_acm_send_data(XUsbPs *InstancePtr, u8 *buffer, u32 len);
int usbd_cdc_acm_prepare_send_data(XUsbPs *InstancePtr, u8 *buffer, u32 len);
void usbd_cdc_process_pending_tx(XUsbPs *InstancePtr);

/* DAP functions */
void usbd_dap_bulk_out(XUsbPs *InstancePtr, u8 EpNum, u32 nbytes, u8 *Buffer);
void usbd_dap_bulk_in(XUsbPs *InstancePtr, u8 EpNum, u32 nbytes);
void usbd_dap_process_pending_tx(void);

void usbd_dap_set_instance(XUsbPs *InstancePtr);

#ifdef __cplusplus
}
#endif

#endif
