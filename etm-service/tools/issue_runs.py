"""Lossless compact diagnostics; JSON rows are expanded only when requested."""
FORMAT = 'etm-issue-runs/1'
CATEGORIES = ('predicate', 'boundary')


def from_native(core, facts, quality, diagnostics):
    import trace_store as ts
    import trace_store_write as writer
    import native_binary
    reasons = [ts.IT_REASON]
    reason_ids = {ts.IT_REASON: 0}
    offsets = dict(diagnostics['events'])
    boundaries = []
    for event in facts['events']:
        if int(event['type']) in ts.BOUNDARY_TYPES:
            seq = int(event['seq'])
            reason = facts['evtexts'][int(event['textId'])]
            if reason not in reason_ids:
                reason_ids[reason] = len(reasons)
                reasons.append(reason)
            boundaries.append([seq, offsets[seq], reason_ids[reason]])
    faults = [dict(category='packet', startSeq=None, endSeq=None, records=0,
                   offset=offset, bytes=size,
                   reason='包问题：' + native_binary.packet_name(kind, core.meta['record']['protocol']))
              for offset, size, kind in diagnostics['faults']]
    extra = writer._packet_issues(quality, diagnostics['status'], quality['inputBytes'],
                                 diagnostics['packetEnd'], faults)
    return dict(format=FORMAT, reasons=reasons, predicates=diagnostics['predicateIssues'],
                boundaries=boundaries, extra=extra,
                total=len(diagnostics['predicateIssues']) + len(boundaries) + len(extra))


def unpack(value):
    import trace_store as ts
    def invalid():
        raise ts.TraceStoreError('紧凑诊断表结构无效')
    if not isinstance(value, dict) or value.get('format') != FORMAT:
        invalid()
    if 'predicates' in value:
        return _unpack_groups(value)
    reasons, rows, extra = (value.get(k) for k in ('reasons', 'rows', 'extra'))
    if (not isinstance(reasons, list) or not all(isinstance(s, str) for s in reasons)
            or not isinstance(rows, list) or not isinstance(extra, list)
            or not all(isinstance(row, dict) for row in extra)
            or type(value.get('total')) is not int or value['total'] != len(rows) + len(extra)):
        invalid()
    result = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 6 or any(type(v) is not int for v in row):
            invalid()
        lo, hi, count, offset, reason, category = row
        if (lo < 0 or hi < lo or count != hi - lo + 1 or offset < 0
                or not 0 <= reason < len(reasons) or not 0 <= category < len(CATEGORIES)):
            invalid()
        result.append(dict(category=CATEGORIES[category], startSeq=lo, endSeq=hi,
                           records=count, offset=offset, reason=reasons[reason]))
    result.extend(extra)
    return result


def _unpack_groups(value):
    import trace_store as ts
    def invalid():
        raise ts.TraceStoreError('紧凑诊断分组无效')
    reasons, predicates, boundaries, extra = (value.get(k) for k in ('reasons', 'predicates', 'boundaries', 'extra'))
    if (not isinstance(reasons, list) or not reasons or not all(isinstance(s, str) for s in reasons)
            or not all(isinstance(v, list) for v in (predicates, boundaries, extra))
            or not all(isinstance(v, dict) for v in extra)
            or type(value.get('total')) is not int
            or value['total'] != len(predicates) + len(boundaries) + len(extra)):
        invalid()
    result = []
    for row in boundaries:
        if not isinstance(row, list) or len(row) != 3 or any(type(v) is not int for v in row):
            invalid()
        seq, offset, reason = row
        if seq < 0 or offset < 0 or not 0 <= reason < len(reasons):
            invalid()
        result.append(dict(category='boundary', startSeq=seq, endSeq=seq, records=1,
                           offset=offset, reason=reasons[reason]))
    for row in predicates:
        if not isinstance(row, list) or len(row) != 3 or any(type(v) is not int for v in row):
            invalid()
        lo, hi, offset = row
        if lo < 0 or hi < lo or offset < 0:
            invalid()
        result.append(dict(category='predicate', startSeq=lo, endSeq=hi, records=hi-lo+1,
                           offset=offset, reason=reasons[0]))
    result.sort(key=lambda row: row['startSeq'])
    result.extend(extra)
    return result
