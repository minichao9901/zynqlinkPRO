"""Replay a reference physical TPIU recording through ORBTrace RTL.

Requires Icarus and the reference project's tpiu_demux.py. Select a complete
formatter-frame boundary, then compare every source-2 byte and detect any
unexpected source IDs. The slow replay checks protocol, not board timing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from analyze_orbtrace_raw import load_demux


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, required=True)
    ap.add_argument('--reference', type=Path, default=Path('E:/superlinkPRO/etm/tools/tpiu_demux.py'))
    ap.add_argument('--bytes', type=int, default=20000)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    work = root/'build/orbtrace_replay'
    work.mkdir(parents=True, exist_ok=True)
    raw = args.input.read_bytes()
    demux = load_demux(args.reference)
    for n in range(min(args.bytes, len(raw)), max(0, min(args.bytes, len(raw))-1024), -1):
        try:
            stats, streams = demux(raw[:n])
        except ValueError:
            continue
        if (not stats['trailing_frame_bytes'] and not stats['trailing_raw_bytes']
                and not stats['trailing_sync_bytes'] and streams.get(2)):
            break
    else:
        raise RuntimeError('no complete reference TPIU boundary found')
    if set(streams)-{0, 2}:
        raise RuntimeError(f'capture has additional source IDs: {sorted(streams)}')
    source = work/'prefix.bin'
    sink = work/'records.txt'
    source.write_bytes(raw[:n])
    rtl = sorted((root/'fpga/rtl').glob('orbtrace_*.v'))
    exe = work/'replay.vvp'
    subprocess.run(['iverilog','-g2012','-DSYNTHESIS','-s','tb_orbtrace_replay',
                    '-Ptb_orbtrace_replay.BOARD=1','-o',str(exe),*[str(p) for p in rtl],
                    str(root/'fpga/sim/sim_primitives.v'),str(root/'fpga/sim/tb_orbtrace_replay.sv')],check=True)
    run = subprocess.run(['vvp',str(exe),'+source='+source.as_posix(),'+sink='+sink.as_posix()],
                         capture_output=True,text=True,timeout=120)
    rows = [tuple(int(v,16) for v in line.split()) for line in sink.read_text().splitlines()]
    actual = bytes(v for ch,v in rows if ch==2)
    expected = streams[2]
    mismatch = next((i for i,(a,b) in enumerate(zip(actual,expected)) if a!=b),None)
    result = {'input':str(args.input.resolve()),'input_sha256':digest(raw),
              'prefix_bytes':n,'prefix_sha256':digest(raw[:n]),
              'reference':str(args.reference.resolve()),'reference_sha256':digest(args.reference.read_bytes()),
              'tpiu_frames':stats['frames'],'fsync':stats['fsyncs'],
              'expected_etm_bytes':len(expected),'actual_etm_bytes':len(actual),
              'expected_sha256':digest(expected),'actual_sha256':digest(actual),
              'other_ids':sorted({ch for ch,v in rows if ch!=2}),
              'first_mismatch':mismatch,'simulator_exit':run.returncode,
              'simulator_summary':run.stdout.splitlines()[-1:] or run.stderr[-300:],
              'matches':run.returncode==0 and actual==expected and all(ch==2 for ch,v in rows),
              'note':'BOARD model includes nominal IDELAY and BUFR skew; slow replay does not validate real timing.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    if not result['matches']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
