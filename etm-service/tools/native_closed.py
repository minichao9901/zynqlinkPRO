"""Whole native decode/build: Python owns files and jobs, never ELF/code/facts."""
import json
import os
from pathlib import Path
import secrets
import time
from types import SimpleNamespace

import trace_store as ts
import native_storebuild as native
import native_complete


def write(record_dir, store_dir, **options):
    from decode_trace import decoder_config, ROOT
    import trace_store_write as writer
    started = time.perf_counter()
    record_dir, store_dir = Path(record_dir).resolve(), Path(store_dir).resolve()
    capabilities = native.probe()
    if 'native-static-v1' not in capabilities.get('capabilities', []):
        raise writer.NativeStorebuildUnavailable('原生核心缺少 native-static-v1，请更新完整程序')
    metadata = options.get('metadata')
    if metadata is None:
        metadata = writer._load_json(record_dir / 'decoded.json') if (record_dir / 'decoded.json').exists() else {}
    metadata = metadata or {}
    config = options.get('config') or metadata.get('config')
    if config is None and (record_dir / writer.CONFIG_FILE).exists():
        config = writer.manifest_config(record_dir / writer.CONFIG_FILE)
    config = decoder_config(config)
    elf = Path(options.get('elf') or record_dir / 'firmware.elf').resolve()
    etm = Path(options.get('etm') or record_dir / 'etm.bin').resolve()
    supplied = options.get('native_bin')
    native_path = Path(supplied).resolve() if supplied else record_dir / 'native.bin'
    binary = native_path.is_file() and native_path.name != 'native-direct.json' and not options.get('prefer_raw')
    if supplied and native_path.name == 'native-direct.json':
        descriptor = json.loads(native_path.read_text(encoding='utf8'))
        if descriptor.get('format') != 'etm-direct-v1':
            raise ts.TraceStoreError('Invalid direct descriptor')
        etm = Path(descriptor['etm']).resolve()
    if not binary and not etm.is_file():
        raise ts.TraceStoreError('缺少原始 ETM 输入')
    elf_sha = ts._sha256_file(elf)
    etm_sha = ts._sha256_file(etm) if etm.is_file() else None
    native_sha = ts._sha256_file(native_path) if binary else None
    source_sha = native_sha if binary else etm_sha
    sources = options.get('sources')
    if sources is None:
        sources = writer._load_json(record_dir / 'sources.json') if (record_dir / 'sources.json').exists() else {}
    retained = {key: metadata[key] for key in writer.METADATA_KEYS if key in metadata}
    core_hz = ((metadata.get('analysis') or {}).get('timing') or {}).get('coreHz')
    if core_hz is not None:
        retained['analysis'] = dict(timing=dict(coreHz=core_hz))
    session = writer._load_json(record_dir / 'session.json') if (record_dir / 'session.json').exists() else {}
    generation = 'g-%s-%s' % (time.strftime('%Y%m%dT%H%M%S'), secrets.token_hex(4))
    tag = secrets.randbits(63) or 1
    directory = store_dir / 'generations' / generation
    work = directory / 'work'
    work.mkdir(parents=True)
    phases, since = {}, started
    published = False

    def mark(name):
        nonlocal since
        now = time.perf_counter()
        phases[name] = round(now - since, 6)
        since = now

    def on_published():
        nonlocal published
        published = True

    context = dict(format='etm-complete-context/1', metadata=retained, config=config,
        session=session, sources={}, sourceSnapshot=sources, sourceRoot=str(ROOT / 'firmware'),
        recordDir=str(record_dir), expectedElfSha256=elf_sha, direct=not binary, elfName=elf.name,
        inputBytes=options.get('input_bytes') if options.get('input_bytes') is not None
        else etm.stat().st_size if etm.exists() else None,
        framing=options.get('framing'), physical=options.get('physical'), capture=options.get('capture'),
        maxEvents=options.get('max_events') or 0, compactIssues=os.environ.get('ETM_COMPACT_ISSUES', '1') != '0')
    context_path = work / 'complete-context.json'
    context_path.write_text(json.dumps(context, ensure_ascii=False), encoding='utf8')
    mark('inputPreparation')
    try:
        args = ['build', '--elf', str(elf), '--complete-context', str(context_path),
                '--out-dir', str(directory), '--generation', generation, '--generation-tag', hex(tag),
                '--native' if binary else '--etm', str(native_path if binary else etm)]
        built = native._run_json_command(args, work / 'native-result.json', native.DEFAULT_TIMEOUT)
        writer._validate_native_build_result(built,
            inputs={'nativeSha256' if binary else 'etmSha256': source_sha, 'elfSha256': elf_sha},
            static_dict_sha256=None)
        complete = built.get('completeStore') or {}
        static = complete.get('nativeStatic')
        if not static or static['elfSha256'] != elf_sha or not built['counts']['instructions']:
            raise ts.TraceStoreError('原生 ELF/静态字典未通过核验')
        mark('nativeClosedBuild')
        direct = None if binary else dict(etm=str(etm), deferred=True, inputs=complete['consumedInputs'])
        return native_complete.publish(record_dir, store_dir, directory, work, built,
            options=options, generation=generation, tag=tag, phases=phases, mark=mark,
            started=started, metadata=metadata, direct=direct, etm=etm, native_path=native_path,
            consumes_record_native=binary and native_path == record_dir / 'native.bin',
            etm_sha=etm_sha, native_sha=native_sha, source_sha=source_sha, elf=elf, elf_sha=elf_sha,
            image=SimpleNamespace(preparation=dict(native=True, cacheHit=False,
                parseSeconds=static['imageSeconds'], totalSeconds=static['imageSeconds'])),
            static_costs=dict(native=True, uniquePCs=static['uniquePCs'],
                buildSeconds=static['dictionarySeconds'], predicateCount=static['predicateCount'],
                knownCount=static['knownCount']), decode_info=None, on_published=on_published)
    except BaseException:
        if not published:
            ts._remove_tree(directory)
        raise


def decode(raw, elf, folder, *, config, sources=None, max_events=None, framing=None, physical=None, capture=None):
    started = time.perf_counter()
    folder = Path(folder)
    (folder / 'etm.bin').write_bytes(raw)
    result, decoded = write(folder, folder / 'store', elf=elf, config=config, sources=sources,
        input_bytes=len(raw), max_events=max_events, framing=framing, physical=physical,
        capture=capture, write_decoded=True, prefer_raw=True)
    decoded['performance'] = dict(version=2, generation=result['generation'],
        scope='offline-decode; excludes acquisition, upload and browser rendering',
        storePhasesSeconds=result['phases'], storeDetails=result['engine']['buildCosts'],
        decodeSeconds=time.perf_counter() - started,
        decodePhasesSeconds=dict(nativeClosedPipeline=time.perf_counter() - started))
    (folder / 'decoded.json').write_text(json.dumps(decoded, ensure_ascii=False), encoding='utf8')
    return decoded
