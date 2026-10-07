"""Small frozen retrieval ablation through the product business query service.

Uses a new SQLite backup; never publishes/approves claims or changes the original.
Questions/choices enter the model; the frozen reference is read only after answers.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.knowledge import business_use
from app.knowledge.business_models import BusinessQuery
from app.knowledge.service import KnowledgeService, utcnow


def write(path, data):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--snapshot')
    source.add_argument('--source-run-id')
    parser.add_argument('--questions', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--question-ids', nargs='+', required=True)
    args = parser.parse_args()
    questions = json.loads(args.questions.read_text())
    selected = [q for q in questions['items'] if q['question_id'] in args.question_ids]
    if {q['question_id'] for q in selected} != set(args.question_ids):
        raise ValueError('Unknown question ID')
    if any(set(q) != {'question_id', 'question', 'choices'} for q in selected):
        raise ValueError('Only questions and choices may enter product calls')
    args.output.mkdir(parents=True, exist_ok=False)
    with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro', uri=True) as source:
        with sqlite3.connect(args.output/'knowledge.db') as destination:
            source.backup(destination)
    service = KnowledgeService(args.output/'knowledge.db')
    arms = [('bm25', 'full'), ('dense', 'entity_event'), ('hipporag2', 'entity_event'), ('hipporag2', 'full')]
    answers = []
    try:
        with service.repository.connect() as db:
            if args.source_run_id:
                origin = service.repository.get(db, 'runs', args.source_run_id)
                snapshot = origin
            else:
                snapshot = service.repository.get(db, 'snapshots', args.snapshot)
                origin = service.repository.get(db, 'runs', snapshot['run_id'])
        code_hashes = {}
        for path in [*ROOT.glob('app/knowledge/*.py'), *ROOT.glob('app/knowledge/vendor/autoschemakg/*'),
                     ROOT/'app/generation/model_client.py', Path(__file__)]:
            if not path.is_file():
                continue
            target = args.output/'executed_code'/path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
            code_hashes[str(path.relative_to(ROOT))] = sha256(path.read_bytes()).hexdigest()
        write(args.output/'freeze.json', dict(started_at=utcnow(), arms=arms, limit=12,
            snapshot_id=args.snapshot, source_run_id=args.source_run_id,
            input_sha256=sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest(),
            model_identity=origin['model_identity'], recipe=origin['recipe'], code_hashes=code_hashes,
            questions=selected, question_version=questions['version'],
            reference_sha256=sha256(args.reference.read_bytes()).hexdigest(),
            source_claims=len(snapshot['claims']), concept_records=len(snapshot['concepts']),
            selection_reason='Predeclared common conditions, corporate condition, application deadline, branch scope, two-document combination and two-period distinction',
            scope=('Stored extraction graph and source passages, not an approval' if args.source_run_id else 'Stored reviewed subset') + '; extraction/conceptualization held fixed; not a new extraction quality evaluation',
            product_entrypoint='business_use.query', human_review=False))
        for retrieval, variant in arms:
            arm = retrieval + '_' + variant
            for question in selected:
                result = business_use.query(service, BusinessQuery(snapshot_id=args.snapshot, source_run_id=args.source_run_id,
                    question=question['question'], choices=[f'{k}. {v}' for k, v in question['choices'].items()],
                    retrieval=retrieval, graph_variant=variant, limit=12))
                run = service.run(result['run_id']) if result.get('run_id') else {}
                item = dict(question_id=question['question_id'], arm=arm, result=result,
                    metrics=run.get('metrics'), graph_retrieval=run.get('graph_retrieval'),
                    units=[dict(stage=u['stage'], status=u['status'], error=u.get('error'),
                        input_tokens=(u.get('response') or {}).get('prompt_eval_count'),
                        output_tokens=(u.get('response') or {}).get('eval_count')) for u in run.get('units', [])])
                write(args.output/f"{question['question_id']}_{arm}.json", item)
                answers.append(item)
                print(json.dumps(dict(question=question['question_id'], arm=arm, status=result['status']), ensure_ascii=False), flush=True)
                if result['status'] == 'retrieval_failed' or any(u['error'] == 'input_capacity' for u in item['units']):
                    write(args.output/'stopped.json', dict(reason='Execution prerequisite failed; do not repeat unchanged calls',
                        question_id=question['question_id'], arm=arm, result=result, units=item['units']))
                    return
        write(args.output/'answers.json', answers)
        reference = json.loads(args.reference.read_text())
        gold = {q['question_id']: q for q in reference['items']}
        scores = []
        for item in answers:
            answer = item['result'].get('answer') or {}
            scores.append(dict(question_id=item['question_id'], arm=item['arm'],
                expected=gold[item['question_id']]['correct_choice'], actual=answer.get('choice'),
                correct=answer.get('choice') == gold[item['question_id']]['correct_choice'],
                status=item['result']['status']))
        write(args.output/'scores.json', dict(scored_at=utcnow(), items=scores,
            summary={r+'_'+v: dict(correct=sum(s['correct'] for s in scores if s['arm']==r+'_'+v),
                denominator=len(selected), failed=sum(s['status']!='answered' for s in scores if s['arm']==r+'_'+v))
                for r,v in arms}, note='Failures remain in denominator; MC correctness is not proof of full requirement satisfaction'))
    finally:
        service.shutdown()


if __name__ == '__main__':
    main()
