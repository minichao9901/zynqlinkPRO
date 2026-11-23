#include "selectio_usb.h"
#include "usb_pipes.h"
#if DAP_SELECTIO
#include "DAP_config.h"
#include "DAP.h"
#include "selectio_mode.h"
#include "selectio_aux.h"
#include "selectio_block.h"
#include "swd_dma.h"
#include "etm_ddr_usb.h"
#include "selectio_combo.h"
#include "probe_stream.h"
#include "xil_cache.h"
#include "xtime_l.h"
#include "xusbps_endpoint.h"
#include <string.h>

/* Each endpoint owns its DMA buffer through the final IOC, independently
 * of the other endpoints. Request sequence numbers are scoped to OUT pipes. */
#define FRAME_SIZE 16384U
#define INITIAL_FRAME_SIZE 4096U
#define HEADER_SIZE 16U
#define PIPE_COUNT 5U
#define OUT_PIPE_COUNT 4U
enum { CONTROL_PIPE, MEMORY_PIPE, RTT_PIPE, SPI_PIPE, SCOPE_PIPE };
static const u8 endpoints[PIPE_COUNT] = {
    USB_NATIVE_CONTROL, USB_NATIVE_MEMORY, USB_NATIVE_RTT, USB_NATIVE_SPI, USB_NATIVE_SCOPE
};
typedef struct {
    u8 bank[2][FRAME_SIZE] __attribute__((aligned(32)));
    unsigned length;
    u32 next_sequence;
    volatile unsigned ready, deferred, next_bank;
} request_pipe;
typedef struct {
    u8 bank[2][FRAME_SIZE] __attribute__((aligned(32)));
    u8 *queued, *active;
    unsigned length, pending_channel, pending_count, active_channel, active_count;
    volatile unsigned busy;
} reply_pipe;
static request_pipe requests[OUT_PIPE_COUNT];
static reply_pipe replies[PIPE_COUNT];
static u8 transport_test_ram[65536] __attribute__((aligned(32)));
static const u8 *input;
static u8 *output;
static unsigned frame_limit, reply_channel, reply_packets;
static volatile unsigned epoch, configured, aux_commit, aux_reset, close_pending;
static unsigned watchdog_div, session_open, abandon_native, next_pipe;
static XTime last_activity;

static u32 read32(const u8 *p) {u32 v;memcpy(&v,p,4);return v;}
static void write32(u8 *p,u32 v) {memcpy(p,&v,4);}
static int pipe_index(unsigned ep) {
    for(unsigned i=0;i<PIPE_COUNT;i++) if(endpoints[i]==ep) return (int)i;
    return -1;
}

static unsigned receive_pipe(unsigned channel, unsigned op) {
    if(channel==8 || (channel==2 && op==1) || (channel==6 && op==1)) return RTT_PIPE;
    if(channel==4) return SPI_PIPE;
    if((channel==1 && (op==0 || op==3 || op==6)) || (channel==7 && op==6)) return MEMORY_PIPE;
    return CONTROL_PIPE;
}
static unsigned transmit_pipe(unsigned rx, unsigned channel, unsigned op) {
    if(rx==CONTROL_PIPE && ((channel==3 && op==1) || (channel==6 && op==2))) return SCOPE_PIPE;
    return rx;
}

void selectio_usb_setup(XUsbPs_DeviceConfig *config) {
    for(unsigned i=0;i<PIPE_COUNT;i++) {
        XUsbPs_EpConfig *ep=&config->EpCfg[endpoints[i]];
        ep->In=(XUsbPs_EpSetup){.Type=XUSBPS_EP_TYPE_BULK,.NumBufs=8,.MaxPacketSize=512};
        if(i!=SCOPE_PIPE)
            ep->Out=(XUsbPs_EpSetup){.Type=XUSBPS_EP_TYPE_BULK,.NumBufs=4,.MaxPacketSize=512,.BufSize=FRAME_SIZE};
    }
}
int selectio_usb_handlers(XUsbPs *usb) {
    for(unsigned i=0;i<PIPE_COUNT;i++) {
        unsigned ep=endpoints[i];
        if(XUsbPs_EpSetHandler(usb,ep,XUSBPS_EP_DIRECTION_IN,selectio_usb_event,usb)!=XST_SUCCESS ||
           (i!=SCOPE_PIPE && XUsbPs_EpSetHandler(usb,ep,XUSBPS_EP_DIRECTION_OUT,selectio_usb_event,usb)!=XST_SUCCESS))
            return XST_FAILURE;
    }
    return XST_SUCCESS;
}

void selectio_usb_reset(void) {
    configured=0;
    if(selectio_mem_active()) close_pending=1;
    selectio_combo_reset();
    epoch++;abandon_native=0;
    aux_reset=1;aux_commit=0;selectio_cdc_reset();selectio_swo_usb_reset();
    frame_limit=INITIAL_FRAME_SIZE;session_open=0;
    for(unsigned i=0;i<PIPE_COUNT;i++) {
        if(i<OUT_PIPE_COUNT) requests[i].ready=requests[i].deferred=requests[i].next_bank=0;
        replies[i].length=replies[i].busy=replies[i].active_count=0;
        replies[i].active=0;
    }
}
static void reset_in(XUsbPs *usb,unsigned ep,int reset_toggle) {
    XUsbPs_EpIn *in=&usb->DeviceConfig.Ep[ep].In;
    XUsbPs_EpFlush(usb,ep,XUSBPS_EP_DIRECTION_IN);
    XUsbPs_WriteReg(usb->Config.BaseAddress,XUSBPS_EPCOMPL_OFFSET,1U<<(16U+ep));
    for(unsigned i=0;i<usb->DeviceConfig.EpCfg[ep].In.NumBufs;i++) {
        XUsbPs_dTD *td=&in->dTDs[i];
        XUsbPs_dTDInvalidateCache(td);
        XUsbPs_WritedTD(td,XUSBPS_dTDTOKEN,0);
        XUsbPs_dTDFlushCache(td);
    }
    XUsbPs_ReconfigureEp(usb,&usb->DeviceConfig,ep,XUSBPS_EP_DIRECTION_IN,0);
    XUsbPs_dQHInvalidateCache(in->dQH);
    XUsbPs_WritedQH(in->dQH,XUSBPS_dQHdTDTOKEN,0);
    XUsbPs_WritedQH(in->dQH,XUSBPS_dQHdTDNLP,1);
    XUsbPs_dQHFlushCache(in->dQH);
    XUsbPs_EpEnable(usb,ep,XUSBPS_EP_DIRECTION_IN);
    XUsbPs_SetBits(usb,XUSBPS_EPCRn_OFFSET(ep),XUSBPS_EPCR_TXT_BULK_MASK|(reset_toggle?XUSBPS_EPCR_TXR_MASK:0U));
}
void selectio_usb_enable_in(XUsbPs *usb,unsigned ep) {reset_in(usb,ep,1);}
static void reset_out(XUsbPs *usb,unsigned ep) {
    XUsbPs_EpFlush(usb,ep,XUSBPS_EP_DIRECTION_OUT);
    XUsbPs_WriteReg(usb->Config.BaseAddress,XUSBPS_EPCOMPL_OFFSET,1U<<ep);
    XUsbPs_ReconfigureEp(usb,&usb->DeviceConfig,ep,XUSBPS_EP_DIRECTION_OUT,0);
    XUsbPs_dQH *qh=usb->DeviceConfig.Ep[ep].Out.dQH;
    XUsbPs_dQHInvalidateCache(qh);
    XUsbPs_WritedQH(qh,XUSBPS_dQHdTDTOKEN,0);
    XUsbPs_dQHFlushCache(qh);
}
void selectio_usb_configured(XUsbPs *usb) {
    selectio_usb_reset();
    for(unsigned i=0;i<PIPE_COUNT;i++) {
        unsigned ep=endpoints[i];
        selectio_usb_enable_in(usb,ep);
        if(i==SCOPE_PIPE) continue;
        reset_out(usb,ep);
        XUsbPs_EpEnable(usb,ep,XUSBPS_EP_DIRECTION_OUT);
        XUsbPs_SetBits(usb,XUSBPS_EPCRn_OFFSET(ep),XUSBPS_EPCR_RXT_BULK_MASK|XUSBPS_EPCR_RXR_MASK);
    }
    selectio_usb_enable_in(usb,USB_SWO_IN);
    configured=1;
    for(unsigned i=0;i<PIPE_COUNT;i++)
        if(i!=SCOPE_PIPE) XUsbPs_EpPrime(usb,endpoints[i],XUSBPS_EP_DIRECTION_OUT);
}

int selectio_usb_rx_available(unsigned ep) {
    int pipe=pipe_index(ep);
    if(pipe>=0 && pipe<(int)OUT_PIPE_COUNT && requests[pipe].ready) {requests[pipe].deferred=1;return 0;}
    return 1;
}
void selectio_usb_event(void *ref,u8 ep,u8 event,void *data) {
    XUsbPs *usb=(XUsbPs *)ref;
    int pipe=pipe_index(ep);
    if (!configured || pipe<0) return;
    if (event==XUSBPS_EP_EVENT_DATA_RX && (unsigned)pipe<OUT_PIPE_COUNT) {
        request_pipe *rx=&requests[pipe];
        u8 *buffer;
        u32 length,handle;
        if (rx->ready || XUsbPs_EpBufferReceive(usb,ep,&buffer,&length,&handle)!=XST_SUCCESS) return;
        if (length>FRAME_SIZE) length=0;
        Xil_DCacheInvalidateRange((UINTPTR)buffer,(length+31U)&~31U);
        memcpy(rx->bank[rx->next_bank],buffer,length);
        rx->length=length;
        __sync_synchronize();
        rx->ready=1;
        XUsbPs_EpBufferRelease(handle);
    } else if(event==XUSBPS_EP_EVENT_DATA_TX) {
        reply_pipe *tx=&replies[pipe];
        if(!tx->busy || data!=tx->active) return;
        if(tx->active_count && tx->active_channel>=6) selectio_combo_commit(tx->active_channel,tx->active_count);
        else if(tx->active_count && tx->active_channel>=4) aux_commit=tx->active_count;
        else if(tx->active_count) probe_native_commit(tx->active_channel,tx->active_count);
        tx->active_count=0;
        tx->busy=0;
    }
}
static unsigned execute_frame(unsigned length, unsigned active_epoch, unsigned rx_pipe) {
    if(!configured || epoch!=active_epoch) return 0;
    unsigned size=0, sequence=0, reply_size=0;
    unsigned channel=0, wire_channel=0, op=0, status=1;
    if (length>=HEADER_SIZE) {
        wire_channel=input[4];op=input[5];sequence=read32(input+8);size=read32(input+12);
        channel=wire_channel==8 ? 1 : wire_channel;
    }
    if (length<HEADER_SIZE || memcmp(input,"ZLK1",4) || input[6] || input[7] ||
        receive_pipe(wire_channel,op)!=rx_pipe || size>frame_limit-HEADER_SIZE-1 || length!=HEADER_SIZE+size+((HEADER_SIZE+size)%512U==0U))
        goto reply;
    if (channel==0 && op==0 && !size) {
        if (selectio_mem_active() || selectio_aux_native_owner() || probe_native_owns_stream()) {status=2;goto reply;}
        if(selectio_combo_active()) selectio_combo_reset();
        unsigned flags=mfcpsr();mtcpsr(flags|0x80U);
        if(epoch!=active_epoch) {mtcpsr(flags);return 0;}
        /* Leave USB DMA and data toggles intact on an application HELLO.
         * The host can still retire previously queued replies. They must
         * not commit cursors belonging to the newly started session. */
        for(unsigned i=1;i<PIPE_COUNT;i++)
            replies[i].active_count=replies[i].pending_count=0;
        frame_limit=INITIAL_FRAME_SIZE;
        session_open=1;
        for(unsigned i=0;i<OUT_PIPE_COUNT;i++) requests[i].next_sequence=sequence+1U;
        mtcpsr(flags);
        memcpy(output+16,"SIO2",4);
        write32(output+20,selectio_serial_hz());
        write32(output+24,swd_read32(SWD_FEATURES));
        write32(output+28,FRAME_SIZE);
        reply_size=16;
        status=0;
    } else if (!session_open || sequence!=requests[rx_pipe].next_sequence) {
        status=2;
    } else {
        requests[rx_pipe].next_sequence++;XTime_GetTime(&last_activity);
        if (channel==0 && op==1) {
            memcpy(output+HEADER_SIZE,input+HEADER_SIZE,size);
            reply_size=size;
            status=0;
        } else if(channel==0 && op==8 && size==4 && !selectio_mem_active() &&
                  !selectio_aux_native_owner() && !probe_native_owns_stream()) {
            unsigned requested=read32(input+16);
            if(requested==INITIAL_FRAME_SIZE || requested==FRAME_SIZE) {
                frame_limit=requested;write32(output+16,requested);reply_size=4;status=0;
            }
        } else if(channel==7 && op==7 && size==12) {
            if(!selectio_mem_active() && !probe_stream_active() && !etm_ddr_owned() &&
               (swd_read32(SWD_FEATURES)&0x400U) && read32(input+24)<=1U) {
                uint64_t values[7];
                unsigned fixed=read32(input+24);
                uint32_t original=Xil_In32(SLCR_FPGA0_CLK_CTRL);
                int hz=fixed ? ps_fixed133_select() : (int)ps_fclk0_hz();
                uint32_t ref=selectio_serial_hz();
                int measured=hz>0 ? selectio_dma_measure(read32(input+16),read32(input+20),values) : -1;
                if(Xil_In32(SLCR_FPGA0_CLK_CTRL)!=original) {
                    Xil_Out32(XSLCR_UNLOCK_ADDR,XSLCR_UNLOCK_CODE);
                    Xil_Out32(SLCR_FPGA0_CLK_CTRL,original);
                    Xil_Out32(SLCR_LOCK_ADDR,0x767bU);
                }
                if(!measured && Xil_In32(SLCR_FPGA0_CLK_CTRL)==original) {
                    memcpy(output+16,values,sizeof values);
                    write32(output+72,(uint32_t)hz);write32(output+76,ref);
                    write32(output+80,swd_read32(0x80010020U));
                    reply_size=68;status=0;
                }
            } else status=2;
        } else if(channel==7 && op==6 && size>=16) {
            // Isolated DDR loopback with exactly the SRAM bulk wire format.
            // The address is an offset within this buffer, never a physical pointer.
            unsigned wr=input[16],words=input[18]|((unsigned)input[19]<<8);
            uint32_t addr=read32(input+20);
            unsigned n=4U*words;
            if(wr<=1 && !input[17] && words && n<=frame_limit-33U &&
               addr>=0x20000000U && addr-0x20000000U<=sizeof transport_test_ram-n &&
               !(addr&3U) && size==16U+(wr?n:0U)) {
                u8 *ram=transport_test_ram+(addr-0x20000000U);
                if(wr)memcpy(ram,input+32,n);else memcpy(output+32,ram,n);
                memset(output+16,0,16);write32(output+16,words);
                reply_size=16U+(wr?0U:n);status=0;
            }
        } else if(channel==0 && op==5 && !size) {
            uint32_t pl=swd_read32(SWD_FEATURES);
            memcpy(output+16,"CAP2",4);
            write32(output+20,2U);
            write32(output+24,4U);
            write32(output+28,(pl&0x400U)?16U:8U);
            write32(output+32,(pl&0x200U)?SELECTIO_SERIAL_BUFFER_BYTES:0U);
            write32(output+36,ps_fclk0_hz());
            reply_size=24;status=0;
        } else if(channel==0 && op==4 && !size) {
            uint32_t fields[8];selectio_cdc_status(fields);memcpy(output+16,fields,sizeof fields);reply_size=sizeof fields;status=0;
        } else if(channel==0 && op==3 && size==1) {
            if(!selectio_cdc_bind(input[16])) status=0;
        } else if (channel==0 && op==2 && size==4) {
            if(!selectio_live_profile(input[16],input[17],input[18],input[19])) status=0;
        } else if(channel==9 && op==0 && size==28 && input[16]==0x8c) {
            dap_request_plan plan;
            if(DAP_ValidateCommand(input+16,size,frame_limit-HEADER_SIZE-1,&plan) && plan.request_bytes==size) {
                reply_size=DAP_ExecuteCommand(input+16,size,output+16,frame_limit-HEADER_SIZE-1)&0xffffU;
                status=0;
            }
        } else if(channel==6) {
            unsigned n=0,source=0;
            if(!selectio_combo_frame(op,input+16,size,output+16,frame_limit-HEADER_SIZE-1,&reply_size,&n,&source)) {
                reply_packets=n;reply_channel=source;status=0;
            }
        } else if(channel==1 && ((selectio_combo_active() && op!=5) || selectio_swd50_rtt_attached())) status=2;
        else if (channel==1 && op==1 && (size==4 || size==8)) {
            dap_wait_begin();
            if(!selectio_mem_open_at(input+16,size==8 ? read32(input+20) : 100000000U)) status=0;
        } else if (channel==1 && op==2 && !size) {
            dap_wait_begin();
            if(!selectio_mem_close()) status=0;
        } else if(channel==1 && op==5 && !size && selectio_mem_active()) {
            unsigned port=selectio_mem_port();
            uint32_t queue=port==1 ? 0x80010000U : 0x80000000U;
            write32(output+16,selectio_serial_hz());write32(output+20,port);
            write32(output+24,swd_read32(queue+(port==1 ? 0x0cU : 0x1cU)));
            write32(output+28,swd_read32(queue+(port==1 ? 0x18U : 0x0cU)));
            reply_size=16;status=0;
        } else if(channel==1 && op==4 && !size) {
            uint64_t values[9];
            selectio_mem_stats(values);memcpy(output+16,values,sizeof values);
            reply_size=sizeof values;status=0;
        } else if(channel==1 && (op==3 || op==6) && size>=8) {
            unsigned header=op==6?16U:8U;
            unsigned write=input[16],words=input[18]|((unsigned)input[19]<<8),completed=0;
            uint32_t detail=0;
            if(write<=1 && !input[17] && words && 4U*words<=frame_limit-HEADER_SIZE-header-1U &&
               size==header+(write?4U*words:0U)) {
                int rc=selectio_mem_bulk(write,read32(input+20),words,input+16+header,output+16+header,&completed,&detail);
                write32(output+16,completed);write32(output+20,detail);
                if(header==16U) memset(output+24,0,8);
                reply_size=header+(!write && !rc?4U*words:0U);
                if(!rc) status=0;
            }
        } else if (channel==1 && op==0 && size && input[16]==0x8e) {
            dap_request_plan plan;
            if (DAP_ValidateCommand(input+16,size,frame_limit-HEADER_SIZE-1,&plan) &&
                plan.request_bytes==size && !probe_target_context_invalid()) {
                u32 flags=mfcpsr();
                mtcpsr(flags|0x80U);
                if (epoch!=active_epoch) {mtcpsr(flags);goto reply;}
                dap_wait_begin();
                mtcpsr(flags);
                int exclusive=selectio_mem_active() && !selectio_swd50_rtt_attached();
                if (exclusive || !probe_before_dap()) {
                    reply_size=DAP_ExecuteCommand(input+16,size,output+16,frame_limit-HEADER_SIZE-1)&0xffffU;
                    if (reply_size>=2 && output[17]==DAP_OK && !dap_wait_command_error()) status=0;
                    if(!exclusive) probe_after_dap();
                }
            }
        } else if (channel==2 || channel==3) {
            if (op==0 && size==1) {
                if (!probe_native_route(channel,input[16])) status=0;
            } else if (op==1 && !size) {
                unsigned packets;
                reply_size=probe_native_peek(channel,output+HEADER_SIZE,frame_limit-HEADER_SIZE-1,&packets);
                reply_channel=channel;reply_packets=packets;status=0;
            } else if (op==2 && size==64 && !probe_native_control(channel,input+16,output+16)) {
                reply_size=64;status=0;
            }
        } else if(channel==4) {
            unsigned consume=0;
            if(!selectio_aux_frame(channel,op,input+16,size,output+16,frame_limit-HEADER_SIZE-1,&reply_size,&consume)) {
                reply_channel=channel;reply_packets=consume;status=0;
            }
        } else status=3;
    }
reply:
    memcpy(output,"ZLK1",4);
    output[4]=(u8)wire_channel;output[5]=(u8)op;output[6]=(u8)status;output[7]=0;
    write32(output+8,sequence);write32(output+12,reply_size);
    length=HEADER_SIZE+reply_size;
    if (length%512U==0U) output[length++]=0;
    return length;
}

static void send_replies(XUsbPs *usb) {
    for(unsigned i=0;i<PIPE_COUNT;i++) {
        reply_pipe *tx=&replies[i];
        if(!tx->length || tx->busy) continue;
        tx->active=tx->queued;tx->active_channel=tx->pending_channel;
        tx->active_count=tx->pending_count;tx->busy=1;
        if(XUsbPs_EpBufferSend(usb,endpoints[i],tx->active,tx->length)==XST_SUCCESS) tx->length=0;
        else tx->busy=0;
    }
}
static void run_request(XUsbPs *usb) {
    u32 flags=mfcpsr();mtcpsr(flags|0x80U);
    unsigned active_epoch=epoch;
    if(!configured) {mtcpsr(flags);return;}
    send_replies(usb);
    for(unsigned offset=0;offset<OUT_PIPE_COUNT;offset++) {
        unsigned i=(next_pipe+offset)%OUT_PIPE_COUNT;
        request_pipe *rx=&requests[i];
        if(!rx->ready) continue;
        unsigned length=rx->length;
        const u8 *frame=rx->bank[rx->next_bank];
        unsigned channel=length>=HEADER_SIZE?frame[4]:0,op=length>=HEADER_SIZE?frame[5]:0;
        reply_pipe *tx=&replies[transmit_pipe(i,channel,op)];
        /* Multiple bulk memory requests can execute ahead of IOC. A FIFO
         * peek waits for its own endpoint's prior cursor to be committed. */
        unsigned pipeline=i==MEMORY_PIPE && (op==3 || op==6);
        if(tx->length || (tx->busy && !pipeline) || (i==SPI_PIPE && aux_commit)) continue;
        input=frame;
        output=tx->active==tx->bank[0]?tx->bank[1]:tx->bank[0];
        rx->next_bank^=1U;rx->ready=0;reply_channel=reply_packets=0;
        if(rx->deferred) {rx->deferred=0;selectio_usb_resume_rx(usb,endpoints[i]);}
        next_pipe=(i+1)%OUT_PIPE_COUNT;
        mtcpsr(flags);
        unsigned response=execute_frame(length,active_epoch,i);
        flags=mfcpsr();mtcpsr(flags|0x80U);
        if(configured && epoch==active_epoch) {
            tx->queued=output;tx->pending_channel=reply_channel;tx->pending_count=reply_packets;
            tx->length=response;
        }
        mtcpsr(flags);
        return;
    }
    mtcpsr(flags);
}
void selectio_usb_poll(XUsbPs *usb) {
    if(aux_reset) {if(selectio_aux_reset())return;aux_reset=0;}
    if(aux_commit) {unsigned n=aux_commit;aux_commit=0;selectio_aux_consume(n);}
    selectio_aux_poll();
    if((++watchdog_div&1023U)==0) {
        XTime now;XTime_GetTime(&now);
        if(selectio_mem_active() && !selectio_swd50_rtt_attached() &&
           now-last_activity>2ULL*COUNTS_PER_SECOND) close_pending=1;
        if((selectio_aux_native_owner() || probe_native_owns_stream()) &&
           now-last_activity>5ULL*COUNTS_PER_SECOND) abandon_native=1;
    }
    if(abandon_native) {
        u32 flags=mfcpsr();mtcpsr(flags|0x80U);
        for(unsigned i=0;i<PIPE_COUNT;i++) replies[i].active_count=replies[i].pending_count=0;
        aux_commit=0;session_open=0;
        mtcpsr(flags);
        if(selectio_aux_release_native() || probe_native_abandon()) return;
        abandon_native=0;
    }
    if(close_pending) {
        dap_wait_begin();
        if(!selectio_mem_close()) {close_pending=0;selectio_combo_reset();}
        else return;
    }
    if(configured) selectio_combo_poll();
    run_request(usb);
}
#endif
