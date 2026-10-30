# ORBTrace reference

Upstream: https://github.com/orbcode/orbtrace

Pinned commit: `e416cd5b074fc725a04cf6b877d458e2074467ae` (main, fetched 2026-10-29).
License: BSD 3-Clause, reproduced verbatim in [COPYING](COPYING).

`stream.py` and `trace/tpiu.py` are unmodified upstream files, retained for an
independent Amaranth reference simulation by `tools/check_orbtrace_capture.py`.
They are not FPGA build inputs. Verification dependency: `amaranth==0.5.8`.

`fpga/rtl/orbtrace_traceif.v` is adapted from upstream `verilog/traceIF.v`:

- module renamed; explicit `wire` declarations for Vivado 2018.3;
- deterministic asynchronous reset of frame, toggle, alignment and counters;
- suppress frames until full synchronization; expose synchronization status;
- restore `default_nettype wire` after the module.

`fpga/rtl/orbtrace_tpiu_demux.v` adapts upstream `Unmangle`, `TrackStream`, and
`StripChannelZero` to Verilog and a single ready/valid byte interface. It advances
state only when consuming an element, and handles channel-zero bytes without
blocking an ID change. ORBFlow, COBS, USB, SWO and CMSIS-DAP from upstream are
outside this simulation stage.
