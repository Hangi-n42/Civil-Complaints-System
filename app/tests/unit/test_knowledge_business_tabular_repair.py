"""Synthetic rows check preservation/address boundaries, not model semantic quality."""
from copy import deepcopy
import json
import pytest
from app.knowledge import autoschema, business_run, business_review as review
from app.tests.unit.test_knowledge_business_local_review import local_run, judgments, meaning
from app.tests.unit.test_knowledge_business_scope import block


def case():
    run = local_run()
    fields = dict(항목_ID='001', 순번=7, 값=1.25)
    rows = [dict(block('row' + str(i), json.dumps(fields, ensure_ascii=False), format='json', fields=deepcopy(fields)),
                 source_id='s', source_version_id='v' + str(i)) for i in range(2)]
    run['blocks'].extend(rows)
    run['chunks'] = autoschema.chunks(run['blocks'], 49152, 8192, 1000)
    req = run['requirements'][0]
    req['question'] = '항목_ID 001 순번 7의 값은?'
    _, selection = review.source_selection(run, req)
    meanings = []
    for i in range(5):
        row = rows[0 if i == 0 else 1]
        m = meaning('m' + str(i))
        m['evidence'] = business_run.exact_evidence([dict(block_id=row['id'], quote=row['text'])], run['blocks'])
        meanings.append(m)
    keys = [m['key'] for m in meanings]
    representation = judgments(keys, status='missing')
    a = dict(id='a', source=dict(meanings=meanings, source_selection=selection), representation=representation,
             errors=[], issues=[], actions=[dict(meaning_key=k, action='recover', claim_ids=[]) for k in keys])
    refresh(run, a)
    return run, req, a


def refresh(run, a):
    ids = [c['id'] for c in run['claims']]
    a['review_scope'] = dict(pool_hash=review.pool_hash(run), inventory_count=len(ids), candidate_inventory_ids=ids,
        batches=[dict(unit_id='local', error=None, meaning_keys=[m['key'] for m in a['source']['meanings']],
                      claim_ids=ids, provided_block_ids=[b['id'] for b in run['blocks']], output=a['representation'])])
    for t in a['actions']:
        t['missing_pool_check'] = dict(pool_hash=review.pool_hash(run), inventory_count=len(ids),
                                      all_candidates_accounted_for=True, failed_unit_ids=[])


def test_direct_rows_restore_two_versions_and_five_meanings_without_model_or_scope(monkeypatch):
    run, req, a = case()
    before, blocks = deepcopy(run['claims']), deepcopy(run['blocks'])
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: pytest.fail('No free-text repair call'))
    assert business_run.repair(None, run, req, a)
    receipt = run['repairs'][-1]
    assert run['claims'][:len(before)] == before and run['blocks'] == blocks
    assert len(receipt['changes']) == 2 and len(receipt['tabular_recovery']) == 5
    assert len({cid for m in receipt['tabular_recovery'] for cid in m['claim_ids']}) == 2
    for c in run['claims'][len(before):]:
        ref = c['evidence'][0]
        b = next(b for b in blocks if b['id'] == ref['block_id'])
        assert c['raw'] == dict(Event=b['text'], fields=b['locator']['fields'])
        assert c['raw']['fields']['항목_ID'] == '001' and type(c['raw']['fields']['값']) is float
        assert ref == business_run.exact_evidence([dict(block_id=b['id'], quote=b['text'])], blocks)[0]
        assert c['review_status'] == 'unreviewed' and c['semantic_status'] == 'unknown'
        assert 'interpretation' not in c and c['repair_id'] == receipt['id']
    assert {c['source_version_ids'][0] for c in run['claims'][len(before):]} == {'v0', 'v1'}
    graph = autoschema.graph(run['claims'])
    original = autoschema.graph(before)
    assert graph['edges'][:len(original['edges'])] == original['edges']
    restored = {c['id'] for c in run['claims'][len(before):]}
    row_edges = [e for e in graph['edges'] if e['claim_id'] in restored]
    assert len(row_edges) == 6 and {e['relation'] for e in row_edges} == {'항목_ID', '순번', '값'}
    assert all(e['status'] == 'unreviewed' for e in row_edges)
    nodes = {n['id']: n for n in graph['nodes']}
    assert len({e['head'] for e in row_edges}) == 2
    assert len({e['tail'] for e in row_edges}) == 6  # No equal-value merging across versions.
    for edge in row_edges:
        c = next(c for c in run['claims'] if c['id'] == edge['claim_id'])
        assert nodes[edge['head']]['fields'] == c['raw']['fields']
        assert nodes[edge['tail']]['value'] == c['raw']['fields'][edge['relation']]
        assert nodes[edge['tail']]['evidence'] == c['evidence']
    assert autoschema.concept_targets(graph) == autoschema.concept_targets(original)


def test_existing_exact_row_is_not_duplicated_or_marked_approved(monkeypatch):
    run, req, a = case()
    changes, _ = business_run.missing_tabular_rows(run, req, a, a['actions'])
    run['claims'].extend(c['after'] for c in changes)
    refresh(run, a)
    before = deepcopy(run['claims'])
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: pytest.fail('Existing row must not be rewritten'))
    assert not business_run.repair(None, run, req, a)
    assert run['claims'] == before and run['repairs'][-1]['changes'] == []
    assert len(run['repairs'][-1]['tabular_recovery']) == 5


@pytest.mark.parametrize('fault', ['non_table', 'partial_quote', 'wrong_version', 'different_rows', 'field_type',
    'no_lookup', 'stale_pool', 'incomplete_inventory', 'failed_local', 'not_required', 'unknown', 'represented'])
def test_ambiguous_or_unproven_rows_do_not_use_direct_recovery(fault):
    run, req, a = case()
    m = a['source']['meanings'][0]
    a['source']['meanings'] = [m]
    a['actions'] = a['actions'][:1]
    t = a['actions'][0]
    if fault == 'non_table':
        run['blocks'][-2]['locator']['format'] = 'html'
    elif fault == 'partial_quote':
        m['evidence'][0]['quote'] = '001'
    elif fault == 'wrong_version':
        m['evidence'][0]['source_version_id'] = 'other'
    elif fault == 'different_rows':
        b = run['blocks'][-1]
        b['locator']['fields']['값'] = 9.5
        b['text'] = json.dumps(b['locator']['fields'], ensure_ascii=False)
        run['chunks'] = autoschema.chunks(run['blocks'], 49152, 8192, 1000)
        m['evidence'].extend(business_run.exact_evidence([dict(block_id=b['id'], quote=b['text'])], run['blocks']))
    elif fault == 'field_type':
        run['blocks'][-2]['locator']['fields']['순번'] = '7'
    elif fault == 'no_lookup':
        req['question'] = '값은?'
    elif fault == 'stale_pool':
        run['claims'][0]['semantic_status'] = 'changed'
    elif fault == 'incomplete_inventory':
        a['review_scope']['candidate_inventory_ids'] = []
    elif fault == 'failed_local':
        t['missing_pool_check']['failed_unit_ids'] = ['local']
    elif fault == 'not_required':
        a['representation']['source_checks'][0]['required_for_requirement'] = False
    elif fault == 'unknown':
        m['source_status'] = 'unknown'
    elif fault == 'represented':
        a['representation']['checks'][0]['status'] = 'represented'
    assert business_run.missing_tabular_rows(run, req, a, a['actions']) == ([], [])


def test_exact_original_rows_are_not_rewritten_to_other_version_values(monkeypatch):
    run, req, a = case()
    newer = run['blocks'][-1]
    newer['locator']['fields']['값'] = 2.5
    newer['text'] = json.dumps(newer['locator']['fields'], ensure_ascii=False)
    run['chunks'] = autoschema.chunks(run['blocks'], 49152, 8192, 1000)
    for m in a['source']['meanings'][1:]:
        m['evidence'] = business_run.exact_evidence([dict(block_id=newer['id'], quote=newer['text'])], run['blocks'])
    refresh(run, a)
    changes, _ = business_run.missing_tabular_rows(run, req, a, a['actions'])
    rows = [c['after'] for c in changes]
    assert len(rows) == 2
    run['claims'].extend(rows)
    a['actions'] = [dict(meaning_key=a['source']['meanings'][i]['key'], action='correct',
                         claim_ids=[c['id']], reason='other version differs') for i, c in enumerate(rows)]
    for check, row in zip(a['representation']['checks'], rows):
        check.update(status='incorrect', claim_ids=[row['id']])
    before, verdicts = deepcopy(run['claims']), deepcopy(a['representation'])
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    monkeypatch.setattr(business_run, 'json_call', lambda *a, **k: pytest.fail('Exact rows need version review, not a rewrite model'))
    assert not business_run.repair(None, run, req, a)
    receipt = run['repairs'][-1]
    assert receipt['status'] == 'unresolved' and receipt['changes'] == [] and receipt['errors']
    assert {p['claim_id'] for p in receipt['protected_source_rows']} == {c['id'] for c in rows}
    assert run['claims'] == before and a['representation'] == verdicts
    assert all(c['review_status'] == 'unreviewed' for c in rows)
    assert [c['raw']['fields']['값'] for c in rows] == [1.25, 2.5]


@pytest.mark.parametrize('fault', ['value', 'type', 'version', 'parse', 'span', 'quote', 'duplicate_block'])
def test_direct_row_integrity_does_not_certify_a_changed_or_ambiguous_row(fault):
    run, _, a = case()
    changes, _ = business_run.missing_tabular_rows(run, run['requirements'][0], a, a['actions'])
    claim = changes[0]['after']
    assert business_run.exact_direct_row(claim, run['blocks']) == claim['evidence'][0]
    if fault == 'value':
        claim['raw']['fields']['값'] = 9.5
    elif fault == 'type':
        claim['raw']['fields']['순번'] = '7'
    elif fault == 'version':
        claim['source_version_ids'] = ['different']
    elif fault == 'parse':
        claim['evidence'][0]['parse_run_id'] = 'different'
    elif fault == 'span':
        claim['evidence'][0]['start_char'] = 1
    elif fault == 'quote':
        claim['evidence'][0]['quote'] = '001'
    else:
        run['blocks'].append(deepcopy(run['blocks'][-2]))
    assert business_run.exact_direct_row(claim, run['blocks']) is None


def test_repair_cannot_replace_one_error_with_another_current_correction_target(monkeypatch):
    run = local_run()
    ids = [c['id'] for c in run['claims']]
    keys = ['first', 'second']
    representation = judgments(keys, ids=ids)
    a = dict(id='a', source=dict(meanings=[meaning(k) for k in keys]),
        representation=representation, errors=[], issues=[], review_scope=dict(batches=[]),
        actions=[dict(meaning_key=k, action='correct', claim_ids=[cid], reason='confirmed error')
                 for k, cid in zip(keys, ids)] +
                [dict(meaning_key=k, action='maintain', claim_ids=[cid]) for k, cid in zip(keys, reversed(ids))])
    before = deepcopy(run['claims'])
    def answer(_service, _run, _stage, _instruction, context, _schema):
        assert context['reuse_candidates'] == []
        return dict(patches=[dict(meaning_key=keys[0], target_id=ids[0], reuse_claim_ids=[ids[1]],
            evidence=[dict(block_id='body', quote='기관은 신청을 접수한다.')])], unresolved=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(business_run, 'save', lambda *a: None)
    assert not business_run.repair(None, run, run['requirements'][0], a)
    assert run['claims'] == before
    assert run['repairs'][-1]['errors'] == ['현재 정상 검수로 확인되지 않은 대체 후보']


def disputed_rows():
    run, req, a = case()
    changes, _ = business_run.missing_tabular_rows(run, req, a, a['actions'])
    rows = [c['after'] for c in changes]
    run['claims'].extend(rows)
    a['actions'] = [dict(meaning_key=m['key'], action='correct', claim_ids=[c['id']], reason='version conflict')
                    for m, c in zip(a['source']['meanings'], rows)]
    a['source']['meanings'].append(meaning('unrelated_control'))
    return run, req, a, rows


def test_literal_row_dispute_reconsiders_own_source_meanings_without_approval():
    run, _, a, rows = disputed_rows()
    before = deepcopy((run, a))
    challenges = review.source_row_challenges(run, a)
    assert {c['meaning_key'] for c in challenges} == {'m0', 'm1', 'm2', 'm3', 'm4'}
    assert {cid for c in challenges for cid in c['claim_ids']} == {c['id'] for c in rows}
    assert all(c['evidence'] and 'required_for_requirement' in c['fields'] for c in challenges)
    assert (run, a) == before
    for row in rows:
        row['raw']['fields']['값'] = 99  # A real literal error must remain a correction target.
    assert review.source_row_challenges(run, a) == []
    plain = local_run()
    assert review.source_row_challenges(plain, dict(source=None, actions=[])) == []
    assert review.source_row_challenges(plain, dict(source=dict(meanings=[meaning('m')]),
        actions=[dict(action='correct', claim_ids=[plain['claims'][0]['id']])])) == []


def test_execute_routes_literal_row_dispute_to_existing_reassessment_once(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from app.knowledge import business_use
    run, _, a, _ = disputed_rows()
    before = deepcopy(run['claims'])
    run.update(id='run', stored_pool=True, concepts=[], metrics={})
    run['recipe']['options']['conceptualize'] = False
    a.update(requirement_id='r', status='partial')
    service = SimpleNamespace(lock=nullcontext(), repository=SimpleNamespace(
        connect=lambda: nullcontext(None), get=lambda *args: run, save=lambda *args: None))
    monkeypatch.setattr(business_run, 'save', lambda *args: None)
    monkeypatch.setattr(business_run, 'cancelled', lambda *args: False)
    monkeypatch.setattr(business_use, 'publish', lambda *args: dict(id='change'))
    monkeypatch.setattr(business_run, 'json_call', lambda *args, **kwargs: pytest.fail('No extra model loop'))
    def assess(*args, **kwargs):
        run['assessments'].append(a)
        return a
    calls = []
    def reassess(_service, _run, _req, previous, challenges):
        calls.append(deepcopy(challenges))
        assert previous is a
        return None  # Unresolved applicability cannot approve or rewrite literal rows.
    monkeypatch.setattr(business_run, 'assess', assess)
    monkeypatch.setattr(review, 'reassess_source', reassess)
    business_run.execute(service, run['id'])
    assert len(calls) == 1 and {c['meaning_key'] for c in calls[0]} == {'m0', 'm1', 'm2', 'm3', 'm4'}
    assert run['claims'] == before and run['status'] == 'partial' and not run.get('error')
    assert run['repairs'][-1]['protected_source_rows'] and not run['repairs'][-1]['changes']


def test_owned_error_boundary_preserves_other_version_without_repair_or_hidden_candidate(monkeypatch):
    from app.knowledge import business_store, business_use
    from app.tests.unit.test_knowledge_business_separated_review import synthesis
    run, req, _ = case()
    run['recipe']['review_contract'] = review.CONTRACT
    row_blocks = run['blocks'][-2:]
    row_blocks[1]['locator']['fields']['값'] = 2.5
    row_blocks[1]['text'] = json.dumps(row_blocks[1]['locator']['fields'], ensure_ascii=False)
    run['chunks'] = autoschema.chunks(run['blocks'], 49152, 8192, 1000)
    rows = [business_run.direct_tabular_row(next(c for c in run['chunks'] if any(b['id']==row['id'] for b in c['blocks'])), row, i)
            for i, row in enumerate(row_blocks)]
    run['claims'] = rows
    old, new = [c['id'] for c in rows]
    before = deepcopy(rows)
    m = dict(meaning('latest'), required_for_requirement=True)
    m['statement'] = '항목_ID 001 순번 7의 값은 2.5다.'
    m['evidence'] = rows[1]['evidence']
    source = dict(meanings=[m], review_contract=review.CONTRACT, examined_block_ids=[b['id'] for b in run['blocks']],
        source_batches=[], source_selection={}, findings=[], completeness='complete', gaps=[], conjunctions=[])
    calls = []
    def answer(service, run, stage, instruction, context, schema):
        calls.append(deepcopy(context));run['units'].append(dict(id=str(len(calls))))
        if context['mode']=='requirement_join': return synthesis()
        assert {c['id'] for c in context['claims']} == {old, new}
        assert {v['claim_id'] for v in context['source_row_integrity']} == {old, new}
        output = judgments(['latest'], ids=[new])
        output['checks'][0].update(incorrect_claim_ids=[old], claim_support={new:'supported',old:'not_assessed'},
            error_fields={old:['raw.fields.값']}, error_evidence=deepcopy(rows[1]['evidence']))
        run['units'][-1]['response'] = dict(parsed=deepcopy(output))
        return output
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(business_run, 'cancelled', lambda *_: False)
    monkeypatch.setattr(business_run, 'save', lambda *_: None)
    monkeypatch.setattr(business_store, 'save_assessment', lambda *_: None)
    result = business_run.assess(None, run, req, source=source)
    check = result['representation']['checks'][0]
    assert result['status']=='satisfied' and check['incorrect_claim_ids']==[]
    assert check['claim_support'][old]=='not_assessed'  # Exact raw is not whole-candidate approval.
    assert check['error_attributions'][0]['status']=='rejected_literal_source_match'
    assert run['units'][0]['response']['parsed']['checks'][0]['incorrect_claim_ids']==[old]
    assert not any(a['action']=='correct' for a in result['actions'])
    assert review.source_row_challenges(run, result)==[] and not business_run.repair(None, run, req, result)
    assert business_use.eligibility(run)[0]=={new} and rows==before
    # A real wrong raw value and an independently alleged Scope error remain reviewable.
    altered = deepcopy(rows[0]);altered['raw']['fields']['값']=9
    for candidate, field in [(altered, 'raw.fields.값'), (rows[0], 'interpretation.raw')]:
        check = dict(meaning_key='latest',status='represented',claim_ids=[new],incorrect_claim_ids=[old],
            claim_support={new:'supported',old:'incorrect'},error_fields={old:[field]},error_evidence=rows[0]['evidence'],reason='자기 원문 대조')
        review.own_source_errors(run,check,[candidate,rows[1]],run['blocks'])
        assert check['incorrect_claim_ids']==[old] and check['error_attributions'][0]['status']=='accepted'


def test_unowned_error_stays_candidate_unknown_without_blocking_independent_normal():
    from app.knowledge import business_use
    run = local_run();run['recipe']['review_contract']=review.CONTRACT;run['units']=[dict(id='u')]
    normal, disputed = [c['id'] for c in run['claims']]
    other = dict(block('other','다른 출처의 원문'),source_version_id='other-version')
    run['blocks'].append(other)
    check = dict(meaning_key='m',status='represented',claim_ids=[normal],incorrect_claim_ids=[disputed],
        claim_support={normal:'supported',disputed:'incorrect'},error_fields={disputed:['raw.Relation']},
        error_evidence=[dict(block_id='other',quote=other['text'])],reason='다른 출처에 근거한 오류 지목')
    review.own_source_errors(run,check,run['claims'],run['blocks'])
    assert check['incorrect_claim_ids']==[] and check['claim_support'][disputed]=='unknown'
    assert review.expression_attribution_valid(check,{normal,disputed})
    source=dict(review_contract=review.CONTRACT,meanings=[dict(meaning('m'),required_for_requirement=True)],completeness='complete',gaps=[])
    representation=judgments(['m']);representation['checks']=[check]
    a=dict(id='a',requirement_id='r',source=source,representation=representation,errors=[],issues=[],
           preservation_complete=True,candidate_accuracy_contract='candidate-own-source-errors-v1')
    a['input_fingerprint']=business_run.assessment_fingerprint(run,run['requirements'][0],source)
    run['assessments']=[a]
    eligible,blocked=business_use.eligibility(run)
    assert eligible=={normal} and 'unresolved_claim_support' in blocked[disputed]
    assert business_run.requirement_completion(a)['status']=='satisfied'
    from app.tests.unit.test_knowledge_business_separated_review import synthesis
    response = synthesis()
    response['checks'] = [dict(check, claim_support={normal: 'supported'}, error_fields={},
        error_attributions=[], error_evidence=[], evidence=meaning('m')['evidence'], revision_basis='prior_misreading')]
    joined, valid, _, errors = review.retain_synthesis(representation, response, {'m'}, {normal, disputed}, run['blocks'])
    assert valid and not errors
    retained = joined['checks'][0]
    assert retained['claim_support'][disputed] == 'unknown'
    assert retained['error_attributions'] == check['error_attributions']
    check['claim_ids']=[disputed]
    assert business_run.requirement_completion(a)['status']=='partial'
