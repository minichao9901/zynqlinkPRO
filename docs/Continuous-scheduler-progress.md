# Continuous scheduler: baseline and measurement checkpoint

Branch: codex/main-continuous-scheduler, base main 74902be.

- Existing main already batches ordinary 0x05 commands when count >= 8.
- 12 fresh OpenOCD sessions: 60 MHz SWCLK, F103 already at its firmware clock,
  halted without reset, randomized 20 KiB, 60 load/dump iterations per session.
  Read 3.857 MB/s; write 4.016 MB/s; data and restoration passed all sessions.
- 3 raw USB sessions x 6 boundary sizes x 100 rounds x 16 outstanding requests:
  28,800 requests passed length/status/DPIDR checks (1/127/128/255/256/1023 words).
- Session-dependent degradation has not yet been reproduced under these exact conditions.

Opt-in instrumentation (vendor 0x81 start/stop, 0x86 stage snapshot) measures
execution, packet RTL polling, CDMA/cache, response copy, request queue wait,
USB submission/completion. No per-event noncacheable trace in the performance build.

Baseline sample, 100 reads + 100 writes of 20 KiB:
- RTL packet read: 665.82 us average (about 3083 bytes/command)
- RTL packet write: 657.70 us average
- entire 0x06 read: 692.55 us; write: 686.10 us
- CDMA upload/cache: 8.69 us/call; download/cache: 8.44 us/call
- response copy: 3.67 us/call
- USB IN submit: 5.19 us; submit-to-complete: 47.09 us (mixed packet sizes)
- request queue wait: 1502.75 us mean, mostly intentional host pipelining;
  it overlaps previous commands and must not be summed into wall time.
- 0x05/control execution total: 251.14 ms; all 0x06 total: 706.57 ms.

These measurements favour small-command scheduling and queue ownership fixes
before a large RTL descriptor-ring redesign: bulk DMA overhead is already small.

Raw evidence is under results/optimization (ignored local artifacts).
No target flash programming was performed; SRAM tests back up and restore data.


## USB ownership/recovery checkpoint

Transport now owns each response until its last DMA descriptor completes,
including an explicit ZLP. Failed submissions retain ownership for retry. RX
applies backpressure instead of overwriting unread requests. Sequence counters
are uint32 with bounded modulo differences. QueueCommands scans only occupied
slots. The main loop revalidates queue state after masking IRQs: a reset between
the outer condition and the lock must not create a phantom request.

The application overrides the SDK interrupt object locally (xusbps_intr.c),
leaving the shared reference BSP unchanged. TX retires a dTD before invoking the
application callback, allowing the next response to be submitted from that IRQ.
SET_CONFIGURATION flushes DMA before resetting software ownership. SDK v2.4 IN
reconfiguration leaves ACTIVE tokens intact, so these tokens are explicitly
cleared after endpoint flush. Queue-head overlays are reset too.

EP0 recovery: vendor IN request 0x5a, wValue=0x4441, wIndex=0x5052, wLength=4,
returns DAP + status (zero on success). Request 0x5b with the same magic and
wLength=32 returns eight uint32 queue diagnostic fields. Host clears both pipes
and drains any already-prefetched bytes. This explicit recovery is a diagnostic
and recovery facility; stock OpenOCD does not automatically issue it. On Windows,
setting the already-active configuration is not a reliable on-wire reset.

Validation:
- Native transport tests compile the real dap_main.c with a mock USB DMA driver:
  response/request-full, delayed ZLP completion, failed submit retry, 70,000
  completions including uint32 wrap, reset during execution and before lock.
- Board: 100 consecutive EP0 recoveries with eight abandoned IN responses each;
  no stale responses after recovery, no submit failures. An earlier revision
  reproduced phantom commands during reset and was corrected before this test.
- Earlier queue stress: 57,600 legal requests across six short/ZLP/full sizes.
- After 100 recoveries, 12 OpenOCD sessions x 60 loads/dumps of randomized 20 KiB
  at requested 60 MHz: read 3.843 MB/s, write 4.006 MB/s. All data and SRAM restore
  checks passed. Baseline 3.857/4.016: differences -0.37%/-0.24%, within measured
  session variation. The originally reported long-term 2.1 MB/s degradation is
  still not reproduced and is not claimed fixed by these tests alone.


## Software copy/cache optimization

Large aligned 0x06 read responses DMA directly into the owned USB response slot.
The first DMA word is rewritten to the CMSIS-DAP header. Nested ExecuteCommands
with an unaligned response retain the private aligned DMA buffer. Only the owning
slot is maintained in cache; XUsbPs already flushes payload before publishing
its dTD, so the second application flush was removed. Transfers <=8 words use
PIO to the uncached AXI BRAM window, avoiding CDMA setup for headers/status.

A measured attempt to batch 2..7 ordinary 0x05 transfers was withdrawn: mixed
command execution averaged 11.83 us versus legacy 10.68 us. Threshold remains 8.

A/B/A/B deployment, same bitstream, 60 MHz requested SWCLK, no target reset,
randomized 20 KiB, 6 sessions x300 reads and writes per leg:
- stable1: 3.8686 / 4.0166 MB/s; optimized1: 3.9465 / 4.0324
- stable2: 3.8698 / 4.0100 MB/s; optimized2: 3.9461 / 4.0258
- aggregate: read 3.86922 -> 3.94626 (+1.99%); write 4.01328 -> 4.02907 (+0.39%).
- each version 12 sessions, all data and restore checks passed.
- optimized 0x06 read mean 682.8 us versus baseline 692.6 us;
  application response-copy calls became zero for the ordinary block workload;
  USB submission mean 3.14 us versus 5.2 us.
- 300 varied-delay EP0 recoveries and another 57,600 queued boundary requests
  passed on the optimized firmware. Native ownership tests also passed.

The copy/cache software artifact uses the original main bitstream. A separate
RTL scheduling experiment follows; do not confuse it with these A/B results.
