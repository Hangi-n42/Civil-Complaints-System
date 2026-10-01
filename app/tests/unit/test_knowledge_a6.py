"""A6 instrumentation contracts; doubles do not count as model or human evidence."""
import json

import pytest

from scripts import run_knowledge_a6 as a6
from scripts import prepare_knowledge_a6_review as review
from app.knowledge import discovery_inputs as inputs
from app.tests.unit.test_knowledge_discovery_run import corpus


def test_order_intervention_preserves_content_and_reverses_execution_priority():
    def survey(files, blocks):
        return ['profile'], [dict(file_id=i, block_ids=[i], priority=1, reason='원문')
                             for i in ['first', 'second']], {'context': 'kept'}
    result = a6.ordered_survey(survey, ['second', 'first'])([], [])
    assert [g['file_id'] for g in sorted(result[1], key=lambda g: g['priority'])] == ['second', 'first']
    assert {i for g in result[1] for i in g['block_ids']} == {'first', 'second'}
    assert result[0] == ['profile'] and result[2] == {'context': 'kept'}


def test_freeze_rejects_changed_asset(tmp_path, monkeypatch):
    monkeypatch.setattr(a6, 'ROOT', tmp_path)
    monkeypatch.setattr(a6, 'ASSETS', tmp_path)
    asset = tmp_path / 'generation.json'
    asset.write_text('{}')
    a6.write(tmp_path / 'freeze.json', {'sha256': {'generation.json': a6.digest(asset)}})
    assert a6.check_freeze()
    asset.write_text('{"changed":true}')
    with pytest.raises(ValueError, match='동결 자산'):
        a6.check_freeze()


def test_failed_first_attempt_is_preserved_without_gold_or_human_claim(corpus, monkeypatch):
    monkeypatch.setattr(a6, 'ASSETS', corpus)
    monkeypatch.setattr(a6, 'check_freeze', lambda: {'sha256': {}})
    identity = {k: dict(name=k, digest=k) for k in ('draft', 'review')}
    monkeypatch.setattr(a6.a2, 'model_identity', lambda recipe: identity)
    config = dict(models={k:k for k in identity}, model_digests={k:k for k in identity},
        manifest_sha256=inputs.catalog()['manifest_sha256'], budgets=dict(model_calls=1, model_seconds=5),
        call_timeout_s=2, cqs={'C':dict(id='C', question='현재 유형은?')},
        cases=[dict(id='case', method='manual', scope='current_discovery', step=0,
                    file_ids=['current:0'], cq_ids=['C'])])
    a6.write(corpus / 'generation.json', config)
    a6.write(corpus / 'assessor.json', {'secret': 'GOLD_MUST_NOT_REACH_PROMPT'})
    output = corpus / 'isolated'
    output.mkdir()
    a6.write(output / 'study.json', {'freeze': {'sha256': {}}})
    prompts = []
    async def fail(instance, prompt, **kwargs):
        prompts.append(prompt)
        assert 0 < kwargs['timeout'] <= 2
        raise ValueError('합성 모델 실패')
    monkeypatch.setattr(a6.GenerationService, 'call_ollama', fail)
    result = a6.run_case('case', output, corpus)
    assert len(prompts) == 1 and 'GOLD_MUST_NOT_REACH_PROMPT' not in prompts[0]
    assert result['run']['status'] == 'failed'
    assert result['generation_attempts'] == 1 and result['generation_calls'] == 0
    assert result['participant_count'] == 0 and result['human_review_s'] is None
    assert json.loads((output / 'case.json').read_text(encoding='utf-8'))['model_calls'][0]['error'] == '합성 모델 실패'
    with pytest.raises(ValueError, match='덮어쓰거나'):
        a6.run_case('case', output, corpus)


def test_review_scoring_keeps_wrong_repairs_false_fulfillment_and_ai_separate():
    spec = json.loads((a6.ASSETS / 'reviewer_cards.json').read_text(encoding='utf-8'))
    record = dict(participant_id='synthetic', participant_kind='ai', condition='assisted', packet='B',
                  preparation_s=None, cq_s=None, review_s=1, repair_s=None, rows=[])
    adjudication = dict(adjudicator='synthetic-independent', rows=[])
    for item in spec['cards'] + spec['requirements']:
        if item['packet'] != 'B': continue
        identifier = item['id']
        record['rows'].append(dict(id=identifier, decision='modify_approve' if identifier=='R06' else
            'reject' if identifier=='R07' else 'approve', discovered=True, corrected_text='합성 잘못된 수정',
            original_views=None, navigation_steps=None))
        adjudication['rows'].append(dict(id=identifier, discovery_correct=identifier=='R07',
            final_semantics='refuted' if identifier in {'R06','M2'} else 'supported', rationale='합성 판정'))
    result = review.score(record, adjudication, spec)
    assert result['counts']['wrong_edit_approved'] == 1
    assert result['counts']['remaining_core_error'] == 2
    assert result['counts']['error_found'] == 1
    assert result['counts']['correct_repair'] == 0 and result['counts']['error_rejected'] == 1
    assert result['counts']['false_fulfillment_found'] == 0  # Self-reported discovery is insufficient.
    assert result['human_times'] is None and result['reported_times']['review_s'] == 1
    adjudication['rows'].append(dict(adjudication['rows'][1], final_semantics='supported'))
    with pytest.raises(ValueError, match='유일한'):
        review.score(record, adjudication, spec)
    adjudication['rows'].pop()
    record['rows'][0]['decision'] = 'modify_approve'
    result = review.score(record, adjudication, spec)
    assert result['counts']['normal_intervention'] == 1 and result['counts']['normal_harmed'] == 0
    record['rows'][0]['id'] = 'R06'
    with pytest.raises(ValueError, match='유일한'):
        review.score(record, adjudication, spec)


def test_review_packet_refuses_other_study_freeze(tmp_path, monkeypatch):
    monkeypatch.setattr(review, 'check_freeze', lambda: {'sha256': {'frozen': 'new'}})
    a6.write(tmp_path/'study.json', {'freeze': {'sha256': {'frozen': 'old'}}})
    with pytest.raises(ValueError, match='다른 동결'):
        review.prepare(tmp_path, tmp_path/'cards')
    assert not (tmp_path/'cards').exists()


def test_inspection_reserves_writable_record_before_service_or_decisions(tmp_path, monkeypatch):
    import sqlite3
    from scripts import inspect_knowledge_a6 as inspection
    monkeypatch.setattr(inspection, 'check_freeze', lambda: {})
    a6.write(tmp_path/'study.json', {'freeze': {}})
    a6.write(tmp_path/'case.json', {'run': {}, 'input_run': {}})
    with sqlite3.connect(tmp_path/'knowledge.db') as db:
        db.execute('CREATE TABLE runs(payload TEXT)')
    def forbidden_service(*args):
        pytest.fail('출력 예약 전 서비스/결정 실행')
    monkeypatch.setattr(inspection, 'KnowledgeService', forbidden_service)
    with pytest.raises(FileNotFoundError):
        inspection.inspect(tmp_path, 'case', tmp_path/'missing-parent'/'record.json')
