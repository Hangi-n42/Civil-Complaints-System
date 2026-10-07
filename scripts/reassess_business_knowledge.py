"""Copy a terminal evaluation DB and exercise the stored-pool product path."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.generation.model_client import ModelClient, configuration
from app.knowledge import business_use
from app.knowledge.business_models import BusinessDecision, BusinessQuery, BusinessRunRequest
from app.knowledge.service import KnowledgeService, utcnow
from run_business_knowledge import wait


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--parent-run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--requirement-id', action='append', default=[])
    parser.add_argument('--query-requirement', action='append', default=[])
    parser.add_argument('--query-limit', type=int, default=12)
    parser.add_argument('--questions', type=Path)
    parser.add_argument('--question-id', action='append', default=[])
    parser.add_argument('--qa-only', action='store_true')
    parser.add_argument('--request-file', type=Path, help='Exact public product request for a prepared source-scope control')
    args = parser.parse_args()
    original, output = args.database.resolve(), args.output.resolve()
    original_hash = sha256(original.read_bytes()).hexdigest()
    with sqlite3.connect(original.as_uri() + '?mode=ro', uri=True) as db:
        runs = [json.loads(row[0]) for row in db.execute('SELECT payload FROM runs')]
        if any(r['status'] in {'queued', 'running', 'cancel_requested'} for r in runs):
            raise ValueError('Source database must be terminal')
        parent = next(r for r in runs if r['id'] == args.parent_run_id)
        versions = [json.loads(db.execute('SELECT payload FROM versions WHERE id=?', (v,)).fetchone()[0])
                    for v in parent['input_version_ids']]
        output.mkdir(parents=True, exist_ok=False)
        with sqlite3.connect(output/'knowledge.db') as target:
            db.backup(target)
    for version in versions:
        old, new = original.parent/version['relative_raw_path'], output/version['relative_raw_path']
        assert sha256(old.read_bytes()).hexdigest() == version['sha256']
        new.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, new)
    files = [*ROOT.glob('app/knowledge/*.py'), *ROOT.glob('app/knowledge/vendor/autoschemakg/*'),
        ROOT/'app/generation/model_client.py', ROOT/'app/generation/service.py', ROOT/'app/core/config.py',
        ROOT/'scripts/run_business_knowledge.py', Path(__file__)]
    code = {}
    for path in files:
        if not path.is_file(): continue
        relative = path.relative_to(ROOT)
        target = output/'executed_code'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        code[str(relative)] = sha256(path.read_bytes()).hexdigest()
    options = dict(parent['recipe']['options'], resume_run_id=None, reuse_run_id=None, reassess_run_id=parent['id'],
        requirement_ids=args.requirement_id or [r['id'] for r in parent['requirements']],
        context_tokens=49152, representation_context_tokens=49152, source_tokens=8192,
        source_reassessment_tokens=8192, representation_tokens=8192, review_tokens=8192, conceptualize=True)
    if args.request_file:
        if args.qa_only or args.requirement_id:
            raise ValueError('Exact request cannot be combined with QA-only or requirement overrides')
        options = json.loads(args.request_file.read_text(encoding='utf-8'))
    request = BusinessRunRequest.model_validate(options)
    if not set(request.source_version_ids) <= set(parent['input_version_ids']):
        raise ValueError('Requested sources must exist in the copied parent inputs')
    if args.request_file and (request.model != parent['recipe']['models']['draft']
                             or request.review_model != parent['recipe']['models']['review']):
        raise ValueError('This comparison freezes the parent local model identities')
    config = configuration()
    if config['provider'] != 'ollama':
        raise ValueError('This evaluation permits only the local product provider')
    identities = ModelClient(config).identities(parent['recipe']['models'], dict(draft=request.context_tokens,
        review=max(request.context_tokens, request.representation_context_tokens or request.context_tokens)))
    questions = json.loads(args.questions.read_text(encoding='utf-8'))['items'] if args.questions else []
    if args.question_id:
        if not set(args.question_id) <= {q['question_id'] for q in questions}:
            raise ValueError('Unknown frozen question ID')
        questions = [q for q in questions if q['question_id'] in args.question_id]
    assert all(set(q) == {'question_id', 'question', 'choices'} for q in questions)
    write(output/'freeze.json', dict(recorded_at=utcnow(), original_database=str(original),
        original_database_sha256=original_hash, parent_run_id=parent['id'],
        parent_claims_sha256=sha256(json.dumps(parent['claims'], ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        request=request.model_dump(), code_hashes=code, model_identity=identities, generation=config,
        qa_only=args.qa_only, question_ids=[q['question_id'] for q in questions], query_requirements=args.query_requirement, query_limit=args.query_limit,
        gold_loaded=False, actual_human_review=False, full_qa_score=False,
        product_entrypoints=([] if args.qa_only else ['KnowledgeService.start_business']) +
            ['business_use.decide', 'business_use.query']))
    service = KnowledgeService(output/'knowledge.db')
    query_usage = []
    try:
        if args.qa_only:
            run = parent
        else:
            dispatched = service.start_business(request)
            write(output/'dispatch.json', dispatched)
            run = wait(service, dispatched['run_id'], output/'result.json')
        if run.get('changeset_id'):
            change = business_use.change_view(service, run['changeset_id'])
            decision = business_use.decide(service, change['id'], BusinessDecision(expected_revision=change['revision'],
                actor='evaluation_operator', reason='저장풀 재검수의 제품 적격 후보 활용 확인; 실제 사람 검토 아님',
                accept_ids=change['eligible_ids']))
            write(output/'decision.json', decision)
            questions.extend(dict(question_id=r['id'], question=r['question'], choices={}, requirement_ids=[r['id']])
                for r in run['requirements'] if r['id'] in args.query_requirement)
            for question in questions:
                result = business_use.query(service, BusinessQuery(snapshot_id=decision['snapshot_id'],
                    question=question['question'], choices=[f'{k}. {v}' for k, v in question['choices'].items()],
                    requirement_ids=question.get('requirement_ids', []), limit=args.query_limit))
                write(output/(question['question_id']+'_graph.json'), result)
                if result.get('run_id'):
                    query_run = service.run(result['run_id'])
                    query_usage.append(dict(question_id=question['question_id'], run_id=query_run['id'],
                        metrics=query_run['metrics'], input_tokens=sum(u.get('response', {}).get('prompt_eval_count', 0) or 0
                            for u in query_run['units']), output_tokens=sum(u.get('response', {}).get('eval_count', 0) or 0
                            for u in query_run['units'])))
                print(json.dumps(dict(question_id=question['question_id'], run_id=result.get('run_id'),
                    status=result['status']), ensure_ascii=False), flush=True)
        unchanged = all(sha256((ROOT/p).read_bytes()).hexdigest() == h for p, h in code.items())
        original_unchanged = sha256(original.read_bytes()).hexdigest() == original_hash
        with service.repository.connect() as db:
            current_parent = service.repository.get(db, 'runs', parent['id'])
        write(output/'terminal.json', dict(recorded_at=utcnow(), run_id=run['id'], status=run['status'],
            code_unchanged=unchanged, code_file_count=len(code), original_database_unchanged=original_unchanged,
            parent_run_unchanged=current_parent == parent, business_run_executed=not args.qa_only,
            metrics=run['metrics'] if not args.qa_only else dict(llm_calls=0, model_total_s=0, elapsed_s=0),
            query_usage=query_usage, error=run.get('error'),
            assessment_statuses={a['requirement_id']: a['status'] for a in run['assessments']},
            repairs=len(run['repairs']), applied_changes=sum(len(r['changes']) for r in run['repairs'])))
        assert unchanged and original_unchanged and current_parent == parent
    finally:
        service.shutdown()


if __name__ == '__main__':
    main()
