"""Read-only summary of the archived offline API timing reports."""
import argparse
import json
from pathlib import Path
import statistics


def summarize(report):
    rows = []
    for row in report['rows']:
        perf = row['performance']
        outer = perf['storePhasesSeconds']
        details = perf['storeDetails']
        # These are sequential wall intervals. Native build includes wrapper
        # wait/validation; this is deliberately NOT a CPU-language breakdown.
        stages = dict(
            imagePreparation=perf['decodePhasesSeconds']['imagePreparation'],
            cppDecodeAndCache=details['preparedDecode']['seconds'],
            pythonStaticDictionary=details['static']['buildSeconds'],
            nativeBuildAndWrapper=outer['nativeBuild'],
            queryIndex=outer['queryIndex'],
            storeFinalization=sum(outer[k] for k in (
                'summary', 'issues', 'copyBlocks', 'assemble',
                'inputBindings', 'publish', 'cleanup')),
        )
        wall = row['completeProcessingWallSeconds']
        stages['otherAndUnattributed'] = wall - sum(stages.values())
        if stages['otherAndUnattributed'] < -0.01:
            raise ValueError('timing scopes overlap or changed')
        index = details['index']
        index_parts = dict(tables=index['tablesSeconds'],
                           defaultViews=index['defaultViewsSeconds'],
                           encode=index['encodeSeconds'])
        index_parts['readFactsAndOther'] = outer['queryIndex'] - sum(index_parts.values())
        rows.append(dict(trial=row['trial'], wallSeconds=wall,
                         imageCacheHit=perf['image']['cacheHit'],
                         addressCacheHit=details['static']['timings']['addressPreparationCacheHit'],
                         stagesSeconds=stages, indexPartsSeconds=index_parts,
                         nativeNestedSeconds=details['native'],
                         staticDetails=details['static'], imageDetails=perf['image'],
                         replay=details['preparedDecode'],
                         jobPhasesSeconds=perf['jobPhasesSeconds']))
    if not rows or not report.get('inputUnchanged'):
        raise ValueError('incomplete campaign or source inputs changed')
    representative = sorted(rows, key=lambda r: r['wallSeconds'])[len(rows) // 2]
    medians = {k: statistics.median(r['stagesSeconds'][k] for r in rows)
               for k in rows[0]['stagesSeconds']}
    ranges = {k: [min(r['stagesSeconds'][k] for r in rows),
                  max(r['stagesSeconds'][k] for r in rows)]
              for k in rows[0]['stagesSeconds']}
    index_medians = {k: statistics.median(r['indexPartsSeconds'][k] for r in rows)
                     for k in rows[0]['indexPartsSeconds']}
    summary = report['rows'][0]['summary']
    return dict(sourceRecord=report['sourceRecord'], inputSha256=report['inputSha256'],
                inputUnchanged=True,
                counts={k: summary[k] for k in ('instructions', 'ranges', 'packets',
                                               'gaps', 'unknownExecution')},
                wallMedianSeconds=statistics.median(r['wallSeconds'] for r in rows),
                medianStagesSeconds=medians, stageRangesSeconds=ranges,
                medianIndexPartsSeconds=index_medians,
                medianWallTrial=representative['trial'], rows=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', action='append', required=True, metavar='NAME=RESULTS_JSON')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cases = {}
    for item in args.input:
        name, filename = item.split('=', 1)
        if name in cases:
            parser.error('duplicate input name: ' + name)
        cases[name] = summarize(json.loads(Path(filename).read_text(encoding='utf8')))
    result = dict(scope='offline source Web API, no acquisition or browser rendering',
                  units='seconds; wall time, not exclusive CPU time',
                  notes=[
                      'Per-trial stages sum to completeProcessingWallSeconds.',
                      'Medians of separate stages do not necessarily sum to the median wall.',
                      'Native nested timings overlap: readNative=assemble; writeBlocks=assembleFile.',
                      'Native buildBlocks is inside readNative; online facts output is inside native queryIndex.',
                      'Index tablesSeconds includes finer table timings; do not sum them again.',
                      'Other includes imports, process startup/exit, handshakes, API scheduling and uninstrumented work.',
                      'Round 1 has empty application caches, but OS disk caches were not flushed.',
                  ], cases=cases)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    for name, case in cases.items():
        print(name, 'median', round(case['wallMedianSeconds'], 3),
              {k: round(v, 3) for k, v in case['medianStagesSeconds'].items()})


if __name__ == '__main__':
    main()
