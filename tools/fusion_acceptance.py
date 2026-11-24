"""Plan or dispatch a case of the single-pair fusion hardware acceptance campaign."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from fusion_evidence import Blocked

ROOT = Path(__file__).resolve().parents[1]
TOOLBOX = [sys.executable, '-X', 'utf8', str(ROOT / 'toolbox.py')]


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_plan():
    return read_json(ROOT / 'acceptance-cases.json')['fusionAcceptance']


def inside(path, root):
    return Path(path).resolve().is_relative_to(root.resolve())


def checked_files(directory, manifest, names, key):
    result = {}
    for name in names:
        path = directory / name
        expected = manifest[key][name]
        actual = sha(path)
        if actual.lower() != expected.lower():
            raise ValueError(f'SHA-256 mismatch: {path}')
        result[name] = {'path': str(path), 'sha256': actual}
    return result


def probe_identity(pair):
    pair = pair.resolve()
    if not inside(pair, ROOT / 'prebuilt'):
        raise ValueError('Select a named fusion pair directory under prebuilt.')
    path = pair / 'manifest.json'
    manifest = read_json(path)
    if manifest.get('firmware_abi') != 2 or 'qspi' in pair.name.lower():
        raise ValueError('The campaign requires a fusion ABI 2 RAM pair.')
    return {'manifest': str(path), 'files': checked_files(
        pair, manifest, ('probe.bit', 'application.elf', 'ps7_init.tcl'), 'hashes')}


def targets(case):
    result = []
    for image in case['targetImages']:
        directory = ROOT / 'firmware/target' / case['board'] / 'images' / image
        manifest = directory / 'manifest.json'
        values = read_json(manifest)
        if values['image'] != image or values['board'] != case['board']:
            raise ValueError(f'Target manifest names another image or board: {manifest}')
        result.append({
            'image': image, 'manifest': str(manifest),
            'files': checked_files(directory, values, ('fw.elf', 'fw.bin', 'fw.hex'), 'files'),
        })
    if case.get('targetElf'):
        path = ROOT / case['targetElf']
        result.append({'image': 'golden', 'files': {'fw.elf': {'path': str(path), 'sha256': sha(path)}}})
    return result


def find_case(plan, name):
    for case in plan['cases']:
        if case['id'] == name:
            return case
    raise ValueError(f'Unknown fusion case: {name}')


def create_campaign(pair, serial, out):
    if not serial.strip():
        raise ValueError('Explicitly specify the J7 USB serial')
    identity = probe_identity(pair)
    out.mkdir(parents=True, exist_ok=False)
    data = {'plan': load_plan()['id'], 'serial': serial, 'probe': identity}
    (out / 'campaign.json').write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    return data


def validated_campaign(path):
    record = read_json(path)
    if record['plan'] != load_plan()['id'] or not record['serial'].strip():
        raise ValueError('Campaign plan or probe serial does not match.')
    pair = Path(record['probe']['manifest']).parent
    if probe_identity(pair) != record['probe']:
        raise ValueError('Campaign probe pair changed. Start a new campaign.')
    return record, pair


def verify_load_receipt(path, campaign, hs3):
    record = read_json(path)
    if record.get('passed') is not True or record.get('operation') != 'JTAG/RAM':
        raise ValueError('A successful probe-load JTAG/RAM receipt is required')
    if (record.get('cableSerial'), record.get('usbSerial')) != (hs3, campaign['serial']):
        raise ValueError('Load receipt does not bind this HS3 cable and USB serial')
    for saved, locked in {'bit': 'probe.bit', 'zynq_elf': 'application.elf', 'ps_init': 'ps7_init.tcl'}.items():
        if record['files'][saved]['sha256'] != campaign['probe']['files'][locked]['sha256']:
            raise ValueError(f'probe-load receipt differs for {locked}')
    return {'path': str(path.resolve()), 'sha256': sha(path)}


def run_capture(argv, out, name):
    completed = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    (out / f'{name}.stdout.txt').write_text(completed.stdout, encoding='utf-8')
    (out / f'{name}.stderr.txt').write_text(completed.stderr, encoding='utf-8')
    if completed.returncode:
        raise RuntimeError(f'{name} returned {completed.returncode}; see {out}')
    return completed.stdout


def verify_live(campaign, pair, hs3, out):
    # The DAP operation and EP5 info must use the named cable/USB serials.
    ocm = [
        sys.executable, '-X', 'utf8', str(ROOT / 'tools/verify_probe_ocm_code.py'),
        '--elf', str(pair / 'application.elf'), '--out-dir', str(out / 'ocm'),
        '--cable-serial', hs3,
    ]
    run_capture(ocm, out, 'probe-ocm')
    info_out = run_capture([*TOOLBOX, 'selectio', '--serial', campaign['serial'], 'info'], out, 'probe-info')
    info = json.loads(info_out)
    if not info.get('dedicated_pipes') or info.get('firmware_abi') != 2 or info['usb']['serial'] != campaign['serial']:
        raise RuntimeError('Live J7 does not have the required ABI 2 endpoint split.')
    from fusion_fixture import bind_probe_identity
    bind_probe_identity(campaign['serial'], hs3, out)


def select_target(case, alias):
    images = targets(case)
    if not images:
        if alias:
            raise ValueError('This case has no target image')
        return None
    if alias is None and len(images) == 1:
        return images[0]
    for image in images:
        if image['image'] == alias:
            return image
    raise ValueError('--image must select one of: ' + ', '.join(i['image'] for i in images))


def validate_point(case, profiles, args):
    p = case['parameters']
    runner = case['runner']
    if runner not in ('sram', 'rtt', 'scope', 'combo') and args.transport and args.transport != case['clock'].get('transport'):
        raise ValueError('The case fixes the target control transport')
    if runner in ('sram', 'rtt', 'scope', 'combo'):
        profile = profiles[case['clock']['profile']]
        if not any(point['transport'] == args.transport and args.rate in point['requestedHz']
                   for point in profile['links']):
            raise ValueError('Select a listed --transport and --rate in Hz')
        if args.transport == 'riscv-jtag':
            if any(value is not None for value in (args.tap, args.slot, args.idle)):
                raise ValueError('RISC-V uses the HPM single-TAP profile. Omit ARM tap, slot and idle.')
        elif args.tap not in range(32) or args.slot not in range(64) or args.idle not in range(256):
            raise ValueError('Provide --tap 0..31, --slot 0..63 and --idle 0..255 from the calibrated link')
        if args.transport == 'arm-jtag' and (args.slot < 16 or args.idle % 2 == 0):
            raise ValueError('ARM JTAG needs slot 16..63 and odd idle')
        if args.transport == 'swd' and args.idle > 15:
            raise ValueError('SWD idle must be in 0..15')
    if runner in ('scope', 'combo') and (args.channels not in p['channels'] or args.group_rate not in p['groupRates']):
        raise ValueError('Select listed --channels and --group-rate points')
    if runner == 'uart' and args.rate not in p['baud']:
        raise ValueError('Select a listed --rate in baud')
    if runner in ('swo-itm', 'swo-source'):
        rates = {'uart': p['nrZBaud'], 'manchester': p['manchesterBitRate']}
        if args.encoding not in rates or args.rate not in rates[args.encoding]:
            raise ValueError('Select a listed --encoding and --rate in information bits/s')
    if runner.startswith('spi-'):
        if args.spi_mode not in p['modes'] or args.rate not in p['sckHz'] or args.tap not in range(32):
            raise ValueError('Select a listed --spi-mode and --rate in Hz and a calibrated --tap')
        if runner != 'spi-target-tx' and args.frame_bytes not in p['frameBytes']:
            raise ValueError('Select listed --frame-bytes')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('list').add_argument('--board')
    sub.add_parser('describe').add_argument('case')
    start = sub.add_parser('campaign')
    start.add_argument('--pair', required=True, type=Path)
    start.add_argument('--serial', required=True)
    start.add_argument('--out', required=True, type=Path)
    for action in ('identity', 'run'):
        command = sub.add_parser(action)
        if action=='run':
            command.add_argument('case')
            command.add_argument('--image')
            command.add_argument('--transport', choices=('swd', 'arm-jtag', 'riscv-jtag'))
            for flag in ('rate', 'tap', 'slot', 'idle', 'channels', 'group-rate', 'spi-mode', 'frame-bytes'):
                command.add_argument('--'+flag, type=int)
            command.add_argument('--encoding', choices=('uart', 'manchester'))
            command.add_argument('--manual-spi-switch', action='store_true',
                                 help='Confirm each exclusive SWD/SPI wiring change at the bench')
        command.add_argument('--campaign', required=True, type=Path)
        command.add_argument('--out', required=True, type=Path)
        command.add_argument('--hs3-serial')
        command.add_argument('--probe-load-receipt', type=Path)
        command.add_argument('--execute', action='store_true')
    args = p.parse_args(argv)
    try:
        plan = load_plan()
        if args.action == 'list':
            result = [
                {key: case[key] for key in ('id','board','feature','runner','execution')}
                for case in plan['cases'] if args.board is None or args.board == case['board']
            ]
        elif args.action == 'describe':
            case = find_case(plan,args.case)
            result = {**case, 'qualification': plan['rules'], 'probe': plan['probe'],
                      'targets': targets(case), 'profiles': plan['profiles'], 'entry': plan['entry']}
        elif args.action == 'campaign':
            result = create_campaign(args.pair,args.serial,args.out)
        else:
            campaign,pair = validated_campaign(args.campaign)
            case = find_case(plan,args.case) if args.action == 'run' else None
            if not args.execute:
                result = {'mode':'offline', 'campaign':campaign, 'case':case,
                          'targets':targets(case) if case else [], 'evidenceDir':str(args.out)}
                if case and case['execution']['mode'] != 'blocked':
                    supplied = any(getattr(args, key) is not None for key in (
                        'image', 'transport', 'rate', 'tap', 'slot', 'idle', 'channels',
                        'group_rate', 'encoding', 'spi_mode', 'frame_bytes'))
                    if supplied:
                        validate_point(case, plan['profiles'], args)
                        result['selectedTarget'] = select_target(case, args.image)
            else:
                if not args.hs3_serial or not args.probe_load_receipt:
                    raise ValueError('--execute needs --hs3-serial and --probe-load-receipt')
                receipt = verify_load_receipt(args.probe_load_receipt, campaign, args.hs3_serial)
                args.out.mkdir(parents=True,exist_ok=False)
                result = {'campaign':campaign, 'case':case['id'] if case else None, 'receipt':receipt}
                failure = False
                try:
                    if case:
                        result['point'] = {k: getattr(args, k) for k in
                            ('image', 'transport', 'rate', 'tap', 'slot', 'idle', 'channels',
                             'group_rate', 'encoding', 'spi_mode', 'frame_bytes')}
                    if case and case['execution']['mode'] == 'blocked':
                        result.update(status='blocked', reason=case['execution']['pending'])
                        failure = True
                    elif case and case['runner'].startswith('spi-') and not args.manual_spi_switch:
                        result.update(status='blocked', reason='SPI and SWD share pins; use --manual-spi-switch with an isolated switch/harness')
                        failure = True
                    else:
                        if case:
                            validate_point(case, plan['profiles'], args)
                            result['target'] = select_target(case, args.image)
                        verify_live(campaign,pair,args.hs3_serial,args.out)
                        result['status'] = 'identity-checked'
                        if case:
                            from fusion_acceptance_run import run_case
                            result.update(run_case(case, plan, campaign, pair, args, result['target']))
                            failure = result['status'] in ('fail', 'blocked')
                except KeyboardInterrupt:
                    result.update(status='blocked', reason='Interrupted. Confirm recorded restoration before continuing.')
                    failure = True
                except Blocked as error:
                    result.update(status='blocked', reason=str(error))
                    failure = True
                except Exception as error:
                    result.update(status='fail', reason=str(error))
                    failure = True
                finally:
                    (args.out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
                print(json.dumps(result,ensure_ascii=False,indent=2))
                return int(failure)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (OSError, KeyError, RuntimeError, ValueError) as error:
        p.exit(2, f'{error}\n')


if __name__=='__main__':
    raise SystemExit(main())
