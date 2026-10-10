"""Explicit source scope and meaning admission never substitute for semantic validation."""
from copy import deepcopy

import pytest

from app.knowledge import autoschema, business_review as review, business_run, parsers
from app.tests.unit.test_knowledge_business_local_review import local_run, meaning, judgments
from app.tests.unit.test_knowledge_business_scope import block


def packet(meanings):
    return dict(meanings=meanings, examined_block_ids=['body', 'context'], inspection_status='complete',
                findings=[], conjunctions=[], meaning_conjunctions=[])


def test_declared_document_tools_preserve_every_text_and_business_location(tmp_path):
    path = tmp_path / 'source.html'
    path.write_text('<body><div id="content"><ul id="tools"><li><a href="#" onclick="custom()">공유</a></li>'
        '<li><a href="#">인쇄</a></li></ul><p>접수기관: 시청. 기한: 10일.</p>'
        '<p><a href="#" onclick="submit()">신청서 제출</a></p>'
        '<p><a href="law.html">법령</a>과 <a href="form.pdf">서류 양식</a></p>'
        '<table><tr><th>대상</th><td>법인은 증명서 제출</td></tr></table></div></body>')
    original = parsers.parse_unit(path, 'html', parsers.plan_units(path, 'html', {'selector': '#content'})[0])
    scope = dict(selector='#content', document_controls=[dict(selector='#tools', reason='확인된 공유/인쇄 영역')])
    parsed = parsers.parse_unit(path, 'html', parsers.plan_units(path, 'html', scope)[0])
    assert len(parsed) == len(original)
    assert [{**b, 'locator': {k: v for k, v in b['locator'].items() if k != 'document_controls'}} for b in parsed] == original
    assert [b['text'] for b in parsed if b['locator'].get('document_controls')] == ['공유', '인쇄']
    assert not any(b['locator'].get('document_controls') for b in original)
    run = local_run(); run['blocks'] = [dict(b, id=str(n), source_id='s', source_version_id='v', parse_run_id='p')
                                        for n, b in enumerate(parsed)]
    bundles, selection = review.source_selection(run, run['requirements'][0])
    assert {e['block_id'] for e in selection['non_target_blocks']} == {'0', '1'}
    assert not {'0', '1'} & set(selection['unselected_block_ids'])
    assert not {'0', '1'} & {b['id'] for c in bundles for b in c['blocks']}
    assert parsers.parser_info('html')['adapter_version'] == '3'
    for selector in ['#missing', '#content', 'body']:
        with pytest.raises(ValueError):
            parsers.parse_unit(path, 'html', parsers.plan_units(path, 'html', dict(scope,
                document_controls=[dict(selector=selector, reason='test')]))[0])


@pytest.mark.parametrize('fault', ['context', 'wrong_quote', 'wrong_parse', 'wrong_version', 'duplicate'])
def test_admission_precedes_application_and_preserves_independent_target(monkeypatch, fault):
    run = local_run(); run['recipe']['review_contract'] = review.SOURCE_APPLICATION_CONTRACT
    run['requirements'][0].update(question='접수?', criterion='기관')
    context = dict(block('context', '대리 신청 조건'), source_id='s', context_only=True)
    run['blocks'].append(context)
    valid = meaning('valid'); valid['evidence'].append(dict(block_id='context', quote=context['text']))
    invalid = meaning('invalid')
    if fault == 'context': invalid['evidence'] = [dict(block_id='context', quote=context['text'])]
    if fault == 'wrong_quote': invalid['evidence'][0]['quote'] = '없는 문장'
    if fault == 'wrong_parse': invalid['evidence'][0]['parse_run_id'] = 'other'
    if fault == 'wrong_version': invalid['evidence'][0]['source_version_id'] = 'other'
    dependent = meaning('dependent'); dependent['premise_keys'] = ['invalid']
    raw = packet([valid, invalid, dependent] + ([deepcopy(invalid)] if fault == 'duplicate' else []))
    raw['findings'] = [dict(kind='interpretation_uncertain', text='두 의미의 관계 미확정', meaning_keys=['valid', 'invalid'])]
    frozen = deepcopy(raw); calls = []
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    monkeypatch.setattr(review, 'source_selection', lambda *a: ([dict(id='bundle', blocks=run['blocks'])],
        dict(selected_block_ids=['body'], unselected_block_ids=[])))
    def answer(service, active, stage, instruction, supplied, schema):
        calls.append(stage); active['units'].append(dict(id=stage))
        if stage == 'requirement_source': return deepcopy(raw)
        assert stage == 'requirement_application'
        assert [m['key'] for m in supplied['source_facts']] == ['valid']
        return dict(links=[dict(key='valid', item_id=i['id'], required_for_requirement=True, requirement_link=dict(
            requested_fact='기관', applicability='applicable', contribution='direct_answer', reason='직접 답', requirement_quote=''))
            for i in supplied['public_answer_items']], meaning_challenges=[])
    monkeypatch.setattr(business_run, 'json_call', answer)
    source = review.source(None, run, run['requirements'][0])
    assert calls == ['requirement_source', 'requirement_application']
    assert [m['key'] for m in review.review_meanings(source)] == ['batch1:valid']
    assert {m['meaning']['key'] for m in source['unadmitted_meanings']} == {'batch1:invalid', 'batch1:dependent'}
    assert source['source_batches'][0]['output'] == frozen and raw == frozen
    result = judgments(['batch1:valid']); result.update(source_completeness='complete', finding_resolutions=[])
    review.resolve_findings(source, result, source['findings'], run['blocks'], [], joined=True)
    assert not result['meaning_challenges'] and not result['source_challenges']
    assert source['meaning_gaps'][0]['meaning_keys'] == ['batch1:valid']
    assert source['finding_resolutions'][0]['status'] == 'unresolved'
    assert business_run.requirement_completion(dict(source=source, representation=result, errors=[], preservation_complete=True))['status'] != 'satisfied'


def test_document_control_membership_uses_dom_identity(tmp_path):
    path = tmp_path / 'siblings.html'
    path.write_text('<main><section><ul><li>동일 내용</li></ul></section>'
                    '<section><ul><li>동일 내용</li></ul></section></main>')
    scope = dict(selector='main', document_controls=[dict(
        selector='main > section:nth-of-type(1) > ul', reason='첫 영역만 확인됨')])
    parsed = parsers.parse_unit(path, 'html', parsers.plan_units(path, 'html', scope)[0])
    assert [bool(b['locator'].get('document_controls')) for b in parsed] == [True, False]
    scope['selector'] = 'main > section:nth-of-type(1)'
    scope['document_controls'][0]['selector'] = 'main > section:nth-of-type(2) > ul'
    with pytest.raises(ValueError):
        parsers.parse_unit(path, 'html', parsers.plan_units(path, 'html', scope)[0])


def test_all_rejected_skips_application_and_conjunction_does_not_poison_independent():
    run = local_run(); context = dict(block('context', '참고 내용'), context_only=True)
    rejected = meaning('context'); rejected['evidence'] = [dict(block_id='context', quote='참고 내용')]
    connected = meaning('connected'); independent = meaning('independent')
    raw = packet([rejected, connected, independent]); raw['meaning_conjunctions'] = [dict(meaning_keys=['context', 'connected'], text='연결 필요')]
    admitted, audit = review.admit_source_output(raw, [*run['blocks'], context])
    assert [m['key'] for m in admitted['meanings']] == ['connected', 'independent']
    assert audit['excluded_connections'] == raw['meaning_conjunctions']
    admitted, audit = review.admit_source_output(packet([rejected]), [*run['blocks'], context])
    assert not admitted['meanings'] and audit['excluded_meanings']
    assert review.admission_findings(packet([rejected]), audit, 'u', ['body'], {'context': 'context'}) == []


def test_rejected_conjunction_keeps_normal_meaning_but_records_its_connection_gap():
    context = dict(block('context', '문맥'), context_only=True)
    invalid = meaning('context'); invalid['evidence'] = [dict(block_id='context', quote='문맥')]
    raw = packet([invalid, meaning('normal')]); raw['meaning_conjunctions'] = [dict(meaning_keys=['context', 'normal'])]
    admitted, audit = review.admit_source_output(raw, [*local_run()['blocks'], context])
    findings = review.admission_findings(raw, audit, 'u', ['body'], {'context': 'context', 'normal': 'normal'})
    assert [m['key'] for m in admitted['meanings']] == ['normal']
    assert len(findings) == 1 and findings[0]['meaning_keys'] == ['normal']


@pytest.mark.parametrize('premises,challenged,expected,global_error', [
    ([], 'background', set(), False),
    (['background'], 'background', {'normal', 'background'}, False),
    (None, 'background', {'normal'}, False),
    ([], 'absent', {'normal'}, True),
    (['bridge'], 'background', {'normal', 'bridge', 'background'}, False),
])
def test_known_background_challenge_preserves_dependency_boundaries(premises, challenged, expected, global_error):
    normal = meaning('normal', required_for_requirement=True); normal['premise_keys'] = premises
    background = meaning('background', required_for_requirement=False)
    bridge = meaning('bridge', required_for_requirement=False); bridge['premise_keys'] = ['background']
    source = dict(review_contract=review.CONTRACT, meanings=[normal, background, bridge])
    result = judgments([m['key'] for m in review.review_meanings(source)])
    result['dependencies'] = []
    result['meaning_challenges'] = [dict(meaning_key=challenged, reason='근거 미확정')]
    assessment = dict(source=source, representation=result, errors=[], issues=[])
    frozen = deepcopy(assessment)
    blocked, reasons = review.blocked(assessment)
    assert blocked == expected and bool(reasons) == global_error and assessment == frozen


def test_explicit_target_plan_exclusion_is_not_a_model_examination(monkeypatch):
    run = local_run(); ui = dict(block('ui', '도구'), source_id='s')
    run['blocks'].append(ui)
    run['source_target_plan'] = dict(source_hash=autoschema.identifier('source', run['blocks']),
        exclusions=[dict(block_id='ui', declarations=[dict(selector='#tools', reason='확인된 도구 영역')])])
    old = dict(meanings=[meaning('kept')], examined_block_ids=['body'], completeness='partial', gaps=[],
        findings=[], conjunctions=[], meaning_conjunctions=[], source_selection=dict(selected_block_ids=['body', 'ui'], unselected_block_ids=[]),
        source_batches=[dict(unit_id='old', target_block_ids=['body', 'ui'], provided_block_ids=['body', 'ui'],
            output=dict(examined_block_ids=['body'], inspection_status='complete'), errors=['local_source_inspection_scope_mismatch'])])
    before = deepcopy(old)
    monkeypatch.setattr(business_run, 'json_call', lambda *a: pytest.fail('Explicit UI-only remainder must not trigger a model'))
    new = review.source(None, run, run['requirements'][0], previous=old)
    assert new['meanings'] == old['meanings'] and new['examined_block_ids'] == ['body'] and old == before
    assert review.pending_inspections(new) == {'old': {'ui'}} and review.pending_source_targets(new) == {}
    assert not review.needs_source_read(new, {'unselected_source_required': False})
    summary = review.inspection_summaries(new)[0]
    assert summary['inspection_error_active'] and summary['excluded_by_target_plan'] == ['ui']
    result = judgments(['kept']); result.update(source_completeness='complete', finding_resolutions=[])
    review.resolve_findings(new, result, [], run['blocks'], [], joined=True)
    assert 'local_source_inspection_scope_mismatch' not in new['gaps']
    assert new['source_batches'] == old['source_batches']


@pytest.mark.parametrize('premises,finding_keys,satisfied', [
    ([], ['background'], True),
    (['background'], ['background'], False),
    (['bridge'], ['background'], False),
    (None, ['background'], False),
    ([], ['absent'], False),
    ([], [], False),
])
def test_requirement_completion_uses_actual_finding_dependencies(premises, finding_keys, satisfied):
    run = local_run()
    normal = meaning('normal', required_for_requirement=True); normal['premise_keys'] = premises
    background = meaning('background', required_for_requirement=False)
    bridge = meaning('bridge', required_for_requirement=False); bridge['premise_keys'] = ['background']
    finding = dict(id='f', origin='source', kind='interpretation_uncertain', text='배경 기록의 근거 미확정',
        meaning_keys=finding_keys, scope_meaning_keys=[], claim_ids=[], fields=[])
    source = dict(review_contract=review.CONTRACT, meanings=[normal, background, bridge], findings=[finding],
        gaps=[], meaning_gaps=[], source_batches=[], source_selection={})
    result = judgments([m['key'] for m in review.review_meanings(source)], ids=[run['claims'][0]['id']])
    result['dependencies'] = []
    result.update(source_completeness='complete', finding_resolutions=[dict(finding_id='f', status='not_required',
        meaning_keys=[], claim_ids=[], fields=[], evidence=[], reason='필수키에 없으므로 무관')])
    review.resolve_findings(source, result, [finding], run['blocks'], run['claims'], joined=True)
    assessment = dict(source=source, representation=result, errors=[], issues=[], preservation_complete=True)
    assert source['finding_resolutions'][0]['status'] == 'unresolved'
    assert source['finding_resolutions'][0]['reason'].startswith('resolution_without_actual_source:')
    assert (business_run.requirement_completion(assessment)['status'] == 'satisfied') is satisfied


def test_frozen_parse_mapping_and_plain_resume_ignore_later_parse(tmp_path, monkeypatch):
    from app.knowledge.service import KnowledgeService, encode
    from app.knowledge.schemas import SourceRegistration
    from app.knowledge.business_models import BusinessRunRequest
    service = KnowledgeService(tmp_path / 'knowledge.db')
    try:
        vid = service.register('s.html', b'<div id="content"><ul id="tools"><li>Print</li></ul><p>Body</p></div>',
            SourceRegistration(title='source', publisher='owner', namespace='test', selected_scope={'selector': '#content'}))['source_version_id']
        def parse(scope):
            return service.parse_input(dict(source_version_id=vid, parser=parsers.parser_info('html'), parser_options=scope))
        first = parse(dict(selector='#content'))
        with service.repository.connect() as db:
            blocks = service.parse_blocks(db, first, vid)
        for b in blocks: b['source_id'] = service.sources()['items'][0]['source']['id']
        classified = parse(dict(selector='#content', document_controls=[dict(selector='#tools', reason='Reviewed tools')]))
        parent = local_run(); parent.update(id='parent', kind='business', status='review_ready', input_version_ids=[vid],
            blocks=blocks, chunks=autoschema.chunks(blocks, 49152, 4096), claims=[], graph=dict(nodes=[], edges=[]),
            concepts=[], model_identity={}, metrics={})
        parent['preservation_reuses'] = [dict(requirement_id='r', requirement_revision=1,
            check=dict(target_id='unavailable', status='unknown', before_normal_meanings=[], after_locations=[], reason='전달 경계 검사'),
            claim_versions={'unavailable': 'old-claim-version'}, meaning_versions={}, source_versions=[], scope='local_preservation_only_not_requirement_independence')]
        with service.repository.connect() as db:
            parent['source_target_plan'] = review.freeze_target_plan(service, db, parent, {vid: classified})
            assert len(parent['source_target_plan']['exclusions']) == 1
            for fault in ['text', 'locator', 'duplicate']:
                changed = deepcopy(parent)
                if fault == 'text': changed['blocks'][0]['text'] += ' changed'
                if fault == 'locator': changed['blocks'][0]['locator']['element_path'] += ' other'
                if fault == 'duplicate': changed['blocks'].append(dict(changed['blocks'][0], id='duplicate'))
                with pytest.raises(ValueError, match='유일'):
                    review.freeze_target_plan(service, db, changed, {vid: classified})
            db.execute('INSERT INTO runs VALUES(?,?)', ('parent', encode(parent)))
            db.execute('INSERT INTO requirements VALUES(?,?)', ('r', encode(parent['requirements'][0])))
        # A different latest policy must not alter a resumed run's selected plan.
        parse(dict(selector='#content', document_controls=[dict(selector='#content > p', reason='Different explicit plan')]))
        monkeypatch.setattr(business_run.ModelClient, 'identities', lambda *a: {})
        monkeypatch.setattr(service.executor, 'submit', lambda *a: None)
        result = business_run.start(service, BusinessRunRequest(source_version_ids=[vid], requirement_ids=['r'], resume_run_id='parent'))
        resumed = service.run(result['run_id'])
        assert resumed['blocks'] == parent['blocks'] and resumed['source_target_plan'] == parent['source_target_plan']
        assert resumed['preservation_reuses'] == parent['preservation_reuses']
        assert review.valid_preservation_reuses(resumed, parent['requirements'][0], []) == []
    finally:
        service.shutdown()


def test_quarantined_only_finding_never_becomes_global_challenge():
    run = local_run(); kept = meaning('kept')
    source = dict(meanings=[kept], review_contract=review.CONTRACT, findings=[], gaps=[], meaning_gaps=[],
        unadmitted_meanings=[dict(meaning=meaning('bad'))], source_batches=[])
    finding = dict(id='f', kind='interpretation_uncertain', text='격리된 대상', meaning_keys=['bad'],
        unadmitted_meaning_keys=['bad'], scope_meaning_keys=['kept'], origin='source', claim_ids=[], fields=[])
    result = judgments(['kept']); result.update(source_completeness='complete', finding_resolutions=[])
    review.resolve_findings(source, result, [finding], run['blocks'], [], joined=True)
    assert not result['meaning_challenges'] and not result['source_challenges']
    assert review.blocked(dict(source=source, representation=result, errors=[], issues=[])) == (set(), [])
    assert source['completeness'] == 'partial'


def test_irrelevant_quarantine_does_not_invent_a_whole_requirement_gap():
    run = local_run(); kept = meaning('kept')
    finding = review.admission_finding('bad', meaning('bad'), 'meaning_outside_local_target', 'u', ['body'])
    source = dict(meanings=[kept], review_contract=review.CONTRACT, findings=[finding], gaps=[], meaning_gaps=[],
        unadmitted_meanings=[dict(meaning=meaning('bad'))], source_batches=[])
    result = judgments(['kept'], ids=[run['claims'][0]['id']])
    result.update(source_completeness='complete', finding_resolutions=[dict(finding_id=finding['id'], status='not_required',
        meaning_keys=['kept'], claim_ids=[], fields=[], evidence=kept['evidence'], reason='필수 원명제는 kept로 확인되고 격리 항목에 의존하지 않음')])
    review.resolve_findings(source, result, [finding], run['blocks'], run['claims'], joined=True)
    assert source['completeness'] == 'complete' and not source['gaps'] and not source['meaning_gaps']
    assert source['unadmitted_meanings']
    assert business_run.requirement_completion(dict(source=source, representation=result, errors=[], preservation_complete=True))['status'] == 'satisfied'


def test_empty_admission_skips_actual_applicability_path(monkeypatch):
    run = local_run(); run['recipe']['review_contract'] = review.SOURCE_APPLICATION_CONTRACT
    context = dict(block('context', '문맥만 있음'), context_only=True)
    run['blocks'].append(context)
    invalid = meaning('context'); invalid['evidence'] = [dict(block_id='context', quote=context['text'])]
    monkeypatch.setattr(review, 'source_selection', lambda *a: ([dict(id='bundle', blocks=run['blocks'])], {}))
    monkeypatch.setattr(business_run, 'cancelled', lambda *a: False)
    calls = []
    def answer(_s, active, stage, *args):
        calls.append(stage); active['units'].append(dict(id=stage))
        assert stage == 'requirement_source'
        return packet([invalid])
    monkeypatch.setattr(business_run, 'json_call', answer)
    source = review.source(None, run, run['requirements'][0])
    assert calls == ['requirement_source'] and not source['meanings'] and source['unadmitted_meanings']
    assert business_run.requirement_completion(dict(source=source, representation=judgments([]), errors=[], preservation_complete=True))['status'] != 'satisfied'
