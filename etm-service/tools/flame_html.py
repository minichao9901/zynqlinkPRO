"""Self-contained interactive flame export, shared by Web and offline CLI."""
import html
import json
import math

from flame_svg import MAX_FRAMES, make_frames
from trace_cli_paths import backend_root


def _aggregate(analysis, weight, root_path):
    if weight not in ('records', 'cycles'):
        raise ValueError('权重必须为 records 或 cycles')
    if weight == 'cycles' and not (analysis.get('timing') or {}).get('timeFlameAvailable'):
        raise ValueError('所选区间没有可用周期计数')
    root = analysis.get('flame')
    try:
        for part in str(root_path).split('.') if root_path else ():
            if not part.isdigit(): raise ValueError()
            root = root['children'][int(part)]
    except (KeyError, TypeError, IndexError, ValueError):
        raise ValueError('聚合图放大节点路径无效') from None
    key = 'valueCycles' if weight == 'cycles' else 'value'
    def value(node):
        v = float(node.get(key) or 0)
        if not math.isfinite(v) or v < 0: raise ValueError('调用树权重无效')
        return v
    if not root or value(root) <= 0: raise ValueError('当前权重下没有可绘制调用段')
    frames, pending = [], [(root, 0., 0, None)]
    while pending:
        node, x, depth, parent = pending.pop()
        width = value(node)
        index = len(frames)
        frames.append(dict(name=str(node['name']), depth=depth, start=x,
                           endExclusive=x+width, parent=parent))
        if len(frames) > MAX_FRAMES: raise ValueError('调用节点超过200000个，请缩小区间后导出')
        children = sorted((c for c in node.get('children', []) if value(c) > 0), key=value, reverse=True)
        if sum(map(value, children)) > width + max(1e-8, width*1e-10):
            raise ValueError('调用树子节点权重超过父节点')
        positions = []
        for child in children:
            positions.append((child, x, depth+1, index)); x += value(child)
        pending.extend(reversed(positions))
    return frames, value(root)


def build_data(view, start=None, end=None, mode='timeline', weight='records', root_path=''):
    if mode not in ('timeline', 'aggregate'): raise ValueError('火焰图模式必须为 timeline 或 aggregate')
    if (start is None) != (end is None): raise ValueError('必须同时指定区间起点和终点')
    info = view.overview()
    low, high = (0, int(info.get('eventCount') or 0)-1) if start is None else (int(start), int(end))
    if not 0 <= low <= high < int(info.get('eventCount') or 0): raise ValueError('火焰图导出区间超出记录范围')
    annotations = []
    if mode == 'timeline':
        if weight != 'records' or root_path: raise ValueError('执行顺序图横轴为执行序号，不接受周期权重或聚合节点路径')
        if hasattr(view, 'iter_events'):
            events = view.iter_events(low, high)
        else:
            def pages():
                offset = 0
                while True:
                    page = view.page('events', offset, 500, '', False, low, high)
                    yield from page['rows']
                    offset += len(page['rows'])
                    if not page['rows'] or offset >= page['total']: break
            events = pages()
        def checked():
            for event in events:
                if event['kind'] != 'instruction':
                    annotations.append([int(event['seq']), str(event.get('text') or event.get('kind'))])
                    if len(annotations) > MAX_FRAMES: raise ValueError('事件超过200000个，请缩小区间后导出')
                yield event
        try: frames, counts, depth = make_frames(checked())
        finally:
            if hasattr(events, 'close'): events.close()
        if not frames: raise ValueError('所选区间没有带调用栈的指令记录')
        for frame in frames: frame['endExclusive'] = frame['end']+1
        domain = [low, high+1]
        counts = {k: counts[k] for k in ('instructions', 'events', 'unknown', 'notTaken')}
    else:
        analysis = info.get('analysis') if start is None else view.window(low, high).get('analysis')
        frames, total = _aggregate(analysis or {}, weight, root_path)
        domain, counts = [0, total], {}
        depth = max(f['depth'] for f in frames)+1
    names, ids, packed = [], {}, []
    for frame in frames:
        name = frame['name']
        if name not in ids: ids[name] = len(names); names.append(name)
        packed.append([ids[name], frame['depth'], frame['start'], frame['endExclusive'], frame['parent']])
    return dict(schema='etm-flame-html/1', title='ETM 火焰图', mode=mode, weight=weight,
                range=[low, high], domain=domain, depth=depth, names=names, frames=packed,
                events=annotations, counts=counts,
                recordName=str(info.get('name') or ''), elfSha256=(info.get('elf') or {}).get('sha256'),
                axisBasis='execution sequence; not per-instruction time' if mode=='timeline' else weight)


def export_html(view, output, start=None, end=None, mode='timeline', weight='records', root_path=''):
    # Keep validating the existing CLI/Web options, but every HTML now opens
    # on the chronological view and contains a second, cycle-weighted tab.
    requested = build_data(view, start, end, mode, weight, root_path)
    data = requested if mode == 'timeline' else build_data(view, start, end)
    analysis = (view.overview().get('analysis') if start is None
                else view.window(start, end).get('analysis')) or {}
    timing = analysis.get('timing') or {}
    cycles = None
    cycle_reason = '所选区间没有周期计数数据（目标未启用，或 ETMv3 不支持）；不能用指令记录数代替周期。'
    if timing.get('timeFlameAvailable'):
        cycles = (requested if mode == 'aggregate' and weight == 'cycles'
                  else build_data(view, start, end, 'aggregate', 'cycles', root_path))
        cycles['timingBasis'] = str(timing.get('basis') or '记录中的周期计数；不是逐指令精确时间戳')
        cycle_reason = ''
    data = dict(data, schema='etm-flame-html/2', defaultTab='timeline',
                views={'timeline': data, 'cycles': cycles}, cycleUnavailableReason=cycle_reason)
    assets = backend_root()/'web/app'
    css = (assets/'standalone-flame.css').read_text(encoding='utf-8')
    js = (assets/'standalone-flame.js').read_text(encoding='utf-8')
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    for char, escaped in [('&', '\\u0026'), ('<', '\\u003c'), ('>', '\\u003e'), ('\u2028', '\\u2028'), ('\u2029', '\\u2029')]:
        payload = payload.replace(char, escaped)
    title = html.escape(data['recordName'] or data['title'])
    document = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>''' + title + ''' · 交互火焰图</title><style>''' + css + '''</style></head><body>
<header><div class="eyebrow">ETM · 离线交互火焰图</div><h1 id="title"></h1><p id="subtitle"></p></header>
<main><div class="tabs" role="tablist" aria-label="火焰图视图"><button id="tab-timeline" role="tab" aria-selected="true" aria-controls="flame-panel">Timeline · 执行顺序</button><button id="tab-cycles" role="tab" aria-selected="false" tabindex="-1" aria-controls="flame-panel">周期权重火焰图</button></div>
<section id="flame-panel" role="tabpanel" aria-labelledby="tab-timeline"><p id="unavailable" role="status" hidden></p><div id="chart-content"><section class="toolbar" aria-label="火焰图控制">
<div class="buttons"><button id="zoom-in" title="放大（+）">＋ 放大</button><button id="zoom-out" title="缩小（−）">− 缩小</button><button id="reset" title="完整导出区间（Home）">复位</button><button id="back">上一级</button><button id="focus" disabled>放大选中调用</button></div>
<div class="search"><input id="search" type="search" placeholder="查找函数，保留其他调用" aria-label="查找函数"><button id="previous-match">上一个</button><button id="next-match">下一个</button><span id="match-count"></span></div>
</section><div class="range"><span id="range-label"></span><span id="hint">左键拖动框选放大 · Shift＋拖动平移 · 滚轮缩放 · 双击调用段放大</span></div>
<div id="axis" aria-hidden="true"></div><div id="viewport"><div id="spacer"></div><canvas id="chart" tabindex="0" role="img" aria-label="可缩放的调用火焰图"></canvas></div>
<div id="tooltip" role="tooltip" hidden></div><section id="detail" aria-live="polite">悬停查看完整函数名和区间；点击保留调用详情。</section>
<footer><span id="stats"></span><span>全部调用数据内嵌，可离线打开。窄调用段放大后可查看，完整调用深度保留。</span></footer></div></section></main>
<script type="application/json" id="flame-data">''' + payload + '''</script><script>''' + js + '''</script></body></html>'''
    output.write_text(document, encoding='utf-8')
    return dict(mode=mode, fromSeq=data['range'][0], toSeq=data['range'][1],
                frames=len(data['frames']), depth=data['depth'], selfContained=True,
                tabs=['timeline', 'cycles'], defaultTab='timeline',
                cyclesAvailable=cycles is not None)
