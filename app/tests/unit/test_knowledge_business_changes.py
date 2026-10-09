import json
from zipfile import ZipFile

from app.knowledge import business_changes, business_run, business_store, structured_tables
from app.knowledge.business_models import RequirementInput, ChangeRequest
from app.knowledge.schemas import SourceRegistration, RunRequest
from app.knowledge.service import KnowledgeService
from app.tests.unit.test_knowledge_business import finish


def test_xlsx_cells_and_json_rows_share_exact_change_boundary(tmp_path):
    path = tmp_path / 'rows.xlsx'
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    with ZipFile(path, 'w') as z:
        z.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" r:id="r1" /></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml" /></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{ns}"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>id</t></is></c><c r="B1" t="inlineStr"><is><t>name</t></is></c></row><row r="2"><c r="A2"><v>1</v></c><c r="B2" t="inlineStr"><is><t>기존</t></is></c></row><row r="3"><c r="A3"><v>2</v></c><c r="B3" t="inlineStr"><is><t>유지</t></is></c></row></sheetData></worksheet>')
    before = structured_tables.parse(path, 'xlsx', {'sheet': 'Data'})
    assert before[0]['locator']['cells'] == {'id': 'A2', 'name': 'B2'}
    jp = tmp_path / 'rows.json'; jp.write_text(json.dumps([[1, '변경'], [2, '유지']], ensure_ascii=False))
    after = structured_tables.parse(jp, 'json', {'columns': ['id', 'name']})
    assert after[0]['locator']['json_pointer'] == '/0'
    for prefix, blocks in [('before', before), ('after', after)]:
        for n, b in enumerate(blocks): b['id'] = prefix + str(n)
    diff = business_changes.differences(before, after, ['id'])
    assert len(diff['changes']) == len(diff['unchanged']) == 1
    assert diff['changes'][0]['fields'] == [dict(field='name', before='기존', after='변경')]


def test_change_rechecks_unlinked_requirement_and_keeps_unaffected(tmp_path, monkeypatch):
    class Client:
        def __init__(self, *_): pass
        def identities(self, *_): return {'review': {'name': 'mock'}}
    monkeypatch.setattr(business_changes, 'ModelClient', Client)
    service = KnowledgeService(tmp_path / 'knowledge.db')
    try:
        versions = [service.register(name, text.encode(), SourceRegistration(title='조건', publisher='기관',
                     namespace='test', external_id='same-source'))['source_version_id']
                    for name, text in [('before.txt', '본인 신청만 가능.\n방문 시간은 9시.'),
                                       ('after.txt', '본인 또는 위임장을 가진 대리인이 신청 가능.\n방문 시간은 9시.')]]
        assert finish(service, service.start(RunRequest(source_version_ids=versions))['run_id'])['status'] == 'succeeded'
        for rid, question in [('new', '대리 신청 조건은?'), ('stable', '방문 시간은?')]:
            business_store.put_requirement(service, RequirementInput(id=rid, question_ids=[rid], question=question,
                target='민원인', situation='신청', period='제공 원문', criterion='해당 조건을 보존한다'))
        def check(service, run, stage, instruction, context, schema):
            assert stage == 'change_impact' and context['direct_dependency_ids'] == []
            assert {r['id'] for r in context['requirements']} == {'new', 'stable'}
            return dict(items=[dict(requirement_id='new', status='affected', reason='새 대리인 허용',
                                    change_ids=[context['diff']['changes'][0]['id']], new_relevance=True),
                               dict(requirement_id='stable', status='unaffected', reason='9시 유지', change_ids=[], new_relevance=False)])
        monkeypatch.setattr(business_run, 'json_call', check)
        run = business_changes.analyze(service, ChangeRequest(before_version_id=versions[0], after_version_id=versions[1]))
        values = {r['id']: r for r in business_store.requirements(service)['items']}
        assert run['status'] == 'succeeded' and values['new']['status'] == 'needs_review'
        assert values['stable']['status'] == 'unassessed'
        assert values['new']['change_history'][0]['run_id'] == run['id']
    finally:
        service.shutdown()


def test_impact_reads_exact_stored_meanings_and_rejects_stale_pointer(tmp_path, monkeypatch):
    service = KnowledgeService(tmp_path / 'knowledge.db')
    try:
        requirement = dict(id='related', revision=1, question='대리 신청 서류는?',
            current_assessment=dict(run_id='old', assessment_id='a1', revision=1, source_version_ids=['v1']))
        meaning = dict(key='document', statement='증명서가 필요하다.', source_status='supported', conditions=['본인 미방문'],
            exceptions=[], period='', references=[], premise_keys=None,
            evidence=[dict(block_id='b1', source_version_id='v1')])
        block = dict(id='b1', source_version_id='v1', text='본인이 방문하지 않을 때 증명서를 제출한다.')
        old = dict(id='old', status='succeeded', input_version_ids=['v1'], blocks=[block],
            recipe=dict(options=dict(context_tokens=8192, review_tokens=1024)),
            claims=[dict(id='c1', role='event_entity', raw=dict(Event='본인 미방문 시 증명서 제출'),
                         source_version_ids=['v1'], evidence=meaning['evidence']),
                    dict(id='bad', role='event_entity', raw=dict(Event='항상 증명서 제출'),
                         semantic_status='unknown', source_version_ids=['v1'], evidence=meaning['evidence'])],
            assessments=[dict(id='a1', requirement_id='related', revision=1, claim_ids=['c1'],
                source=dict(meanings=[meaning]), representation=dict(checks=[dict(meaning_key='document',
                    status='represented', claim_ids=['c1'], incorrect_claim_ids=['bad'])], dependencies=[]))])
        with service.repository.connect() as db:
            db.execute('INSERT INTO runs VALUES(?,?)', ('old', json.dumps(old)))
        def check(service, run, stage, instruction, context, schema):
            dep = context['stored_dependencies'][0]
            if requirement['current_assessment']['assessment_id'] == 'a1':
                assert dep['status'] == 'provided'
                assert dep['meanings'][0]['conditions'] == ['본인 미방문']
                assert dep['meanings'][0]['premise_keys'] is None
                assert dep['claims'][0]['raw']['Event'] == '본인 미방문 시 증명서 제출'
                assert dep['claims'][1]['id'] == 'bad' and dep['claims'][1]['semantic_status'] == 'unknown'
                assert context['blocks'][0]['text'] == block['text']
            else:
                assert dep['status'] == 'unavailable'
            return dict(items=[dict(requirement_id='related', status='unaffected', reason='mock',
                                    change_ids=[], new_relevance=False)])
        monkeypatch.setattr(business_run, 'json_call', check)
        result, valid = business_changes.review_impacts(service, {}, [requirement], dict(changes=[]), [], [])
        assert valid and result['items'][0]['status'] == 'unaffected'
        requirement['current_assessment']['assessment_id'] = 'wrong'
        result, valid = business_changes.review_impacts(service, {}, [requirement], dict(changes=[]), [], [])
        assert result['items'][0]['status'] == 'unknown'
    finally:
        service.shutdown()


def test_impact_cannot_preserve_status_after_assessment_pointer_changes(tmp_path):
    service = KnowledgeService(tmp_path / 'knowledge.db')
    try:
        before = dict(id='r', revision=1, status='satisfied', current_assessment=dict(assessment_id='old'))
        with service.repository.connect() as db:
            db.execute('INSERT INTO requirements VALUES(?,?)', ('r', json.dumps(dict(before,
                current_assessment=dict(assessment_id='new')))))
        impacts = [dict(requirement_id='r', status='unaffected', reason='old assessment independent',
                        change_ids=[], new_relevance=False)]
        business_changes.apply_impacts(service, dict(id='impact-run'), [before], impacts)
        with service.repository.connect() as db:
            current = service.repository.get(db, 'requirements', 'r')
        assert impacts[0]['status'] == 'unknown'
        assert current['status'] == 'needs_review'
        assert current['current_assessment'] == dict(assessment_id='new')
        assert current['change_history'][0]['run_id'] == 'impact-run'
    finally:
        service.shutdown()
