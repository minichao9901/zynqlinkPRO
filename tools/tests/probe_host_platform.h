#ifndef PROBE_HOST_PLATFORM_H
#define PROBE_HOST_PLATFORM_H
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <stdio.h>
#include <assert.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef uintptr_t UINTPTR;
typedef uint64_t XTime;
#define COUNTS_PER_SECOND 1000000ULL
#define XST_SUCCESS 0
#define XST_FAILURE 1
typedef struct {u8 bmRequestType,bRequest;u16 wValue,wIndex,wLength;} XUsbPs_SetupData;
#define XUSBPS_EP_DIRECTION_IN 1
#define XUSBPS_EP_DIRECTION_OUT 2
#define XUSBPS_EP_EVENT_DATA_TX 1
#define XUSBPS_EP_EVENT_DATA_RX 2
#define XUSBPS_dTDTOKEN 0
#define XUSBPS_dQHdTDTOKEN 0
#define XUSBPS_dQHdTDNLP 1
#define XUSBPS_EPCRn_OFFSET(n) (0x100+(n)*4)
#define XUSBPS_EPCR_TXT_INTR_MASK 0x000c0000
#define XUSBPS_EPCR_RXT_INTR_MASK 0xc
#define XUSBPS_EPCR_TXT_BULK_MASK 0x00080000
#define XUSBPS_EPCR_RXT_BULK_MASK 8
#define XUSBPS_EPCR_TXR_MASK 0x00400000
#define XUSBPS_EPCR_RXR_MASK 0x40
#define XUSBPS_EPFLUSH_OFFSET 0x1b4
#define XUSBPS_EPSTAT_OFFSET 0x1b8
#define XUSBPS_EPCOMPL_OFFSET 0x1bc
#define XUSBPS_EPRDY_OFFSET 0x1bc
#define XUSBPS_PORTSCR1_OFFSET 0x184
#define Xil_AssertVoid(x) assert(x)
#define Xil_AssertNonvoid(x) assert(x)
#define xil_printf(...) ((void)0)
typedef struct {uint32_t x[8];} XUsbPs_dTD;
typedef struct {uint32_t x[8];} XUsbPs_dQH;
typedef struct {unsigned NumBufs,MaxPacketSize;} HostEpCfg;
typedef struct {XUsbPs_dTD *dTDs;XUsbPs_dQH *dQH;} HostEp;
typedef struct {
    struct {uintptr_t BaseAddress;} Config;
    struct {
        struct {HostEpCfg In,Out;} EpCfg[8];
        struct {HostEp In,Out;} Ep[8];
    } DeviceConfig;
} XUsbPs;
static inline uint32_t mfcpsr(void) {return 0;}
static inline void mtcpsr(uint32_t x) {(void)x;}
static inline void Xil_DCacheInvalidateRange(UINTPTR p,uint32_t n) {(void)p;(void)n;}
static inline void XUsbPs_dTDInvalidateCache(XUsbPs_dTD *p) {(void)p;}
static inline void XUsbPs_dTDFlushCache(XUsbPs_dTD *p) {(void)p;}
static inline void XUsbPs_dQHInvalidateCache(XUsbPs_dQH *p) {(void)p;}
static inline void XUsbPs_dQHFlushCache(XUsbPs_dQH *p) {(void)p;}
static inline void XUsbPs_WritedTD(XUsbPs_dTD *p,unsigned n,u32 v) {(void)p;(void)n;(void)v;}
static inline void XUsbPs_WritedQH(XUsbPs_dQH *p,unsigned n,u32 v) {(void)p;(void)n;(void)v;}
static inline int XUsbPs_EpFlush(XUsbPs *p,unsigned e,unsigned d) {(void)p;(void)e;(void)d;return 0;}
static inline int XUsbPs_ReconfigureEp(XUsbPs *p,void *cfg,unsigned e,unsigned d,unsigned z) {(void)p;(void)cfg;(void)e;(void)d;(void)z;return 0;}
static inline void XUsbPs_EpEnable(XUsbPs *p,unsigned e,unsigned d) {(void)p;(void)e;(void)d;}
static inline void XUsbPs_SetBits(XUsbPs *p,unsigned r,unsigned v) {(void)p;(void)r;(void)v;}
static inline void XUsbPs_WriteReg(uintptr_t p,unsigned r,unsigned v) {(void)p;(void)r;(void)v;}
static inline u32 XUsbPs_ReadReg(uintptr_t p,unsigned r) {(void)p;(void)r;return 0;}
static inline int XUsbPs_EpPrime(XUsbPs *p,unsigned e,unsigned d) {(void)p;(void)e;(void)d;return 0;}
int XUsbPs_EpBufferSend(XUsbPs *,u8,u8 *,u32);
int XUsbPs_EpBufferSendWithZLT(XUsbPs *,u8,u8 *,u32);
int XUsbPs_EpBufferReceive(XUsbPs *,u8,u8 **,u32 *,u32 *);
void XUsbPs_EpBufferRelease(u32);
void XTime_GetTime(XTime *);
uint32_t Xil_In32(uintptr_t);
void Xil_Out32(uintptr_t,uint32_t);
#endif
