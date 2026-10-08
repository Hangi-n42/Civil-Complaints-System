"""Inspection receipts and approved retrieval evidence do not replace semantic review."""
from copy import deepcopy

import pytest

from app.knowledge import autoschema, business_review as review, business_run, graph_retrieval as graph
from app.tests.unit.test_knowledge_business_local_review import local_run, current_source, judgments
from app.tests.unit.test_knowledge_business_scope import block
from app.tests.unit.test_knowledge_graph_retrieval import snapshot


@pytest.mark.parametrize('fault', [None, 'partial', 'wrong_block', 'wrong_version', 'wrong_parse',
                                    'wrong_revision', 'short_span', 'failed', 'meaning_error'])
def test_inspection_resume_keeps_history_and_requires_same_complete_target(monkeypatch, fault):
    run = local_run()
    run['blocks'].append(dict(block('unread', '다른 원문 구간이다.'), source_id='s'))
    old = current_source(); old['findings'] = []
    old['source_selection'] = dict(selected_block_ids=['body', 'unread'], unselected_block_ids=[])
    old['source_batches'] = [dict(unit_id='old', target_block_ids=['body', 'unread'],
        provided_block_ids=['body', 'unread'], errors=['local_source_inspection_scope_mismatch'],
        output=dict(examined_block_ids=['body'], inspection_status='complete'))]
    before = deepcopy(old)
    assert review.pending_inspections(old) == {'old': {'unread'}}
    assert review.needs_source_read(old, {'unselected_source_required': False})
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    calls = []
    def inspect(service, active, stage, prompt, context, schema):
        calls.append(context); active['units'].append(dict(id='followup'))
        assert {b['id'] for b in context['blocks'] if not b.get('context_only')} == {'unread'}
        return dict(examined_block_ids=[b['id'] for b in context['blocks']], inspection_status='complete',
            meanings=[], findings=[], conjunctions=[], meaning_conjunctions=[])
    monkeypatch.setattr(business_run, 'json_call', inspect)
    updated = review.source(None, run, run['requirements'][0], previous=old)
    assert len(calls) == 1 and updated['meanings'] == old['meanings'] and old == before
    assert updated['source_batches'][0] == old['source_batches'][0]
    receipt = updated['source_batches'][-1]
    if fault == 'partial': receipt['output']['inspection_status'] = 'partial'
    if fault == 'wrong_block': receipt['target_evidence'][0]['block_id'] = 'body'
    if fault == 'wrong_version': receipt['target_evidence'][0]['source_version_id'] = 'other'
    if fault == 'wrong_parse': receipt['target_evidence'][0]['parse_run_id'] = 'other'
    if fault == 'wrong_revision': receipt['inspection_context']['revision'] = 99
    if fault == 'short_span':
        ref = receipt['target_evidence'][0]; ref['quote'] = ref['quote'][:-1]; ref['end_char'] -= 1
    if fault == 'failed': receipt['errors'] = ['local_source_call_failed']; receipt['output'] = None
    if fault == 'meaning_error': receipt['errors'] = [dict(meaning_key='m', reason='meaning record invalid')]
    assert review.pending_inspections(updated) == ({'old': {'unread'}, 'followup': {'unread'}} if fault == 'failed'
        else {'old': {'unread'}} if fault and fault != 'meaning_error' else {})
    summaries = review.inspection_summaries(updated)
    unresolved = bool(fault and fault != 'meaning_error')
    assert summaries[0]['errors'] == old['source_batches'][0]['errors']
    assert summaries[0]['inspection_error_active'] == unresolved
    assert summaries[0]['remaining_target_block_ids'] == (['unread'] if unresolved else [])
    assert summaries[1]['reinspection_of'] == ['old']
    if fault == 'failed': assert summaries[1]['inspection_error_active']
    if fault == 'meaning_error': assert summaries[1]['errors'] == receipt['errors']
    result = judgments(['m']); result.update(source_completeness='complete', finding_resolutions=[])
    review.resolve_findings(updated, result, [], run['blocks'], [], joined=True)
    assert ('local_source_inspection_scope_mismatch' in updated['gaps']) == bool(fault and fault != 'meaning_error')
    if fault == 'meaning_error': assert 'meaning record invalid' in updated['gaps']
    assert updated['source_batches'][0] == old['source_batches'][0]


@pytest.mark.parametrize('fault', [None, 'wrong_version', 'outside_provided'])
def test_partial_declared_coverage_accumulates_without_retiring_uncovered_error(monkeypatch, fault):
    run = local_run()
    run['blocks'].extend(dict(block(bid, text), source_id='s') for bid, text in
                         [('read_next', '추가로 조사한 내용'), ('still_unread', '아직 조사하지 않은 내용')])
    old = current_source(); old['findings'] = []
    ids = [b['id'] for b in run['blocks']]
    old['source_selection'] = dict(selected_block_ids=ids, unselected_block_ids=[])
    old['source_batches'] = [dict(unit_id='old', target_block_ids=ids, provided_block_ids=ids,
        errors=['local_source_inspection_scope_mismatch'],
        output=dict(examined_block_ids=['body'], inspection_status='complete'))]
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    def inspect(service, active, stage, prompt, context, schema):
        active['units'].append(dict(id='partial'))
        return dict(examined_block_ids=['read_next'], inspection_status='complete',
                    meanings=[], findings=[], conjunctions=[], meaning_conjunctions=[])
    monkeypatch.setattr(business_run, 'json_call', inspect)
    updated = review.source(None, run, run['requirements'][0], previous=old)
    receipt = updated['source_batches'][-1]
    if fault == 'wrong_version':
        for ref in receipt['target_evidence']: ref['source_version_id'] = 'other'
    if fault == 'outside_provided': receipt['output']['examined_block_ids'].append('absent')
    pending = review.pending_inspections(updated)
    assert pending['old'] == ({'read_next', 'still_unread'} if fault else {'still_unread'})
    assert review.inspection_summaries(updated)[0]['inspection_error_active']
    assert updated['source_batches'][0] == old['source_batches'][0]
    if fault:
        return
    assert pending['partial'] == {'still_unread'}
    def finish(service, active, stage, prompt, context, schema):
        assert {b['id'] for b in context['blocks'] if not b.get('context_only')} == {'still_unread'}
        active['units'].append(dict(id='finished'))
        return dict(examined_block_ids=['still_unread'], inspection_status='complete',
                    meanings=[], findings=[], conjunctions=[], meaning_conjunctions=[])
    monkeypatch.setattr(business_run, 'json_call', finish)
    completed = review.source(None, run, run['requirements'][0], previous=updated)
    assert review.pending_inspections(completed) == {}
    assert not any(s['inspection_error_active'] for s in review.inspection_summaries(completed))
    assert completed['source_batches'][:2] == updated['source_batches']


@pytest.mark.parametrize('fault', [None, 'changed_claim', 'unapproved', 'missing_receipt',
                                    'wrong_version', 'wrong_parse', 'outside_span', 'changed_source'])
def test_reviewed_graph_view_preserves_all_evidence_and_raw_snapshot(fault):
    s = snapshot(); c = s['claims'][0]
    for b in s['blocks']: b['parse_run_id'] = 'p'
    # This synthetic claim originally points to all four input blocks.
    c['evidence'] = [deepcopy(v['evidence'][0]) for v in s['claims']]
    refs = business_run.exact_evidence(c['evidence'][:2], s['blocks'])
    s['reviewed_claim_evidence'] = {'c0': dict(claim_version=autoschema.identifier('claim', c),
        receipt_id='receipt', unit_id='unit', evidence=refs)}
    record = s['reviewed_claim_evidence']['c0']
    if fault == 'changed_claim': c['raw']['Tail'] = '다른 대상'
    if fault == 'unapproved': c['review_status'] = 'unreviewed'
    if fault == 'missing_receipt': record.pop('receipt_id')
    if fault == 'wrong_version': record['evidence'][0]['source_version_id'] = 'another'
    if fault == 'wrong_parse': record['evidence'][0]['parse_run_id'] = 'another'
    if fault == 'outside_span': record['evidence'][0]['start_char'] = 100
    if fault == 'changed_source': s['blocks'][0]['text'] = '바뀐 원문'
    before = deepcopy(s)
    expected = c['evidence'] if fault else refs
    assert graph.reviewed_evidence(s, c) == expected
    built, edges, passages, ignored = graph.build(s, 'full')
    assert {p['evidence']['block_id'] for p in passages.values() if 'c0' in p['claim_ids']} == {e['block_id'] for e in expected}
    raw, raw_edges, _, raw_ignored = graph.build(dict(s, reviewed_claim_evidence={}), 'full')
    assert edges == raw_edges and ignored == raw_ignored
    assert {n: d for n, d in built.nodes(data=True) if d['kind'] != 'passage'} == {
        n: d for n, d in raw.nodes(data=True) if d['kind'] != 'passage'}
    assert s == before
