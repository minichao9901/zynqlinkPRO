"""Sequential H743 SRAM/RTT/HSS campaign; requires a loaded, verified pair.

Targets the running CPU60/HCLK60 CDC Golden, without programming Flash or PLLs.
Outputs must be new. Never run this concurrently with another board owner.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('sram', 'rtt', 'hss'), required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--bit', type=Path, required=True)
    parser.add_argument('--elf', type=Path, required=True, help='Probe PS ELF')
    parser.add_argument('--speeds', default='1000000,10000000,25000000,35000000,50000000,60000000')
    parser.add_argument('--transports',default='swd,jtag',help='Comma-separated swd,jtag; permits continuing an interrupted campaign in a new directory')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    common = ['--bit', str(args.bit.resolve()), '--elf', str(args.elf.resolve()), '--bootstrap-speed-khz', '1000']
    results = []

    def run(label, argv, low_jtag_rejection=False):
        command = [sys.executable, '-X', 'utf8', *map(str, argv), *common]
        output = args.out/(label+'.json')
        command += ['--output', str(output)]
        meta = dict(argv=command, startedAtUtc=datetime.now(timezone.utc).isoformat(),
                    driverSha256=hashlib.sha256((ROOT/argv[0]).read_bytes()).hexdigest())
        print('START', label, flush=True)
        with (args.out/(label+'.log')).open('wb') as stream:
            result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
        meta.update(returncode=result.returncode, endedAtUtc=datetime.now(timezone.utc).isoformat())
        (args.out/(label+'-command.json')).write_text(json.dumps(meta, indent=2)+'\n')
        value = json.loads(output.read_text()) if output.exists() else {}
        if low_jtag_rejection:
            assert value.get('restore_match') and "'HSS start rejected', -6" in value.get('failure',''), (label,value)
            results.append(dict(label=label,result=str(output),supported=False,
                                reason='HSS requires FCLK>=24MHz; current low-JTAG clock policy is below that limit'))
            print('UNSUPPORTED',label,flush=True)
            return
        assert result.returncode == 0 and not value.get('failure') and not value.get('error'), (label, value)
        assert value.get('restore_match') and 'recover_error' not in value, (label, value)
        if args.phase == 'rtt': assert value.get('registers_match'), label
        if args.phase == 'sram': assert value.get('passed'), label
        results.append(dict(label=label, result=str(output)))
        print('DONE', label, flush=True)

    for transport in args.transports.split(','):
        assert transport in ('swd','jtag'), transport
        if args.phase == 'sram':
            for speed in map(int, args.speeds.split(',')):
                run(f'{transport}-{speed}', ['tools/h743_peak.py', '--transport', transport,
                    '--jtag-ir', '4,5', '--speed-hz', speed, '--words', '512', '--depth', '32',
                    '--loops', '64', '--repeats', '3', '--address', '0x24040000',
                    '--soak-seconds', '10' if speed >= 50000000 else '0'])
        elif args.phase == 'rtt':
            run(transport, ['tools/benchmark_rtt_forward.py', '--transport', transport, '--jtag-ir', '4,5',
                '--fixture-base', '0x24040000', '--speeds', args.speeds, '--chunks', '1024',
                '--seconds', '2', '--repeats', '3'])
        else:
            for speed in map(int,args.speeds.split(',')):
                run(f'{transport}-{speed}', ['tools/benchmark_hss_matrix.py', '--transports', transport, '--jtag-ir', '4,5',
                    '--speeds', speed, '--seconds', '.5'],low_jtag_rejection=transport=='jtag' and speed<12000000)
    (args.out/'summary.json').write_text(json.dumps(results, indent=2)+'\n')


if __name__ == '__main__':
    main()
