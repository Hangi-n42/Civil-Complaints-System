"""Freeze both equal-information arms before any new conceptualization call."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.knowledge import business_concepts
from app.knowledge.business_models import ConceptRunRequest
from app.knowledge.service import KnowledgeService, utcnow
from app.generation.model_client import ModelClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--parent-run-id', required=True)
    parser.add_argument('--target-id', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        if any(json.loads(r[0])['status'] in {'queued', 'running', 'cancel_requested'} for r in db.execute('SELECT payload FROM runs')):
            raise ValueError('기존 실행이 종료된 뒤 비교하세요.')
    args.output.mkdir(parents=True, exist_ok=False)
    service = KnowledgeService(args.database)
    try:
        requests = [ConceptRunRequest(parent_run_id=args.parent_run_id, target_ids=args.target_id, neighbor_mode=mode)
                    for mode in ('plain', 'structured')]
        plans = [business_concepts.plan(service, request) for request in requests]
        parent = plans[0][0]
        identity = ModelClient(parent['recipe']['generation']).identities(parent['recipe']['models'],
            {role: parent['recipe']['options']['context_tokens'] for role in parent['recipe']['models']})
        if identity != parent['model_identity']: raise ValueError('모델 identity가 변경되어 새 비교 동결이 필요합니다.')
        for a, b in zip(plans[0][1], plans[1][1]):
            assert a['target'] == b['target']
            assert a['selection']['information_fingerprint'] == b['selection']['information_fingerprint']
            assert a['selection']['selected_edge_ids'] == b['selection']['selected_edge_ids']
            assert a['selection']['source_reference_map'] == b['selection']['source_reference_map']
        hashes = {}
        for path in [*ROOT.glob('app/knowledge/*.py'), *ROOT.glob('app/knowledge/vendor/autoschemakg/*'),
                     ROOT/'app/generation/model_client.py', ROOT/'app/generation/service.py', ROOT/'app/core/config.py', Path(__file__)]:
            if not path.is_file(): continue
            target = args.output/'executed_code'/path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(path.read_bytes())
            hashes[str(path.relative_to(ROOT))] = sha256(path.read_bytes()).hexdigest()
        freeze = dict(started_at=utcnow(), code_hashes=hashes, parent_run_id=parent['id'],
            model_identity=identity, recipe=parent['recipe'], graph=parent['graph'],
            arms=[dict(request=r.model_dump(), planned=p[1]) for r,p in zip(requests,plans)],
            gold_reference_loaded=False, semantic_effect='unmeasured', product_entrypoint='business_concepts.start')
        (args.output/'freeze.json').write_text(json.dumps(freeze, ensure_ascii=False, indent=2), encoding='utf-8')
        for request in requests:
            result = business_concepts.start(service, request)
            (args.output/(request.neighbor_mode+'.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(dict(mode=request.neighbor_mode, run_id=result['id'], status=result['status']), ensure_ascii=False), flush=True)
    finally:
        service.shutdown()


if __name__ == '__main__':
    main()
