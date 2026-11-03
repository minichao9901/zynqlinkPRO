"""Static context and atomic publication for a completely C++-built store.

No execution facts, numeric query arrays or store blocks pass through Python.
Python retains record ownership, actual source bindings and manifest publication.
"""
import hashlib
import json
import os
from pathlib import Path
import time

import trace_store as ts


def write_context(path, entries, image, record_dir, *, metadata, config, elf, etm,
                  direct, options):
    import native_binary
    import trace_store_write as writer
    sources = {name: image.source(name) for name in sorted({e['file'] for e in entries if e['file']})}
    session = writer._load_json(record_dir / 'session.json') if (record_dir / 'session.json').exists() else {}
    # Match the pre-existing core metadata's packet diagnostic naming contract.
    # Protocol decoding itself always uses config.protocol, not this label map.
    retained = {key: metadata[key] for key in writer.METADATA_KEYS if key in metadata}
    core_hz = ((metadata.get('analysis') or {}).get('timing') or {}).get('coreHz')
    if core_hz is not None:
        retained['analysis'] = dict(timing=dict(coreHz=core_hz))
    context = dict(format='etm-complete-context/1', metadata=retained, config=config,
                   session=session, sources=sources, direct=bool(direct), elfName=elf.name,
                   inputBytes=options.get('input_bytes') if options.get('input_bytes') is not None
                   else etm.stat().st_size if etm.exists() else None,
                   framing=options.get('framing'), physical=options.get('physical'),
                   capture=options.get('capture'), maxEvents=options.get('max_events') or 0,
                   compactIssues=os.environ.get('ETM_COMPACT_ISSUES', '1') != '0',
                   packetNames=native_binary.ETMV4_PACKET_NAMES,
                   packetDefault=native_binary.ETMV4_DEFAULT_NAME)
    Path(path).write_text(json.dumps(context, ensure_ascii=False), encoding='utf8')


def publish(record_dir, store_dir, directory, work, built, *, options, generation, tag,
            phases, mark, started, metadata, direct, etm, native_path,
            consumes_record_native, etm_sha, native_sha, source_sha, elf, elf_sha,
            image, static_costs, decode_info, on_published):
    import trace_store_write as writer
    complete = built.get('completeStore')
    if not isinstance(complete, dict):
        raise ts.TraceStoreError('原生 builder 未返回完整索引/最终库结果')
    decoded, meta, index_meta = (complete[k] for k in ('decoded', 'meta', 'queryIndex'))
    counts = built['counts']
    if (decoded['summary']['instructions'] != counts['instructions']
            or meta['counts']['events'] != counts['events']
            or decoded['traceStore']['generation'] != generation
            or index_meta['instructions'] != counts['instructions']
            or not index_meta.get('tables') or len(index_meta['tables']) != 60
            or index_meta.get('builtBy') != 'native-complete-index'):
        raise ts.TraceStoreError('原生完整库计数/代/索引声明不符')
    files = built['files']
    if len(files) != 1 or files[0]['name'] != 'store.bin':
        raise ts.TraceStoreError('原生最终库文件声明不符')
    path = directory / 'store.bin'
    if path.stat().st_size != files[0]['bytes'] or ts._sha256_file(path) != files[0]['sha256']:
        raise ts.TraceStoreError('原生最终库长度/SHA 校验失败')
    container = ts._Container(path, ts.FILE_TRACE, tag)
    try:
        compact = os.environ.get('ETM_COMPACT_ISSUES', '1') != '0'
        if container.optional_features != ts.QUERY_INDEX_FEATURE or container.required_features != (ts.ISSUE_RUNS_FEATURE if compact else 0):
            raise ts.TraceStoreError('原生最终库特性位不符')
        stored_meta = container.of_type(ts.BLK_META)
        if len(stored_meta) != 1 or json.loads(container.block(stored_meta[0])) != meta:
            raise ts.TraceStoreError('原生最终库元信息与返回结果不符')
    finally:
        container.close()
    mark('verifyNativeStore')
    hash_inputs = options.get('hash_inputs', True)
    names = ('etm.bin', 'native-config.txt', 'firmware.elf', 'physical.json', 'framing.json',
             'tpiu.bin', 'session.json', 'sources.json')
    if consumes_record_native:
        names += ('native.bin',)
    names += tuple(p.name for p in record_dir.glob('image-*.bin'))
    capture = decoded.get('capture') or {}
    if capture.get('name'):
        names += (Path(capture['name']).name,)
    inputs = {name: dict(bytes=(record_dir / name).stat().st_size,
                         sha256=ts._sha256_file(record_dir / name) if hash_inputs else None)
              for name in names if (record_dir / name).is_file()}
    if direct:
        for name, expected in direct['inputs'].items():
            if ts._sha256_file(name) != expected:
                raise ts.TraceStoreError('Direct input changed during build: ' + name)
    if hash_inputs:
        consumed = [(elf, elf_sha)]
        if etm_sha is not None:
            consumed.append((etm, etm_sha))
        if native_sha is not None:
            consumed.append((native_path, native_sha))
        for path, expected in consumed:
            bound = inputs.get(path.name) if path.resolve() == (record_dir / path.name).resolve() else None
            observed = bound['sha256'] if bound else ts._sha256_file(path)
            if observed != expected:
                raise ts.TraceStoreError('输入在构建期间变化：' + path.name)
    mark('inputBindings')
    engine = dict(name='native', version=built['engine']['buildSha'], fallback=False,
                  buildCosts=dict(phases=phases, index=complete['indexTimings'], native=built['phases'],
                                  preparedDecode=dict(seconds=built.get('prepareSeconds'),
                                      replayBytes=built.get('replayBytes'), nativePeakRssBytes=built.get('peakRssBytes')),
                                  static=static_costs, image=getattr(image, 'preparation', None),
                                  completeIndex=True, scratchFactsWritten=False, storeWrites=1,
                                  controlResultBytes=built.get('controlResultBytes')))
    bindings = dict(inputs=inputs, config=decoded['config'], engine=engine,
                    processing=dict(traceStore=1, engine='native',
                        nativeFormat='direct-opencsd-v1' if direct else 'trace-bin native v1',
                        issueFormat='etm-issue-runs/1' if os.environ.get('ETM_COMPACT_ISSUES', '1') != '0' else 'json-list',
                        decodeStrategy='typed-replay-v1' if direct and direct.get('deferred') else 'direct-rescan' if direct else 'native-binary',
                        indexEngine='native-complete-index', finalStoreEngine='native'),
                    sourceInput=dict(kind='etm' if direct else 'native-binary',
                        recordFile='etm.bin' if direct and etm.resolve() == (record_dir / 'etm.bin').resolve()
                        else 'native.bin' if consumes_record_native else None, sha256=source_sha))
    if not consumes_record_native:
        bindings['unconsumedDerivedInputs'] = ['native.bin']
    if not hash_inputs:
        bindings['inputHash'] = dict(skipped=True, computed=False)
    manifest = dict(format=ts.FORMAT_NAME, schemaVersion=1, state='complete', byteOrder='little',
                    generation=generation, generationTag=hex(tag), files=files, counts=counts,
                    fieldPresence=meta['fieldPresence'], bindings=bindings,
                    queryIndex=index_meta, engine=engine)
    metadata_before = {}
    published = False
    try:
        if options.get('write_decoded'):
            sources = json.loads((work / 'complete-context.json').read_text(encoding='utf8'))['sources']
            for name, value in (('decoded.json', decoded), ('sources.json', sources)):
                destination = record_dir / name
                metadata_before[destination] = destination.read_bytes() if destination.exists() else None
                staged = work / name
                staged.write_text(json.dumps(value, ensure_ascii=False), encoding='utf8')
                os.replace(staged, destination)
                if name == 'sources.json':
                    inputs[name] = dict(bytes=destination.stat().st_size,
                                        sha256=ts._sha256_file(destination) if hash_inputs else None)
        ts._publish_manifest(store_dir, manifest)
        published = True
        on_published()
        mark('publish')
    finally:
        if not published:
            for path, payload in metadata_before.items():
                if payload is None:
                    path.unlink(missing_ok=True)
                else:
                    staged = work / (path.name + '.restore')
                    staged.write_bytes(payload)
                    os.replace(staged, path)
    if decode_info is not None and options.get('keep_native'):
        kept = directory / 'native.bin'
        os.replace(native_path, kept)
        native_path = kept
    warnings = []
    writer._compare_declared(metadata, decoded['summary'], decoded['quality'], warnings)
    if not hash_inputs:
        warnings.append('--no-hash-inputs：发布绑定未计算输入哈希')
    ts._remove_tree(work)
    mark('cleanup')
    return dict(ok=True, storeDir=str(store_dir), generation=generation, counts=counts,
                elapsedSeconds=time.perf_counter() - started, phases=phases, queryIndex=index_meta,
                storeBytes=files[0]['bytes'], storeSha256=files[0]['sha256'], engine=engine,
                inputBytes=decoded['inputBytes'], nativePath=str(native_path) if native_path.is_file() else None,
                nativeGenerated=decode_info is not None, decodeInfo=decode_info,
                peakRssBytes=ts.peak_rss_bytes(), nativePeakRssBytes=built.get('peakRssBytes'),
                elementsVerified=counts['ranges'], staticPcs=counts['staticPcs'],
                runs=counts['runs'], events=counts['events'], instructions=counts['instructions'],
                packetText=False, decodedWritten=bool(options.get('write_decoded')),
                decodedPath=str(record_dir / 'decoded.json') if options.get('write_decoded') else None,
                warnings=warnings), decoded
