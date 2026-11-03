"""Recompute the archived three-round offline API comparison (no decoding)."""
import json
from pathlib import Path
import statistics


def summarize(raw):
    cases = {}
    for name in ('f103', 'h743-1s', 'h743-2s'):
        reports = {mode: json.loads((raw / ('api-' + mode + '-' + name + '.json')).read_text(encoding='utf8'))
                   for mode in ('reference', 'cpp')}
        before, after = reports['reference'], reports['cpp']
        assert before['inputSha256'] == after['inputSha256']
        assert before['inputUnchanged'] and after['inputUnchanged']
        assert len(before['rows']) == len(after['rows']) == 3
        times = {mode: [r['completeProcessingWallSeconds'] for r in report['rows']]
                 for mode, report in reports.items()}
        medians = {mode: statistics.median(values) for mode, values in times.items()}
        for a, b in zip(before['rows'], after['rows']):
            assert a['summary'] == b['summary'] and a['quality'] == b['quality']
        def index_median(report, key):
            return statistics.median(r['performance']['storeDetails']['index'][key] for r in report['rows'])
        cases[name] = dict(inputSha256=before['inputSha256'],
                           instructions=after['rows'][0]['summary']['instructions'],
                           trialsSeconds=times, medianSeconds=medians,
                           reductionPercent=100 * (medians['reference'] - medians['cpp']) / medians['reference'],
                           indexMedianSeconds={mode: {k: index_median(report, k) for k in (
                               'tablesSeconds', 'defaultViewsSeconds', 'encodeSeconds', 'totalSeconds')}
                               for mode, report in reports.items()},
                           cppControlResultBytes=[r['performance']['storeDetails']['controlResultBytes']
                                                  for r in after['rows']])
    return dict(scope='source offline API, three fresh records per input and implementation; OS caches retained',
                referenceCommit='b03275a99f6c', candidateRuntimeCommit='48e4d3d',
                nativeImplementationCommit='d39965bbb3a5', cases=cases)


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    result = summarize(root / 'raw')
    (root / 'raw/performance-summary.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    for name, case in result['cases'].items():
        print(name, case['medianSeconds'], 'reduction', round(case['reductionPercent'], 1), '%')
