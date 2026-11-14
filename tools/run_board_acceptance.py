"""Run the minimum ZynqLinkPRO board acceptance and publish each result as JSONL."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BOARDS = {
    'f103ze': (60_000_000, ('swd', 'jtag'), 'prebuilt/golden/f103ze-cdc48.elf'),
    'h743': (50_000_000, ('swd', 'jtag'), 'prebuilt/targets/stm32h743-cdc-trace-20261101/cpu480-trace20/fw.elf'),
    'hpm6800evk': (25_000_000, ('jtag',), 'firmware/target/hpm6800_web_validation/dbgstress/fw.elf'),
}
FEATURES = ('sram', 'flash', 'debug', 'rtt-viewer', 'rtt-forward', 'jscope', 'stress', 'etm')
BUSINESSES = ('rtt-viewer', 'rtt-forward', 'jscope', 'debug')
ENDINGS = ('switch', 'idle-disconnect', 'active-disconnect', 'usb-disconnect')
STATUSES = ('pass', 'fail', 'pending', 'not-applicable', 'blocked')


class Pending(RuntimeError):
    """A required path or prerequisite could not be exercised."""


class Unsafe(RuntimeError):
    """Current operation or restoration could not be confirmed."""


def rotation(seed):
    rng = random.Random(seed)
    # Columns are businesses. Each round uses each ending once. The two
    # active disconnects each visit RTT, Scope and debug across the campaign.
    columns = list(zip(
        ('switch', 'active-disconnect', 'usb-disconnect', 'idle-disconnect'),
        ('idle-disconnect', 'switch', 'active-disconnect', 'usb-disconnect'),
        ('usb-disconnect', 'idle-disconnect', 'switch', 'active-disconnect'),
    ))
    if rng.randrange(2):
        columns[0], columns[1] = columns[1], columns[0]
    matrix = list(zip(*columns))
    rng.shuffle(matrix)
    if rng.randrange(2):
        swap = {'switch': 'idle-disconnect', 'idle-disconnect': 'switch'}
        matrix = [tuple(swap.get(value, value) for value in row) for row in matrix]
    seen = set()
    result = []
    for row in matrix:
        order = list(BUSINESSES)
        while True:
            rng.shuffle(order)
            if tuple(order) not in seen:
                seen.add(tuple(order))
                break
        endings = dict(zip(BUSINESSES, row))
        result.append([{'business': name, 'ending': endings[name]} for name in order])
    return result


def plan(board, transports, only, seed):
    hz, available, _ = BOARDS[board]
    result = []
    for transport in transports or available:
        for feature in FEATURES[:-1]:
            if feature not in only:
                continue
            common = {'feature': feature, 'transport': transport, 'requestedHz': hz}
            if feature == 'stress':
                for number, actions in enumerate(rotation(seed), 1):
                    result.append(dict(common, id=f'{transport}-stress-{number}', round=number, actions=actions))
            elif feature == 'jscope':
                for count in (1, 8):
                    result.append(dict(common, id=f'{transport}-jscope-{count}', channels=count, seconds=60))
            else:
                result.append(dict(common, id=f'{transport}-{feature}'))
    if 'etm' in only:
        if board == 'hpm6800evk':
            result.append({'id': 'etm', 'feature': 'etm', 'notApplicable': 'HPM6800EVK has no ARM ETM'})
        else:
            result.append({'id': 'etm', 'feature': 'etm', 'transport': 'swd',
                           'requestedHz': 10_000_000, 'seconds': 1})
    return result


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


class Report:
    def __init__(self, folder, metadata):
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=False)
        self.value = dict(metadata, startedAt=utc_now(), status='running', results=[])
        write_json(folder / 'summary.json', self.value)

    def event(self, kind, **fields):
        row = dict(fields, event=kind, time=utc_now())
        line = json.dumps(row, ensure_ascii=False)
        with (self.folder / 'events.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(line + '\n')
        print(line, flush=True)

    def result(self, case, status, started, **details):
        row = dict(case, status=status, secondsElapsed=round(time.monotonic() - started, 3), **details)
        self.value['results'].append(row)
        write_json(self.folder / 'summary.json', self.value)
        self.event('result', **row)

    def finish(self, full, health):
        counts = Counter(row['status'] for row in self.value['results'])
        failures = counts['fail'] or counts['blocked'] or not health
        status = 'fail' if failures else 'incomplete' if counts['pending'] else 'pass'
        coverage = 'full' if full else 'selected'
        self.value.update(status=status, scope=coverage, accepted=full and status == 'pass',
                          counts={key: counts[key] for key in STATUSES}, finishedAt=utc_now())
        destination = self.folder / 'summary.json'
        write_json(destination, self.value)
        self.event('summary', status=status, scope=coverage, accepted=self.value['accepted'],
                   counts=self.value['counts'], report=str(destination))
        return {'pass': 0, 'fail': 1, 'incomplete': 2}[status]


def campaign(cases, driver, report, full=True):
    stop_reason = None
    started = time.monotonic()
    report.event('start', id='preflight')
    try:
        report.result({'id': 'preflight'}, 'pass', started, evidence=driver.preflight())
    except (Exception, KeyboardInterrupt) as error:
        stop_reason = str(error) or type(error).__name__
        report.result({'id': 'preflight'}, 'fail', started, error=stop_reason)
    for case in cases:
        started = time.monotonic()
        if 'notApplicable' in case:
            report.result(case, 'not-applicable', started)
            continue
        if stop_reason:
            report.result(case, 'blocked', started, reason=stop_reason)
            continue
        report.event('start', **case)
        folder = report.folder / case['id']
        folder.mkdir()
        status, details = 'pass', {}
        try:
            details = driver.run(case, folder)
        except Pending as error:
            status, details = 'pending', {'reason': str(error)}
        except KeyboardInterrupt:
            status, details = 'fail', {'error': 'Interrupted by operator'}
            stop_reason = details['error']
        except Exception as error:
            status, details = 'fail', {'error': str(error)}
            (folder / 'error.txt').write_text(traceback.format_exc(), encoding='utf-8')
            if isinstance(error, Unsafe):
                stop_reason = str(error)
        try:
            if not stop_reason:
                details['recovery'] = driver.check_idle()
        except (Exception, KeyboardInterrupt) as error:
            stop_reason = str(error) or type(error).__name__
            status = 'fail'
            details['recoveryError'] = stop_reason
            (folder / 'recovery-error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        report.result(case, status, started, evidenceDirectory=case['id'], evidence=details)
    started = time.monotonic()
    if stop_reason:
        report.result({'id': 'final-state'}, 'blocked', started, reason=stop_reason)
    else:
        try:
            report.result({'id': 'final-state'}, 'pass', started, evidence=driver.final_state())
        except (Exception, KeyboardInterrupt) as error:
            stop_reason = str(error) or type(error).__name__
            report.result({'id': 'final-state'}, 'fail', started, error=stop_reason)
    return report.finish(full, not stop_reason)


def digest(path):
    with path.open('rb') as stream:
        return {'path': str(path), 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}


def review(paths):
    """Merge physical board sessions using the latest result for each planned case."""
    by_board = {board: {} for board in BOARDS}
    identity = None
    for source in paths:
        path = source / 'summary.json' if source.is_dir() else source
        report = json.loads(path.read_text(encoding='utf-8'))
        board = report['board']
        if board not in by_board:
            raise ValueError(f'Unknown board in {path}: {board}')
        if report['status'] not in ('pass', 'fail', 'incomplete') or not report.get('finishedAt'):
            raise ValueError(f'Cannot review an unfinished session: {path}')
        binding = (report['revision'], report['probeSerial'], report['files']['bit']['sha256'],
                   report['files']['zynqElf']['sha256'])
        if report.get('sourceDirty') or identity not in (None, binding):
            raise ValueError(f'Review requires one clean source revision and probe pair: {path}')
        identity = binding
        expected = {item['id']: item for item in plan(board, None, FEATURES, report['seed'])}
        cases = {item['id']: item for item in report['plan']}
        checks = {'preflight', 'final-state'}
        allowed = set(expected) | checks
        if any(item['id'] not in allowed or item['status'] not in STATUSES for item in report['results']):
            raise ValueError(f'Invalid result records: {path}')
        for row in report['results']:
            case_id = row['id']
            if case_id not in checks and cases.get(case_id) != expected[case_id]:
                raise ValueError(f'Unexpected plan for {board}/{case_id}: {path}')
            if case_id not in checks and ((row['status'] == 'not-applicable') !=
                                           ('notApplicable' in expected[case_id])):
                raise ValueError(f'Inconsistent applicability for {board}/{case_id}: {path}')
            key = (report['finishedAt'], str(path))
            prior = by_board[board].get(case_id)
            if prior is None or key > prior[0]:
                by_board[board][case_id] = (key, row, report['seed'], report['files']['targetElf']['sha256'])
    outputs = {}
    for board, results in by_board.items():
        expected = plan(board, None, FEATURES, 0)
        values = []
        for case_id in ['preflight', *(case['id'] for case in expected), 'final-state']:
            if case_id in results:
                key, row, seed, target_sha = results[case_id]
                values.append(dict(id=case_id, status=row['status'], source=key[1], seed=seed,
                                   targetElfSha256=target_sha))
            else:
                values.append(dict(id=case_id, status='pending', reason='No completed run covering this case'))
        # Never stitch together a three-round scenario from different
        # randomized sequences. A supplemental ETM run can use another seed.
        for link in BOARDS[board][1]:
            rounds = [row for row in values if row['id'].startswith(link + '-stress-')]
            if len({row.get('source') for row in rounds if row.get('source')}) > 1:
                for row in rounds:
                    if row['status'] == 'pass':
                        row.update(status='pending', reason='Run all three stress rounds in one session')
        outputs[board] = values
    counts = Counter(row['status'] for rows in outputs.values() for row in rows)
    status = 'fail' if counts['fail'] or counts['blocked'] else 'incomplete' if counts['pending'] else 'pass'
    return dict(status=status, accepted=status == 'pass', revision=identity[0], probeSerial=identity[1],
                bitSha256=identity[2], zynqElfSha256=identity[3], boards=outputs,
                counts={name: counts[name] for name in STATUSES})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--board', choices=BOARDS)
    mode.add_argument('--review', type=Path, nargs='+', help='Offline verdict for completed board summaries')
    parser.add_argument('--transport', choices=('swd', 'jtag'), action='append')
    parser.add_argument('--only', choices=FEATURES, action='append')
    parser.add_argument('--seed', type=int, default=680014)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--runtime', type=Path, help='Toolbox runtime with a live browser worker')
    parser.add_argument('--bit', type=Path, default=ROOT / 'prebuilt/qspi-release/probe.bit')
    parser.add_argument('--zynq-elf', type=Path, default=ROOT / 'prebuilt/qspi-release/application.elf')
    parser.add_argument('--target-elf', type=Path)
    parser.add_argument('--etm-elf', type=Path)
    parser.add_argument('--serial', default='12345678', help='ZynqLinkPRO J7 USB serial')
    parser.add_argument('--sdk', type=Path, default=Path('E:/Xilinx/SDK/2018.3'))
    parser.add_argument('--rv-gcc', type=Path)
    parser.add_argument('--arm-gcc', type=Path)
    parser.add_argument('--break-symbol', help='Frequently executed function in the target ELF')
    parser.add_argument('--openocd', type=Path, help='Native OpenOCD executable for the matching target')
    parser.add_argument('--openocd-scripts', type=Path)
    parser.add_argument('--allow-flash', action='store_true', help='Permit target MCU Flash program and reset')
    parser.add_argument('--f103-restore-swj', type=int, choices=(0, 1, 2),
                        help='Original SWJ_CFG verified from firmware source (required for F103 JTAG)')
    parser.add_argument('--usb-data-cycle', action='store_true',
                        help='Prompt at physical data-only disconnects. Requires independent power.')
    parser.add_argument('--execute', action='store_true', help='Actually access the board')
    args = parser.parse_args(argv)
    if args.review:
        if args.execute:
            parser.error('--review is offline; omit --execute')
        try:
            result = review(args.review)
            if args.out:
                args.out.mkdir(parents=True, exist_ok=False)
                write_json(args.out / 'summary.json', result)
        except (KeyError, OSError, ValueError) as error:
            parser.error(str(error))
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return {'pass': 0, 'fail': 1, 'incomplete': 2}[result['status']]
    available = BOARDS[args.board][1]
    transports = tuple(dict.fromkeys(args.transport or available))
    if any(link not in available for link in transports):
        parser.error('Selected board does not support this link')
    only = set(args.only or FEATURES)
    cases = plan(args.board, transports, only, args.seed)
    if not args.execute:
        print(json.dumps({'execute': False, 'board': args.board, 'seed': args.seed,
                          'cases': cases}, ensure_ascii=False, indent=2))
        return 0
    if sys.flags.optimize:
        parser.error('Hardware acceptance requires Python assertions enabled')
    if not args.out or not args.runtime:
        parser.error('--execute requires --out and --runtime')
    if not args.serial.strip():
        parser.error('--serial must identify the J7 probe')
    args.out = args.out.resolve()
    if args.out.exists():
        parser.error('--out must be a new evidence directory')
    args.target_elf = (args.target_elf or ROOT / BOARDS[args.board][2]).resolve()
    args.bit = args.bit.resolve()
    args.zynq_elf = args.zynq_elf.resolve()
    args.sdk = args.sdk.resolve()
    args.runtime = args.runtime.resolve()
    if args.etm_elf is None:
        args.etm_elf = (ROOT / 'prebuilt/targets/stm32h743-cdc-trace-20261101/cpu60-trace20/fw.elf'
                        if args.board == 'h743' else args.target_elf)
    from tools.board_acceptance import BoardAcceptance
    try:
        metadata = {'board': args.board, 'probeSerial': args.serial, 'seed': args.seed, 'plan': cases,
                    'files': {label: digest(path.resolve()) for label, path in (
                        ('bit', args.bit), ('zynqElf', args.zynq_elf), ('targetElf', args.target_elf))}}
        git = ['git', '-C', str(ROOT)]
        metadata['revision'] = subprocess.check_output([*git, 'rev-parse', 'HEAD'], text=True).strip()
        metadata['sourceDirty'] = bool(subprocess.check_output([*git, 'status', '--porcelain',
                                                               '--untracked-files=no'], text=True).strip())
    except OSError as error:
        parser.error(str(error))
    report = Report(args.out, metadata)
    driver = BoardAcceptance(args, report)
    return campaign(cases, driver, report, set(transports) == set(available) and only == set(FEATURES))


if __name__ == '__main__':
    # Keep exception identities shared when drivers import the runner helpers.
    sys.modules.setdefault('tools.run_board_acceptance', sys.modules[__name__])
    raise SystemExit(main())
