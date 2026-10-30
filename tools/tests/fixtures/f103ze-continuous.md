# F103ZE formatter regression fixture

Source: retained hardware recording
`E:/superlinkPRO/etm/records/capture-2d6da5829a8c4811b7c5ed2ca9e08cc3/tpiu.bin`.
The 8,180-byte slice starts at physical offset 11,995 (the full sync immediately
before the first non-idle frame), and ends at a complete frame boundary.

The independent `etm-service/tools/tpiu_demux.py` produces 413 formatter frames,
393 full syncs, no half syncs, 874 source-2 bytes and 4,055 idle-source bytes.
The source-2 stream is retained separately as `f103ze-continuous.etm`.
This deliberately includes consecutive frames without a full sync in between.
Synthetic HSYNC and malformed-stream coverage is in tb_orbtrace_tpiu_stream.sv.

The fixture checks simulation against hardware data; it is not a new board test.
