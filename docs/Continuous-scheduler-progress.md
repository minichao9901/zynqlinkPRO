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


## Packet RTL scheduling checkpoint (simulation)

The packet engine starts the next transfer directly when the previous core
completion is observed. Write data is prefetched from synchronous BRAM while
the current serial frame is executing. WAIT retries retain the current write
word; prefetched words are not committed after FAULT/parity errors. Final DP
RDBUFF draining and partial completion counts remain in place.

`tools/test_packet_engine.py --compare-ref 74902be` passes basic cases,
synchronous BRAM, stalled core, retry/error/partial results, full 1023-word
boundary, and AXI/mux integration. Added a WAIT at the sixth write to check that
retry cannot consume the prefetched next word. Mock-core cycles for a 1023-word
read fall 9225 -> 7178; 1022-word write 11260 -> 7173. These numbers describe the
short mock core, NOT physical SWD throughput. The actual saved scheduling time
is about 2 FCLK cycles/read and 4 cycles/write.

Real user-supplied Cortex-M0 DesignStart model via XSim:
- packet_pipeline: packet reads/writes 1/2/127/256/770/1023 words pass.
- pipeline_tco8: packets plus WAIT/release/ABORT recovery pass at the default
  16ns return delay. The supplied tco=8 argument was not a recognized TB option;
  this run is NOT evidence for 8ns timing. The runner now rejects unknown
  plusargs. This target model does not report injected AHB FAULT in the
  forced-error case (explicit FAULT_SKIP); RTL mock tests cover partial FAULT.
- All model sources remain outside the repository.

Implementation/timing and physical F103 validation are separate next gates.


Timing sweep correction: the testbench's actual option is return_ns, not tco.
An explicit return_ns=8 run fails on the first legacy DPIDR before packet mode
is used. This matches the pre-existing narrow return-delay sampling window
reported in docs/交接-20261026-SWD高速与M0+仿真.md (about 12..24ns at 60MHz,
phase-dependent). It is not claimed fixed by the packet scheduler. Preserve
negative tests in the handover instead of counting them as covered successes.


Explicit return_ns=24 at FCLK=120MHz also passes all packet lengths. The default
return_ns=16 run includes WAIT recovery. Return_ns=8 is a retained negative test.
For USB-only recovery without FPGA/ELF reload, close OpenOCD then run:
`python tools/dap_transport_control.py state` or
`python tools/dap_transport_control.py recover`.
This resets USB queue ownership, not a stuck RTL engine; no host-side automatic
OpenOCD recovery is claimed.

A 100-session stress run during parallel Vivado synthesis passed all byte and
restore checks, but wall throughput varied down to 2.31 MB/s transiently and
recovered without a reload. Concurrent profiling still measured RTL read/write
665.83/657.81 us while USB submit-to-complete increased to 75.16 us (from about
44 us). Aggregate read/write 3.51/3.75 MB/s in that host-load run is not a fair
performance comparison with the quiet A/B runs. Re-test without any reflash once
the Vivado load ends to distinguish persistent device state from host scheduling.
RCC readback: CR=0x03035983, CFGR=0x0029250a, matching the existing HSE x12 PLL
configuration used by the board's 96MHz firmware; it was not reset or changed.


Build the tested 60MHz firmware cap explicitly, independent of a higher routed
STA limit: `python tools/build_xusbps_daplink.py --project xusbps_daplink_dma
--max-swclk-hz 60000000 --bsp <usb_bsp/ps7_cortexa9_0>`. The new limit option
rejects a value above routed timing (or the conservative 60MHz fallback).


## Isolated-build IP cache reuse

This isolated worktree's first build already uses Hierarchical/OOC synthesis,
but had no local IP cache. The unchanged CDMA IP is expensive in Vivado 2018.3
(original project's log: about 11 minutes in RTL elaboration). It is not a reason
to rerun this core on every SWD RTL edit. Ordinary incremental builds already
retain the OOC runs; new isolated projects can now seed a separate cache:

```powershell
python tools/prepare_ip_cache.py --source E:/zynqlinkPRO/build/fpga_dma_global/zynqlink_dma.cache/ip --destination build/shared_ip_cache
python tools/run_vivado.py -mode batch -nojournal -source fpga/build_dma.tcl -tclargs --ip-cache build/shared_ip_cache
```

Seeding copied 27 entries; repeating it copied zero and retained all entries.
Vivado's in-memory project probe accepted the selected cache location. Vivado
checks configuration fingerprints, so modified module RTL is still synthesized.
The reference cache/project is read only during seeding; existing destination
entries are never overwritten. No completed implementation is fabricated.


## First packet-pipeline board checkpoint

Routed timing passes at FCLK150MHz (setup +0.173ns, hold +0.016ns). Firmware still
caps requested SWCLK at the tested 60MHz. Physical F103, existing HCLK96MHz:
- 60MHz, 6 sessions x300 operations of 20KiB: read 3.966 / write 4.084 MB/s.
- 50MHz, same test: read 3.364 / write 3.447 MB/s.
- Full byte comparisons and SRAM restore checks pass each session.
- Small mixed/nested transfer validation passes 1200 commands plus boundaries.
- RTL packet mean read 651.30us / write 631.29us (was 665.82 / 657.70).
  Full 0x06 processing 668.33 / 655.80us. Ordinary block response copy remains zero.

Controlled host-load retest: before/after Vivado exit, same loaded bit/ELF and
same USB session_epoch=3, no queue recovery or target reset between those two
samples. Read 3.606 -> 3.913; write 3.781 -> 4.016 MB/s. This proves the measured
wall-throughput reduction in this experiment recovers without device reload.
It does not prove that every historical 2.1MB/s report has the same cause.

This checkpoint predates the upcoming explicit execution-engine soft-reset CSR.


## Execution-engine recovery checkpoint (simulation)

New CSRs: +0x4c FEATURES=0x44500001; +0x50 write bit0 resets the SWD core,
batch and packet execution FSMs; reading +0x50 returns a monotonic reset count.
AXI/configuration, FCLK selection and BRAM are preserved. Firmware detects the
feature before using it, so older bits retain USB-only recovery. EP0 recovery
and USB session reset now also cancel execution on a matching bit. Batch aborts
and packet-error cleanup use the same recovery mechanism; accepted target
operations are never replayed automatically. This is not target nRESET.
EP0 request 0x5c with the same magic and length24 exposes features/reset count,
core/batch/packet status and recovery errors even when bulk is blocked.

A newly proven status bug: busy_reg was set in HOST_CTRL but overwritten by
ST_IDLE in the same clock, so BATCH_STATUS.busy could stay zero while state was
active. START already used state==IDLE, so do not claim it accepted duplicate
starts. The redundant register is removed; status now uses the same state-derived
active signal as core ownership. This improves diagnostics/recovery checks; it
is not proven to be the cause of historical throughput degradation.

Native queue tests pass with the new reset callback. AXI test stalls packet and
batch core completions, resets each while busy, checks counter/configuration and
runs another data-checked packet. Full real Cortex-M0 packet regression plus a
reset during a stalled posted AP read, SWJ reconnect and two-word SRAM read/write
pass (engine_reset_full). The TB's HRDATA adapter was also refreshed each target
half-cycle: its earlier continuous function could retain stale data after a
same-address SRAM write; no licensed external model source was edited.
Physical-board validation and final prebuilt refresh remain separate next gates.


## Final recovery board validation

Final recovery bit routed at FCLK138.461539MHz: setup +0.488ns, hold +0.016ns.
150MHz failed setup (-0.068ns); it is NOT a supported timing point for this bit.
The operational firmware cap remains 60MHz SWCLK (120MHz FCLK).

- 100 packet/AP read abort/reconnect rounds pass; 74 snapshots prove RTL busy
  immediately before recovery. Reset acknowledged, all engines idle afterwards,
  no recovery errors and no USB submit errors; F103 reconnects each round.
- 100 ordinary 0x05 batch abort/reconnect rounds pass; 46 busy snapshots, same
  zero-error result. This also exercises the corrected BATCH_STATUS.busy bit.
- Another 57,600 queued short/ZLP/4096B requests pass on the final recovery pair.
- Mixed/nested commands: 1200 +8 boundary cases pass.
- 60MHz SRAM: 6 sessions x300 reads/writes of 20KiB, read 3.98702 and write
  4.11566 MB/s; full data and original SRAM restore checks pass.
- 50MHz initial final-pair sample: read 3.32048 / write 3.43528 MB/s, same checks.
  Fresh main/final comparison under the identical runtime follows separately.

At the new turn boundary, patched OpenOCD failed before emitting any output
(exit 0xc0000135). The matching x64 DLLs were absent beside it. Creating an
application-local runtime with the unchanged EXE plus MSYS64 x64 libusb/hidapi
restored launch. The nightly distribution's DLLs are x86 and must not be mixed
with this x64 EXE. tools/prepare_openocd_runtime.py checks PE architecture,
records hashes, and tests --version; no system PATH or DLL installation changes.
The benchmark now reports process exit code even if stdout/stderr are empty.

```powershell
python tools/prepare_openocd_runtime.py --exe E:/zynqlinkPRO/build/openocd-src/src/openocd.exe
python tools/stress_dap_sessions.py --rtl --rounds 100 --output results/optimization/packet_reset.json
python tools/stress_dap_sessions.py --batch --rounds 100 --output results/optimization/batch_reset.json
```

Recovery verification does not claim automatic retry in stock OpenOCD: after
an actual host timeout, close that process and run the EP0 recovery utility,
then reconnect. Truncated SWD frames require SWJ line reset/reconnect. The
original historical long-term 2.1MB/s condition is still not proven reproduced
as persistent firmware degradation; do not describe it as comprehensively fixed.
