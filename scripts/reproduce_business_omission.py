"""Declare a missing-candidate stored pool in a copy, then use the product runner.

This intervention is not a naturally occurring extraction omission. The original
run, all source blocks, and the undeleted candidates remain unchanged.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.knowledge import autoschema
from app.knowledge.service import utcnow
from reassess_business_knowledge import write


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--copy-directory', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--request-file', type=Path)
    args = parser.parse_args()
    folder = args.copy_directory.resolve()
    manifest = json.loads((folder/'copy_receipt.json').read_text(encoding='utf-8'))
    database = folder/'knowledge.db'
    original = Path(manifest['original_database'])
    if database.resolve() == original.resolve():
        raise ValueError('원본 DB에서는 누락을 주입하지 않습니다.')
    assert sha256(original.read_bytes()).hexdigest() == manifest['original_database_sha256']
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as db:
        rows = [json.loads(r[0]) for r in db.execute('SELECT payload FROM runs')]
    if any(r['status'] in {'queued', 'running', 'cancel_requested'} for r in rows):
        raise ValueError('준비 사본에 실행 중인 작업이 있습니다.')
    parent = next(r for r in rows if r['id'] == manifest['parent_run_id'])
    assert digest(parent) == manifest['parent_run_sha256']
    omitted = set(manifest['omitted_claim_ids'])
    parent_claims = {c['id']: c for c in parent['claims']}
    if len(omitted) != 2 or not omitted <= set(parent_claims):
        raise ValueError('명시한 두 원래 후보만 제거할 수 있습니다.')
    receipt_path = folder/'omission_receipt.json'
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        prepared = next(r for r in rows if r['id'] == receipt['prepared_run_id'])
        assert digest(prepared) == receipt['prepared_run_sha256']
    else:
        prepared = deepcopy(parent)
        prepared.update(id=uuid4().hex, parent_run_id=parent['id'], units=[], analysis_units=[],
            assessments=[], repairs=[], prior_repairs=[], reusable_units=[], status='partial',
            started_at=None, finished_at=utcnow(), metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0))
        prepared.pop('changeset_id', None)
        prepared['claims'] = [c for c in prepared['claims'] if c['id'] not in omitted]
        prepared['graph'] = autoschema.graph(prepared['claims'])
        targets = {t['id']: t for t in autoschema.concept_targets(prepared['graph'])}
        prepared['concepts'] = [c for c in prepared['concepts'] if targets.get(c['target']['id']) == c['target']]
        prepared['evaluation_intervention'] = dict(kind='explicit_candidate_omission', natural_omission=False,
            parent_run_id=parent['id'], omitted_claim_ids=sorted(omitted), reconstruction_performed=False)
        assert len(prepared['claims']) == len(parent['claims']) - len(omitted)
        assert all(c == parent_claims[c['id']] for c in prepared['claims'])
        assert prepared['blocks'] == parent['blocks']
        with sqlite3.connect(database) as db:
            db.execute('INSERT INTO runs VALUES(?,?)', (prepared['id'], json.dumps(prepared, ensure_ascii=False)))
        receipt = dict(recorded_at=utcnow(), intervention='explicit_stored_candidate_omission',
            prepared_run_id=prepared['id'], prepared_run_sha256=digest(prepared),
            removed_candidates=[c for c in parent['claims'] if c['id'] in omitted],
            unchanged_count=len(prepared['claims']), remaining_sha256=digest(prepared['claims']),
            source_blocks_unchanged=True, parent_run_unchanged=True, injected_into_model_prompt=False,
            reconstruction_performed=False, model_calls=0,
            script_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
        write(receipt_path, receipt)
    print(json.dumps(dict(prepared_run_id=prepared['id'], remaining_claims=len(prepared['claims']),
                         prepare_only=args.prepare_only)), flush=True)
    if args.prepare_only:
        return
    request_args = ['--requirement-id', manifest['requirement_id']]
    if args.request_file:
        request = json.loads(args.request_file.read_text(encoding='utf-8'))
        if request.get('reassess_run_id') != prepared['id'] or request.get('requirement_ids') != [manifest['requirement_id']]:
            raise ValueError('선언 누락의 같은 저장 후보와 요구만 재검토할 수 있습니다.')
        request_args = ['--request-file', str(args.request_file.resolve())]
    output = folder/'execution'
    subprocess.run([sys.executable, str(ROOT/'scripts/reassess_business_knowledge.py'),
        '--database', str(database), '--parent-run-id', prepared['id'], '--output', str(output),
        *request_args, '--query-requirement', manifest['requirement_id']], check=True)
    run = json.loads((output/'result.json').read_text(encoding='utf-8'))
    remaining = {c['id']: c for c in run['claims']}
    normal = [cid for cid in parent_claims if cid not in omitted]
    write(output/'preservation.json', dict(expected_normal_count=len(normal),
        unchanged_ids=[cid for cid in normal if remaining.get(cid) == parent_claims[cid]],
        changed_or_missing_ids=[cid for cid in normal if remaining.get(cid) != parent_claims[cid]],
        original_parent_run_sha256=digest(parent), actual_repair_receipts=run['repairs']))
    assert sha256(original.read_bytes()).hexdigest() == manifest['original_database_sha256']


if __name__ == '__main__':
    main()
