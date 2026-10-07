"""Boundary checks for local source work size and unverified source addressing."""
from copy import deepcopy
import json
import jsonschema

from app.knowledge import autoschema, business_run
from app.knowledge.business_models import BusinessRunRequest


def block(identifier, text, path='', **locator):
    return dict(id=identifier, text=text, source_version_id='v', parse_run_id='p',
                locator=dict(element_path=path, **locator))


def scope_for(chunk, quote, head='기관', tail='신청'):
    alias=next(k for k,v in chunk['source_reference_map'].items() if v['block_id']=='body')
    evidence=[dict(block_id=alias, quote=quote)]
    def qualifier(text=None):
        return dict(state='present' if text else 'absent', text=text)
    meaning=dict(statement_type='rule', relation_kind='authority',
        subject=head, action='접수', object=tail, applies_to='본인 신청', modality='permission',
        conditions=qualifier('본인이 신청한 경우'), exceptions=qualifier(), time=qualifier(),
        local_negation=qualifier(), references=qualifier(), premises=dict(state='absent', meaning_indices=[]),
        evidence=evidence, participants=[
            dict(field='Head',entity_index=None,evidence=[dict(block_id=alias,quote=head)]),
            dict(field='Tail',entity_index=None,evidence=evidence)])
    return dict(evidence=evidence,meanings=[meaning])


def test_work_target_is_independent_of_capacity_and_context_keeps_ancestors():
    blocks=[block('heading','접수 안내','#root > h3:nth-of-type(1)'),
            block('parent','본인 미방문시','#root > ul > li::text(0)'),
            block('a','위임장 지참','#root > ul > li > ul > li:nth-of-type(1)'),
            block('b','대리인 신분증','#root > ul > li > ul > li:nth-of-type(2)')]
    small=autoschema.chunks(blocks,49152,4096,target_chars=10)
    roomy=autoschema.chunks(blocks,98304,4096,target_chars=10)
    large=autoschema.chunks(blocks,49152,4096,target_chars=1000)
    assert [c['blocks'] for c in small]==[c['blocks'] for c in roomy]
    assert len(small)>len(large)
    child=next(c for c in small if any(b['id']=='a' and not b.get('context_only') for b in c['blocks']))
    assert any(b['id']=='parent' and b['context_only'] for b in child['blocks'])
    assert any(b['id']=='heading' for b in child['blocks'])
    assert all(c['target_chars']<=10 or c['target_overflow_reason'] for c in small)
    packet=autoschema.source_packet([dict(blocks[2],continuation_bundle='bundle',context_only=False)])
    assert packet[0]['continuation_bundle']=='bundle'
    assert BusinessRunRequest(source_version_ids=['v'],requirement_ids=['r'],extraction_target_chars=10).extraction_target_chars==10


def test_scope_schema_raw_and_address_identity_survive_chunk_change():
    text='기관은 본인이 신청한 경우 접수할 수 있다.'
    original=block('body',text)
    one=autoschema.chunks([original],49152,4096,target_chars=1000)[0]
    two=autoschema.chunks([block('heading','안내','#root > h1:'),original],49152,4096,target_chars=1000)[0]
    raw=dict(Head='기관',Relation='접수',Tail='신청')
    scope1,scope2=scope_for(one,text),scope_for(two,text)
    schema=autoschema.extraction_schema('entity_relation')
    jsonschema.validate([dict(raw,Scope=scope1)],schema)
    assert 'Scope' not in autoschema.ATLAS_SCHEMA['entity_relation']['items']['properties']
    valid,rejected=autoschema.partition([dict(raw,Scope=scope1)],'entity_relation')
    assert valid[0]['value']==raw and not rejected
    a=autoschema.graph_record(one,'entity_relation',raw,0,scope=scope1)
    b=autoschema.graph_record(two,'entity_relation',raw,0,scope=scope2)
    assert a['raw']==raw and a['semantic_status']=='unknown'
    assert a['interpretation']['semantic_status']=='unverified'
    assert a['interpretation']['meanings'][0]['id']==b['interpretation']['meanings'][0]['id']
    graph=autoschema.graph([a,b])
    assert len(graph['nodes'])==2 and len(graph['edges'])==2
    node=next(n for n in graph['nodes'] if n['label']=='기관')
    assert set(node['chunk_ids'])=={one['id'],two['id']}
    messages,selection=autoschema.concept_messages(node,graph,{one['id']:one,two['id']:two})
    assert '미검증 지역 추출 해석' in messages[-1]['content']
    assert set(selection['mandatory_chunk_ids'])=={one['id'],two['id']}
    assert business_run.compact_claim(a)['interpretation']['semantic_status']=='unverified'
    before=deepcopy(a)
    compact=business_run.compact_claim(a)['interpretation']
    assert a==before and 'raw' not in compact
    assert compact['meanings'][0]['evidence'][0]['block_id']=='body'
    assert 'quote' not in compact['meanings'][0]['evidence'][0]
    assert compact['evidence'][0]['quote']==text
    assert 'mentions' not in compact
    assert [p['field'] for p in compact['meanings'][0]['participants']]==['Head','Tail']


def test_unresolved_and_reference_only_addresses_do_not_merge_or_generate_edges():
    original=block('body','기관과 기관은 신청을 접수한다.')
    chunk=autoschema.chunks([original],49152,4096)[0]
    raw=dict(Head='기관',Relation='접수',Tail='신청')
    scoped=scope_for(chunk,original['text'])
    a=autoschema.graph_record(chunk,'entity_relation',raw,0,scope=scoped)
    b=autoschema.graph_record(chunk,'entity_relation',raw,1,scope=scoped)
    assert a['interpretation']['mentions'][0]['address_status']=='unresolved'
    assert len([n for n in autoschema.graph([a,b])['nodes'] if n['label']=='기관'])==2
    context=deepcopy(chunk)
    context['blocks'][0]['context_only']=True
    c=autoschema.graph_record(context,'entity_relation',raw,0,scope=scoped)
    assert c['interpretation']['target_status']=='reference_only'
    assert autoschema.graph([c])['edges']==[]


def test_wide_evidence_does_not_identify_different_or_repeated_endpoints():
    text='장관과 시ㆍ도지사는 서로 다른 공급 주체의 신청을 처리한다.'
    chunk=autoschema.chunks([block('body',text)],49152,4096)[0]
    scope=scope_for(chunk,text,head='장관',tail='시ㆍ도지사')
    scope['meanings'][0]['participants'][0]['evidence']=scope['evidence']
    claim=autoschema.graph_record(chunk,'entity_relation',dict(Head='장관',Relation='비교',Tail='시ㆍ도지사'),0,scope=scope)
    mentions=claim['interpretation']['mentions']
    assert [m['evidence'][0]['quote'] for m in mentions]==['장관','시ㆍ도지사']
    assert len(autoschema.graph([claim])['nodes'])==2
    repeated='장관은 장관의 신청을 처리한다.'
    chunk2=autoschema.chunks([block('body',repeated)],49152,4096)[0]
    scope2=scope_for(chunk2,repeated,head='장관')
    scope2['meanings'][0]['participants'][0]['evidence']=scope2['evidence']
    ambiguous=autoschema.graph_record(chunk2,'entity_relation',dict(Head='장관',Relation='처리',Tail='신청'),0,scope=scope2)
    assert ambiguous['interpretation']['mentions'][0]['address_status']=='unresolved'
    events=deepcopy(scope)
    event=autoschema.graph_record(chunk,'event_relation',dict(Head='장관이 처리할 수 있다',Relation='비교',Tail='시ㆍ도지사가 처리할 수 있다'),0,scope=events)
    assert len(autoschema.graph([event])['nodes'])==2


def test_structure_repair_does_not_revert_to_chunk_label_identity(monkeypatch):
    chunk=autoschema.chunks([block('body','기관은 신청을 접수한다.')],49152,4096)[0]
    run=dict(recipe=dict(version=autoschema.VERSION),chunks=[chunk],claims=[],units=[dict(id='u')])
    business_run.store_extraction(run,chunk,'event_entity',dict(parsed=[dict(Event='기관은 신청을 접수한다.',Entity=[])]),run['units'][0])
    monkeypatch.setattr(business_run,'save',lambda *a:None)
    monkeypatch.setattr(business_run,'cancelled',lambda *a:False)
    monkeypatch.setattr(business_run,'json_call',lambda *a,**k:dict(status='repaired',rows=[dict(Event='기관은 신청을 접수한다.',Entity=['기관'])],evidence=[dict(block_id='body',quote='기관은 신청을 접수한다.')],reason='구조 보완'))
    business_run.repair_extraction(None,run)
    assert run['claims'][0]['interpretation']['target_status']=='unresolved'
    assert {n['identity_scope'] for n in autoschema.graph(run['claims'])['nodes']}=={'unresolved_item_address'}


def test_same_mention_shares_node_but_keeps_obligation_conditions_separate():
    text='기관은 접수 시 신청을 확인하고, 심사 시 서류를 확인한다.'
    chunk=autoschema.chunks([block('body',text)],49152,4096)[0]
    claims=[]
    for n,(tail,condition) in enumerate([('신청','접수 시'),('서류','심사 시')]):
        scope=scope_for(chunk,text,tail=tail)
        scope['meanings'][0]['conditions']=dict(state='present',text=condition)
        claims.append(autoschema.graph_record(chunk,'entity_relation',
            dict(Head='기관',Relation='확인',Tail=tail),n,scope=scope))
    graph=autoschema.graph(claims)
    assert len(graph['nodes'])==3 and len(graph['edges'])==2
    assert len(next(n for n in graph['nodes'] if n['label']=='기관')['claim_ids'])==2
    assert [graph['interpretations'][c['id']]['meanings'][0]['conditions']['text'] for c in claims]==['접수 시','심사 시']
    invalid=scope_for(chunk,text)
    invalid['meanings'][0]['exceptions']=dict(state='absent',text='absent')
    record=autoschema.graph_record(chunk,'entity_relation',dict(Head='기관',Relation='확인',Tail='신청'),2,scope=invalid)
    assert record['interpretation']['errors']
    assert record['interpretation']['raw']['meanings'][0]['exceptions']['text']=='absent'


def test_note_context_keeps_its_base_item_and_original_order():
    parent='#root > ul > li:nth-of-type(1) > ul'
    blocks=[block('title','서류 안내','#root > h3:nth-of-type(1)'),
            block('a','기본 확인서',parent+' > li:nth-of-type(1)'),
            block('b','대표자의 신분증',parent+' > li:nth-of-type(2)'),
            block('c','법인의 경우 추가 확인서',parent+' > li:nth-of-type(3)'),
            block('d','다만 방문 시 기본 확인서 생략',parent+' > li:nth-of-type(4)')]
    order={b['id']:n for n,b in enumerate(blocks)}
    chunks=autoschema.chunks(blocks,49152,4096,target_chars=10)
    for chunk in chunks:
        ids=[b['id'] for b in chunk['blocks']]
        assert ids==sorted(ids,key=order.get)
        if 'c' in ids or 'd' in ids:
            assert {'a','b','c','d'}<=set(ids)
    assert all(sum(not b.get('context_only') for c in chunks for b in c['blocks'] if b['id']==original['id'])==1
               for original in blocks)


def test_missing_html_parent_does_not_attach_the_entire_txt_article():
    body='제2조 정의. ' + '조건을 보존한다. ' * 250
    blocks=[block('title','법령 제목'),block('body',body)]
    chunks=autoschema.chunks(blocks,49152,4096,100)
    assert not any(b['id']=='body' and b.get('context_only') and b['text']==body for c in chunks for b in c['blocks'])
    assert {tuple(b['span']) for c in chunks for b in c['blocks'] if b['id']=='body' and not b['context_only']}


def test_selected_html_heading_is_context_for_every_body_chunk(tmp_path):
    from app.knowledge.parsers import plan_units, parse_unit
    path=tmp_path/'source.html'
    path.write_text('<section class="content-header"><h1>회의 제목<br>원문 날짜</h1></section>'
                    '<div id="record">첫 발언이다. 다음 발언이다. 조건이 있는 경우에도 원문을 보존한다.</div>',encoding='utf-8')
    units=plan_units(path,'html',{'selector':'section.content-header h1, #record'})
    rows=[b for u in units for b in parse_unit(path,'html',u)]
    blocks=[dict(row,id=str(i),source_version_id='v',parse_run_id='p') for i,row in enumerate(rows)]
    assert blocks[0]['locator']['heading_level']==1
    chunks=autoschema.chunks(blocks,49152,4096,10)
    body_chunks=[c for c in chunks if any(b['id']=='1' and not b.get('context_only') for b in c['blocks'])]
    assert body_chunks and all(any(b['id']=='0' for b in c['blocks']) for c in body_chunks)
    assert all(any(b.get('locator',{}).get('heading_level')==1 for b in autoschema.source_packet(c['blocks'])) for c in body_chunks)


def test_present_qualifier_requires_content_without_turning_unknown_into_absent():
    import pytest
    from pydantic import ValidationError
    from app.knowledge.business_models import ExtractionScope
    chunk = autoschema.chunks([block('body', '기관은 신청을 접수한다.')], 49152, 4096)[0]
    scope = scope_for(chunk, chunk['blocks'][0]['text'])
    for text in [None, '', '  ']:
        scope['meanings'][0]['conditions'] = dict(state='present', text=text)
        with pytest.raises(ValidationError):
            ExtractionScope.model_validate(scope)
    scope['meanings'][0]['conditions'] = dict(state='present', text=None)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate([dict(Head='기관', Relation='접수', Tail='신청', Scope=scope)], autoschema.extraction_schema('entity_relation'))
    for state in ['absent', 'unresolved', 'unavailable']:
        scope['meanings'][0]['conditions'] = dict(state=state, text=None)
        assert ExtractionScope.model_validate(scope).meanings[0].conditions.state == state


def test_repeated_quote_resolves_only_inside_an_actually_unique_parent_span():
    text = '기관은 신청을 접수한다. 기관은 이의를 심사한다.'
    chunk = autoschema.chunks([block('body', text)], 49152, 4096)[0]
    scope = scope_for(chunk, '기관은 이의를 심사한다.', head='기관', tail='이의')
    scope['meanings'][0]['evidence'] = [dict(block_id='b1', quote='기관')]
    scope['meanings'][0]['participants'][1]['evidence'] = [dict(block_id='b1', quote='이의')]
    raw = dict(Head='기관', Relation='심사', Tail='이의')
    record = autoschema.scope_record(scope, chunk, raw, 'entity_relation')
    head = record['meanings'][0]['participants'][0]
    assert head['address_status'] == 'resolved' and head['evidence'][0]['start_char'] == text.rindex('기관')
    assert record['raw'] == scope and record['semantic_status'] == 'unverified'
    # A broad parent containing both mentions still does not select an occurrence.
    scope['evidence'][0]['quote'] = text
    ambiguous = autoschema.scope_record(scope, chunk, raw, 'entity_relation')
    assert ambiguous['meanings'][0]['participants'][0]['address_status'] == 'unresolved'


def event_address_pair():
    first, second, third = '담당자가 접수한다.', '담당자가 검토한다.', '담당자가 교부한다.'
    chunk = autoschema.chunks([block('body', ' → '.join([first, second, third]))], 49152, 4096)[0]
    claims = []
    for index, (head, tail) in enumerate([(first, second), (second, third)]):
        scope = scope_for(chunk, head + ' → ' + tail, head=head, tail=tail)
        scope['meanings'][0]['participants'][1]['evidence'] = [dict(block_id='b1', quote=tail)]
        if index == 0:
            scope['meanings'][0]['participants'].pop()
        claims.append(autoschema.graph_record(chunk, 'event_relation',
            dict(Head=head, Relation='before', Tail=tail), index, scope=scope))
    return claims


def test_missing_event_endpoint_reuses_only_existing_exact_address_without_changing_claims():
    claims = event_address_pair()
    original = deepcopy(claims)
    donor_graph = autoschema.graph([claims[1]])
    graph = autoschema.graph(claims)
    assert graph['edges'][0]['tail'] == graph['edges'][1]['head'] == donor_graph['edges'][0]['head']
    assert len(graph['nodes']) == 3 and len(graph['edges']) == 2
    node = next(n for n in graph['nodes'] if n['id'] == graph['edges'][0]['tail'])
    receipt = node['address_reuses'][0]
    assert receipt['claim_id'] == claims[0]['id'] and receipt['field'] == 'Tail'
    assert receipt['donors'] == [dict(claim_id=claims[1]['id'], field='Head')]
    assert receipt['evidence'] == claims[1]['interpretation']['mentions'][0]['evidence'][0]
    assert claims == original and 'missing endpoint selector: Tail' in claims[0]['interpretation']['errors']
    assert graph['interpretations'] == {c['id']: c['interpretation'] for c in original}
    assert all(c['review_status'] == 'unreviewed' and c['semantic_status'] == 'unknown' for c in claims)
    reversed_graph = autoschema.graph(list(reversed(claims)))
    assert {n['id'] for n in reversed_graph['nodes']} == {n['id'] for n in graph['nodes']}


def test_event_endpoint_reuse_rejects_unproven_or_conflicting_addresses():
    for case in ('source', 'parse', 'block', 'ambiguous', 'unresolved', 'mixed_donor', 'existing_unresolved',
                 'existing_conflict', 'outside', 'invalid_relation', 'wording', 'wrong_kind',
                 'superseded', 'reference_only', 'stale_scope', 'stale_target'):
        claims = event_address_pair()
        target, donor = claims
        mention = donor['interpretation']['mentions'][0]
        ref = mention['evidence'][0]
        if case in {'source', 'parse', 'block'}:
            ref[{'source': 'source_version_id', 'parse': 'parse_run_id', 'block': 'block_id'}[case]] = 'different'
        elif case == 'ambiguous':
            other = deepcopy(donor)
            other['id'] += '_other'
            other_ref = other['interpretation']['mentions'][0]['evidence'][0]
            other_ref['start_char'] += 30
            other_ref['end_char'] += 30
            claims.append(other)
        elif case == 'unresolved':
            mention['address_status'] = 'unresolved'
        elif case == 'mixed_donor':
            unresolved = deepcopy(mention)
            unresolved['address_status'] = 'unresolved'
            donor['interpretation']['mentions'].append(unresolved)
        elif case in {'existing_unresolved', 'existing_conflict'}:
            existing = deepcopy(mention)
            existing['field'] = 'Tail'
            if case == 'existing_unresolved':
                existing['address_status'] = 'unresolved'
            else:
                existing['evidence'] = deepcopy(donor['interpretation']['mentions'][1]['evidence'])
            target['interpretation']['mentions'].append(existing)
        elif case == 'outside':
            target['interpretation']['evidence'] = deepcopy(target['interpretation']['mentions'][0]['evidence'])
        elif case == 'invalid_relation':
            target['interpretation']['evidence'] = []  # Claim/chunk fallback is deliberately retained.
        elif case == 'wording':
            donor['raw']['Head'] += ' 다른 문장'
            mention['value'] = donor['raw']['Head']
        elif case == 'wrong_kind':
            donor['role'] = 'entity_relation'
        elif case == 'superseded':
            donor['superseded_by'] = ['replacement']
        elif case == 'reference_only':
            donor['interpretation']['target_status'] = 'reference_only'
        elif case == 'stale_scope':
            donor['interpretation']['semantic_status'] = 'superseded'
        elif case == 'stale_target':
            target['interpretation']['semantic_status'] = 'superseded'
        original = deepcopy(claims)
        graph = autoschema.graph(claims)
        assert not any(n.get('address_reuses') for n in graph['nodes']), case
        assert claims == original, case
