"""Analysis views over immutable blocks. IDs and offsets always point to the original."""
from copy import deepcopy
import re

from . import discovery_profile as profile

VERSION = 'source-spans-v3'


def clause_views(views):
    """Address circled paragraphs in the same packet, including their subordinate items."""
    result = []
    for view in views:
        starts = [m.start() for m in re.finditer('[①-⑳]', view['text'])]
        if view.get('context_only') or len(starts)<2:
            result.append(view); continue
        offset = view.get('span', [0])[0]
        boundaries = sorted({0, *starts, len(view['text'])})
        for a,b in zip(boundaries,boundaries[1:]):
            result.append(dict(view, text=view['text'][a:b], span=[offset+a,offset+b],
                context_only=a not in starts, analysis_target=a in starts))
    return result


def split(block):
    text = block['text']
    numbered = profile.numbered_items([block])
    markers = sorted({m['start'] for m in numbered} | {m.start() for m in re.finditer('[①-⑳]', text)})
    if len(markers) < 3:
        markers = [m.start() for m in re.finditer(r'(?m)^\s*[-*•]\s+\S', text)]
    if len(markers) < 3 and len(text) > 1600:
        markers = [m.end() for m in re.finditer(r'\n\s*\n|(?<=[다요]\.)\s+|;\s+', text)]
    if len(markers) < 3:
        return [dict(block_id=block['id'], span=[0,len(text)], shared_spans=[], recipe=VERSION)]
    if len(markers) <= 5 and len(text) <= 1600:
        return [dict(block_id=block['id'], span=[0,len(text)], shared_spans=[], recipe=VERSION)]
    boundaries = sorted({0, *markers, len(text)})
    spans = [[a,b] for a,b in zip(boundaries,boundaries[1:]) if text[a:b].strip()]
    prefix = [[0,markers[0]]] if markers[0] else []
    # ponytail: preserve all explicit exception passages as shared context; unresolved oversized
    # context stays partial. This is structural slicing, not a legal scope inference engine.
    shared = prefix + [span for span in spans if re.search('다만|이 경우|제외|예외|다음 각|각 호.*경우', text[slice(*span)])]
    focus = [span for span in spans if span not in prefix]
    return [dict(block_id=block['id'], span=[part[0][0],part[-1][1]],
                 shared_spans=[s for s in shared if not part[0][0] <= s[0] < part[-1][1]], recipe=VERSION)
            for n in range(0,len(focus),2) if (part := focus[n:n+2])]


def expand(frontier, by_id):
    """Split only groups containing a block that exceeds a small semantic working set."""
    expanded = []
    for group in frontier:
        views = [view for identifier in group['block_ids'] for view in split(by_id[identifier])]
        if len(views)==len(group['block_ids']):
            expanded.append(group)
            continue
        headers = [v['block_id'] for v in views if v['span']==[0,len(by_id[v['block_id']]['text'])] and len(by_id[v['block_id']]['text'])<256]
        for view in views:
            if view['block_id'] in headers: continue
            expanded.append(dict(group, id='sg_'+profile.digest([group['id'],view])[:20],
                parent_group_id=group['id'], block_ids=[view['block_id']], context_block_ids=headers, segments=[view],
                input_chars=view['span'][1]-view['span'][0], reason=group['reason']+'; 원문 구간별 분석',
                status='unvisited'))
    return expanded


def packet(group, by_id, context_map, whole_packet):
    raw = whole_packet(list(dict.fromkeys(group['block_ids'] + group.get('context_block_ids', []))), by_id, context_map)
    if not group.get('segments'): return clause_views(raw)
    views = []
    for block in raw:
        segments = [s for s in group['segments'] if s['block_id']==block['ref']]
        if not segments:
            views.append(dict(block, context_only=True))
            continue
        seen = set()
        for segment in segments:
            for span in [segment['span'], *segment['shared_spans']]:
                if tuple(span) in seen: continue
                seen.add(tuple(span))
                views.append(dict(block, text=block['text'][slice(*span)], span=span,
                                  analysis_target=span==segment['span'] and segment.get('analysis_target',False),
                                  context_only=span!=segment['span'], segment_recipe=segment['recipe']))
    return clause_views(views)


def target_coverage(output, provided):
    """Response presence only; citations never certify semantic completeness."""
    targets = {v['source_ref']:v for v in provided if v.get('analysis_target') and not v.get('context_only')}
    gaps = {}
    output['target_gap_errors'] = []
    for gap in output.get('target_gaps', []):
        if gap['source_ref'] not in targets:
            output['target_gap_errors'].append(dict(gap,reason='미제공 분석 항의 공백 응답: '+gap['reason']))
            continue
        gaps.setdefault(gap['source_ref'], []).append(gap['reason'])
    return [dict(block_id=v['ref'],span=v['span'],source_ref=ref,
        candidate_ids=[c['id'] for c in output.get('relations', []) if ref in c.get('source_refs', [])
                       and not c.get('validation') and not c.get('outside_scope_reason')],
        gaps=gaps.get(ref, []), semantic_status='unverified') for ref,v in targets.items()]


def originals(value):
    if isinstance(value, list): return [b for item in value for b in originals(item)]
    if isinstance(value, dict):
        if 'ref' in value and 'text' in value: return [value]
        return [b for child in value.values() for b in originals(child)]
    return []


def bind(context, run_id, unit_id):
    """Address existing packet views in one call, without serializing another copy of the text."""
    context = deepcopy(context)
    for view in originals(context):
        view['source_ref'] = 's' + profile.digest([run_id, unit_id, view['ref'],
            view.get('span', [0, len(view['text'])]), view['text']])[:16]
    return context


def restore(value, by_id, provided):
    """Resolve only this call's selected views. Legacy exact quotes remain untouched."""
    if isinstance(value, list):
        for child in value: restore(child, by_id, provided)
    elif isinstance(value, dict):
        for child in list(value.values()): restore(child, by_id, provided)
        for selected, ids, refs in [('source_refs','evidence_ids','evidence_refs'),
                                   ('counter_source_refs','counter_evidence_ids','counter_evidence_refs')]:
            if not value.get(selected): continue
            candidate = dict(source_refs=value[selected], evidence_ids=value.get(ids, []),
                source_quotes=value.get('source_quotes', []) if selected=='source_refs' else [])
            if selected=='source_refs' and value.get('quote'):
                candidate['source_quotes'] = [dict(evidence_id=value.get('evidence_id', ''), quote=value['quote'])]
            restored, errors = references(candidate, by_id, provided)
            if selected=='source_refs' and value.get('evidence_id') and value['evidence_id'] not in {e['evidence_id'] for e in restored}:
                errors.append('선택 구간과 근거 ID 불일치')
            if errors: raise ValueError('; '.join(errors))
            value[ids] = list(dict.fromkeys(e['evidence_id'] for e in restored))
            value[refs] = restored
            if selected=='source_refs' and 'evidence_id' in value:
                value.update(evidence_id=restored[0]['evidence_id'], quote=restored[0]['quote'])


def references(candidate, by_id, provided):
    """Ground exact quotes within actually provided views, retaining parent offsets."""
    result = []
    quotes = candidate.get('source_quotes', [])
    errors = []
    if candidate.get('source_refs'):
        views = {v['source_ref']:v for v in provided if v.get('source_ref')}
        for identifier in candidate['source_refs']:
            view = views.get(identifier)
            if view is None:
                errors.append('이번 호출에 제공되지 않은 source_ref'); continue
            b = by_id[view['ref']]
            start,end = view.get('span', [0,len(b['text'])])
            if not 0 <= start < end <= len(b['text']) or b['text'][start:end]!=view['text']:
                errors.append('선택 구간의 부모 원문 불일치'); continue
            ref = dict(evidence_id=view['ref'],block_id=b['id'],source_version_id=b['source_version_id'],
                parse_run_id=b['parse_run_id'],locator=deepcopy(b['locator']),span=[start,end],quote=view['text'])
            if ref not in result: result.append(ref)
        if candidate.get('evidence_ids') and set(candidate['evidence_ids'])!={r['evidence_id'] for r in result}:
            errors.append('선택 구간과 근거 ID 목록 불일치')
        if any(not any(q['evidence_id']==r['evidence_id'] and q['quote']==r['quote'] for r in result) for q in quotes):
            errors.append('선택 구간과 legacy 인용 불일치')
        return result, errors
    for identifier in candidate['evidence_ids']:
        b = by_id[identifier]
        views = [v for v in provided if v['ref']==identifier]
        selected = [q['quote'] for q in quotes if q['evidence_id']==identifier]
        if not selected:
            selected = [v['text'] for v in views if not v.get('context_only')] or [v['text'] for v in views]
        for quote in selected:
            positions = {v.get('span',[0,len(b['text'])])[0]+m.start()
                         for v in views for m in re.finditer(re.escape(quote),v['text'])} if quote else set()
            if len(positions)!=1:
                errors.append('원문 인용 구간 불명확 또는 이번 입력 밖')
                continue
            start = positions.pop(); end = start+len(quote)
            if b['text'][start:end]!=quote:
                errors.append('부모 원문 구간 불일치');continue
            ref = dict(evidence_id=identifier,block_id=b['id'],source_version_id=b['source_version_id'],
                       parse_run_id=b['parse_run_id'],locator=deepcopy(b['locator']),span=[start,end],quote=quote)
            if ref not in result: result.append(ref)
    if any(q['evidence_id'] not in candidate['evidence_ids'] for q in quotes):
        errors.append('인용과 근거 ID 목록 불일치')
    return result, errors
