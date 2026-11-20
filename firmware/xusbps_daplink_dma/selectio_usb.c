#include "selectio_usb.h"
#if DAP_SELECTIO
#include "DAP_config.h"
#include "DAP.h"
#include "selectio_mode.h"
#include "selectio_aux.h"
#include "selectio_block.h"
#include "selectio_combo.h"
#include "probe_stream.h"
#include "xil_cache.h"
#include "xtime_l.h"
#include "xusbps_endpoint.h"
#include <string.h>

/* One completed request owns the IN buffer until its USB IOC callback.
 * OUT descriptors supply bounded backpressure while the foreground is busy.
 * Header: magic, channel/op/status/reserved, sequence and payload bytes (LE).
 */
#define FRAME_SIZE 4096U
#define HEADER_SIZE 16U
static u8 arrival[FRAME_SIZE] __attribute__((aligned(32)));
static u8 input[FRAME_SIZE] __attribute__((aligned(32)));
static u8 reply_bank[2][FRAME_SIZE] __attribute__((aligned(4096)));
static u8 *output,*in_flight;
static volatile unsigned tx_channel,tx_packets;
static volatile unsigned epoch, configured, rx_hint, tx_busy;
static volatile unsigned received_length, deferred, reply_channel, reply_packets;
static volatile unsigned aux_commit,aux_reset;
static volatile unsigned close_pending;
static XTime last_activity;
static unsigned watchdog_div;
static unsigned pending_length, next_sequence, session_open;

static u32 read32(const u8 *p) {u32 v;memcpy(&v,p,4);return v;}
static void write32(u8 *p,u32 v) {memcpy(p,&v,4);}

void selectio_usb_reset(void) {
    configured=0;
    if(selectio_mem_active()) close_pending=1;
    selectio_combo_reset();
    epoch++;
    aux_reset=1;aux_commit=0;selectio_cdc_reset();
    rx_hint=tx_busy=pending_length=session_open=deferred=reply_packets=tx_packets=0;
}
void selectio_usb_configured(XUsbPs *usb) {
    selectio_usb_reset();
    XUsbPs_EpFlush(usb,1,XUSBPS_EP_DIRECTION_OUT);
    XUsbPs_EpFlush(usb,4,XUSBPS_EP_DIRECTION_IN);
    XUsbPs_ReconfigureEp(usb,&usb->DeviceConfig,1,XUSBPS_EP_DIRECTION_OUT,0);
    for(unsigned i=0;i<usb->DeviceConfig.EpCfg[4].In.NumBufs;i++) {
        XUsbPs_dTD *td=&usb->DeviceConfig.Ep[4].In.dTDs[i];
        XUsbPs_dTDInvalidateCache(td);
        XUsbPs_WritedTD(td,XUSBPS_dTDTOKEN,0);
        XUsbPs_dTDFlushCache(td);
    }
    XUsbPs_ReconfigureEp(usb,&usb->DeviceConfig,4,XUSBPS_EP_DIRECTION_IN,0);
    XUsbPs_EpEnable(usb,1,XUSBPS_EP_DIRECTION_OUT);
    XUsbPs_EpEnable(usb,4,XUSBPS_EP_DIRECTION_IN);
    XUsbPs_SetBits(usb,XUSBPS_EPCRn_OFFSET(1),XUSBPS_EPCR_RXT_BULK_MASK|XUSBPS_EPCR_RXR_MASK);
    XUsbPs_SetBits(usb,XUSBPS_EPCRn_OFFSET(4),XUSBPS_EPCR_TXT_BULK_MASK|XUSBPS_EPCR_TXR_MASK);
    configured=1;
    XUsbPs_EpPrime(usb,1,XUSBPS_EP_DIRECTION_OUT);
}

int selectio_usb_rx_available(void) {
    if (rx_hint) {deferred=1;return 0;}
    return 1;
}

void selectio_usb_event(void *ref,u8 ep,u8 event,void *data) {
    XUsbPs *usb=(XUsbPs *)ref;
    if (!configured) return;
    if (ep==1 && event==XUSBPS_EP_EVENT_DATA_RX) {
        u8 *buffer;
        u32 length,handle;
        if (XUsbPs_EpBufferReceive(usb,ep,&buffer,&length,&handle)!=XST_SUCCESS) return;
        if (length>FRAME_SIZE) length=0;
        Xil_DCacheInvalidateRange((UINTPTR)buffer,(length+31U)&~31U);
        memcpy(arrival,buffer,length);
        received_length=length;
        __sync_synchronize();
        rx_hint=1;
        XUsbPs_EpBufferRelease(handle);
    }
    if (ep==4 && event==XUSBPS_EP_EVENT_DATA_TX && tx_busy && data==in_flight) {
        if(tx_packets && tx_channel>=6) selectio_combo_commit(tx_channel,tx_packets);
        else if(tx_packets && tx_channel>=4) aux_commit=tx_packets;
        else if (tx_packets) probe_native_commit(tx_channel,tx_packets);
        tx_packets=0;
        tx_busy=0;
    }
}

static unsigned execute_frame(unsigned length, unsigned active_epoch) {
    if(!configured || epoch!=active_epoch) return 0;
    unsigned size=0, sequence=0, reply_size=0;
    unsigned channel=0, op=0, status=1;
    if (length>=HEADER_SIZE) {
        channel=input[4];op=input[5];sequence=read32(input+8);size=read32(input+12);
    }
    if (length<HEADER_SIZE || memcmp(input,"ZLK1",4) || input[6] || input[7] ||
        size>FRAME_SIZE-HEADER_SIZE-1 || length!=HEADER_SIZE+size+((HEADER_SIZE+size)%512U==0U))
        goto reply;
    if (channel==0 && op==0 && !size) {
        if (selectio_mem_active()) {status=2;goto reply;}
        if(selectio_combo_active()) selectio_combo_reset();
        session_open=1;
        next_sequence=sequence+1U;
        memcpy(output+16,"SIO1",4);
        write32(output+20,ps_fclk_decode(0xf8000180U));
        write32(output+24,swd_read32(SWD_FEATURES));
        write32(output+28,FRAME_SIZE);
        reply_size=16;
        status=0;
    } else if (!session_open || sequence!=next_sequence) {
        status=2;
    } else {
        next_sequence++;XTime_GetTime(&last_activity);
        if (channel==0 && op==1) {
            memcpy(output+HEADER_SIZE,input+HEADER_SIZE,size);
            reply_size=size;
            status=0;
        } else if(channel==0 && op==4 && !size) {
            uint32_t fields[8];selectio_cdc_status(fields);memcpy(output+16,fields,sizeof fields);reply_size=sizeof fields;status=0;
        } else if(channel==0 && op==3 && size==1) {
            if(!selectio_cdc_bind(input[16])) status=0;
        } else if (channel==0 && op==2 && size==4) {
            if(!selectio_live_profile(input[16],input[17],input[18],input[19])) status=0;
        } else if(channel==6) {
            unsigned n=0,source=0;
            if(!selectio_combo_frame(op,input+16,size,output+16,FRAME_SIZE-HEADER_SIZE-1,&reply_size,&n,&source)) {
                reply_packets=n;reply_channel=source;status=0;
            }
        } else if(channel==1 && selectio_combo_active()) status=2;
        else if (channel==1 && op==1 && size==4) {
            dap_wait_begin();
            if(!selectio_mem_open(input+16)) status=0;
        } else if (channel==1 && op==2 && !size) {
            dap_wait_begin();
            if(!selectio_mem_close()) status=0;
        } else if(channel==1 && op==4 && !size) {
            uint64_t values[9];
            selectio_mem_stats(values);memcpy(output+16,values,sizeof values);
            reply_size=sizeof values;status=0;
        } else if(channel==1 && (op==3 || op==6) && size>=8) {
            unsigned header=op==6?16U:8U;
            unsigned write=input[16],words=input[18]|((unsigned)input[19]<<8),completed=0;
            uint32_t detail=0;
            if(write<=1 && !input[17] && words && words<=1008 &&
               size==header+(write?4U*words:0U)) {
                int rc=selectio_mem_bulk(write,read32(input+20),words,input+16+header,output+16+header,&completed,&detail);
                write32(output+16,completed);write32(output+20,detail);
                if(header==16U) memset(output+24,0,8);
                reply_size=header+(!write && !rc?4U*words:0U);
                if(!rc) status=0;
            }
        } else if (channel==1 && op==0 && size && input[16]==0x8e) {
            dap_request_plan plan;
            if (DAP_ValidateCommand(input+16,size,FRAME_SIZE-HEADER_SIZE-1,&plan) &&
                plan.request_bytes==size && !probe_target_context_invalid()) {
                u32 flags=mfcpsr();
                mtcpsr(flags|0x80U);
                if (epoch!=active_epoch) {mtcpsr(flags);goto reply;}
                dap_wait_begin();
                mtcpsr(flags);
                int exclusive=selectio_mem_active();
                if (exclusive || !probe_before_dap()) {
                    reply_size=DAP_ExecuteCommand(input+16,size,output+16,FRAME_SIZE-HEADER_SIZE-1)&0xffffU;
                    if (reply_size>=2 && output[17]==DAP_OK && !dap_wait_command_error()) status=0;
                    if(!exclusive) probe_after_dap();
                }
            }
        } else if (channel==2 || channel==3) {
            if (op==0 && size==1) {
                if (!probe_native_route(channel,input[16])) status=0;
            } else if (op==1 && !size) {
                unsigned packets;
                reply_size=probe_native_peek(channel,output+HEADER_SIZE,FRAME_SIZE-HEADER_SIZE-1,&packets);
                reply_channel=channel;reply_packets=packets;status=0;
            } else if (op==2 && size==64 && !probe_native_control(channel,input+16,output+16)) {
                reply_size=64;status=0;
            }
        } else if(channel==4 || channel==5) {
            unsigned consume=0;
            if(!selectio_aux_frame(channel,op,input+16,size,output+16,FRAME_SIZE-HEADER_SIZE-1,&reply_size,&consume)) {
                reply_channel=channel;reply_packets=consume;status=0;
            }
        } else status=3;
    }
reply:
    memcpy(output,"ZLK1",4);
    output[4]=(u8)channel;output[5]=(u8)op;output[6]=(u8)status;output[7]=0;
    write32(output+8,sequence);write32(output+12,reply_size);
    length=HEADER_SIZE+reply_size;
    if (length%512U==0U) output[length++]=0;
    return length;
}

void selectio_usb_poll(XUsbPs *usb) {
    u32 length,active_epoch,flags;
    if(aux_reset) {aux_reset=0;selectio_aux_reset();}
    if(aux_commit) {unsigned n=aux_commit;aux_commit=0;selectio_aux_consume(n);}
    if(selectio_mem_active() && (++watchdog_div&4095U)==0) {
        XTime now;XTime_GetTime(&now);
        if(now-last_activity>2U*(uint64_t)COUNTS_PER_SECOND) close_pending=1;
    }
    if(close_pending) {
        dap_wait_begin();
        if(!selectio_mem_close()) {close_pending=0;selectio_combo_reset();}
        else return;
    }
    if(configured) selectio_combo_poll();
    if (!configured || (!rx_hint && !pending_length)) return;
    flags=mfcpsr();mtcpsr(flags|0x80U);
    active_epoch=epoch;
    if(pending_length && !tx_busy) {
        in_flight=output;tx_channel=reply_channel;tx_packets=reply_packets;
        tx_busy=1;
        if (XUsbPs_EpBufferSend(usb,4,in_flight,pending_length)==XST_SUCCESS) pending_length=0;
        else tx_busy=0;
    }
    if(pending_length || !rx_hint) {mtcpsr(flags);return;}
    /* A data block or echo may execute while a previous IN payload is
     * being transmitted. Queue peeks and control remain stop-and-wait, so
     * an uncommitted ring slot cannot be included in two replies. */
    int pipelined=received_length>=HEADER_SIZE &&
                  ((arrival[4]==1 && (arrival[5]==3 || arrival[5]==6)) ||
                   (arrival[4]==0 && arrival[5]==1));
    if((tx_busy || aux_commit) && !pipelined) {mtcpsr(flags);return;}
    length=received_length;memcpy(input,arrival,length);
    output=in_flight==reply_bank[0] ? reply_bank[1] : reply_bank[0];
    reply_packets=0;rx_hint=0;
    if(deferred) {deferred=0;selectio_usb_resume_rx(usb);}
    mtcpsr(flags);
    unsigned response=execute_frame(length,active_epoch);
    flags=mfcpsr();mtcpsr(flags|0x80U);
    if (configured && epoch==active_epoch) {
        Xil_DCacheFlushRange((UINTPTR)output,(response+31U)&~31U);
        pending_length=response;

    }
    mtcpsr(flags);
}
#endif
