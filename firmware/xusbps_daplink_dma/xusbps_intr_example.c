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
* @file xusbps_intr_example.c
*
* This file contains an example of how to use the USB driver with the USB
* controller in DEVICE mode.
*
*
*<pre>
* MODIFICATION HISTORY:
*
* Ver   Who     Date     Changes
* ----- ------  -------- ----------------------------------------------------
* 1.00a wgr/nm  10/09/10 First release
* 1.01a nm      03/05/10 Included xpseudo_asm.h instead of xpseudo_asm_gcc.h
* 1.04a nm      02/05/13 Fixed CR# 696550.
*		         Added template code for Vendor request.
* 1.06a kpc		11/11/13 Fixed CR#759458, cacheInvalidate size should be
*				 ailgned to ccahe line size.
* 2.1   kpc    04/28/14 Cleanup and removed unused functions
*</pre>
******************************************************************************/

/***************************** Include Files *********************************/

#include "xparameters.h"		/* XPAR parameters */
#include "xusbps.h"			/* USB controller driver */
#include "xscugic.h"
#include "xusbps_ch9.h"		/* Generic Chapter 9 handling code */
#include "xusbps_class_cdc.h"	/* CDC ACM class handling code */
#include "xusbps_ch9_storage.h"
#include "xil_exception.h"
#include "xpseudo_asm.h"
#include "xreg_cortexa9.h"
#include "xil_cache.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sleep.h"

/************************** Constant Definitions *****************************/
#define MEMORY_SIZE (512 * 1024)

// #define CDC_IN_EP   0x82
// #define CDC_OUT_EP  0x02
// #define CDC_INT_EP  0x81

#ifdef __ICCARM__
#pragma data_alignment = 32
u8 Buffer[MEMORY_SIZE];
#pragma data_alignment = 4
#else
u8 Buffer[MEMORY_SIZE] ALIGNMENT_CACHELINE;
#endif

/**************************** Type Definitions *******************************/

/***************** Macros (Inline Functions) Definitions *********************/

/************************** Function Prototypes ******************************/

static int UsbIntrExample(XScuGic *IntcInstancePtr, XUsbPs *UsbInstancePtr,
			  u16 UsbDeviceId, u16 UsbIntrId);

static void UsbIntrHandler(void *CallBackRef, u32 Mask);
static void XUsbPs_Ep0EventHandler(void *CallBackRef, u8 EpNum,
					u8 EventType, void *Data);
static void XUsbPs_EpDapEventHandler(void *CallBackRef, u8 EpNum,
					u8 EventType, void *Data);
static void XUsbPs_EpCdcEventHandler(void *CallBackRef, u8 EpNum,
					u8 EventType, void *Data);
static int UsbSetupIntrSystem(XScuGic *IntcInstancePtr,
			      XUsbPs *UsbInstancePtr, u16 UsbIntrId);
static void UsbDisableIntrSystem(XScuGic *IntcInstancePtr, u16 UsbIntrId);

void cdc_acm_data_send_with_dtr_test(XUsbPs *InstancePtr);


/************************** Variable Definitions *****************************/

static XScuGic IntcInstance;
static XUsbPs UsbInstance;

static volatile int NumIrqs = 0;
static volatile int NumReceivedFrames = 0;
static volatile int NumSendFrames = 0;
static volatile int DapEpEvents = 0;

static u8 cdc_write_buffer[4096] ALIGNMENT_CACHELINE;

#define CDC_MAX_MPS 512


/*****************************************************************************/
/**
 *
 * Main function to call the USB interrupt example.
 *
 * @param	None
 *
 * @return
 * 		- XST_SUCCESS if successful
 * 		- XST_FAILURE on error
 *
 ******************************************************************************/

int main(void)
{
	int Status;
	printf("hello cdc acm test!\n");
	extern int swd_dma_selftest(void);
	Status = swd_dma_selftest();
	xil_printf("[DMA] BRAM/CDMA/CACHE selftest=%d\r\n", Status);
	if (Status) return XST_FAILURE;

	/* Run the USB Interrupt example.*/
	Status = UsbIntrExample(&IntcInstance, &UsbInstance,
				XPAR_XUSBPS_0_DEVICE_ID, XPAR_XUSBPS_0_INTR);
	if (Status != XST_SUCCESS) {
		return XST_FAILURE;
	}

	return XST_SUCCESS;
}

/*****************************************************************************/
/**
 *
 * This function does a minimal DEVICE mode setup on the USB device and driver
 * as a design example. The purpose of this function is to illustrate how to
 * set up a USB flash disk emulation system.
 *
 *
 * @param	IntcInstancePtr is a pointer to the instance of the INTC driver.
 * @param	UsbInstancePtr is a pointer to the instance of USB driver.
 * @param	UsbDeviceId is the Device ID of the USB Controller and is the
 * 		XPAR_<USB_instance>_DEVICE_ID value from xparameters.h.
 * @param	UsbIntrId is the Interrupt Id and is typically
 * 		XPAR_<INTC_instance>_<USB_instance>_IP2INTC_IRPT_INTR value
 * 		from xparameters.h.
 *
 * @return
 * 		- XST_SUCCESS if successful
 * 		- XST_FAILURE on error
 *
 ******************************************************************************/
static int UsbIntrExample(XScuGic *IntcInstancePtr, XUsbPs *UsbInstancePtr,
					u16 UsbDeviceId, u16 UsbIntrId)
{
	int	Status;
	u8	*MemPtr = NULL;
	int	ReturnStatus = XST_FAILURE;

	/* DAPLink endpoint configuration:
	 *   Endpoint 0 (default control endpoint)
	 *   Endpoint 1 (Bulk IN for DAP)
	 *   Endpoint 2 (Bulk OUT for DAP)
	 *   Endpoint 3 (Bulk IN for CDC)
	 *   Endpoint 4 (Bulk OUT for CDC)
	 *   Endpoint 5 (Interrupt IN for CDC notifications)
	 */
	const u8 NumEndpoints = 6;

	XUsbPs_Config		*UsbConfigPtr;
	XUsbPs_DeviceConfig	DeviceConfig;

	/* Initialize the USB driver so that it's ready to use,
	 * specify the controller ID that is generated in xparameters.h
	 */
	UsbConfigPtr = XUsbPs_LookupConfig(UsbDeviceId);
	if (NULL == UsbConfigPtr) {
		goto out;
	}


	/* We are passing the physical base address as the third argument
	 * because the physical and virtual base address are the same in our
	 * example.  For systems that support virtual memory, the third
	 * argument needs to be the virtual base address.
	 */
	Status = XUsbPs_CfgInitialize(UsbInstancePtr,
				       UsbConfigPtr,
				       UsbConfigPtr->BaseAddress);
	if (XST_SUCCESS != Status) {
		goto out;
	}

	/* Set up the interrupt subsystem.
	 */
	Status = UsbSetupIntrSystem(IntcInstancePtr,
				    UsbInstancePtr,
				    UsbIntrId);
	if (XST_SUCCESS != Status)
	{
		goto out;
	}

	/* Configuration of the DEVICE side of the controller happens in
	 * multiple stages.
	 *
	 * 1) The user configures the desired endpoint configuration using the
	 * XUsbPs_DeviceConfig data structure. This includes the number of
	 * endpoints, the number of Transfer Descriptors for each endpoint
	 * (each endpoint can have a different number of Transfer Descriptors)
	 * and the buffer size for the OUT (receive) endpoints.  Each endpoint
	 * can have different buffer sizes.
	 *
	 * 2) Request the required size of DMAable memory from the driver using
	 * the XUsbPs_DeviceMemRequired() call.
	 *
	 * 3) Allocate the DMAable memory and set up the DMAMemVirt and
	 * DMAMemPhys members in the XUsbPs_DeviceConfig data structure.
	 *
	 * 4) Configure the DEVICE side of the controller by calling the
	 * XUsbPs_ConfigureDevice() function.
	 */

	/*
	 * DAPLink endpoint configuration:
	 *   Endpoint 0 (default control endpoint)
	 *   Endpoint 1 (Bulk IN for DAP: 0x81)
	 *   Endpoint 2 (Bulk OUT for DAP: 0x02)
	 *   Endpoint 3 (Bulk IN for CDC: 0x83)
	 *   Endpoint 4 (Bulk OUT for CDC: 0x04)
	 *   Endpoint 5 (Interrupt IN for CDC: 0x85)
	 */

	/* Endpoint 0: Control Endpoint */
	DeviceConfig.EpCfg[0].Out.Type		= XUSBPS_EP_TYPE_CONTROL;
	DeviceConfig.EpCfg[0].Out.NumBufs	= 2;
	DeviceConfig.EpCfg[0].Out.BufSize	= 64;
	DeviceConfig.EpCfg[0].Out.MaxPacketSize	= 64;
	DeviceConfig.EpCfg[0].In.Type		= XUSBPS_EP_TYPE_CONTROL;
	DeviceConfig.EpCfg[0].In.NumBufs	= 2;
	DeviceConfig.EpCfg[0].In.MaxPacketSize	= 64;

	/* Endpoint 1: DAP Bulk IN (0x81) */
	DeviceConfig.EpCfg[1].In.Type		= XUSBPS_EP_TYPE_BULK;
	DeviceConfig.EpCfg[1].In.NumBufs	= 16;
	DeviceConfig.EpCfg[1].In.MaxPacketSize	= 512;

	/* Endpoint 2: DAP Bulk OUT (0x02) */
	DeviceConfig.EpCfg[2].Out.Type		= XUSBPS_EP_TYPE_BULK;
	DeviceConfig.EpCfg[2].Out.NumBufs	= 16;
	DeviceConfig.EpCfg[2].Out.BufSize	= 4096;
	DeviceConfig.EpCfg[2].Out.MaxPacketSize	= 512;

	/* Endpoint 3: CDC Bulk IN (0x83) */
	DeviceConfig.EpCfg[3].In.Type		= XUSBPS_EP_TYPE_BULK;
	DeviceConfig.EpCfg[3].In.NumBufs	= 16;
	DeviceConfig.EpCfg[3].In.MaxPacketSize	= 512;

	/* Endpoint 4: CDC Bulk OUT (0x04) */
	DeviceConfig.EpCfg[4].Out.Type		= XUSBPS_EP_TYPE_BULK;
	DeviceConfig.EpCfg[4].Out.NumBufs	= 16;
	DeviceConfig.EpCfg[4].Out.BufSize	= 4096;
	DeviceConfig.EpCfg[4].Out.MaxPacketSize	= 512;

	/* Endpoint 5: CDC Interrupt IN (0x85) */
	DeviceConfig.EpCfg[5].Out.Type		= XUSBPS_EP_TYPE_INTERRUPT;
	DeviceConfig.EpCfg[5].Out.NumBufs	= 2;
	DeviceConfig.EpCfg[5].Out.BufSize	= 64;
	DeviceConfig.EpCfg[5].Out.MaxPacketSize	= 64;
	DeviceConfig.EpCfg[5].In.Type		= XUSBPS_EP_TYPE_INTERRUPT;
	DeviceConfig.EpCfg[5].In.NumBufs	= 2;
	DeviceConfig.EpCfg[5].In.MaxPacketSize	= 64;

	DeviceConfig.NumEndpoints = NumEndpoints;

	MemPtr = (u8 *)&Buffer[0];
	memset(MemPtr,0,MEMORY_SIZE);
	Xil_DCacheFlushRange((unsigned int)MemPtr, MEMORY_SIZE);

	/* Finish the configuration of the DeviceConfig structure and configure
	 * the DEVICE side of the controller.
	 */
	DeviceConfig.DMAMemPhys = (u32) MemPtr;

	Status = XUsbPs_ConfigureDevice(UsbInstancePtr, &DeviceConfig);
	if (XST_SUCCESS != Status) {
		goto out;
	}

	/* Set the handler for receiving frames. */
	Status = XUsbPs_IntrSetHandler(UsbInstancePtr, UsbIntrHandler, NULL,
						XUSBPS_IXR_UE_MASK);
	if (XST_SUCCESS != Status) {
		goto out;
	}

	Status = XUsbPs_EpSetHandler(UsbInstancePtr, 0,
				XUSBPS_EP_DIRECTION_OUT,
				XUsbPs_Ep0EventHandler, UsbInstancePtr);

	/* DAP Endpoint Handlers */
	Status = XUsbPs_EpSetHandler(UsbInstancePtr, 2,
				XUSBPS_EP_DIRECTION_OUT,
				XUsbPs_EpDapEventHandler, UsbInstancePtr);

	Status = XUsbPs_EpSetHandler(UsbInstancePtr, 1,
				XUSBPS_EP_DIRECTION_IN,
				XUsbPs_EpDapEventHandler, UsbInstancePtr);

	/* CDC Endpoint Handlers */
	Status = XUsbPs_EpSetHandler(UsbInstancePtr, 4,
				XUSBPS_EP_DIRECTION_OUT,
				XUsbPs_EpCdcEventHandler, UsbInstancePtr);

	Status = XUsbPs_EpSetHandler(UsbInstancePtr, 3,
				XUSBPS_EP_DIRECTION_IN,
				XUsbPs_EpCdcEventHandler, UsbInstancePtr);

	/* Enable the interrupts. */
	XUsbPs_IntrEnable(UsbInstancePtr, XUSBPS_IXR_UR_MASK |
					   XUSBPS_IXR_UI_MASK);


	XUsbPs_Start(UsbInstancePtr);
	xil_printf("[DAP] BOOT USB_STARTED\r\n");
	/* High-throughput XUsbPs setting: complete descriptors promptly while
	 * keeping the 16-entry DAP queues continuously primed. */
	XUsbPs_WriteReg(UsbInstancePtr->Config.BaseAddress, XUSBPS_CMD_OFFSET,
		(XUsbPs_ReadReg(UsbInstancePtr->Config.BaseAddress, XUSBPS_CMD_OFFSET) &
		 ~XUSBPS_CMD_ITC_MASK));

	/* 设置DAP USB实例，用于DAPLink对接 */
	usbd_dap_set_instance(UsbInstancePtr);
	/* Give Windows time to finish enumeration before entering the DAP loop. */
	sleep(1);


	/* DAP can be initialized before USB configuration.  The old application
	 * waited on g_UsbConfigured here; with a cached global that could leave the
	 * CPU spinning after the configuration interrupt had already arrived. */
	extern void chry_dap_init(void);
	xil_printf("[DAP] BEFORE_DAP_INIT\r\n");
	chry_dap_init();
	xil_printf("[DAP] AFTER_DAP_INIT\r\n");

	while (1) {
		// cdc_acm_data_send_with_dtr_test(UsbInstancePtr);

		/* 处理DAP待发送数据 - 从中断上下文延迟到主循环发送 */
		// usbd_dap_process_pending_tx();

		/* 处理CDC待发送数据 - 从中断上下文延迟到主循环发送 */
		// usbd_cdc_process_pending_tx(UsbInstancePtr);

		// sleep(1);
		/* No delay for maximum throughput test */

		extern void chry_dap_handle(void);
		chry_dap_handle();
	}

	ReturnStatus = XST_SUCCESS;

out:
	/* Clean up. It's always safe to disable interrupts and clear the
	 * handlers, even if they have not been enabled/set. The same is true
	 * for disabling the interrupt subsystem.
	 */
	XUsbPs_Stop(UsbInstancePtr);
	XUsbPs_IntrDisable(UsbInstancePtr, XUSBPS_IXR_ALL);
	(int) XUsbPs_IntrSetHandler(UsbInstancePtr, NULL, NULL, 0);

	UsbDisableIntrSystem(IntcInstancePtr, UsbIntrId);

	/* Free allocated memory.
	 */
	if (NULL != UsbInstancePtr->UserDataPtr) {
		free(UsbInstancePtr->UserDataPtr);
	}
	return ReturnStatus;
}

/*****************************************************************************/
/**
 *
 * This function is the handler which performs processing for the USB driver.
 * It is called from an interrupt context such that the amount of processing
 * performed should be minimized.
 *
 * This handler provides an example of how to handle USB interrupts and
 * is application specific.
 *
 * @param	CallBackRef is the Upper layer callback reference passed back
 *		when the callback function is invoked.
 * @param 	Mask is the Interrupt Mask.
 * @param	CallBackRef is the User data reference.
 *
 * @return
 * 		- XST_SUCCESS if successful
 * 		- XST_FAILURE on error
 *
 * @note	None.
 *
 ******************************************************************************/
static void UsbIntrHandler(void *CallBackRef, u32 Mask)
{
	NumIrqs++;
	if (NumIrqs <= 8) {
		xil_printf("[DAP] USB_IRQ n=%d mask=0x%08x\r\n", NumIrqs, Mask);
	}
}


/*****************************************************************************/
/**
* This funtion is registered to handle callbacks for endpoint 0 (Control).
*
* It is called from an interrupt context such that the amount of processing
* performed should be minimized.
*
*
* @param	CallBackRef is the reference passed in when the function
*		was registered.
* @param	EpNum is the Number of the endpoint on which the event occured.
* @param	EventType is type of the event that occured.
*
* @return	None.
*
******************************************************************************/
static void XUsbPs_Ep0EventHandler(void *CallBackRef, u8 EpNum,
					u8 EventType, void *Data)
{
	XUsbPs			*InstancePtr;
	int			Status;
	XUsbPs_SetupData	SetupData;
	u8	*BufferPtr;
	u32	BufferLen;
	u32	Handle;


	Xil_AssertVoid(NULL != CallBackRef);

	InstancePtr = (XUsbPs *) CallBackRef;

	switch (EventType) {

	/* Handle the Setup Packets received on Endpoint 0. */
	case XUSBPS_EP_EVENT_SETUP_DATA_RECEIVED:
		Status = XUsbPs_EpGetSetupData(InstancePtr, EpNum, &SetupData);
		if (XST_SUCCESS == Status) {
			/* Handle the setup packet. */
			(int) XUsbPs_Ch9HandleSetupPacket(InstancePtr,
							   &SetupData);
		}
		break;

	/* We get data RX events for 0 length packets on endpoint 0. We receive
	 * and immediately release them again here, but there's no action to be
	 * taken.
	 */
	case XUSBPS_EP_EVENT_DATA_RX:
		/* Get the data buffer. */
		Status = XUsbPs_EpBufferReceive(InstancePtr, EpNum,
					&BufferPtr, &BufferLen, &Handle);
		if (XST_SUCCESS == Status) {
			/* Return the buffer. */
			XUsbPs_EpBufferRelease(Handle);
		}
		break;

	default:
		/* Unhandled event. Ignore. */
		break;
	}
}


/*****************************************************************************/
/**
* This funtion is registered to handle callbacks for endpoint 1 (Bulk data).
*
* It is called from an interrupt context such that the amount of processing
* performed should be minimized.
*
*
* @param	CallBackRef is the reference passed in when the function was
*		registered.
* @param	EpNum is the Number of the endpoint on which the event occured.
* @param	EventType is type of the event that occured.
*
* @return	None.
*
* @note 	None.
*
******************************************************************************/
static void XUsbPs_EpDapEventHandler(void *CallBackRef, u8 EpNum,
					u8 EventType, void *Data)
{
	XUsbPs *InstancePtr;
	int Status;
	u8	*BufferPtr;
	u32	BufferLen;
	u32 InavalidateLen;
	u32	Handle;

	Xil_AssertVoid(NULL != CallBackRef);

	InstancePtr = (XUsbPs *) CallBackRef;
	if (DapEpEvents < 8) {
		xil_printf("[DAP] EP event ep=%d type=%d\r\n", EpNum, EventType);
		DapEpEvents++;
	}

	switch (EventType) {
	case XUSBPS_EP_EVENT_DATA_RX:
		/* DAP Bulk OUT - EP 2 */
		Status = XUsbPs_EpBufferReceive(InstancePtr, EpNum,
					&BufferPtr, &BufferLen, &Handle);
		InavalidateLen = BufferLen;
		if (BufferLen % 32) {
			InavalidateLen = (BufferLen/32) * 32 + 32;
		}

		Xil_DCacheInvalidateRange((unsigned int)BufferPtr, InavalidateLen);
		if (XST_SUCCESS == Status) {
			usbd_dap_bulk_out(InstancePtr, EpNum, BufferLen, BufferPtr);
			XUsbPs_EpBufferRelease(Handle);
		}
		break;

	case XUSBPS_EP_EVENT_DATA_TX:
		/* DAP Bulk IN - EP 1 */
		usbd_dap_bulk_in(InstancePtr, EpNum, 0);
		break;

	default:
		break;
	}
}

static void XUsbPs_EpCdcEventHandler(void *CallBackRef, u8 EpNum,
					u8 EventType, void *Data)
{
	XUsbPs *InstancePtr;
	int Status;
	u8	*BufferPtr;
	u32	BufferLen;
	u32 InavalidateLen;
	u32	Handle;

	Xil_AssertVoid(NULL != CallBackRef);

	InstancePtr = (XUsbPs *) CallBackRef;

	switch (EventType) {
	case XUSBPS_EP_EVENT_DATA_RX:
		/* CDC Bulk OUT - EP 4 */
		Status = XUsbPs_EpBufferReceive(InstancePtr, EpNum,
					&BufferPtr, &BufferLen, &Handle);
		InavalidateLen = BufferLen;
		if (BufferLen % 32) {
			InavalidateLen = (BufferLen/32) * 32 + 32;
		}

		Xil_DCacheInvalidateRange((unsigned int)BufferPtr, InavalidateLen);
		if (XST_SUCCESS == Status) {
			usbd_cdc_acm_bulk_out(InstancePtr, EpNum, BufferLen, BufferPtr);
			XUsbPs_EpBufferRelease(Handle);
		}
		break;

	case XUSBPS_EP_EVENT_DATA_TX:
		/* CDC Bulk IN - EP 3 */
		usbd_cdc_acm_bulk_in(InstancePtr, EpNum, 0);
		break;

	default:
		break;
	}
}

/*****************************************************************************/
/**
*
* This function setups the interrupt system such that interrupts can occur for
* the USB controller. This function is application specific since the actual
* system may or may not have an interrupt controller. The USB controller could
* be directly connected to a processor without an interrupt controller.  The
* user should modify this function to fit the application.
*
* @param	IntcInstancePtr is a pointer to instance of the Intc controller.
* @param	UsbInstancePtr is a pointer to instance of the USB controller.
* @param	UsbIntrId is the Interrupt Id and is typically
* 		XPAR_<INTC_instance>_<USB_instance>_VEC_ID value
* 		from xparameters.h
*
* @return
* 		- XST_SUCCESS if successful
* 		- XST_FAILURE on error
*
******************************************************************************/
static int UsbSetupIntrSystem(XScuGic *IntcInstancePtr,
			      XUsbPs *UsbInstancePtr, u16 UsbIntrId)
{
	int Status;
	XScuGic_Config *IntcConfig;

	/*
	 * Initialize the interrupt controller driver so that it is ready to
	 * use.
	 */
	IntcConfig = XScuGic_LookupConfig(XPAR_SCUGIC_SINGLE_DEVICE_ID);
	if (NULL == IntcConfig) {
		return XST_FAILURE;
	}
	Status = XScuGic_CfgInitialize(IntcInstancePtr, IntcConfig,
					IntcConfig->CpuBaseAddress);
	if (Status != XST_SUCCESS) {
		return XST_FAILURE;
	}

	Xil_ExceptionInit();
	/*
	 * Connect the interrupt controller interrupt handler to the hardware
	 * interrupt handling logic in the processor.
	 */
	Xil_ExceptionRegisterHandler(XIL_EXCEPTION_ID_IRQ_INT,
				    (Xil_ExceptionHandler)XScuGic_InterruptHandler,
				    IntcInstancePtr);
	/*
	 * Connect the device driver handler that will be called when an
	 * interrupt for the device occurs, the handler defined above performs
	 * the specific interrupt processing for the device.
	 */
	Status = XScuGic_Connect(IntcInstancePtr, UsbIntrId,
				(Xil_ExceptionHandler)XUsbPs_IntrHandler,
				(void *)UsbInstancePtr);
	if (Status != XST_SUCCESS) {
		return Status;
	}
	/*
	 * Enable the interrupt for the device.
	 */
	XScuGic_Enable(IntcInstancePtr, UsbIntrId);

	/*
	 * Enable interrupts in the Processor.
	 */
	Xil_ExceptionEnableMask(XIL_EXCEPTION_IRQ);

	return XST_SUCCESS;
}

/*****************************************************************************/
/**
*
* This function disables the interrupts that occur for the USB controller.
*
* @param	IntcInstancePtr is a pointer to instance of the INTC driver.
* @param	UsbIntrId is the Interrupt Id and is typically
* 		XPAR_<INTC_instance>_<USB_instance>_VEC_ID value
* 		from xparameters.h
*
* @return	None
*
* @note		None.
*
******************************************************************************/
static void UsbDisableIntrSystem(XScuGic *IntcInstancePtr, u16 UsbIntrId)
{
	XScuGic_Disconnect(IntcInstancePtr, UsbIntrId);
}




#if 1
/*****************************************************************************/
/**
*
* Send data with DTR test - sends test data if DTR is enabled
*
******************************************************************************/
void cdc_acm_data_send_with_dtr_test(XUsbPs *InstancePtr)
{
	static u8 initialized = 0;
	u32 i;
	u32 send_len = 4095;  /* Test with 512 bytes (requires ZLP) */
	int Status;

	if (!initialized) {
		/* Fill first 10 bytes with '0'-'9' */
		for (i = 0; i < 10; i++) {
			cdc_write_buffer[i] = '0' + i;
		}
		/* Fill remaining with 'a' */
		for (i = 10; i < sizeof(cdc_write_buffer); i++) {
			cdc_write_buffer[i] = 'a';
		}
		initialized = 1;
	}

	/* Try to send data - if endpoint busy, XUsbPs_EpBufferSendWithZLT will return error */
	Status = XUsbPs_EpBufferSendWithZLT(InstancePtr, 3, cdc_write_buffer, send_len);
	if (Status == XST_SUCCESS) {
		NumSendFrames++;
	}
	/* If XST_USB_NO_DESC_AVAILABLE, endpoint is busy, just skip this frame */
}

#endif
