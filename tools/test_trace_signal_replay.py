"""Replay retained real 24MHz pads through baseline/filtered RTL and compare bytes."""
import hashlib
import json
from pathlib import Path
import subprocess

from trace_signal_analysis import unpack,filter_samples,physical

ROOT=Path(__file__).resolve().parents[1]


def main():
    output=ROOT/'build/filtered-signal-regression';output.mkdir(exist_ok=True)
    rtl=sorted((ROOT/'fpga/rtl').glob('orbtrace_*.v'))
    for mode in (2,4):
        subprocess.run(['iverilog','-g2012','-s','tb_orbtrace_signal_replay',
                        f'-Ptb_orbtrace_signal_replay.MODE={mode}','-o',str(output/f'mode{mode}.vvp'),
                        *map(str,rtl),str(ROOT/'fpga/sim/sim_primitives.v'),
                        str(ROOT/'fpga/sim/tb_orbtrace_signal_replay.sv')],check=True)
    rows=[]
    source=ROOT/'docs/validation/f103ze-web-flow-20261031/frequency/samples/48mhz'
    for capture in sorted(source.glob('cpu48-div1*')):
        samples=unpack((capture/'raw.samples16').read_bytes())
        filtered=filter_samples(samples,'stable2');_,edges=physical(filtered,200_000_000)
        n=filtered[edges[:-1]]&15;n=n[1:];n=n[:len(n)//2*2]
        from tpiu_demux import demux
        _,streams=demux(bytes((n[::2] | (n[1::2]<<4)).tolist()));expected=streams[2]
        comparison=json.loads((capture/'comparison.json').read_text(encoding='utf8'))
        golden=next(r for r in comparison['rows'] if r['filter']=='stable2' and r['phaseFraction']==0 and r['nibblePhase']==1)
        assert hashlib.sha256(expected).hexdigest()==golden['etmSha256']
        vector=output/(capture.name+'.hex');vector.write_text(''.join(f'{x:02x}\n' for x in samples))
        for mode in (2,4):
            sink=output/(capture.name+f'-mode{mode}.txt')
            run=subprocess.run(['vvp',str(output/f'mode{mode}.vvp'),'+source='+vector.as_posix(),
                                '+sink='+sink.as_posix()],capture_output=True,text=True,check=True)
            records=[line.split() for line in sink.read_text().splitlines()]
            actual=bytes(int(byte,16) for channel,byte in records if int(channel,16)==2)
            equal=actual==expected
            row=dict(capture=capture.name,mode=mode,referenceBytes=len(expected),actualBytes=len(actual),
                     exact=equal,simulation=run.stdout.strip(),sampleSha256=comparison['inputSha256'])
            rows.append(row)
            if mode==4:assert equal and 'loss=0' in run.stdout,row
            else:assert not equal and 'loss=1' in run.stdout,row
            print(capture.name,mode,'exact=',equal,flush=True)
    (output/'summary.json').write_text(json.dumps({'hardwareAcceptance':False,'rows':rows},indent=2)+'\n')


if __name__=='__main__':main()
