// Probe-side RTT bridge and HSS transport. USB IRQs only move bounded messages;
// target access, ownership changes and packet construction run in main.
#include "probe_stream.h"
#include "xil_cache.h"
#include "xil_exception.h"
#include "xil_io.h"
#include "xtime_l.h"
#include "xusbps_ch9.h"
#include "xusbps_class_cdc.h"
#include "xusbps_endpoint.h"
#include <string.h>

// The standalone host state-machine harness supplies claim/release stubs but
// does not link probe_target.c.  The ARM target provides the strong version.
__attribute__((weak)) int probe_target_claimed(void) { return 0; }

#define REG(n) (0x40010060U + 4U * (n))
#define R(n) Xil_In32(REG(n))
#define W(n, v) Xil_Out32(REG(n), (v))
#define PK(n) (0x42020000U+4U*(n))
#define PR(n) Xil_In32(PK(n))
#define PW(n,v) Xil_Out32(PK(n),(v))
static uint32_t link_clock(uint32_t fclk) {
    uint32_t cfg = Xil_In32(0x40010008U);
    uint32_t half_cycles = 1U + ((cfg >> 13) & 15U) + (((cfg >> 28) & 15U) << 4);
    return fclk / (2U * half_cycles);
}
extern int swd_dma_packet_to(uint32_t bank, uint32_t bytes, uint8_t *destination);
static uint8_t pl_packets, rtt_pl_running, rtt_paused, dma_pending;
static uint32_t dma_tail, dma_length;
#define QSIZE 8U
typedef struct {
#ifdef __arm__
    uint8_t *data;
    uint32_t stride;
#else
    // Keep the deterministic host harness layout intact; the ARM build uses
    // right-sized endpoint storage below to avoid wasting OCM on HSS/HID.
    uint8_t data[QSIZE][1024];
#endif
    uint16_t len[QSIZE];
    volatile uint32_t in, out;
    volatile uint8_t busy;
    uint8_t zlp;
    uintptr_t final;
    uint32_t completed;
    uint8_t ep;
} tx_queue;
#define CDC_SLOT_SIZE 2048U
static uint8_t cdc_data[QSIZE][CDC_SLOT_SIZE] __attribute__((aligned(32)));
static uint8_t hss_data[QSIZE][512] __attribute__((aligned(32)));
static uint8_t hid_data[QSIZE][64] __attribute__((aligned(32)));
#ifdef __arm__
static tx_queue cdc = {.data = &cdc_data[0][0], .stride = CDC_SLOT_SIZE, .ep = 3};
static tx_queue hss = {.data = &hss_data[0][0], .stride = 512, .ep = 7};
static tx_queue hid = {.data = &hid_data[0][0], .stride = 64, .ep = 6};
#else
static tx_queue cdc = {.ep = 3}, hss = {.ep = 7}, hid = {.ep = 6};
#endif
static uint8_t hid_rx[QSIZE][64];
static uint8_t cdc_zlp[32] __attribute__((aligned(32)));
static uint8_t cdc_needs_zlp;
static uint32_t cdc_activity;
static volatile uint32_t rx_in, rx_out, epoch;
static volatile uint8_t configured, reset_pending;
static uint32_t current_epoch;
static uint8_t stopping;
static uint8_t hss_fault_handled;
static uint8_t mode; // 0 stopped, 1 RTT, 2 HSS
static int8_t result;
static uint32_t requested_hz = 50000000, actual_hz;
static uint32_t swd_errors, yields;
static uint32_t irq_save(void) {
    uint32_t v = mfcpsr();
    mtcpsr(v | 0x80U);
    return v;
}
static void irq_restore(uint32_t v) { mtcpsr(v); }
static uint32_t get32(const uint8_t *p) {
    return p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static void put16(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
}
static void put32(uint8_t *p, uint32_t v) {
    put16(p, v);
    put16(p + 2, v >> 16);
}
static uint32_t now(void) {
    XTime t;
    XTime_GetTime(&t);
    return (uint32_t)((t / COUNTS_PER_SECOND) * 24000000ULL +
                      ((t % COUNTS_PER_SECOND) * 24000000ULL) / COUNTS_PER_SECOND);
}
int probe_session_live(void) { return configured && !reset_pending && current_epoch == epoch; }
static int space(tx_queue *q) { return (uint32_t)(q->in - q->out) < QSIZE; }
static uint8_t *slot(tx_queue *q) {
#ifdef __arm__
    return q->data + (q->in % QSIZE) * q->stride;
#else
    return q->data[q->in % QSIZE];
#endif
}
static int publish(tx_queue *q, uint32_t len) {
    uint32_t f = irq_save();
    if (!probe_session_live() || !space(q)) {
        irq_restore(f);
        return -7;
    }
    q->len[q->in % QSIZE] = (uint16_t)len;
    __sync_synchronize();
    q->in++;
    irq_restore(f);
    return 0;
}
static void kick(XUsbPs *usb, tx_queue *q) {
    uint32_t f = irq_save();
    int rc;
    uint8_t *p;
    uint32_t len;
    if (!probe_session_live() || q->busy) {
        irq_restore(f);
        return;
    }
    if(q->in==q->out) {
        // Windows CDC may retain an integral max-packet tail until a short
        // packet terminates its URB. Flush once after 1 ms of inactivity;
        // never add a ZLP between chunks of a sustained transfer.
        if(q==&cdc && cdc_needs_zlp && (uint32_t)(now()-cdc_activity)>=24000) {
            q->busy=1;q->zlp=1;q->final=(uintptr_t)cdc_zlp;
            if(XUsbPs_EpBufferSend(usb,q->ep,cdc_zlp,0)!=XST_SUCCESS) q->busy=q->zlp=0;
        }
        irq_restore(f);return;
    }
#ifdef __arm__
    p = q->data + (q->out % QSIZE) * q->stride;
#else
    p = q->data[q->out % QSIZE];
#endif
    len = q->len[q->out % QSIZE];
    q->final = (uintptr_t)p;
    q->busy = 1;
    q->zlp=0;
    // CDC is a byte stream; don't append a ZLP to every internal chunk.
    rc = XUsbPs_EpBufferSend(usb, q->ep, p, len);
    if (rc != XST_SUCCESS)
        q->busy = 0; // Keep the same slot for retry.
    else if(q==&cdc) {
        uint32_t mps=usb->DeviceConfig.EpCfg[q->ep].In.MaxPacketSize;
        if(!mps) mps=512;
        cdc_needs_zlp=(len%mps)==0;cdc_activity=now();
    }
    irq_restore(f);
}
const uint8_t probe_hid_report[] = {0x06, 0x00, 0xff, 0x09, 0x01, 0xa1, 0x01, 0x15, 0x00, 0x26,
                                    0xff, 0x00, 0x75, 0x08, 0x95, 0x3f, 0x85, 0x01, 0x09, 0x01,
                                    0x91, 0x02, 0x85, 0x02, 0x09, 0x01, 0x81, 0x02, 0xc0};
const uint32_t probe_hid_report_size = sizeof(probe_hid_report);
uint32_t probe_hid_descriptor(uint8_t *out, uint32_t capacity, int report) {
    const uint8_t desc[] = {9, 0x21, 0x11, 1, 0, 1, 0x22, sizeof(probe_hid_report), 0};
    uint32_t n = report ? sizeof(probe_hid_report) : sizeof(desc);
    if (capacity < n)
        return 0;
    memcpy(out, report ? probe_hid_report : desc, n);
    return n;
}
void probe_usb_event(void *ref, u8 ep, u8 event, void *data) {
    XUsbPs *usb = (XUsbPs *)ref;
    tx_queue *q;
    if (event == XUSBPS_EP_EVENT_DATA_TX) {
        q = ep == 3 ? &cdc : ep == 7 ? &hss : &hid;
        if (configured && q->busy && q->final == (uintptr_t)data) {
            if(q->zlp) {q->zlp=0;cdc_needs_zlp=0;}
            else {q->out++;q->completed++;}
            q->busy = 0;
        }
    } else if (event == XUSBPS_EP_EVENT_DATA_RX && ep == 6) {
        uint8_t *p;
        u32 len, handle;
        if ((uint32_t)(rx_in - rx_out) >= QSIZE)
            return;
        if (XUsbPs_EpBufferReceive(usb, ep, &p, &len, &handle) != XST_SUCCESS)
            return;
        Xil_DCacheInvalidateRange((UINTPTR)p, (len + 31) & ~31U);
        if (len == 64) {
            memcpy(hid_rx[rx_in % QSIZE], p, 64);
            __sync_synchronize();
            rx_in++;
        }
        XUsbPs_EpBufferRelease(handle);
        XUsbPs_EpPrime(usb, ep, XUSBPS_EP_DIRECTION_OUT);
    }
}
void probe_usb_reset(void) {
    configured = 0;
    epoch++;
    reset_pending = 1;
}
static void reset_in(XUsbPs *usb, unsigned ep) {
    unsigned i;
    XUsbPs_EpFlush(usb, ep, XUSBPS_EP_DIRECTION_IN);
    for (i = 0; i < usb->DeviceConfig.EpCfg[ep].In.NumBufs; i++) {
        XUsbPs_dTD *td = &usb->DeviceConfig.Ep[ep].In.dTDs[i];
        XUsbPs_dTDInvalidateCache(td);
        XUsbPs_WritedTD(td, XUSBPS_dTDTOKEN, 0);
        XUsbPs_dTDFlushCache(td);
    }
    XUsbPs_ReconfigureEp(usb, &usb->DeviceConfig, ep, XUSBPS_EP_DIRECTION_IN, 0);
    XUsbPs_dQHInvalidateCache(usb->DeviceConfig.Ep[ep].In.dQH);
    XUsbPs_WritedQH(usb->DeviceConfig.Ep[ep].In.dQH, XUSBPS_dQHdTDTOKEN, 0);
    XUsbPs_WritedQH(usb->DeviceConfig.Ep[ep].In.dQH, XUSBPS_dQHdTDNLP, 1);
    XUsbPs_dQHFlushCache(usb->DeviceConfig.Ep[ep].In.dQH);
}
void probe_usb_configured(XUsbPs *usb) {
    probe_usb_reset();
    reset_in(usb, 3);
    reset_in(usb, 6);
    reset_in(usb, 7);
    XUsbPs_EpFlush(usb, 6, XUSBPS_EP_DIRECTION_OUT);
    XUsbPs_ReconfigureEp(usb, &usb->DeviceConfig, 6, XUSBPS_EP_DIRECTION_OUT, 0);
    XUsbPs_EpEnable(usb, 6, XUSBPS_EP_DIRECTION_IN);
    XUsbPs_EpEnable(usb, 6, XUSBPS_EP_DIRECTION_OUT);
    XUsbPs_EpEnable(usb, 7, XUSBPS_EP_DIRECTION_IN);
    XUsbPs_SetBits(usb, XUSBPS_EPCRn_OFFSET(6),
                   XUSBPS_EPCR_TXT_INTR_MASK | XUSBPS_EPCR_RXT_INTR_MASK | XUSBPS_EPCR_TXR_MASK |
                       XUSBPS_EPCR_RXR_MASK);
    XUsbPs_SetBits(usb, XUSBPS_EPCRn_OFFSET(7), XUSBPS_EPCR_TXT_BULK_MASK | XUSBPS_EPCR_TXR_MASK);
    XUsbPs_EpPrime(usb, 6, XUSBPS_EP_DIRECTION_OUT);
    configured = 1;
}

typedef struct {
    uint32_t addr;
    uint8_t size, type, word, offset;
} variable;
static variable vars[8];
static uint32_t addresses[24], period = 2400, step = 100, plan_hash;
static uint32_t bench_requested,bench_count,bench_ticks;
static int32_t bench_error;
static uint8_t bench_active;
static uint8_t nvars, nwords, frame_size, version = 1, flags, direct_layout;
static uint32_t produced, seq, formatted, fill_count, fill_time, last_stamp;
static uint32_t skipped_base, tx_done_base, fill_started;
static uint64_t elapsed;
static uint8_t fill[512] __attribute__((aligned(32)));
static int have_stamp;
static uint32_t rtt_base = 0x20000000, rtt_size = 65536, scan, cb, up, drained, polls, drains,
                write_errors;
static uint32_t pending_rd, pending_len, chunk = CDC_SLOT_SIZE;
static uint8_t channel, discard;
static uint32_t backoff;

static void packet_config(uint32_t index,uint32_t value) { PW(6,index);PW(7,value); }
static void packet_poll(void) {
    tx_queue *q=mode==1 ? &cdc : &hss;
    uint32_t d,tail;
    if(!probe_session_live()) return;
    if(dma_pending) {
        // RTT ACK means DDR is durable. Publish to USB only after the target
        // RdOff write and DP RDBUFF completion advance the PL consumer index.
        tail=PR(3);
        if(tail==dma_tail) {
            if(PR(1)&0x80U) PW(3,1); // Retry the same idempotent RdOff write.
            return;
        }
        if(!discard && publish(&cdc,dma_length)) return;
        drained+=dma_length;drains++;dma_pending=0;
    }
    d=PR(2);
    if(!(d&0xfffU) || !space(q)) return;
    uint32_t bytes=d&0xfffU;
    if(!((mode==1 && discard) || (mode==2 && (flags&2))) &&
       swd_dma_packet_to((d>>16)&7U,bytes,slot(q))) {
        result=-4;swd_errors++;return; // No ACK: immutable bank can be retried.
    }
    uint32_t irq_flags=irq_save();
    if(!probe_session_live()) { irq_restore(irq_flags);return; }
    if(mode==1) {
        dma_length=bytes;dma_tail=PR(3);dma_pending=1;PW(3,1);
    } else {
        PW(3,1);
        if(!(flags&2)) publish(&hss,bytes);
        formatted+=bytes;
    }
    irq_restore(irq_flags);
}

static int sampler_stop(void) {
    uint32_t budget = 1000000;
    W(0, 0);
    if(pl_packets) PW(0,0);
    while ((R(1) & 2) && --budget) {
    }
    if (!budget) {
        Xil_Out32(0x40010050, 1);
        swd_errors++;
        result = -4;
        return -4;
    }
    return 0;
}
static void header(uint8_t *p, uint8_t kind, uint32_t t, uint16_t n, uint16_t aux) {
    put16(p, 0x4a53);
    p[2] = version;
    p[3] = kind;
    put32(p + 4, seq++);
    put32(p + 8, t);
    put16(p + 12, n);
    put16(p + 14, aux);
}
static int flush_data(void) {
    uint8_t *p;
    if (!fill_count)
        return 0;
    if (!space(&hss))
        return -7;
    p = slot(&hss);
    header(p, 2, fill_time, (uint16_t)fill_count, (uint16_t)(fill_count * frame_size));
    memcpy(p + 16, fill + 16, fill_count * frame_size);
    if (!(flags & 2) && publish(&hss, 512))
        return -7;
    formatted += 512;
    fill_count = 0;
    return 0;
}
static void definition(void) {
    uint8_t *p = slot(&hss), *q;
    unsigned i;
    header(p, 1, 0, 0, nvars);
    q = p + 16;
    put32(q, actual_hz);
    put32(q + 4, step);
    put16(q + 8, flags);
    q[10] = nvars;
    q[11] = nvars;
    for (i = 0; i < nvars; i++) {
        put32(q + 12 + 8 * i, vars[i].addr);
        q[16 + 8 * i] = vars[i].size;
        q[17 + 8 * i] = vars[i].type;
    }
    publish(&hss, 512);
    formatted += 512;
}
static void stat_packet(void) {
    uint8_t *p, *q;
    if (!space(&hss) || (flags & 2))
        return;
    p = slot(&hss);
    header(p, 3, fill_time, 0, 0);
    q = p + 16;
    put32(q, produced);
    put32(q + 4, skipped_base + R(7));
    put32(q + 8, seq);
    put16(q + 14, swd_errors);
    put32(q + 16, step);
    q[20] = (uint8_t)(actual_hz / 1000000);
    publish(&hss, 512);
    formatted += 512;
}
static int sampler_arm(void) {
    unsigned i;
    if ((R(0) >> 16) != 0x4853)
        return -10;
    int rc = probe_target_claim(requested_hz);
    if (rc)
        return rc;
    uint32_t fclk = probe_target_fclk();
    if (fclk < 24000000) {
        probe_target_release();
        return -6;
    }
    actual_hz = link_clock(fclk);
    W(6, fclk);
    W(4, period);
    for (i = 0; i < nwords; i++) {
        W(2, i);
        W(3, addresses[i]);
    }
    if(pl_packets) {
        unsigned k=0,j;
        packet_config(0,frame_size);packet_config(1,version);
        packet_config(2,period);packet_config(5,nwords);
        for(i=0;i<nvars;i++) for(j=0;j<vars[i].size;j++)
            packet_config(16+k++,4*vars[i].word+vars[i].offset+j);
        PW(0,1);
    }
    W(7, now()); // Rebase after a DAP clock change while the sampler was paused.
    W(0, 1 | ((uint32_t)nwords << 8));
    return 0;
}
void probe_before_dap(void) {
    if(bench_active){bench_active=0;bench_error=-7;}
    if(pl_packets && mode==1 && rtt_pl_running) {
        uint32_t budget=1000000;
        PW(0,0);
        rtt_paused=1;
        while(((PR(1)&8U) || (Xil_In32(0x40010004)&1U)) && --budget) { }
        if(!budget) { Xil_Out32(0x40010050,1);rtt_pl_running=0;dma_pending=0;mode=0;result=-4; }
    }
    if (mode == 2) {
        if (sampler_stop()) {
            mode = 0;
            stopping = 0;
        }
        yields++;
    }
    // Read and restore AP registers while the PL core is quiescent.
    probe_target_release();
}
void probe_after_dap(void) {
    if(pl_packets && mode==1 && rtt_pl_running && !stopping && probe_session_live()) {
        int rc=probe_target_claim(requested_hz);
        if(rc && rc!=-7) { mode=0;result=-4; }
        else if(!rc && (discard || usbd_cdc_acm_get_dtr())) { PW(0,2);rtt_paused=0; }
    }
    if (mode == 2 && !stopping && probe_session_live()) {
        int rc=sampler_arm();
        if(rc && rc!=-7) { mode=0;result=-4;swd_errors++; }
    }
}
static void hss_poll(void) {
    if(pl_packets) {
        packet_poll();produced=PR(4);seq=PR(5);
        if(((R(1)&16) || (PR(1)&0x40U)) && !hss_fault_handled) {
            hss_fault_handled=1;result=-4;swd_errors++;sampler_stop();
            skipped_base+=R(7);W(0,2);stopping=1;
        }
        return;
    }
    // The RTL fixed-address pipe can publish much faster than the old
    // timestamp+TAR path.  Drain a larger bounded batch per main-loop pass,
    // otherwise STOP spends many HID round trips emptying a full FIFO.
    unsigned budget = 128, i, k;
    uint32_t sample[24], stamp, t;
    if (R(1) & 16) {
        result = -4;
        swd_errors++;
        sampler_stop();
        probe_target_release();
        mode = 0;
        return;
    }
    while (budget-- && (R(1) >> 16) && probe_session_live()) {
        if (!space(&hss))
            break;
        stamp = R(5);
        if (!have_stamp) {
            have_stamp = 1;
            last_stamp = stamp;
            elapsed = 0;
        } else {
            elapsed += (uint32_t)(stamp - last_stamp);
            last_stamp = stamp;
        }
        if (!have_stamp) {
            have_stamp = 1;
            last_stamp = stamp;
            elapsed = 0;
        } else {
            elapsed += (uint32_t)(stamp - last_stamp);
            last_stamp = stamp;
        }
        t = version == 2 ? stamp : (uint32_t)(elapsed / 24);
        // A missed deadline is represented by the RTL skipped counter.  Keep
        // packing the valid samples into the same fixed-period frame instead
        // of flushing a one-sample USB packet on every timestamp gap.  The
        // STAT stream reports the accumulated jump count separately.
        if (!fill_count) {
            fill_time = t;
            fill_started = now();
        }
        k = 16 + fill_count * frame_size;
        if (direct_layout) {
            // The common scope case is a contiguous list of aligned u32s.
            // Read straight into the packet staging area and avoid the
            // sample[] gather plus a second memcpy per variable.
            for (i = 0; i < nwords; i++)
                put32(fill + k + 4 * i, R(5));
        } else {
            for (i = 0; i < nwords; i++)
                sample[i] = R(5);
            for (i = 0; i < nvars; i++) {
                memcpy(fill + k, ((uint8_t *)sample) + vars[i].word * 4 + vars[i].offset, vars[i].size);
                k += vars[i].size;
            }
        }
        produced++;
        fill_count++;
        if (16 + (fill_count + 1) * frame_size > 512) {
            flush_data();
            if (seq % 64 == 0)
                stat_packet();
        }
    }
    if (fill_count && (uint32_t)(now() - fill_started) >= 240000)
        flush_data();
}
static int rtt_commit(void) {
    if (!pending_len)
        return 0;
    if (probe_target_write_word(up + 16, pending_rd)) {
        write_errors++;
        return -4;
    }
    if (!discard && publish(&cdc, pending_len))
        return -7;
    drained += pending_len;
    drains++;
    pending_len = 0;
    return 0;
}
static int stop(void) {
    if(bench_active){bench_active=0;bench_error=-7;}
    int rc = 0;
    if(pl_packets && mode) {
        stopping=1;PW(0,0);
        if(mode==2) { W(0,0);hss_poll(); }
        else if(rtt_pl_running) {
            uint32_t budget=10000;
            do {
                packet_poll();
                if(!(PR(1)&8U) && !(PR(2)&0xfffU) && !dma_pending) break;
                if(!space(&cdc)) break;
            } while(--budget && probe_session_live());
        }
        if((PR(1)&12U) || (PR(2)&0xfffU) || dma_pending ||
           (mode==2 && (R(1)>>16))) return -7;
        // A partial HSS packet is flushed autonomously after sampler stop.
        // Give its state machine time to publish before releasing SWD.
        if(mode==2) {
            uint32_t i;
            for(i=0;i<256;i++) (void)PR(1);
            packet_poll();
            if(PR(2)&0xfffU) return -7;
            // hss_poll() observed these before the final partial packet was
            // published. Refresh after draining it so STAT cannot reuse its
            // sequence number or under-report its last sample.
            produced=PR(4);
            seq=PR(5);
        }
        if(mode==2) stat_packet();
        probe_target_release();mode=0;stopping=0;rtt_pl_running=0;return 0;
    }
    if (mode == 2) {
        stopping = 1;
        rc = sampler_stop();
        hss_poll();
        if (flush_data() || (R(1) >> 16))
            return -7;
        stat_packet();
    }
    if (mode == 1 && pending_len) {
        if (probe_target_claim(requested_hz))
            return -4;
        rc = rtt_commit();
        if (rc) {
            probe_target_release();
            return rc;
        }
    }
    probe_target_release();
    mode = 0;
    stopping = 0;
    return rc;
}
static void rtt_poll(void) {
    uint8_t desc[24], search[256];
    uint32_t size, wr, rd, n, a, i;
    int rc = 0;
    if(pl_packets && rtt_pl_running) {
        if(!stopping && !discard && !usbd_cdc_acm_get_dtr()) {
            if(!rtt_paused) { PW(0,0);rtt_paused=1; }
            if(dma_pending) packet_poll();
            return;
        }
        if(!stopping && rtt_paused) {
            if(!probe_target_claimed() && probe_target_claim(requested_hz)) return;
            PW(0,2);rtt_paused=0;
        }
        packet_poll();polls=PR(13);
        if((PR(1)&0x80U) && !dma_pending && !(PR(2)&0xfffU)) {
            PW(0,0);result=-4;swd_errors++;rtt_pl_running=0;cb=up=0;
            if(Xil_In32(0x40010004)&1U) { Xil_Out32(0x40010050,1);probe_target_forget(); }
            else probe_target_release();
            backoff=now()+240000;
        }
        return;
    }
    if (backoff && (int32_t)(now() - backoff) < 0)
        return;
    if (!discard && (!usbd_cdc_acm_get_dtr() || !space(&cdc)))
        return;
    // Keep the SWD context claimed between polls.  probe_before_dap() still
    // releases it when a real DAP command arrives, so ownership remains
    // safe while the steady RTT path avoids a full save/restore per chunk.
    if (!probe_target_claimed()) {
        rc = probe_target_claim(requested_hz);
        if (rc) {
            swd_errors++;
            result = (int8_t)rc;
            backoff = now() + 240000;
            return;
        }
    }
    actual_hz = link_clock(probe_target_fclk());
    if (pending_len) {
        rc = rtt_commit();
        goto end;
    }
    if (!cb) {
        n = rtt_size - scan;
        if (n > sizeof(search))
            n = sizeof(search);
        a = rtt_base + scan;
        if (probe_target_read(a, search, n)) {
            rc = -4;
            goto end;
        }
        for (i = 0; i + 24 <= n; i += 4)
            if (!memcmp(search + i, "SEGGER RTT", 10)) {
                uint32_t channels = get32(search + i + 16), down = get32(search + i + 20);
                if (channels && channels <= 16 && down <= 16 && channel < channels &&
                    a + i <= UINT32_MAX - 24 - 24U * channels) {
                    cb = a + i;
                    up = cb + 24 + 24U * channel;
                    break;
                }
            }
        // Overlap descriptor header so a signature at the boundary is found.
        if (n <= 24 || scan + n >= rtt_size) {
            scan = 0;
            if (!cb)
                result = -3;
        } else
            scan += n - 24;
        goto end;
    }
    polls++;
    if (probe_target_read(up, desc, 24)) {
        rc = -4;
        goto end;
    }
    a = get32(desc + 4);
    size = get32(desc + 8);
    wr = get32(desc + 12);
    rd = get32(desc + 16);
    if (!a || size < 2 || size > 0x1000000 || a > UINT32_MAX - size || wr >= size || rd >= size) {
        cb = up = 0;
        rc = -6;
        goto end;
    }
    n = wr >= rd ? wr - rd : size - rd;
    if (n > chunk)
        n = chunk;
    if (!n)
        goto end;
    if(pl_packets) {
        PW(0,0x100);PW(8,up);PW(9,a);PW(10,size);PW(11,rd);PW(12,chunk);
        PW(0,2);rtt_pl_running=1;rtt_paused=0;goto end;
    }
    if (probe_target_read(a + rd, slot(&cdc), n)) {
        rc = -4;
        goto end;
    }
    if (!probe_session_live())
        goto end;
    pending_len = n;
    pending_rd = rd + n;
    if (pending_rd == size)
        pending_rd = 0;
    rc = rtt_commit();
end:
    if (rc)
        probe_target_release();
    if (rc) {
        swd_errors++;
        result = (int8_t)rc;
        backoff = now() + 240000;
    } else
        result = 0;
}
static void status(uint8_t cmd, uint32_t out[12], int metrics) {
    memset(out, 0, 48);
    if (cmd == 0x31) {
        out[0] = (mode == 1) | ((uint32_t)channel << 8) | (1U << 16);
        out[1] = cb;
        out[2] = up;
        out[3] = drained;
        out[4] = (polls & 65535) | (drains << 16);
        out[5] = (swd_errors & 65535) | (write_errors << 16);
        out[10] = (uint32_t)(int32_t)result;
        out[11] = chunk | ((uint32_t)discard << 16) | ((actual_hz / 1000000) << 24);
    } else if (metrics) {
        out[0] = 0x31535348;
        out[1] = now();
        out[2] = 24000000;
        out[3] = produced;
        out[4] = skipped_base + R(7);
        out[6] = swd_errors;
        out[7] = yields;
        out[8] = hss.completed - tx_done_base;
        out[9] = formatted;
        out[10] = period;
        out[11] = flags | ((uint32_t)(mode == 2) << 8);
    } else {
        out[0] = (mode == 2) | ((uint32_t)(mode == 2) << 16) | (1U << 2) | (1U << 4) |
                 ((uint32_t)nvars << 8) | ((uint32_t)nvars << 24);
        out[1] = actual_hz;
        out[2] = produced;
        out[3] = skipped_base + R(7);
        out[4] = formatted & 65535;
        out[5] = (swd_errors & 65535) | (yields << 16);
        out[6] = seq;
        out[7] = out[3] & 65535;
        out[8] = plan_hash;
        out[9] = (hss.completed - tx_done_base) << 16;
        out[10] = (uint32_t)(int32_t)result;
        out[11] = (step & 65535) | ((uint32_t)(version == 2) << 17) |
                  ((uint32_t)((flags & 2) != 0) << 16) | ((actual_hz / 1000000) << 24);
    }
}
static int configure_hss(const uint8_t *req) {
    variable plan[8], v;
    uint32_t p = get32(req + 4), hash = 0x811c9dc5;
    unsigned i, j, w = 0, bytes = 0;
    uint8_t n = req[9], f = req[8];
    if (mode == 2 || bench_active)
        return -7;
    if (!n || n > 8 || req[1] < 8 + 6 * n || (f & 0x44))
        return -6; // No RISC-V/trigger backend.
    for (i = 0; i < n; i++) {
        const uint8_t *q = req + 10 + 6 * i;
        plan[i].addr = get32(q);
        plan[i].size = q[4];
        plan[i].type = q[5];
        if ((q[4] != 1 && q[4] != 2 && q[4] != 4 && q[4] != 8) || q[5] > 7 ||
            get32(q) > UINT32_MAX - (q[4] - 1))
            return -6;
    }
    for (i = 1; i < n; i++) {
        v = plan[i];
        j = i;
        while (j && plan[j - 1].addr > v.addr) {
            plan[j] = plan[j - 1];
            j--;
        }
        plan[j] = v;
    }
    for (i = 0; i < n; i++) {
        uint8_t raw[6];
        uint32_t a = plan[i].addr & ~3U;
        plan[i].offset = (uint8_t)(plan[i].addr & 3);
        for (j = 0; j < (unsigned)(plan[i].offset + plan[i].size + 3) / 4; j++) {
            unsigned k;
            for(k=0;k<w && addresses[k]!=a+4*j;k++) { }
            if(j==0) plan[i].word=(uint8_t)k;
            if(k==w) addresses[w++]=a+4*j;
        }
        bytes += plan[i].size;
        put32(raw, plan[i].addr);
        raw[4] = plan[i].size;
        raw[5] = plan[i].type;
        for (j = 0; j < 6; j++) {
            hash ^= raw[j];
            hash *= 0x01000193;
        }
    }
    memcpy(vars, plan, sizeof(plan));
    nvars = n;
    nwords = (uint8_t)w;
    frame_size = (uint8_t)bytes;
    flags = f;
    version = req[3] == 10 ? 2 : 1;
    if (version == 1) {
        if (p < 2)
            p = 2;
        if (p > 1000000)
            p = 1000000;
        step = p;
        period = p * 24;
    } else {
        if (p < 24)
            p = 24;
        if (p > 24000000)
            p = 24000000;
        step = period = p;
    }
    direct_layout = 1;
    for (i = 0; i < n; i++)
        if (plan[i].size != 4 || (plan[i].addr & 3) ||
            (i && plan[i].addr != plan[i - 1].addr + 4))
            direct_layout = 0;
    plan_hash = hash;
    return 0;
}
static void control(const uint8_t *req, uint8_t *res) {
    uint32_t words[12];
    unsigned i;
    uint8_t cmd = req[2], act = req[3];
    int rc = 0;
    memset(res, 0, 64);
    res[0] = 2;
    res[2] = cmd;
    res[1] = 2;
    if (req[0] != 1 || req[1] < 1 || req[1] > 62) {
        res[3] = (uint8_t)-6;
        return;
    }
    if (cmd == 0x10 || cmd == 0x11 || cmd == 0x13) {
        const char *s = cmd == 0x10 ? "ZynqLinkPro" : cmd == 0x11 ? "12345678" : "0.5-orbtrace";
        size_t n = strlen(s);
        memcpy(res + 3, s, n);
        res[1] = (uint8_t)(1 + n);
        return;
    }
    if ((cmd != 0x31 && cmd != 0x32) || req[1] < 2) {
        res[3] = (uint8_t)-9;
        return;
    }
    switch (act) {
    case 0:
        rc = stop();
        break;
    case 1:
    case 3:
        if (cmd == 0x32 && act == 3) {
            if (req[1] < 6 || mode || bench_active) {
                rc = -7;
                break;
            }
            uint32_t hz = get32(req + 4);
            if (hz && (hz < 15000000 || hz > 60000000)) {
                rc = -6;
                break;
            }
            if (hz)
                requested_hz = hz;
            break;
        }
        if (cmd == 0x31 && act == 1 && req[1] < 11) {
            rc = -6;
            break;
        }
        if ((rc = stop()))
            break;
        if (cmd == 0x31) {
            if (cdc.in != cdc.out) {
                rc = -7;
                break;
            }
            if (act == 1) {
                rtt_base = get32(req + 4);
                rtt_size = get32(req + 8);
                channel = req[12];
            } else {
                rtt_base = 0x20000000;
                rtt_size = 65536;
                channel = 0;
            }
            if (!rtt_base)
                rtt_base = 0x20000000;
            if (!rtt_size)
                rtt_size = 65536;
            if ((rtt_base & 3) || rtt_size < 24 || rtt_base > UINT32_MAX - rtt_size ||
                channel >= 16) {
                rc = -6;
                break;
            }
            cb = up = scan = drained = polls = drains = pending_len = write_errors = swd_errors =
                backoff = 0;
            rtt_pl_running=rtt_paused=dma_pending=0;
            mode = 1;
            actual_hz = requested_hz;
        } else {
            if (!nvars) {
                rc = -3;
                break;
            }
            if (hss.in != hss.out) {
                rc = -7;
                break;
            }
            W(0, 2);
            if(pl_packets) PW(0,0x100);
            produced = seq = formatted = fill_count = skipped_base = yields = swd_errors = 0;
            tx_done_base = hss.completed;
            have_stamp = 0;
            hss_fault_handled=0;
            rc = sampler_arm();
            if (!rc) {
                mode = 2;
                definition();
            }
        }
        break;
    case 2:
        break;
    case 8:
        if(cmd!=0x32 || req[1]<6 || !nwords || mode || bench_active){rc=-7;break;}
        bench_requested=get32(req+4);
        if(!bench_requested || bench_requested>10000){rc=-6;break;}
        bench_count=bench_ticks=0;bench_error=-1;bench_active=1;
        break;
    case 9:
        if(cmd!=0x32)rc=-9;
        break;
    case 7:
    case 10:
        if (cmd == 0x32) {
            rc = configure_hss(req);
            if (rc == -6 && mode != 2)
                nvars = nwords = frame_size = 0;
        } else if (act == 10)
            rc = req[1] >= 3 && req[4] == 0 ? 0 : -9;
        else if (req[1] < 10 || mode == 2 || pending_len || rtt_pl_running || dma_pending)
            rc = -7;
        else {
            uint32_t hz = get32(req + 4);
            if (hz)
                requested_hz = hz;
            chunk = req[8] | ((uint32_t)req[9] << 8);
            if (!chunk || chunk > CDC_SLOT_SIZE)
                chunk = CDC_SLOT_SIZE;
            discard = req[10] & 1;
        }
        break;
    case 11:
        if (cmd != 0x32)
            rc = -9;
        break;
    case 12:
        rc=req[1]<3 ? -6 : (mode || bench_active) ? -7 : probe_target_transport(req[4]);
        break;
    default:
        rc = -9;
        break;
    }
    if (requested_hz < 1000000 || requested_hz > 60000000) {
        requested_hz = 50000000;
        rc = -6;
    }
    if (act != 2 && act != 9 && act != 11)
        result = (int8_t)rc;
    status(cmd, words, cmd == 0x32 && act == 11);
    if(cmd==0x32 && act==9){
        words[0]=bench_ticks;words[1]=bench_count;words[2]=(uint32_t)bench_error;
        words[3]=0x5a594e51U;words[4]=0; // Zynq PS MEM-AP plan benchmark.
    }
    res[1] = 50;
    res[3] = (uint8_t)result;
    for (i = 0; i < 12; i++)
        put32(res + 4 + 4 * i, words[i]);
}
void probe_poll(XUsbPs *usb) {
    if (reset_pending) {
        uint32_t f = irq_save();
        // RESET already flushed USB DMA. No old slot may survive reconfiguration.
        mode = 0;
        bench_active=0;bench_error=-7;
        stopping = 0;
        W(0, 0);
        Xil_Out32(0x40010050, 1);
        pl_packets=(Xil_In32(0x4001004c)&4U)!=0;
        if(pl_packets && PR(0)!=0x53545232U) { pl_packets=0;result=-10; }
        rtt_pl_running=rtt_paused=dma_pending=0;
        cdc.in = cdc.out = cdc.busy = 0;
        cdc.zlp=cdc_needs_zlp=0;
        hss.in = hss.out = hss.busy = 0;
        hid.in = hid.out = hid.busy = 0;
        rx_out = rx_in;
        pending_len = fill_count = 0;
        current_epoch = epoch;
        reset_pending = 0;
        irq_restore(f);
        // Engine reset invalidates AP context; release happens only on normal stops.
        probe_target_forget();
    }
    if (!probe_session_live())
        return;
    if(bench_active){
        unsigned sample,word;uint8_t scratch[4];int rc=probe_target_claim(requested_hz);
        if(rc && rc!=-7){bench_error=rc;bench_active=0;}
        if(!rc){
            actual_hz=link_clock(probe_target_fclk());
            for(sample=0;sample<8 && bench_count<bench_requested;sample++){
                uint32_t begin=now();
                for(word=0;word<nwords;word++)if((rc=probe_target_read(addresses[word],scratch,4)))break;
                bench_ticks+=now()-begin;
                if(rc){bench_error=rc;bench_active=0;break;}
                bench_count++;
            }
            if(bench_count==bench_requested){bench_error=0;bench_active=0;}
            if(!bench_active)probe_target_release();
        }
    }
    kick(usb, &hid);
    kick(usb, &hss);
    kick(usb, &cdc);
    if (rx_in != rx_out && space(&hid)) {
        uint8_t req[64];
        uint32_t f = irq_save();
        memcpy(req, hid_rx[rx_out % QSIZE], 64);
        rx_out++;
        irq_restore(f);
        control(req, slot(&hid));
        publish(&hid, 64);
        XUsbPs_EpPrime(usb, 6, XUSBPS_EP_DIRECTION_OUT);
    }
    if (!probe_session_live())
        return;
    if (mode == 1)
        rtt_poll();
    else if (mode == 2) {
        hss_poll();
        if (stopping)
            stop();
    }
    if(stopping && mode==1) stop();
    kick(usb, &hid);
    kick(usb, &hss);
    kick(usb, &cdc);
}
