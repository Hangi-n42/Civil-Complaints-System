"""Evaluation operator + identical frozen questions through the product query path.

Only question/choice files enter product calls. Gold references are read after
answers have been persisted, solely for deterministic multiple-choice scoring.
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
from app.knowledge.business_models import BusinessDecision, BusinessQuery
from app.knowledge.service import KnowledgeService, utcnow


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--questions', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scope-note', required=True, help='State incomplete requirements/known failures; descriptive evaluation metadata, never model input')
    parser.add_argument('--stop-file', type=Path, help='Stop between calls when this explicit local marker exists')
    args = parser.parse_args()
    with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        rows = [json.loads(r[0]) for r in db.execute('SELECT payload FROM runs')]
        if any(r['status'] in {'queued', 'running', 'cancel_requested'} for r in rows):
            raise ValueError('실행 중인 DB에는 평가 서비스 인스턴스를 추가하지 않습니다.')
    questions = json.loads(args.questions.read_text(encoding='utf-8'))
    if any(set(q) != {'question_id', 'question', 'choices'} for q in questions['items']):
        raise ValueError('QA에는 질문·선택지 파일만 허용합니다.')
    args.output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for path in [*ROOT.glob('app/knowledge/*.py'), *ROOT.glob('app/knowledge/vendor/autoschemakg/*'),
                 ROOT/'app/generation/model_client.py', ROOT/'app/generation/service.py', ROOT/'app/core/config.py', Path(__file__)]:
        if not path.is_file(): continue
        target = args.output/'executed_code'/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        hashes[str(path.relative_to(ROOT))] = sha256(path.read_bytes()).hexdigest()
    service = KnowledgeService(args.database)
    try:
        with service.repository.connect() as db:
            run = service.repository.get(db, 'runs', args.run_id)
        change = business_use.change_view(service, run['changeset_id'])
        freeze = dict(started_at=utcnow(), run_id=run['id'], model_identity=run['model_identity'],
                      query_recipe=run['recipe'], query_limit=12, question_version=questions['version'],
                      code_hashes=hashes, retrieval_contract='source-claims+concept-hints-v1',
                      eligibility_contract=change['eligibility_contract'],
                      completion_contract=change['completion_contract'],
                      answer_contract=business_use.ANSWER_CONTRACT,
                      completion_status_basis='New snapshot recalculates under this contract; original run status is retained as recorded_status',
                      published_eligible_claim_ids=change['published_eligible_ids'],
                      question_sha256=sha256(args.questions.read_bytes()).hexdigest(),
                      reference_sha256=sha256(args.reference.read_bytes()).hexdigest(),
                      evaluation_operator=True, actual_human_review=False,
                      product_entrypoints=['business_use.decide', 'business_use.query'],
                      baseline='same frozen source blocks, same BM25 and query model; no gold source filter')
        freeze.update(scope_note=args.scope_note, assessed_requirement_ids=[r['id'] for r in run['requirements']],
                      qa_score_does_not_establish_requirement_validation=True,
                      graph_eligible_claim_ids=change['eligible_ids'], all_extracted_claim_count=len(run['claims']))
        write_new(args.output/'freeze.json', freeze)
        if not change['eligible_ids']:
            write_new(args.output/'blocked.json', dict(reason='No review-eligible source claims',
                context_mode='graph', required_questions=len(questions['items']), executed_questions=0, status='incomplete',
                document_baseline_independent=True))
        decision = business_use.decide(service, change['id'], BusinessDecision(expected_revision=change['revision'],
            actor='evaluation_operator', reason='평가 운영자가 자동 검수 통과 후보를 평가용으로 선택함; 실제 사람 검토 아님' if change['eligible_ids']
                else '승인 주장 0개. 동결 원문 문서 기준선만 확인하기 위한 명시적 빈 검토 기록; 실제 사람 검토 아님',
            accept_ids=change['eligible_ids']))
        write_new(args.output/'decision.json', decision)
        answers = []
        for question in questions['items']:
            request = BusinessQuery(question=question['question'], choices=[f'{k}. {v}' for k, v in question['choices'].items()],
                                    snapshot_id=decision['snapshot_id'], limit=12)
            for mode in ('document', 'graph'):
                if args.stop_file and args.stop_file.exists():
                    write_new(args.output/'stopped.json', dict(recorded_at=utcnow(),
                        reason='Explicit stop marker observed between calls', stop_file=str(args.stop_file),
                        planned_questions=len(questions['items']), planned_arms_per_question=2,
                        completed_answer_records=len(answers), next_question_id=question['question_id'], next_mode=mode))
                    write_new(args.output/'partial_answers.json', answers)
                    return
                result = business_use.query(service, request, context_mode=mode)
                item = dict(question_id=question['question_id'], mode=mode, result=result)
                write_new(args.output/f"{question['question_id']}_{mode}.json", item)
                answers.append(item)
                print(json.dumps(dict(question_id=question['question_id'], mode=mode, status=result['status']), ensure_ascii=False), flush=True)
        # Answer generation is over before loading any gold answer/meaning.
        reference = json.loads(args.reference.read_text(encoding='utf-8'))
        write_new(args.output/'answers.json', answers)
        # Preserve mismatched reference contracts instead of guessing answer keys.
        keys = {item['question_id']: item['correct_choice'] for item in reference['items']}
        if any(k not in {'A', 'B', 'C', 'D'} for k in keys.values()):
            write_new(args.output/'scoring_pending.json', dict(reason='Reference answer field needs explicit mapping', answer_files_preserved=True))
            return
        scores = []
        for mode in ('document', 'graph'):
            results = [a for a in answers if a['mode'] == mode]
            rows = [dict(question_id=a['question_id'], expected=keys[a['question_id']],
                         actual=(a['result'].get('answer') or {}).get('choice'), status=a['result']['status'],
                         answer_nonempty=bool(((a['result'].get('answer') or {}).get('answer') or '').strip())) for a in results]
            for row in rows:
                row['correct'] = row['status'] == 'answered' and row['answer_nonempty'] and row['actual'] == row['expected']
            scores.append(dict(mode=mode, denominator=len(questions['items']), correct=sum(r['correct'] for r in rows),
                               failed_or_unverified=sum(r['status'] != 'answered' for r in rows),
                               empty_answers=sum(not r['answer_nonempty'] for r in rows),
                               no_choice_or_abstention=sum(r['actual'] not in {'A','B','C','D'} for r in rows), rows=rows))
        write_new(args.output/'scores.json', dict(reference_version=reference['version'], scores=scores,
                                               semantic_quality_verified=False, actual_human_review=False))
    finally:
        service.shutdown()


if __name__ == '__main__':
    main()
