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
