"""Historical request scope cannot become inspection or semantic success."""
from copy import deepcopy
import json

import pytest

from app.knowledge import business_review as review, business_run
from app.knowledge.business_models import LocalSourceCheck
from app.tests.unit.test_knowledge_business_reassessment_scope import setup_source
from app.tests.unit.test_knowledge_business_local_review import judgments
from app.tests.unit.test_knowledge_business_scope import block


def historical_source():
    run, req, source = setup_source()
    run['blocks'].insert(0, dict(block('parent', '신청 안내'), source_id='s'))
    previous = deepcopy(source['meanings'][:1])
    supplied = [dict(run['blocks'][0], context_only=True), run['blocks'][1]]
    request = business_run.json_request(run, 'source_reassessment', '원문 대조',
        dict(blocks=supplied, previous=dict(meanings=previous)), LocalSourceCheck)
    run['reusable_units'] = [dict(id='historical', stage='source_reassessment', status='succeeded', **request)]
    source['reassessment_history'] = [dict(unit_id='historical', previous=previous,
        output=dict(examined_block_ids=['body', 'parent'], completeness='complete'))]
    return run, req, source


def test_exact_request_recovers_scope_without_promoting_historical_verdicts():
    run, _, source = historical_source()
    before = deepcopy((run, source))
    pending = review.pending_inspections(source)
    receipt = review.inspection_summaries(source, run)[0]
    assert receipt['scope_record_status'] == 'available'
    assert receipt['provided_block_ids'] == ['body', 'parent']
    assert receipt['target_block_ids'] == ['body']
    assert receipt['parent_context_block_ids'] == ['parent']
    assert receipt['meaning_keys'] == ['m']
    assert receipt['source_version_ids'] == ['v'] and receipt['parse_run_ids'] == ['p']
    assert receipt['inspection_status'] is None
    assert receipt['examined_block_ids_origin'] == 'model_report'
    assert receipt['inspection_scope'] == 'historical_meaning_reassessment'
    assert review.pending_inspections(source) == pending
    assert (run, source) == before


@pytest.mark.parametrize('corruption', ['message_text', 'map', 'view_text', 'version', 'parse',
    'span', 'locator', 'previous', 'unit_id'])
def test_mismatched_records_cannot_supply_historical_scope(corruption):
    run, _, source = historical_source()
    unit = run['reusable_units'][0]
    payload = json.loads(unit['messages'][1]['content'])
    if corruption == 'message_text':
        payload['blocks'][1]['text'] += ' 추가 의무'
        unit['messages'][1]['content'] = json.dumps(payload, ensure_ascii=False)
    elif corruption == 'map':
        unit['reference_map']['body'] = unit['reference_map']['parent']
    elif corruption == 'view_text':
        unit['evidence_reference_map']['e2']['text'] += ' 추가 의무'
    elif corruption in {'version', 'parse', 'locator'}:
        field = {'version': 'source_version_id', 'parse': 'parse_run_id', 'locator': 'locator'}[corruption]
        run['blocks'][1][field] = {} if field == 'locator' else 'different'
    elif corruption == 'span':
        unit['evidence_reference_map']['e2']['span'] = [1, 99]
    elif corruption == 'previous':
        source['reassessment_history'][0]['previous'][0]['statement'] = '다른 선택 의미'
    else:
        unit.update(id='other', reused_from=dict(unit_id='historical'))
    before = deepcopy((run, source))
    receipt = review.inspection_summaries(source, run)[0]
    assert receipt['scope_record_status'] == 'unavailable'
    assert not {'provided_block_ids', 'target_block_ids', 'source_version_ids', 'parse_run_ids'} & receipt.keys()
    assert receipt['inspection_status'] is None
    assert (run, source) == before


def test_missing_unit_does_not_infer_scope_from_examined_or_success():
    run, _, source = historical_source()
    run['reusable_units'] = []
    receipt = review.inspection_summaries(source, run)[0]
    assert receipt['scope_record_status'] == 'unavailable'
    assert receipt['scope_record_error'] == 'unit_missing_or_ambiguous'
    assert receipt['examined_block_ids'] == ['body', 'parent']
    assert 'provided_block_ids' not in receipt and receipt['inspection_status'] is None


def test_complete_receipt_is_reused_without_unit_reconstruction(monkeypatch):
    run, _, source = historical_source()
    source['reassessment_history'][0].update(inspection_scope='selected_meanings', meaning_keys=['m'],
        provided_block_ids=['body'], target_block_ids=['body'], source_version_ids=['v'], errors=[])
    expected = review.inspection_summaries(source)
    monkeypatch.setattr(review, 'historical_inspection_scope', lambda *a: pytest.fail('Existing scope is complete'))
    assert review.inspection_summaries(source, run) == expected


def test_existing_join_receives_recovered_scope_without_an_extra_review(monkeypatch):
    run, req, source = historical_source()
    joined = {}
    def answer(_service, _run, _stage, _instruction, context, _schema):
        run['units'].append(dict(id='review'))
        if context['mode'] == 'requirement_join':
            joined.update(deepcopy(context))
            return None
        return judgments([m['key'] for m in context['source']['meanings']], ids=[run['claims'][0]['id']])
    monkeypatch.setattr(business_run, 'json_call', answer)
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    review.represent(None, run, req, source, [])
    assert joined['source_inspections'][0]['target_block_ids'] == ['body']
    assert joined['source_inspections'][0]['inspection_status'] is None
    assert joined['findings'] == source['findings']
