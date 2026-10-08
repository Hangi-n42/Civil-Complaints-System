"""Correction provenance, source-only callbacks, occurrence addresses and literal answers."""
from copy import deepcopy
from types import SimpleNamespace
import json

import pytest

from app.knowledge import autoschema, business_edit, business_review, business_run, business_use
from app.knowledge.business_models import BusinessDecision, SourceMeaningEdit
from app.knowledge.service import KnowledgeConflict, encode
from app.tests.unit.test_knowledge_business_edit import editing
from app.tests.unit.test_knowledge_business_local_review import meaning, judgments
from app.tests.unit.test_knowledge_business_event_repair import event_case


def with_source(editing):
    service, parent, change, request = editing
    source = dict(meanings=[meaning('m')], examined_block_ids=['body'], completeness='complete', gaps=[], conjunctions=[])
    assessment = dict(id='previous', requirement_id='r', revision=1, source=source,
        representation=judgments(['m'], ids=[request.claim_id]), errors=[], issues=[], status='satisfied')
    assessment['input_fingerprint'] = business_run.assessment_fingerprint(parent, parent['requirements'][0], source)
    parent['assessments'] = [assessment]
    with service.repository.connect() as db:
        service.repository.save(db, 'runs', parent)
    request.event = parent['claims'][0]['raw']['Event']
    request.error_owner = 'source'
    request.source_edits = [SourceMeaningEdit(requirement_id='r', meaning_key='m',
        expected_meaning_version=autoschema.identifier('meaning', source['meanings'][0]), mode='replace',
        reason='합성 원문 대조', evidence=source['meanings'][0]['evidence'], statement='정정된 원문 해석', conditions=['명시 조건'])]
    return service, parent, change, request


def test_source_only_correction_reaches_callback_and_stays_separate_from_model(editing, monkeypatch):
    service, parent, change, request = with_source(editing)
    child_id = business_edit.start(service, change['id'], request)['run_id']
    seen = []
    monkeypatch.setattr(business_run.ModelClient, 'identities', lambda *a: {})
    monkeypatch.setattr(business_review, 'apply_requirement', lambda _s, _r, _q, facts, _b: facts)
    def assess(_s, run, requirement, *, source, phase):
        seen.append(source['meanings'][0]['statement'])
        result = dict(id='new', requirement_id='r', revision=1, source=source, representation=None, errors=[], status='unknown')
        run['assessments'].append(result)
        return result
    monkeypatch.setattr(business_run, 'assess', assess)
    business_edit.recheck(service, child_id)
    child = service.run(child_id)
    assert seen == ['정정된 원문 해석']
    assert child['claims'] == parent['claims']
    assert child['source_corrections'][0]['origin'] == 'user'
    assert child['assessments'][-1]['source']['meanings'][0]['conditions'] == ['명시 조건']
    assert child['status'] == 'partial' and not business_use.change_view(service, child['changeset_id'])['eligible_ids']
    a = child['assessments'][-1]
    a['representation'] = dict(meaning_challenges=[dict(meaning_key='m', reason='모델의 이견')])
    monkeypatch.setattr(business_review, 'reassess_source', lambda *a: pytest.fail('explicit correction must not be overwritten'))
    assert business_run.reassess_challenges(service, child, child['requirements'][0], a) is a
    assert child['source_corrections'][0]['model_disagreements'][0]['challenge']['reason'] == '모델의 이견'


def test_stale_meaning_edit_rejected_before_revision_consumed(editing):
    service, parent, change, request = with_source(editing)
    request.source_edits[0].expected_meaning_version = 'stale'
    with pytest.raises(KnowledgeConflict):
        business_edit.start(service, change['id'], request)
    assert business_use.change_view(service, change['id'])['revision'] == 0
    with service.repository.connect() as db:
        assert service.repository.get(db, 'runs', parent['id']) == parent


def test_explicit_confirmation_is_separate_from_edit_and_model_eligibility(editing, monkeypatch):
    service, parent, change, request = with_source(editing)
    request.error_owner = 'both'
    request.event = request.source_edits[0].statement
    child = service.run(business_edit.start(service, change['id'], request)['run_id'])
    source = business_run.apply_source_corrections(child, child['requirements'][0], parent['assessments'][0]['source'])
    child['assessments'].append(dict(id='unresolved-model', requirement_id='r', revision=1, source=source,
        representation=None, errors=[], issues=[], status='unknown'))
    child['status'] = 'partial'
    with service.repository.connect() as db: service.repository.save(db, 'runs', child)
    published = business_use.publish(service, child)
    view = business_use.change_view(service, published['id'])
    assert not view['eligible_ids'] and len(view['explicit_review_options']) == 1
    decision = BusinessDecision(expected_revision=0, actor='synthetic reviewer', reason='원문과 정정 문장 명시 대조', accept_ids=[request.claim_id])
    with pytest.raises(ValueError): business_use.decide(service, published['id'], decision)
    decision.confirm_source_correction_ids = [view['explicit_review_options'][0]['correction_id']]
    receipt = business_use.decide(service, published['id'], decision)
    with service.repository.connect() as db: snapshot=service.repository.get(db,'snapshots',receipt['snapshot_id'])
    assert snapshot['assessments']['r']['recorded_status'] == 'unknown'
    rows = business_use.reviewed_answer_meanings(snapshot, {request.claim_id}, ['r'])
    assert rows[0]['expression_status'] == 'explicitly_reviewed'
    assert rows[0]['judgment_origin']['origin'] == 'user'
    assert rows[0]['statement'] == request.event


def test_snapshot_invalidation_is_scoped_and_preserves_contents(editing):
    service, parent, change, request = editing
    affected = dict(id='affected', kind='source_graph', run_id=parent['id'], claims=[parent['claims'][0]], assessments={})
    normal = dict(id='normal', kind='source_graph', run_id=parent['id'], claims=[parent['claims'][1]], assessments={})
    with service.repository.connect() as db:
        for snapshot in (affected, normal): db.execute('INSERT INTO snapshots VALUES(?,?)', (snapshot['id'], encode(snapshot)))
    business_edit.start(service, change['id'], request)
    with service.repository.connect() as db:
        assert service.repository.get(db, 'snapshots', 'normal') == normal
        stored = service.repository.get(db, 'snapshots', 'affected')
        events = [json.loads(row['payload']) for row in db.execute('SELECT payload FROM snapshot_events')]
    assert stored == affected
    assert events[0]['claim_ids'] == [request.claim_id] and events[0]['snapshot_id'] == 'affected'


def test_participant_occurrences_do_not_drop_parent_condition(monkeypatch):
    run, _, _ = event_case()
    old = run['claims'][0]
    block = dict(run['blocks'][0], text='기관은 신청을 받는다. 기관은 신청을 확인한다.')
    parent = dict(block, id='condition', text='대리 방문인 경우에만 적용한다.', locator={'heading_level':2})
    run['blocks'] = [parent, block]
    task = dict(meanings=[dict(meaning_key='m', reason='합성 오류', error_evidence=[dict(block_id='body',quote=block['text'])])])
    def call(_s, _r, _stage, _instruction, context, schema):
        options = context['participant_occurrences']
        assert len(options[0]) == 2 and len(options[1]) == 2
        return schema.model_validate(dict(sentences=['대리 방문인 경우 기관은 신청을 확인한다.'],
            participants={f'entity_{i}': list(values)[-1] for i,values in enumerate(options)})).model_dump()
    monkeypatch.setattr(business_run, 'json_call', call)
    patch = business_run.event_meaning_edit(None, run, task, old, run['blocks'])
    new = business_run.materialize_patch(run, patch, old, 'repair', run['blocks'], origin='model_event_edit')
    assert {e['block_id'] for e in new['evidence']} == {'body'}
    assert {e['block_id'] for e in new['evidence_context']} == {'condition'}
    assert new['edit_participants'][0]['start_char'] == block['text'].rindex('기관')
    assert new['edit_participants'][1]['start_char'] == block['text'].rindex('신청')
    assert new['raw']['Entity'] == old['raw']['Entity'] and new['semantic_status'] == 'unknown'


def reviewed(key='m', **updates):
    return dict(requirement_id='r', key=key, statement='대리 방문 때 서류를 구비한다.', conditions=['대리 방문'],
        exceptions=[], period='2~3일', references=[], claim_ids=['c'], required_claim_ids=['c'],
        complete_claim_bundle=True, expression_status='represented', source_status='supported', availability='provided',
        record_error=None, evidence=[dict(block_id='b', quote='원문')], claim_support={'c':'supported'},
        premise_keys=[], judgment_origin={'origin':'user'}, interpretation_version='v1',
        field_judgments={field: dict(status='supported', reason='합성 원문 개별 대조')
                         for field in ('statement', 'conditions', 'period')}, **updates)


@pytest.mark.parametrize('prior_applicability', ['outside_scope', 'unresolved'])
def test_reviewed_selection_renders_exact_meaning_and_rejects_partial_bundle(monkeypatch, prior_applicability):
    good = reviewed()
    good['requirement_link'] = dict(applicability=prior_applicability, contribution='background', requested_fact='이전 질문')
    partial = dict(reviewed('partial'), complete_claim_bundle=False, required_claim_ids=['c','missing'])
    run = dict(reviewed_meanings=[good,partial], answer_items=[dict(id='docs', requirement_id='r', request_quote='구비서류')])
    def choose(_s, _r, _stage, prompt, context, schema):
        assert list(context['reviewed_meanings']) == ['m1']
        assert 'requirement_link' not in context['reviewed_meanings']['m1']
        assert '번호판' not in prompt and '반납' not in prompt
        return schema.model_validate(dict(items=[dict(item_id='docs', selected=[dict(meaning_ref='m1',use='direct_fact')], unconfirmed=[])])).model_dump()
    monkeypatch.setattr(business_run, 'json_call', choose)
    answer = business_use.reviewed_item_answer(None,run,SimpleNamespace(question='어떤 서류?'),[])
    assert good['statement'] in answer['answer'] and '기간: 2~3일' in answer['answer']
    assert 'v1' not in answer['answer'] and 'user' not in answer['answer']
    assert answer['citations'] == ['c'] and run['answer_meaning_selection']['excluded'][0]['key'] == 'partial'
    assert run['answer_meaning_selection']['available']['m1']['requirement_link'] == good['requirement_link']
    assert run['answer_meaning_selection']['public_answer_items'] == run['answer_items']


def test_reviewed_selection_missing_and_premise_only_are_not_final_facts(monkeypatch):
    m = dict(reviewed(), premise_keys=['absent'])
    run = dict(reviewed_meanings=[m], answer_items=[dict(id='i',requirement_id='r',request_quote='처리 범위')])
    monkeypatch.setattr(business_run,'json_call',lambda *a,**k: pytest.fail('no complete premises'))
    assert business_use.reviewed_item_answer(None,run,SimpleNamespace(question='처리 가능?'),[])['citations'] == []
    m['premise_keys'] = None
    monkeypatch.setattr(business_run,'json_call',lambda *a,**k: dict(items=[dict(item_id='i',selected=[dict(meaning_ref='m1',use='premise_only')],unconfirmed=['이 기간과 처리 권한을 연결할 근거가 없다.'])]))
    answer = business_use.reviewed_item_answer(None,run,SimpleNamespace(question='처리 가능?'),[])
    assert '결론 연결 미확인' in answer['answer'] and '확인 불가:' in answer['answer']
    assert answer['limitations'] and not run['answer_item_errors']


def test_preservation_reuse_is_local_and_invalidated_by_meaning_or_claim_change(editing):
    _, run, _, _ = editing
    m = meaning('m'); claim = run['claims'][0]; requirement=run['requirements'][0]
    run['preservation_reuses']=[dict(requirement_id='r', requirement_revision=1,
        claim_versions={claim['id']:autoschema.identifier('claim',claim)},
        meaning_versions={'m':autoschema.identifier('meaning',m)},check={'target_id':claim['id']})]
    assert business_review.valid_preservation_reuses(run,requirement,[m])
    changed=dict(m,conditions=['새 조건'])
    assert not business_review.valid_preservation_reuses(run,requirement,[changed])
    run['claims'][0]['raw']['Event']='수정됨'
    assert not business_review.valid_preservation_reuses(run,requirement,[m])
