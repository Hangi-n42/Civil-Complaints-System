from app.knowledge import discovery_segments as segments
import pytest


def block(text):
    return dict(id='b',text=text,source_version_id='v',parse_run_id='p',locator={'page':1})


def test_seven_items_keep_shared_conditions_offsets_and_full_original():
    original='제2조 이 조의 유형은 다음과 같다. '+ ' '.join(f'{i}. 유형{i}의 정의.' for i in range(1,8))+' 다만 예외 조건은 유지한다.'
    b=block(original); parts=segments.split(b)
    assert len(parts)==4 and b['text']==original
    for part in parts:
        text=original[slice(*part['span'])]
        shared=' '.join(original[slice(*s)] for s in part['shared_spans'])
        assert '제2조' in shared and '다만 예외 조건은 유지한다.' in text+shared
        assert part['block_id']=='b' and part['recipe']==segments.VERSION
    covered=''.join(original[slice(*p['span'])] for p in parts)
    assert all(f'유형{i}의 정의.' in covered for i in range(1,8))


def test_unnumbered_bullets_and_ambiguous_unstructured_text():
    assert len(segments.split(block('공통 조건\n'+''.join(f'- 항목{i} 정의\n' for i in range(7)))))==4
    assert len(segments.split(block('경계없는원문'*500)))==1


def test_quote_must_exist_in_the_provided_parent_span():
    b=block('앞 문장. 주 분석 정의. 미제공 문장.')
    view=dict(ref='b',text=b['text'][6:14],span=[6,14])
    ref,errors=segments.references(dict(evidence_ids=['b'],source_quotes=[dict(evidence_id='b',quote='주 분석 정의.')]),{'b':b},[view])
    assert not errors and ref[0]['span']==[6,14] and ref[0]['locator']==b['locator']
    ref,errors=segments.references(dict(evidence_ids=['b'],source_quotes=[dict(evidence_id='b',quote='미제공 문장.')]),{'b':b},[view])
    assert not ref and errors


def test_nested_article_preserves_governing_clause_for_later_numbered_item():
    text='제15조 ① 기본 선정. ② 잔여 주택 완화. ③ 다음 각 호에 해당하면 장관 또는 시ㆍ도지사가 별도 기준을 정한다. 1. 첫 조건. 2. 둘째 조건. 3. 셋째 조건. 4. 지방공사 건설 공급.'
    parts=segments.split(block(text))
    assert len(parts)>1
    last=parts[-1]
    provided=text[slice(*last['span'])]+' '.join(text[slice(*s)] for s in last['shared_spans'])
    assert '4. 지방공사 건설 공급.' in provided and '장관 또는 시ㆍ도지사가 별도 기준을 정한다.' in provided


def test_short_clauses_keep_one_group_and_subitems_with_parent():
    text='제15조 ① 별표에 따른 선정. ② 잔여주택이면 완화 또는 선착순. ③ 다음 각 호이면 별도 기준. 1. LH 공급. 2. 지방공사 공급.'
    b=block(text);group=dict(id='g',block_ids=['b'])
    assert segments.expand([group],{'b':b})==[group]
    raw=segments.packet(group,{'b':b},{},lambda *args:[dict(ref='b',text=text)])
    assert ''.join(v['text'] for v in raw)==text
    assert raw[0]['context_only'] and sum(v['analysis_target'] for v in raw)==3
    assert '1. LH' in raw[-1]['text'] and '2. 지방공사' in raw[-1]['text']
    provided=segments.originals(segments.bind(dict(blocks=raw),'run','relation:g'))
    output=dict(relations=[dict(id='r',source_refs=[provided[1]['source_ref']])],
                target_gaps=[dict(source_ref=provided[3]['source_ref'],reason='참조 별표 상세 미제공')],gaps=['별표 부재'])
    coverage=segments.target_coverage(output,provided)
    assert [bool(t['candidate_ids']) for t in coverage]==[True,False,False]
    assert not coverage[1]['gaps'] and coverage[2]['gaps']  # Missing vs deferred, neither is completed meaning.
    output['target_gaps'].append(dict(source_ref='outside',reason='미제공 항'))
    assert segments.target_coverage(output,provided)==coverage and output['target_gap_errors']
    output['relations'][0]['source_refs']=['whole_block_quote']
    assert all(not t['candidate_ids'] for t in segments.target_coverage(output,provided))
    assert segments.clause_views([dict(ref='b',text='표지 없는 원문')])==[dict(ref='b',text='표지 없는 원문')]


def test_selected_focus_and_shared_views_resolve_duplicate_text_and_parent_positions():
    b=block('공통. 반복. 반복. 미제공.')
    context=dict(blocks=[dict(ref='b',text=b['text'][a:z],span=[a,z],context_only=shared)
                        for a,z,shared in [(8,11,False),(0,3,True),(4,7,True)]])
    bound=segments.bind(context,'run','concept:g')
    provided=segments.originals(bound)
    assert context['blocks'][0].get('source_ref') is None
    selected=[v['source_ref'] for v in provided]
    assert len(set(selected))==3 and all(len(v['text'])==3 for v in provided)
    refs,errors=segments.references(dict(source_refs=selected,evidence_ids=[]),{'b':b},provided)
    assert not errors and [r['span'] for r in refs]==[[8,11],[0,3],[4,7]]
    assert all(r['quote']==b['text'][slice(*r['span'])] and r['locator']=={'page':1}
               and r['parse_run_id']=='p' and r['source_version_id']=='v' for r in refs)
    _,errors=segments.references(dict(evidence_ids=['b'],source_quotes=[dict(evidence_id='b',quote='반복.')]),{'b':b},provided)
    assert errors  # Legacy ambiguous quotes are not silently located at the first occurrence.
    item=dict(source_refs=[selected[0]],evidence_ids=[],counter_source_refs=[selected[1]],counter_evidence_ids=[])
    segments.restore(item,{'b':b},provided)
    assert item['evidence_refs']==refs[:1] and item['counter_evidence_refs']==refs[1:2]


@pytest.mark.parametrize('change', ['other_run','other_call','outside','different_quote','different_id'])
def test_source_ref_rejects_nonprovided_or_inconsistent_legacy_evidence(change):
    b=block('제공. 미제공.')
    context=dict(blocks=[dict(ref='b',text='제공.',span=[0,3])])
    provided=segments.originals(segments.bind(context,'run','concept:g'))
    candidate=dict(source_refs=[provided[0]['source_ref']],evidence_ids=[])
    if change in {'other_run','other_call'}:
        other=segments.bind(context,'other' if change=='other_run' else 'run',
                            'relation:g' if change=='other_call' else 'concept:g')
        candidate['source_refs']=[other['blocks'][0]['source_ref']]
    elif change=='outside': candidate['source_refs']=['unprovided']
    elif change=='different_quote': candidate['source_quotes']=[dict(evidence_id='b',quote='미제공.')]
    else: candidate['evidence_ids']=['other']
    with pytest.raises(ValueError): segments.restore(candidate,{'b':b},provided)
    exact=dict(source_refs=[provided[0]['source_ref']],evidence_ids=['b'],source_quotes=[dict(evidence_id='b',quote='제공.')])
    segments.restore(exact,{'b':b},provided)
    assert exact['evidence_refs'][0]['span']==[0,3]
