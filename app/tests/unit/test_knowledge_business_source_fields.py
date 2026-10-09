"""Field evidence, independent facts, source impacts and local history boundaries."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from app.knowledge import business_review as review, business_use as use, business_run, business_edit, autoschema
from app.knowledge.business_models import SourceFieldJudgment
from app.knowledge.service import encode
from app.tests.unit.test_knowledge_business_edit import editing
from app.tests.unit.test_knowledge_business_semantic_edit import with_source, reviewed
from app.tests.unit.test_knowledge_business_local_review import meaning


def test_whole_source_status_does_not_fabricate_field_review():
    m = dict(meaning('m'), period='상시', conditions=['조건'])
    checks = review.source_judgment(m)['field_checks']
    assert checks['statement'] == 'supported'
    assert checks['period'] == checks['conditions'] == 'not_assessed'
    assert checks['exceptions'] == 'not_applicable'
    m['field_judgments'] = {'period': dict(status='unknown', reason='추가 기간 지지 없음', statement_affected=False)}
    assert review.source_judgment(m)['field_checks']['period'] == 'unknown'
    assert review.unresolved_source_fields(m) == []
    m['field_judgments']['period']['statement_affected'] = True
    assert review.unresolved_source_fields(m) == ['period']


def answer_selection(_s, _r, _stage, _prompt, context, schema):
    return schema.model_validate(dict(items=[dict(item_id='i', selected=[dict(meaning_ref='m1',use='direct_fact')],
        unconfirmed=[])])).model_dump()


@pytest.mark.parametrize('period', ['상시', '2~3일', '2026-10-08'])
def test_verified_period_is_preserved_and_independent_unverified_value_is_not_asserted(monkeypatch, period):
    m = reviewed(); m['period'] = period
    run = dict(reviewed_meanings=[m], answer_items=[dict(id='i',requirement_id='r',request_quote='요건')])
    monkeypatch.setattr(business_run, 'json_call', answer_selection)
    answer = use.reviewed_item_answer(None,run,SimpleNamespace(question='요건'),[])
    assert '기간: ' + period in answer['answer']
    m['field_judgments']['period'] = dict(status='unknown', reason='추가 기간과 정상 본문은 독립', statement_affected=False)
    answer = use.reviewed_item_answer(None,run,SimpleNamespace(question='요건'),[])
    assert m['statement'] in answer['answer'] and '기간:' not in answer['answer']
    assert run['answer_meaning_selection']['available']['m1']['period'] == period


def test_unresolved_condition_cannot_be_hidden_to_broaden_statement(monkeypatch):
    m = reviewed(); m['statement'] = '서류를 구비한다.'
    m['field_judgments']['conditions'] = dict(status='unknown', reason='부모 조건 미확정')
    normal = reviewed('normal'); normal['claim_ids'] = normal['required_claim_ids'] = ['normal']
    normal['claim_support'] = {'normal':'supported'}
    run = dict(reviewed_meanings=[m,normal], answer_items=[dict(id='i',requirement_id='r',request_quote='요건')])
    monkeypatch.setattr(business_run, 'json_call', answer_selection)
    answer = use.reviewed_item_answer(None,run,SimpleNamespace(question='요건'),[])
    assert answer['citations'] == ['normal']
    assert run['answer_meaning_selection']['excluded'][0]['key'] == 'm'
    # Legacy wording remains in the same bundle without a fabricated field verdict.
    m['field_judgments'].pop('conditions')
    answer = use.reviewed_item_answer(None,run,SimpleNamespace(question='요건'),[])
    assert '조건: 대리 방문' in answer['answer']
    assert 'c' in answer['citations'] and not run['answer_meaning_selection']['excluded']
    assert review.source_judgment(m)['field_checks']['conditions'] == 'not_assessed'


def test_empty_unknown_period_is_distinct_from_no_added_claim(editing):
    service,parent,change,request = with_source(editing)
    request.source_edits[0].period = ''
    request.source_edits[0].field_judgments = {'period':SourceFieldJudgment(status='unknown', reason='이전 기간 주장 미확인',statement_affected=False)}
    child = service.run(business_edit.start(service, change['id'], request)['run_id'])
    correction = child['source_corrections'][0]
    assert correction['after']['period'] == ''
    assert review.source_judgment(correction['after'])['field_checks']['period'] == 'unknown'
    assert review.source_judgment(correction['after'])['field_checks']['references'] == 'not_applicable'
    assert correction['origin'] == 'user' and correction['before'] == parent['assessments'][0]['source']['meanings'][0]
    assert correction['after_version'] != correction['expected_version']
    assert child['claims'] == parent['claims']


def test_source_only_edit_includes_corrected_document_in_related_requirements(editing):
    service,parent,change,request = with_source(editing)
    source_block = dict(parent['blocks'][0], id='other',source_id='source-other',source_version_id='v2')
    parent['blocks'].append(source_block); parent['input_version_ids'].append('v2')
    m = parent['assessments'][0]['source']['meanings'][0]
    m['evidence'] = [dict(block_id='other',quote=source_block['text'])]
    edit = request.source_edits[0]
    edit.expected_meaning_version = autoschema.identifier('meaning',m)
    edit.evidence = [type(request.evidence[0])(block_id='other',quote=source_block['text'])]
    related = dict(parent['requirements'][0],id='other-requirement',source_ids=['source-other'])
    with service.repository.connect() as db:
        service.repository.save(db,'runs',parent)
        db.execute('INSERT INTO requirements VALUES(?,?)',(related['id'],encode(related)))
    child = service.run(business_edit.start(service, change['id'], request)['run_id'])
    assert child['edit_impact']['candidate_requirement_ids'] == ['other-requirement']
    assert child['claims'] == parent['claims']


def test_local_history_uses_meaning_and_evidence_while_join_retains_all():
    docs = dict(meaning('docs'), evidence=[dict(block_id='document')],premise_keys=[])
    scope = dict(meaning('scope'), evidence=[dict(block_id='office')],premise_keys=[])
    change = dict(meaning_key='scope', before=dict(id='old',evidence=[dict(block_id='office')]),
                  after=dict(id='new',evidence=[dict(block_id='office')]),replacements=[])
    context = [dict(id='repair',changes=[change])]; original = deepcopy(context)
    assert review.local_repair_context(context,[docs],[docs,scope]) == []
    assert review.local_repair_context(context,[scope],[docs,scope]) == context
    docs['premise_keys'] = ['scope']
    assert review.local_repair_context(context,[docs],[docs,scope]) == context
    docs['premise_keys'] = []
    context[0]['changes'][0]['replacements'] = [dict(id='replacement', evidence=[dict(block_id='document')])]
    assert review.local_repair_context(context,[docs],[docs,scope]) == context
    assert original[0]['changes'][0]['replacements'] == []


def test_compact_history_resolves_actual_claim_evidence_and_ignores_extraction_chunks():
    m = dict(meaning('m'), evidence=[dict(block_id='body')],premise_keys=[])
    c = dict(id='c',role='event_entity',raw={'Event':'수정','Entity':['문서']},source_version_ids=['v'],
             evidence=[dict(block_id='body',precision='exact')])
    compact = business_run.compact_claim(c)
    assert 'evidence' not in compact
    context=[dict(id='repair',changes=[dict(meaning_key='user_edit',before=compact,after=compact)])]
    assert review.local_repair_context(context,[m],[m],[c]) == context
    c['evidence'][0]['precision']='chunk'
    assert review.local_repair_context(context,[m],[m],[c]) == []


def test_legacy_period_only_is_not_silently_removed_or_promoted(monkeypatch):
    m=reviewed(); m['field_judgments'].pop('period')
    assert m['period'] not in m['statement']
    run=dict(reviewed_meanings=[m],answer_items=[dict(id='i',requirement_id='r',request_quote='요건')])
    monkeypatch.setattr(business_run,'json_call',answer_selection)
    answer=use.reviewed_item_answer(None,run,SimpleNamespace(question='요건'),[])
    assert '기간: 2~3일' in answer['answer']
    assert review.source_judgment(m)['field_checks']['period']=='not_assessed'


def test_shared_heading_alone_is_not_a_local_expression_dependency():
    m=dict(meaning('m'),evidence=[dict(block_id='title'),dict(block_id='own-body')],premise_keys=[])
    c=dict(id='neighbor',evidence=[dict(block_id='other-body',precision='exact')],
           evidence_context=[dict(block_id='title',precision='exact')])
    context=[dict(id='repair',changes=[dict(meaning_key='other',before=None,after=c)])]
    assert review.local_repair_context(context,[m],[m],[c])==[]


def test_join_projection_keeps_uncertainty_and_all_semantic_fields():
    m=dict(meaning('m'), conditions=['원문 조건'],period='',
        field_judgments={'period':dict(status='unknown',statement_affected=False,reason='기간 주장 미확인'),
                         'conditions':dict(status='supported',statement_affected=True,reason='저장된 지지 이유')},
        correction=dict(id='correction',origin='user',actor='reviewer',reason='중복 감사 설명'),reason='중복 감사 설명')
    before=deepcopy(m); projected=review.join_source_meaning(m)
    assert m==before
    assert projected['statement']==m['statement'] and projected['conditions']==m['conditions']
    assert projected['field_judgments']['period']==m['field_judgments']['period']
    assert projected['field_judgments']['conditions']=={'status':'supported'}
    assert projected['judgment_version']==autoschema.identifier('meaning',m)
    assert projected['correction']==dict(id='correction',origin='user')


def test_application_resume_preserves_valid_cells_challenges_and_rejects_changed_parent(monkeypatch):
    import json
    from app.tests.unit.test_knowledge_business_local_review import local_run
    run=local_run();run.update(model_identity={});run['recipe'].update(generation={},models={'review':'local'})
    req=dict(id='r',revision=1,question='담당 기관?',criterion='서류')
    fact=meaning('m'); facts=dict(meanings=[fact]);saved={}
    good=dict(key='m',item_id='question',required_for_requirement=True,requirement_link=dict(
        requested_fact='담당 기관',applicability='applicable',contribution='direct_answer',reason='직접 업무'))
    challenge=dict(meaning_key='m',fields=['references'],claim_ids=[],reason='해결되지 않은 원문 이의',evidence=fact['evidence'])
    def first(_s,_r,_stage,_prompt,context,_schema):
        saved.update(deepcopy(context)); run['units'].append(dict(id='first', status='succeeded'))
        return dict(links=[deepcopy(good)],meaning_challenges=[challenge])
    monkeypatch.setattr(business_run,'json_call',first)
    prior=review.apply_requirement(None,run,req,facts,run['blocks'])
    unit=dict(id='first',messages=[{},dict(content=json.dumps(saved,ensure_ascii=False))],reference_map={},
        evidence_reference_map={str(i):b for i,b in enumerate(run['blocks'])},
        request_configuration=dict(identity={},generation={},model='local'))
    resume=dict(run_id='old',unit=unit,receipt=prior['application_history'][-1])
    assert len(resume['receipt']['errors'])==1
    def complete(_s,_r,_stage,_prompt,context,schema):
        assert context['application_tasks']==[dict(key='m',item_id='criterion')]
        run['units'].append(dict(id='second'))
        return schema.model_validate(dict(links=[dict(good,item_id='criterion',required_for_requirement=False,
            requirement_link=dict(requested_fact='',applicability='outside_scope',contribution='background',reason='다른 요청'))],meaning_challenges=[])).model_dump()
    monkeypatch.setattr(business_run,'json_call',complete)
    result=review.apply_requirement(None,run,req,prior,run['blocks'],resume=resume)
    assert not result['application_history'][-1]['errors']
    assert result['meanings'][0]['requirement_applications'][0]==prior['meanings'][0]['requirement_applications'][0]
    assert result['application_challenges']==prior['application_challenges']
    changed=deepcopy(run['blocks']);changed[0]['text']+='새 부모 조건'
    with pytest.raises(ValueError,match='동일한 원문'):
        review.apply_requirement(None,run,req,prior,changed,resume=resume)


def test_application_only_resume_never_hides_source_or_dependency_changes():
    before=dict(meanings=[dict(meaning('m'),premise_keys=[])],application_history=[],gaps=[])
    after=deepcopy(before);after['meanings'][0]['requirement_applications']=[{'item_id':'new'}]
    assert review.same_source_facts(before,after)
    for field,value in [('conditions',['다른 조건']),('premise_keys',['other']),('period','새 기간')]:
        changed=deepcopy(after);changed['meanings'][0][field]=value
        assert not review.same_source_facts(before,changed)


@pytest.mark.parametrize('sparse_response', [False, True])
def test_edit_recheck_resumes_only_recorded_sparse_response_once(editing, monkeypatch, sparse_response):
    service, parent, change, request = with_source(editing)
    parent['assessments'][0]['source']['application_history'] = [dict(unit_id='old')]
    with service.repository.connect() as db:
        service.repository.save(db, 'runs', parent)
    child_id = business_edit.start(service, change['id'], request)['run_id']
    calls = []
    monkeypatch.setattr(business_run.ModelClient, 'identities', lambda *a: {})
    def apply(_s, run, _q, facts, _b, *, resume=None):
        calls.append(resume)
        result = deepcopy(facts)
        if resume:
            assert resume['unit']['id'] == 'first'
            result['application_history'].append(dict(unit_id='second', output={'links':[]}, errors=[]))
        else:
            assert facts['application_history'] == []
            run['units'].append(dict(id='first', status='succeeded'))
            result['application_history'].append(dict(unit_id='first',
                output={'links':[]} if sparse_response else None,
                errors=[dict(meaning_key='m', item_id='i', reason='requirement_application_missing_or_duplicate')]))
        return result
    monkeypatch.setattr(review, 'apply_requirement', apply)
    def assess(_s, run, requirement, *, source, phase):
        assert [r['unit_id'] for r in source['application_history']] == ['old','first'] + (['second'] if sparse_response else [])
        result = dict(id='new', requirement_id='r', revision=1, source=source, representation=None, errors=[], status='unknown')
        run['assessments'].append(result)
        return result
    monkeypatch.setattr(business_run, 'assess', assess)
    business_edit.recheck(service, child_id)
    child = service.run(child_id)
    assert child['status'] == 'partial'
    assert len(calls) == (2 if sparse_response else 1)
