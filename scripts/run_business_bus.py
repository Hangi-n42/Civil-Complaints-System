"""Small real before/after experiment through product storage, review and change APIs."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.knowledge import business_store, business_changes, structured_tables
from app.knowledge.business_models import RequirementInput, BusinessRunRequest, ChangeRequest
from app.knowledge.schemas import SourceRegistration, RunRequest
from app.knowledge.service import KnowledgeService, utcnow
from app.core.config import settings
from run_business_knowledge import wait


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--public-requirements', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', choices=['prepare', 'before', 'change', 'after'], required=True)
    parser.add_argument('--before-run-id', help='Explicit terminal before child after a recorded capacity correction')
    args = parser.parse_args()
    if args.before_run_id and args.phase != 'after':
        parser.error('--before-run-id applies only to the after phase')
    args.output.mkdir(parents=True, exist_ok=True)
    database = args.output/'knowledge.db'
    if database.exists():
        with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
            if any(json.loads(r[0])['status'] in {'queued', 'running', 'cancel_requested'} for r in db.execute('SELECT payload FROM runs')):
                raise ValueError('DB의 기존 실행이 종료된 뒤 다음 단계를 시작하세요.')
    phase_dir = args.output/args.phase
    phase_dir.mkdir(exist_ok=False)
    hashes = {}
    for path in [*ROOT.glob('app/knowledge/*.py'), *ROOT.glob('app/knowledge/vendor/autoschemakg/*'),
                 ROOT/'app/generation/model_client.py', ROOT/'app/generation/service.py', ROOT/'app/core/config.py', Path(__file__)]:
        if not path.is_file(): continue
        target = phase_dir/'executed_code'/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(path.read_bytes())
        hashes[str(path.relative_to(ROOT))] = sha256(path.read_bytes()).hexdigest()
    write_new(phase_dir/'code_freeze.json', dict(started_at=utcnow(), code_hashes=hashes,
        reference_answers_loaded=False, construction='Direct structured rows plus AutoSchemaKG for narrative sources'))
    service = KnowledgeService(database)
    try:
        if args.phase == 'prepare':
            columns = ['ROUTE_ID', '노선명', '순번', 'NODE_ID', 'ARS_ID', '정류소명', 'X좌표', 'Y좌표']
            versions, source_ids, receipts = {}, {}, []
            for label, day in [('before', '20250513'), ('after', '20250624')]:
                names = [f'1127_{label}.json', f'seoul_route_order_{day}.xlsx']
                rows = []
                for name in names:
                    path = args.source_root/name
                    format = path.suffix[1:]
                    scope = {'columns': columns} if format == 'json' else {'sheet': 'Data', 'equals': {'ROUTE_ID':100100143}}
                    rows.append(structured_tables.parse(path, format, scope))
                    registered = service.register(name, path.read_bytes(), SourceRegistration(title=name, publisher='서울시 공개 정차표',
                        namespace='bus-public', external_id='1127-' + format, selected_scope=scope,
                        dates=[dict(role='file_snapshot', value=day[:4] + '-' + day[4:6] + '-' + day[6:])]))
                    versions[name] = registered['source_version_id']; source_ids[name] = registered['source_id']
                assert [r['locator']['fields'] for r in rows[0]] == [r['locator']['fields'] for r in rows[1]]
                receipts.append(dict(snapshot=day, rows=len(rows[0]), exact_json_xlsx_match=True,
                    sources=[dict(filename=n, sha256=sha256((args.source_root/n).read_bytes()).hexdigest()) for n in names],
                    xlsx_addresses=[r['locator'] for r in rows[1]]))
            for name, selector in [('dobong_proposal.html', '#record8'), ('dobong_approved.html', '#record5')]:
                path = args.source_root/name
                value = service.register(name, path.read_bytes(), SourceRegistration(title=name, publisher='도봉구의회 회의록',
                    namespace='bus-public', external_id=name, selected_scope={'selector': selector}))
                versions[name] = value['source_version_id']; source_ids[name] = value['source_id']
            parsed = wait(service, service.start(RunRequest(source_version_ids=list(versions.values())))['run_id'], phase_dir/'parse.json')
            if parsed['status'] != 'succeeded': raise ValueError('전후 원문 파싱 미완료')
            public = json.loads(args.public_requirements.read_text(encoding='utf-8'))
            requirements = []
            for item in public['requirements']:
                rid = item['requirement_id']
                business_store.put_requirement(service, RequirementInput(id=rid, question_ids=[rid],
                    question=item['question'], target=item['target'], situation=item['situation'], period=item['period'],
                    criterion=item['fulfillment_criteria']))
                requirements.append(rid)
            for seq in [12, 47]:
                rid = 'BUS-CONTROL-' + str(seq)
                business_store.put_requirement(service, RequirementInput(id=rid, question_ids=[rid],
                    question=f'1127번 순번 {seq} 정차의 ID·명칭·좌표는 무엇인가?', target=f'ROUTE_ID 100100143 순번 {seq}',
                    situation='동명·인접 정차를 다른 순번과 혼동하지 않고 조회', period='조회 원문 스냅샷',
                    criterion='해당 순번의 실제 행값을 보존하고 다른 행의 변경을 전이하지 않는다.'))
                requirements.append(rid)
            # Declared before any model output; created only after the baseline
            # to exercise relevance discovery without an assessment dependency.
            new_requirement = RequirementInput(id='BUS-NEW-13', question_ids=['BUS-NEW-13'],
                question='1127번 순번 13의 현재 정차 식별자와 좌표는 무엇인가?', target='ROUTE_ID 100100143 순번 13',
                situation='신규 등록된 업무 질문', period='최신 제공 정차표 스냅샷',
                criterion='실제 행의 ID와 좌표를 함께 확인한다. 이름만으로 동일 정차를 추정하지 않는다.').model_dump()
            write_new(args.output/'inputs.json', dict(versions=versions, source_ids=source_ids, requirements=requirements,
                public_requirements_sha256=sha256(args.public_requirements.read_bytes()).hexdigest(), new_requirement=new_requirement))
            write_new(phase_dir/'table_receipt.json', dict(items=receipts, model_calls=0, semantic_quality_claim=False))
            return
        inputs = json.loads((args.output/'inputs.json').read_text(encoding='utf-8'))
        versions = inputs['versions']
        if args.phase == 'change':
            business_store.put_requirement(service, RequirementInput.model_validate(inputs['new_requirement']))
            result = business_changes.analyze(service, ChangeRequest(before_version_id=versions['1127_before.json'],
                after_version_id=versions['1127_after.json'], key_fields=['ROUTE_ID', '순번']))
            write_new(phase_dir/'result.json', result)
            print(json.dumps(dict(run_id=result['id'], status=result['status']), ensure_ascii=False), flush=True)
            return
        names = ['1127_before.json', 'dobong_proposal.html']
        requirements = list(inputs['requirements'])
        if args.phase == 'after':
            names += ['1127_after.json', 'dobong_approved.html']
            requirements.append(inputs['new_requirement']['id'])
        before_run = (args.before_run_id or json.loads((args.output/'before'/'dispatch.json').read_text())['run_id']) if args.phase == 'after' else None
        plan_path = args.output/'execution_plan.json'
        if args.phase == 'before':
            # The actual 120-row representation input exceeded 49,152 before
            # any model call. Freeze both phases together without dropping rows.
            write_new(plan_path, dict(recorded_at=utcnow(),
                capacity_basis='Product serialization lower bound before exact duplicate removal: before 40701, after 70484; source meanings and narrative claims are additional.',
                options=BusinessRunRequest(source_version_ids=[versions[n] for n in names], requirement_ids=requirements,
                    context_tokens=98304, conceptualize=False, model=settings.STRUCTURING_MODEL,
                    review_model=settings.KNOWLEDGE_REVIEW_MODEL).model_dump(exclude={
                        'source_version_ids', 'requirement_ids', 'reuse_run_id', 'resume_run_id'}),
                before_source_versions=[versions[n] for n in names],
                after_source_versions=[versions[n] for n in names + ['1127_after.json', 'dobong_approved.html']],
                before_requirement_ids=requirements, after_requirement_ids=requirements + [inputs['new_requirement']['id']]))
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        if plan[args.phase + '_source_versions'] != [versions[n] for n in names] or plan[args.phase + '_requirement_ids'] != requirements:
            raise ValueError('동결한 전후 입력 계약이 변경됐습니다.')
        options = plan['options']
        if args.phase == 'after':
            # Preserve the defaults actually frozen before the first call, even
            # if a later adoption decision changes defaults for new runs.
            before_parent = service.run(before_run)
            if (before_parent['input_version_ids'] != plan['before_source_versions'] or
                    [r['id'] for r in before_parent['requirements']] != plan['before_requirement_ids']):
                raise ValueError('선택한 before 실행은 동결한 동일 원문/요구 범위가 아닙니다.')
            before_request = before_parent['recipe']['options']
            options = {k:v for k,v in before_request.items() if k not in {
                'source_version_ids', 'requirement_ids', 'reuse_run_id', 'resume_run_id'}}
        request = BusinessRunRequest(source_version_ids=[versions[n] for n in names], requirement_ids=requirements,
                                     reuse_run_id=before_run, **options)
        write_new(phase_dir/'request.json', request.model_dump())
        run = service.start_business(request)
        write_new(phase_dir/'dispatch.json', run)
        result = wait(service, run['run_id'], phase_dir/'result.json')
        print(json.dumps(dict(run_id=result['id'], status=result['status']), ensure_ascii=False), flush=True)
    finally:
        service.shutdown()


if __name__ == '__main__':
    main()
