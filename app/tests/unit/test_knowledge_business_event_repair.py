"""Native event patches preserve their role, provenance and review boundary."""
from copy import deepcopy

import jsonschema
import pytest
from pydantic import ValidationError

from app.knowledge import autoschema, business_run, business_review
from app.knowledge.business_models import Repairs
from app.knowledge.service import KnowledgeService, encode
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning, judgments
from app.tests.unit.test_knowledge_business_scope import scope_for


def event_case():
    run = local_run()
    run.update(id='event-repair-test', status='running')
    old = autoschema.graph_record(run['chunks'][0], 'event_entity',
        dict(Event='기관은 신청을 거부한다.', Entity=['기관', '신청']), 0)
    run['claims'][0] = old
    scope = scope_for(run['chunks'][0], run['blocks'][0]['text'])
    scope['evidence'] = [dict(block_id='body', quote=run['blocks'][0]['text'])]
    scope['meanings'][0]['evidence'] = deepcopy(scope['evidence'])
    scope['meanings'][0]['participants'] = [
        dict(field='Event', entity_index=None, evidence=deepcopy(scope['evidence'])),
        *[dict(field='Entity', entity_index=i, evidence=[dict(block_id='body', quote=value)])
          for i, value in enumerate(old['raw']['Entity'])]]
    patch = dict(meaning_key='m', target_id=old['id'], role='event_entity',
        raw=dict(Event=run['blocks'][0]['text'], Entity=deepcopy(old['raw']['Entity'])),
        evidence=deepcopy(scope['evidence']), conditions=[], exceptions=[], period='', references=[], scope=scope)
    assessment = dict(id='a', source=dict(meanings=[meaning('m')]),
        representation=judgments(['m'], 'incorrect', [old['id']]), errors=[], issues=[],
        actions=[dict(meaning_key='m', action='correct', claim_ids=[old['id']])])
    return run, assessment, patch


def test_native_event_patch_stores_before_after_and_builds_unreviewed_graph(tmp_path, monkeypatch):
    run, assessment, patch = event_case()
    before = deepcopy(run['claims'])
    def answer(_service, _run, stage, instruction, context, schema):
        payload = dict(patches=[patch], unresolved=[])
        jsonschema.validate(payload, schema.model_json_schema())
        return schema.model_validate(payload).model_dump()
    monkeypatch.setattr(business_run, 'json_call', answer)
    service = KnowledgeService(tmp_path / 'knowledge.db')
    try:
        with service.repository.connect() as db:
            db.execute('INSERT INTO runs VALUES (?,?)', (run['id'], encode(run)))
        assert business_run.repair(service, run, run['requirements'][0], assessment)
        with service.repository.connect() as db:
            stored = service.repository.get(db, 'runs', run['id'])
    finally:
        service.shutdown()
    assert stored == run
    after = stored['claims'][0]
    assert after['raw'] == patch['raw'] and after['statement'] == patch['raw']['Event']
    assert after['role'] == 'event_entity' and 'role_conversion' not in after
    assert after['source_extraction_raw'] == before[0]['raw']
    assert after['evidence'][0]['source_version_id'] == 'v'
    assert after['evidence'][0]['parse_run_id'] == 'p'
    assert after['review_status'] == 'unreviewed' and after['semantic_status'] == 'unknown'
    assert after['interpretation']['target_status'] == 'addressed'
    assert not after['interpretation']['errors']
    assert {(m['field'], m['entity_index']) for m in after['interpretation']['mentions']} == {
        ('Event', None), ('Entity', 0), ('Entity', 1)}
    receipt = stored['repairs'][0]
    assert receipt['before'] == before and receipt['after'] == stored['claims']
    assert receipt['status'] == 'applied_awaiting_recheck' and not stored['assessments']
    assert after['repair_id'] == receipt['id'] and stored['claims'][1] == before[1]
    context = business_review.candidate_repair_context(stored, {after['id']})
    assert context[0]['changes'][0]['before']['raw'] == before[0]['raw']
    assert context[0]['changes'][0]['after']['raw'] == after['raw']
    graph = autoschema.graph(stored['claims'])
    edges = [e for e in graph['edges'] if e['claim_id'] == after['id']]
    assert len(edges) == 2 and all(e['relation'] == 'participation' and e['status'] == 'unreviewed' for e in edges)
    nodes = {n['id']: n for n in graph['nodes']}
    assert {nodes[e['head']]['label'] for e in edges} == {patch['raw']['Event']}
    assert {nodes[e['tail']]['label'] for e in edges} == set(patch['raw']['Entity'])


@pytest.mark.parametrize('fault', ['empty_entity', 'bad_quote', 'missing_event', 'entity_index', 'foreign_source'])
def test_invalid_native_event_patch_cannot_change_claim(monkeypatch, fault):
    run, assessment, patch = event_case()
    if fault == 'empty_entity':
        patch['raw']['Entity'] = []
    elif fault == 'bad_quote':
        patch['evidence'][0]['quote'] = '없는 원문'
    elif fault == 'missing_event':
        patch['scope']['meanings'][0]['participants'].pop(0)
    elif fault == 'entity_index':
        patch['scope']['meanings'][0]['participants'][-1]['entity_index'] = 2
    else:
        other = dict(run['blocks'][0], id='other', source_version_id='foreign')
        run['blocks'].append(other)
        for refs in [patch['evidence'], patch['scope']['evidence'], patch['scope']['meanings'][0]['evidence'],
                     *[p['evidence'] for p in patch['scope']['meanings'][0]['participants']]]:
            for ref in refs: ref['block_id'] = 'other'
    before = deepcopy(run['claims'])
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: dict(patches=[patch], unresolved=[]))
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    assert not business_run.repair(None, run, run['requirements'][0], assessment)
    assert run['claims'] == before and run['repairs'][0]['errors']


def test_native_event_schema_requires_only_its_own_shape_and_legacy_shape_stays_valid():
    _, _, patch = event_case()
    native = Repairs.model_validate(dict(patches=[patch], unresolved=[])).model_dump()['patches'][0]
    assert 'head' not in native and 'relation' not in native and 'tail' not in native and 'statement' not in native
    legacy = {k: v for k, v in patch.items() if k not in {'raw', 'role'}}
    legacy.update(statement='기관은 신청을 접수한다.', head='기관', relation='접수', tail='신청')
    assert Repairs.model_validate(dict(patches=[legacy], unresolved=[])).patches[0].head == '기관'
    with pytest.raises(ValidationError):
        Repairs.model_validate(dict(patches=[dict(patch, head='기관', relation='접수', tail='신청')], unresolved=[]))


@pytest.mark.parametrize('reason', ['', '원문에서 사건과 참여자로 표현하도록 역할을 명시적으로 변경'])
def test_role_conversion_to_native_event_still_requires_reason(monkeypatch, reason):
    run, assessment, patch = event_case()
    run['claims'][0]['role'] = 'entity_relation'
    run['claims'][0]['raw'] = dict(Head='기관', Relation='거부', Tail='신청')
    patch['conversion_reason'] = reason
    before = deepcopy(run['claims'])
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: dict(patches=[patch], unresolved=[]))
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    assert business_run.repair(None, run, run['requirements'][0], assessment) is bool(reason)
    if reason:
        assert run['claims'][0]['role_conversion'] == dict(before='entity_relation', after='event_entity', reason=reason)
    else:
        assert run['claims'] == before
