"""Auxiliary grading must retain invalid judgments without counting them as success."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys


def test_qa_empty_answer_stays_in_denominator_and_stop_is_between_calls(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[3] / 'scripts/evaluate_business_knowledge.py'
    spec = importlib.util.spec_from_file_location('business_qa_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    database = tmp_path/'knowledge.db'
    service = module.KnowledgeService(database)
    run = dict(id='r', status='partial', units=[], model_identity={}, recipe={}, changeset_id='c',
               requirements=[], claims=[])
    with service.repository.connect() as db:
        db.execute('INSERT INTO runs VALUES(?,?)', ('r', json.dumps(run)))
    service.shutdown()
    questions, reference = tmp_path/'questions.json', tmp_path/'reference.json'
    questions.write_text(json.dumps(dict(version='frozen', items=[dict(question_id='q1',
        question='접수 기관은?', choices=dict(A='기관', B='없음', C='센터', D='미상'))])), encoding='utf-8')
    reference.write_text(json.dumps(dict(version='frozen', items=[dict(question_id='q1', correct_choice='A')])), encoding='utf-8')
    monkeypatch.setattr(module.business_use, 'change_view', lambda *_: dict(id='c', revision=0,
        eligible_ids=[], published_eligible_ids=[], eligibility_contract='test', completion_contract='test'))
    monkeypatch.setattr(module.business_use, 'decide', lambda *_: dict(snapshot_id='s'))
    calls = []
    stop = tmp_path/'STOP'

    def empty_answer(_service, _request, *, context_mode):
        calls.append(context_mode)
        if len(calls) == 3:
            stop.write_text('explicit stop', encoding='utf-8')
        return dict(status='answered', answer=dict(answer='   ', choice='A', citations=[], limitations=[]))

    monkeypatch.setattr(module.business_use, 'query', empty_answer)
    args = [str(path), '--database', str(database), '--run-id', 'r', '--questions', str(questions),
            '--reference', str(reference), '--scope-note', 'mock scoring boundary', '--stop-file', str(stop)]
    output = tmp_path/'scores'
    monkeypatch.setattr(sys, 'argv', [*args, '--output', str(output)])
    module.main()
    scores = json.loads((output/'scores.json').read_text())['scores']
    assert all(s['denominator'] == 1 and s['correct'] == 0 and s['empty_answers'] == 1 for s in scores)
    # A stop after one saved answer prevents the next call and any gold parsing.
    reference.write_text('not JSON: must not be loaded while stopped', encoding='utf-8')
    stopped = tmp_path/'stopped'
    monkeypatch.setattr(sys, 'argv', [*args, '--output', str(stopped)])
    module.main()
    record = json.loads((stopped/'stopped.json').read_text())
    assert record['completed_answer_records'] == 1 and record['next_mode'] == 'graph'
    assert calls == ['document', 'graph', 'document']
    assert len(json.loads((stopped/'partial_answers.json').read_text())) == 1
    assert not (stopped/'scores.json').exists()


def test_local_reference_grading_keeps_bad_quote_unverified(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[3] / 'scripts/evaluate_business_semantics.py'
    spec = importlib.util.spec_from_file_location('business_semantics_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    database = tmp_path / 'knowledge.db'
    run = dict(id='r', status='partial', model_identity={'review': 'fixed'}, sources={'v': {}},
        recipe=dict(generation={'provider': 'ollama'}, models={'review': 'local'},
                    options=dict(context_tokens=49152, think=False, timeout=10)),
        blocks=[dict(id='b', text='기관은 신청을 접수한다.', source_version_id='v', locator={})],
        claims=[dict(id='c', role='entity_relation', raw=dict(Head='기관', Relation='접수한다', Tail='신청'))])
    fields = {'id': 13, 'name': '정류장'}
    row_text = json.dumps(fields, ensure_ascii=False)
    run['blocks'].append(dict(id='row', text=row_text, source_version_id='v', run_id='parse',
                             locator=dict(format='json', json_pointer='/0', fields=fields)))
    run['claims'].append(dict(id='row-claim', role='structured_row', construction_method='direct_tabular_row',
        statement=row_text, raw=dict(Event=row_text, fields=fields), source_version_ids=['v'],
        evidence=[dict(block_id='row', source_version_id='v', parse_run_id='parse', quote=row_text,
                       start_char=0, end_char=len(row_text))]))
    run['claims'].append(dict(id='old', role='entity_relation', raw=dict(Head='옛 오류', Relation='발생', Tail='신청'), superseded_by=['c']))
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE runs(id TEXT, payload TEXT)')
        db.execute('INSERT INTO runs VALUES(?,?)', ('r', json.dumps(run, ensure_ascii=False)))
    reference = tmp_path / 'reference.json'
    reference.write_text(json.dumps(dict(version='fixed', items=[dict(status='included', question_id=q,
        question='누가 접수하는가?', choices={'A': '기관'}, correct_choice='A', evidence=[],
        required_semantics_conditions_scope=['기관이 접수한다']) for q in ('q1', 'q2')]), ensure_ascii=False))

    class Client:
        def __init__(self, config): assert config['provider'] == 'ollama'
        def identities(self, *_): return run['model_identity']
        async def generate(self, request):
            if request.stage == 'evaluation_output_claims':
                return dict(failure_kind=None, parsed=dict(items=[dict(key='c1', status='supported',
                    claim_ids=['c1'], actual_expression='기관', source_quote='기관은 신청을 접수한다.', reason='원문 대조')]))
            assert request.stage == 'evaluation_fixed_semantics'
            return dict(failure_kind=None, parsed=dict(items=[dict(key=q + ':0', status='represented',
                claim_ids=['c1'], actual_expression='기관', source_quote=quote, reason='대조')
                for q, quote in [('q1', '기관은 신청을 접수한다.'), ('q2', '없는 원문')]]))

    output = tmp_path / 'output'
    monkeypatch.setattr(module, 'ModelClient', Client)
    monkeypatch.setattr(sys, 'argv', [str(path), '--database', str(database), '--run-id', 'r',
                                   '--reference', str(reference), '--output', str(output)])
    module.main()
    summary = json.loads((output / 'summary.json').read_text())
    assert summary['denominator'] == 2
    assert summary['counts']['represented'] == 1 and summary['unverified'] == 1
    assert not summary['model_independent'] and not summary['human_verified']
    batch = json.loads((output / 'batch_00.json').read_text())
    assert batch['judgments'][1]['record_errors'] == ['원문에 없는 인용']
    claim_output = tmp_path / 'claim_output'
    monkeypatch.setattr(sys, 'argv', [str(path), '--database', str(database), '--run-id', 'r',
                                   '--mode', 'output_claims', '--output', str(claim_output)])
    module.main()
    claim_summary = json.loads((claim_output / 'summary.json').read_text())
    assert claim_summary['denominator'] == 1 and claim_summary['counts']['supported'] == 1
    assert claim_summary['mode'] == 'output_claims' and not claim_summary['model_independent']
    assert claim_summary['structured_rows'] == dict(denominator=1, exact=1, mismatch_or_unverified=0, model_calls=0)
    freeze = json.loads((claim_output / 'freeze.json').read_text())
    assert freeze['reference_sha256'] is None and freeze['claim_view'] == 'active'
    assert freeze['stored_claim_count'] == 3 and freeze['all_claim_count'] == 2
    assert freeze['excluded_superseded_ids'] == ['old']


def test_auxiliary_claim_views_and_bounded_claim_precision_do_not_reconstruct_raw(tmp_path, monkeypatch):
    import pytest
    path = Path(__file__).resolve().parents[3] / 'scripts/evaluate_business_semantics.py'
    spec = importlib.util.spec_from_file_location('business_semantics_view_test', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    original = dict(claims=[dict(id='a')])
    assert module.evaluation_claims(original, 'construction') == original['claims']
    for history in [dict(repairs=[dict(changes=[dict(before=dict(id='a'), after=dict(id='a'))])]),
                    dict(stored_pool={'parent_run_id': 'old'}), dict(evaluation_intervention={'declared': True})]:
        with pytest.raises(ValueError):
            module.evaluation_claims(dict(original, **history), 'construction')
    run = dict(id='r', status='partial', sources={'v': {'title': '안내'}}, model_identity={'review': {'name': 'local'}},
        recipe=dict(generation={'provider': 'ollama'}, models={'review': 'local'},
                    options=dict(context_tokens=49152, think=False, timeout=10)),
        blocks=[dict(id='b', text='기관은 신청을 접수한다.', source_version_id='v', locator={})],
        claims=[dict(id=f'claim{i}', role='entity_relation', raw=dict(Head='기관', Relation='접수', Tail='신청')) for i in range(9)])
    database=tmp_path/'knowledge.db'
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE runs(id TEXT, payload TEXT)')
        db.execute('INSERT INTO runs VALUES(?,?)', ('r', json.dumps(run, ensure_ascii=False)))
    batch_sizes=[]
    contexts=[]
    class Client:
        def __init__(self, *_): pass
        def identities(self, *_): return run['model_identity']
        async def generate(self, request):
            context, targets = request.messages[-1]['content'].split('\n고정 참조 대상:\n')
            context, targets = json.loads(context), json.loads(targets)
            batch_sizes.append(len(context['claims']))
            contexts.append(request.context_tokens)
            assert len(context['blocks']) == 1 and not context['candidate_pool_is_reviewed_snapshot']
            assert {c['id'] for c in context['claims']} == {t['target_claim_id'] for t in targets}
            return dict(failure_kind=None, parsed=dict(items=[dict(key=t['key'], status='supported',
                claim_ids=[t['target_claim_id']], actual_expression='기관', source_quote='기관은 신청을 접수한다.', reason='원문 대조') for t in targets]))
    monkeypatch.setattr(module,'ModelClient',Client)
    args=[str(path),'--database',str(database),'--run-id','r','--mode','output_claims']
    preflight=tmp_path/'preflight';monkeypatch.setattr(sys,'argv',[*args,'--output',str(preflight),'--preflight-only'])
    module.main()
    assert not batch_sizes and json.loads((preflight/'preflight.json').read_text())['all_batches_fit']
    assert not (preflight/'summary.json').exists()
    construction=tmp_path/'construction'
    monkeypatch.setattr(sys,'argv',[*args,'--claim-view','construction','--output',str(construction),'--preflight-only'])
    module.main()
    assert json.loads((construction/'freeze.json').read_text())['planned'] == json.loads((preflight/'freeze.json').read_text())['planned']
    output=tmp_path/'output';monkeypatch.setattr(sys,'argv',[*args,'--output',str(output),'--context-tokens','65536'])
    module.main()
    assert batch_sizes == [8,1] and contexts == [65536,65536]
    freeze=json.loads((output/'freeze.json').read_text())
    assert freeze['options']['context_tokens'] == 65536
    assert freeze['product_options']['context_tokens'] == run['recipe']['options']['context_tokens'] == 49152
    assert json.loads((output/'summary.json').read_text())['denominator'] == 9


def test_auxiliary_expression_quote_can_use_scope_content_but_not_evidence_or_status():
    path = Path(__file__).resolve().parents[3] / 'scripts/evaluate_business_semantics.py'
    spec = importlib.util.spec_from_file_location('business_semantics_content_test', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    claim=dict(id='c', role='event_entity', raw=dict(Event='신청', Entity=['법인']),
        interpretation=dict(contract='unverified-local-extraction-scope-v3', semantic_status='unverified',
            evidence=[dict(quote='인용에만 있는 절차')], errors=['오류문구'], meanings=[dict(subject='법인',
            local_negation=dict(state='present',text='법인 방문 시 생략할 수 없다.'),
            evidence=[dict(quote='다른 인용')], address_errors=['잘못된 주소'])]))
    content=json.dumps(module.expression_content(claim),ensure_ascii=False)
    assert '법인 방문 시 생략할 수 없다.' in content
    assert all(text not in content for text in ['인용에만 있는 절차','다른 인용','오류문구','잘못된 주소','unverified','present'])
