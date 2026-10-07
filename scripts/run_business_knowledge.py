"""Recorded local execution through KnowledgeService, never an alternate pipeline."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import sleep

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.knowledge import business_store, business_use, business_run
from app.knowledge.business_models import RequirementInput, BusinessRunRequest
from app.knowledge.schemas import SourceRegistration, RunRequest
from app.knowledge.service import KnowledgeService, utcnow


def wait(service, run_id, output):
    previous = None
    while True:
        run = service.run(run_id)
        state = (run['status'], len(run['units']), run['units'][-1]['stage'] if run['units'] and 'stage' in run['units'][-1] else 'parse')
        if state != previous:
            print(json.dumps(dict(run_id=run_id, state=state), ensure_ascii=False), flush=True)
            previous = state
        if run['status'] not in {'queued', 'running', 'cancel_requested'}:
            output.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding='utf-8')
            return run
        sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--public-requirements', type=Path, required=True)
    parser.add_argument('--dataset', choices=['busan', 'lh', 'bus'], default='busan')
    parser.add_argument('--resume-database', type=Path)
    parser.add_argument('--resume-run-id')
    parser.add_argument('--requirement-id', action='append', help='Focused requirement IDs from the existing database; reuse unchanged source work')
    parser.add_argument('--skip-concepts', action='store_true', help='Focus a regression on source/requirement checks; selected conceptualization is a separate product call')
    parser.add_argument('--source-reassessment-tokens', type=int, help='Stage-specific output reservation after a recorded truncation')
    parser.add_argument('--source-tokens', type=int, help='Output reservation for initial source grounding after a recorded truncation')
    parser.add_argument('--representation-context-tokens', type=int, help='Representation-only context reservation after a recorded capacity block')
    parser.add_argument('--representation-tokens', type=int, help='Representation-only output reservation after a recorded truncation')
    args = parser.parse_args()
    if args.dataset == 'bus' and not args.resume_database:
        parser.error('Bus registration uses run_business_bus.py; this runner only resumes its stored run.')
    output = ROOT / 'data/knowledge/evaluations/autoschemakg_business_20261006' / args.name
    output.mkdir(parents=True, exist_ok=False)
    # Load every product module used by this execution before concurrent development.
    files = [*ROOT.glob('app/knowledge/*.py'), *ROOT.glob('app/knowledge/vendor/autoschemakg/*'),
             ROOT/'app/generation/model_client.py', ROOT/'app/generation/service.py', ROOT/'app/core/config.py', Path(__file__)]
    frozen = output/'executed_code'
    hashes = {}
    for path in files:
        if not path.is_file(): continue
        relative = path.relative_to(ROOT)
        target = frozen/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        hashes[str(relative)] = sha256(path.read_bytes()).hexdigest()
    public = json.loads(args.public_requirements.read_text(encoding='utf-8'))
    meta = dict(started_at=utcnow(), head=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
                code_hashes=hashes, public_requirements_sha256=sha256(args.public_requirements.read_bytes()).hexdigest(),
                source_hashes={}, product_entrypoint='KnowledgeService.start_business',
                gold_reference_loaded=False, files={})
    if bool(args.resume_database) != bool(args.resume_run_id):
        raise ValueError('재개 DB와 부모 run ID가 모두 필요합니다.')
    database = (args.resume_database or output/'knowledge.db').resolve()
    # Inspect a running parent before constructing a service (startup recovery
    # deliberately closes interrupted jobs and must not touch a live process).
    if args.resume_database:
        import sqlite3
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
            parent = json.loads(db.execute('SELECT payload FROM runs WHERE id=?', (args.resume_run_id,)).fetchone()[0])
            if parent['status'] in {'queued', 'running', 'cancel_requested'}:
                raise ValueError('부모 실행의 종료를 먼저 기다려야 합니다.')
        meta.update(parent_run_id=parent['id'], parent_run_sha256=sha256(json.dumps(parent, sort_keys=True, ensure_ascii=False).encode()).hexdigest())
    meta['database'] = str(database)
    service = KnowledgeService(database)
    try:
        if args.resume_database:
            options = dict(parent['recipe']['options'], resume_run_id=parent['id'], reuse_run_id=None)
            if args.requirement_id:
                options.update(requirement_ids=args.requirement_id, resume_run_id=None, reuse_run_id=parent['id'])
            if args.source_reassessment_tokens is not None:
                options['source_reassessment_tokens'] = args.source_reassessment_tokens
            if args.source_tokens is not None:
                options['source_tokens'] = args.source_tokens
            if args.representation_context_tokens is not None:
                options['representation_context_tokens'] = args.representation_context_tokens
            if args.representation_tokens is not None:
                options['representation_tokens'] = args.representation_tokens
            request = BusinessRunRequest.model_validate(options)
            meta['request'] = request.model_dump()
            (output/'freeze.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
            execution = service.start_business(request)
            meta['run_id'] = execution['run_id']
            (output/'freeze.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
            result = wait(service, execution['run_id'], output/'result.json')
            print(json.dumps(dict(status=result['status'], run_id=result['id'], output=str(output), error=result.get('error')), ensure_ascii=False), flush=True)
            return
        versions, source_ids = [], []
        names = ['busan_transfer.html', 'busan_departments.html'] if args.dataset == 'busan' else ['public_housing_act_art2.txt', 'public_housing_rule_art15.txt']
        for name in names:
            path = args.source_root/name
            content = path.read_bytes()
            meta['source_hashes'][name] = sha256(content).hexdigest()
            registered = service.register(name, content, SourceRegistration(title=name,
                publisher='부산광역시 차량등록사업소' if args.dataset == 'busan' else '법령 원문',
                namespace=args.dataset + '-public', external_id=name, selected_scope={'selector':'#contents'} if args.dataset == 'busan' else {}))
            versions.append(registered['source_version_id']); source_ids.append(registered['source_id'])
        parse = service.start(RunRequest(source_version_ids=versions))
        parsed = wait(service, parse['run_id'], output/'parse.json')
        if parsed['status'] != 'succeeded': raise RuntimeError('source parse incomplete')
        requirement_ids = []
        for item in public['requirements']:
            rid = args.dataset + '-' + item['requirement_id']
            value = RequirementInput(id=rid, question_ids=[args.dataset + '-q-' + item['requirement_id']],
                question=item['question'], target=item['target'], situation=item['situation'], period=item['period'],
                criterion=item['fulfillment_criteria'], source_ids=source_ids)
            business_store.put_requirement(service, value)
            requirement_ids.append(rid)
        request = BusinessRunRequest(source_version_ids=versions, requirement_ids=requirement_ids,
            conceptualize=not args.skip_concepts, source_tokens=args.source_tokens,
            representation_context_tokens=args.representation_context_tokens,
            representation_tokens=args.representation_tokens,
            source_reassessment_tokens=args.source_reassessment_tokens)
        meta['request'] = request.model_dump()
        (output/'freeze.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        execution = service.start_business(request)
        meta['run_id'] = execution['run_id']
        (output/'freeze.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        result = wait(service, execution['run_id'], output/'result.json')
        print(json.dumps(dict(status=result['status'], run_id=result['id'], output=str(output), error=result.get('error')), ensure_ascii=False), flush=True)
    finally:
        service.shutdown()


if __name__ == '__main__':
    main()
