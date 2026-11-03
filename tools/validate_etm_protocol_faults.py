"""Inject fault packet types in real-record-derived native input, offline."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'etm-service/tools'))
from trace_cli import engine_environment
import decode_stream
import native_binary
import native_core
import trace_store_write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--f103', required=True, type=Path)
    parser.add_argument('--h743', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    engine_environment()
    rows = []
    for name, source, protocol, codes in [('f103', args.f103, 'ETMv3', [23,24]),
                                         ('h743', args.h743, 'ETMv4', [0x300,0x301])]:
        source = source.resolve()
        session = json.loads((source / 'session.json').read_text(encoding='utf8'))
        raw_path = source / ('etm.bin' if (source / 'etm.bin').exists() else 'capture.bin')
        original_sha = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        folder = args.out / name
        folder.mkdir()
        for filename in ('firmware.elf', 'sources.json', 'session.json'):
            shutil.copy2(source / filename, folder / filename)
        raw = raw_path.read_bytes()[:65536]
        (folder / 'capture.bin').write_bytes(raw)
        os.environ['ETM_DIRECT_DECODE'] = '0'
        decoded = decode_stream.decode_stream(raw, folder / 'firmware.elf', folder,
            config=session['config'], sources=json.loads((folder / 'sources.json').read_text(encoding='utf8')))
        payload = bytearray((folder / 'native.bin').read_bytes())
        position, inserted = native_binary.HEADER_BYTES, []
        while position < len(payload) and len(inserted) < len(codes):
            kind, size = struct.unpack_from('<BI', payload, position)
            if kind == native_binary.RECORD_PACKET:
                code = codes[len(inserted)]
                struct.pack_into('<I', payload, position+5, code)
                inserted.append(code)
            position += size
        assert inserted == codes
        (folder / 'native.bin').write_bytes(payload)
        trace_store_write.write(folder, folder / 'store', native_bin=folder / 'native.bin',
            elf=folder / 'firmware.elf', config=session['config'], metadata=decoded, write_decoded=True)
        native = native_binary.NativeFile(folder / 'native.bin')
        expected = [dict(offset=r[1], bytes=r[2], reason='包问题：'+native_binary.packet_name(r[3], protocol))
                    for r in native.records() if r[0] == native_binary.RECORD_PACKET
                    and native_binary.classify_packet(r[3], protocol) & native_binary.PACKET_INVALID]
        assert len(expected) >= 2
        with native_core.Store(folder / 'store') as store:
            assert store.meta['record']['protocol'] == protocol
            actual = [{k: item[k] for k in ('offset', 'bytes', 'reason')}
                      for item in store.issues_list if item['category'] == 'packet']
            assert actual == expected, (protocol, actual, expected)
        assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == original_sha
        rows.append(dict(protocol=protocol, source=str(source), sourceSha256=original_sha,
            injectedPacketCodes=codes, expected=expected, sourceUnchanged=True,
            nativeInputSha256=hashlib.sha256(payload).hexdigest()))
        print(protocol, 'injected packet names and native metadata: PASS', flush=True)
    (args.out / 'result.json').write_text(json.dumps(dict(ok=True, offline=True, rows=rows,
        scope='Fault type injection in a real-record-derived native container, not hardware or raw packet parser acceptance'), ensure_ascii=False, indent=2)+'\n', encoding='utf8')


if __name__ == '__main__':
    main()
