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
 * @file xusbps_class_cdc.c
 *
 * This file contains the implementation of the CDC ACM class code.
 *
 ******************************************************************************/

#include <string.h>

#include "xparameters.h"
#include "xusbps.h"
#include "xusbps_ch9.h"
#include "xusbps_class_cdc.h"
#include "xil_cache.h"

static CDC_LineCoding line_coding ALIGNMENT_CACHELINE;

extern void usbd_cdc_acm_set_dtr(XUsbPs *InstancePtr, u8 intf, u8 dtr);

/**
 * fast_memcpy - Optimized memory copy for Cortex-A9
 * 
 * This implementation uses word-level (32-bit) copying for aligned data
 * and byte-level copying for unaligned head/tail. For large copies,
 * it can achieve close to memory bandwidth limits.
 * 
 * @param dest: Destination address
 * @param src: Source address
 * @param n: Number of bytes to copy
 * @return: Destination address
 */
static inline void *fast_memcpy(void *dest, const void *src, size_t n)
{
	u8 *d = dest;
	const u8 *s = src;
	
	/* Handle small copies with simple byte loop */
	if (n < 16) {
		while (n--)
			*d++ = *s++;
		return dest;
	}
	
	/* Align destination to 4-byte boundary */
	while (((uintptr_t)d & 3) && n) {
		*d++ = *s++;
		n--;
	}
	
	/* Copy 32-bit words if source is also aligned */
	if (((uintptr_t)s & 3) == 0) {
		u32 *dw = (u32 *)d;
		const u32 *sw = (const u32 *)s;
		
		/* Copy 8 words (32 bytes) at a time */
		while (n >= 32) {
			dw[0] = sw[0];
			dw[1] = sw[1];
			dw[2] = sw[2];
			dw[3] = sw[3];
			dw[4] = sw[4];
			dw[5] = sw[5];
			dw[6] = sw[6];
			dw[7] = sw[7];
			dw += 8;
			sw += 8;
			n -= 32;
		}
		
		/* Copy remaining words */
		while (n >= 4) {
			*dw++ = *sw++;
			n -= 4;
		}
		
		d = (u8 *)dw;
		s = (const u8 *)sw;
	}
	
	/* Copy remaining bytes */
	while (n--)
		*d++ = *s++;
	
	return dest;
}



void XUsbPs_ClassReq(XUsbPs *InstancePtr, void *SetupDataPtr)
{
	XUsbPs_SetupData *SetupData = (XUsbPs_SetupData *)SetupDataPtr;
	u8 Reply[CDC_LINE_CODING_SIZE];
	int ReplyLen = 0;

	switch (SetupData->bRequest) {
	case CDC_SET_LINE_CODING:
		line_coding.dwDTERate = 115200;
		line_coding.bCharFormat = 0;
		line_coding.bParityType = 0;
		line_coding.bDataBits = 8;
		XUsbPs_EpBufferSend(InstancePtr, 0, NULL, 0);
		break;

	case CDC_GET_LINE_CODING:
		Reply[0] = line_coding.dwDTERate & 0xFF;
		Reply[1] = (line_coding.dwDTERate >> 8) & 0xFF;
		Reply[2] = (line_coding.dwDTERate >> 16) & 0xFF;
		Reply[3] = (line_coding.dwDTERate >> 24) & 0xFF;
		Reply[4] = line_coding.bCharFormat;
		Reply[5] = line_coding.bParityType;
		Reply[6] = line_coding.bDataBits;
		ReplyLen = CDC_LINE_CODING_SIZE;
		XUsbPs_EpBufferSend(InstancePtr, 0, Reply, ReplyLen);
		break;

	case CDC_SET_CONTROL_LINE_STATE:
		/* wValue: bit0=DTR, bit1=RTS */
		usbd_cdc_acm_set_dtr(InstancePtr,
			SetupData->wIndex,
			(SetupData->wValue & 0x01) || (SetupData->wValue & 0x02));
		XUsbPs_EpBufferSend(InstancePtr, 0, NULL, 0);
		break;

	default:
		XUsbPs_EpStall(InstancePtr, 0,
			XUSBPS_EP_DIRECTION_IN | XUSBPS_EP_DIRECTION_OUT);
		break;
	}
}


XUsbPs *g_dap_usb_instance = NULL;
void usbd_dap_set_instance(XUsbPs *InstancePtr)
{
	g_dap_usb_instance = InstancePtr;
}


#if 1
/* DAP发送累积缓冲区 - 收满2048字节再发送 */
#define DAP_AGGREGATE_SIZE 512
static u8 dap_tx_pending_buffer[DAP_AGGREGATE_SIZE];
static volatile u32 dap_tx_buffered_len = 0;  /* 已缓冲的数据长度 */
static volatile u32 dap_tx_pending_len = 0;   /* 待发送的数据长度 */
static volatile u8 dap_tx_pending = 0;
static volatile u8 dap_tx_busy = 0;
static XUsbPs *dap_instance_ptr = NULL;

/* CDC发送延迟缓冲区 */
static u8 cdc_tx_pending_buffer[4096];
static volatile u32 cdc_tx_pending_len = 0;
static volatile u8 cdc_tx_pending = 0;

/*****************************************************************************/
/**
*
* DAP Bulk OUT callback - called when data is received from host on DAP EP
*
******************************************************************************/
__attribute__((weak)) void usbd_dap_bulk_out(XUsbPs *InstancePtr, u8 EpNum, u32 nbytes, u8 *Buffer)
{
	// u32 space_left;
	// u32 copy_len;

	// /* 保存实例指针供后续使用 */
	// dap_instance_ptr = InstancePtr;

	// /* 累积数据到缓冲区，收满DAP_AGGREGATE_SIZE再发送 */
	// if (nbytes > 0) {
	// 	/* 计算剩余空间 */
	// 	space_left = DAP_AGGREGATE_SIZE - dap_tx_buffered_len;
	// 	copy_len = (nbytes < space_left) ? nbytes : space_left;
		
	// 	if (copy_len > 0) {
	// 		fast_memcpy(&dap_tx_pending_buffer[dap_tx_buffered_len], Buffer, copy_len);
	// 		dap_tx_buffered_len += copy_len;
	// 	}
		
	// 	/* 如果缓冲区已满，标记为待发送 */
	// 	if (dap_tx_buffered_len >= DAP_AGGREGATE_SIZE) {
	// 		dap_tx_pending_len = dap_tx_buffered_len;
	// 		dap_tx_buffered_len = 0;  /* 重置缓冲计数 */
	// 		dap_tx_pending = 1;  /* 标记有数据待发送 */
	// 	}
	// }

	/* 重新准备EP2接收下一个数据包 */
	XUsbPs_EpPrime(InstancePtr, 2, XUSBPS_EP_DIRECTION_OUT);
}

/*****************************************************************************/
/**
*
* DAP Bulk IN callback - called when data transmission is complete on DAP EP
*
******************************************************************************/
__attribute__((weak)) void usbd_dap_bulk_in(XUsbPs *InstancePtr, u8 EpNum, void *buffer)
{
	/* DAP TX complete - nbytes bytes sent */
	dap_tx_busy = 0;  /* 清除忙标志 */
}

/*****************************************************************************/
/**
*
* DAP处理待发送数据 - 应在主循环中调用
*
******************************************************************************/
// void usbd_dap_process_pending_tx(void)
// {
// 	/* 如果有数据待发送且总线空闲 */
// 	if (dap_tx_pending && !dap_tx_busy && dap_instance_ptr != NULL) {
// 		dap_tx_pending = 0;
// 		dap_tx_busy = 1;  /* 设置忙标志 */
// 		// XUsbPs_EpBufferSend(dap_instance_ptr, 1, 
// 		// 	(u8 *)dap_tx_pending_buffer, dap_tx_pending_len);
// 	}
// }

#endif



/* CDC接收缓冲区 */
// static u8 cdc_rx_buffer[4096] ALIGNMENT_CACHELINE;
// static volatile u32 cdc_rx_len = 0;
// static volatile u8 cdc_rx_ready = 0;
// static volatile u8 ep_tx_busy_flag = 0;
static volatile u8 dtr_enable = 0;
// static XUsbPs *cdc_instance_ptr = NULL;

/*****************************************************************************/
/**
*
* CDC ACM Bulk OUT callback - called when data is received from host on CDC EP
*
******************************************************************************/
__attribute__((weak)) void usbd_cdc_acm_bulk_out(XUsbPs *InstancePtr, u8 EpNum, u32 nbytes, u8 *Buffer)
{
	// xil_printf("CDC RX: %d bytes\r\n", (unsigned int)nbytes);
	/* CDC数据接收 */
	// cdc_instance_ptr = InstancePtr;

	// if (nbytes > 0 && nbytes <= sizeof(cdc_rx_buffer)) {
	// 	memcpy(cdc_rx_buffer, Buffer, nbytes);
	// 	cdc_rx_len = nbytes;
	// 	cdc_rx_ready = 1;
	// }

	/* 重新准备EP4接收下一个数据包 */
	XUsbPs_EpPrime(InstancePtr, 4, XUSBPS_EP_DIRECTION_OUT);
}

/*****************************************************************************/
/**
*
* CDC ACM Bulk IN callback - called when data transmission is complete on CDC EP
*
******************************************************************************/
__attribute__((weak)) void usbd_cdc_acm_bulk_in(XUsbPs *InstancePtr, u8 EpNum, u32 nbytes)
{
	// xil_printf("CDC TX: %d bytes\r\n", (unsigned int)nbytes);
	/* 发送完成，清除忙标志 */
	// ep_tx_busy_flag = 0;
}


/*****************************************************************************/
/**
*
* Set DTR state callback
*
******************************************************************************/
void usbd_cdc_acm_set_dtr(XUsbPs *InstancePtr, u8 intf, u8 dtr)
{
	if (dtr) {
		dtr_enable = 1;
	} else {
		dtr_enable = 0;
	}
}

/*****************************************************************************/
/**
*
* 获取DTR状态
*
******************************************************************************/
u8 usbd_cdc_acm_get_dtr(void)
{
	return dtr_enable;
}

// /*****************************************************************************/
// /**
// *
// * 获取接收到的CDC数据
// *
// ******************************************************************************/
// u32 usbd_cdc_acm_get_rx_data(u8 *buffer, u32 max_len)
// {
// 	u32 len = 0;
// 	if (cdc_rx_ready && buffer != NULL) {
// 		len = (cdc_rx_len < max_len) ? cdc_rx_len : max_len;
// 		memcpy(buffer, cdc_rx_buffer, len);
// 		cdc_rx_ready = 0;
// 	}
// 	return len;
// }

// /*****************************************************************************
// *
// * 发送CDC数据（立即发送，如果总线空闲）
// *
// ******************************************************************************/
// int usbd_cdc_acm_send_data(XUsbPs *InstancePtr, u8 *buffer, u32 len)
// {
// 	if (ep_tx_busy_flag) {
// 		return -1;  /* 正在发送中 */
// 	}

// 	if (len > 0) {
// 		ep_tx_busy_flag = 1;
// 		XUsbPs_EpBufferSend(InstancePtr, 3, buffer, len);
// 		return 0;
// 	}
// 	return -1;
// }

// /*****************************************************************************/
// /**
// *
// * 准备CDC发送数据（延迟发送，用于中断上下文）
// *
// ******************************************************************************/
// int usbd_cdc_acm_prepare_send_data(XUsbPs *InstancePtr, u8 *buffer, u32 len)
// {
// 	if (cdc_tx_pending || ep_tx_busy_flag) {
// 		return -1;  /* 有数据待发送或正在发送中 */
// 	}

// 	if (len > 0 && len <= sizeof(cdc_tx_pending_buffer)) {
// 		memcpy(cdc_tx_pending_buffer, buffer, len);
// 		cdc_tx_pending_len = len;
// 		cdc_tx_pending = 1;
// 		return 0;
// 	}
// 	return -1;
// }

// /*****************************************************************************/
// /**
// *
// * CDC处理待发送数据 - 应在主循环中调用
// *
// ******************************************************************************/
// void usbd_cdc_process_pending_tx(XUsbPs *InstancePtr)
// {
// 	if (cdc_tx_pending && !ep_tx_busy_flag) {
// 		cdc_tx_pending = 0;
// 		ep_tx_busy_flag = 1;
// 		XUsbPs_EpBufferSend(InstancePtr, 3, 
// 			(u8 *)cdc_tx_pending_buffer, cdc_tx_pending_len);
// 	}
// }
