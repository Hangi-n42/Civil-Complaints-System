"""One serial pass over frozen K6 questions; no scoring, retries, or generation of facts."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.request import urlopen

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.config import settings
from app.knowledge import search
from app.knowledge.service import KnowledgeService
from app.knowledge.repository import KnowledgeRepository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=['development', 'new_question_once', 'all'], required=True)
    parser.add_argument('--variants', nargs='+', choices=['A', 'B', 'C', 'D'], default=['A', 'B', 'C'])
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/knowledge/k6_answer_quality_v1.json')
    parser.add_argument('--cases', nargs='+')
    parser.add_argument('--think', action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument('--chat', action='store_true')
    parser.add_argument('--model', default='exaone3.5:7.8b')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config_path = args.config.resolve()
    config = json.loads(config_path.read_text())
    code_hashes = {p: sha256((ROOT / p).read_bytes()).hexdigest() for p in
                   ['app/knowledge/search.py', 'app/knowledge/search_answer.py', str(config_path.relative_to(ROOT))]}
    with urlopen(settings.OLLAMA_BASE_URL.rstrip('/') + '/api/tags') as response:
        model_info = next(m for m in json.load(response)['models'] if m['name'] == args.model)
    repository = KnowledgeRepository(Path(settings.KNOWLEDGE_DB_PATH))
    with repository.connect() as db:
        if any(json.loads(r['payload'])['status'] in {'queued','running','cancel_requested'} for r in db.execute('SELECT payload FROM runs')):
            raise RuntimeError('Finish the active knowledge run before this offline comparison.')
    service = KnowledgeService(settings.KNOWLEDGE_DB_PATH)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with service.repository.connect() as db:
            for identifier, expected in config['snapshots'].items():
                snapshot = service.repository.get(db, 'snapshots', identifier)
                actual = sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                if actual != expected:
                    raise ValueError('Frozen snapshot changed: ' + identifier)
        # Refuse to overwrite or silently resume a comparison.
        with args.output.open('x') as output:
            for case in config['cases']:
                if args.cases and case['id'] not in args.cases:continue
                if args.split != 'all' and case['split'] != args.split:
                    continue
                for variant in args.variants:
                    row = dict(case_id=case['id'], split=case['split'], variant=variant,
                               model=model_info, code_hashes=code_hashes, request=case['request'])
                    wire_requests = []
                    original_post = httpx.AsyncClient.post
                    async def observed_post(client, url, **kwargs):
                        body = kwargs['json']
                        # Diagnostic endpoint comparison stays out of the production client.
                        if args.chat:
                            url=url.rsplit('/',1)[0]+'/chat'
                            body['messages']=[{'role':'user','content':body.pop('prompt')}]
                        wire_requests.append({k: body[k] for k in ['model','think','options'] if k in body})
                        wire_requests[-1]['endpoint']=url.rsplit('/',1)[-1]
                        response=await original_post(client, url, **kwargs)
                        if response.status_code==200:
                            data=response.json()
                            wire_requests[-1]['response_metadata']={k:data.get(k) for k in ['done','done_reason','eval_count']}
                            if args.chat:
                                data['response']=data.get('message',{}).get('content','')
                                response=httpx.Response(200,json=data,request=response.request)
                        return response
                    try:
                        with patch.object(httpx.AsyncClient, 'post', observed_post):
                            row['result'] = search.search(service, case['request'], answer_variant=variant, model=args.model, think=args.think)
                    except Exception as exc:
                        row['error'] = str(exc)
                    row['wire_requests'] = wire_requests
                    with service.repository.connect() as db:
                        row['run'] = json.loads(db.execute('SELECT payload FROM runs ORDER BY rowid DESC LIMIT 1').fetchone()[0])
                    output.write(json.dumps(row, ensure_ascii=False) + '\n'); output.flush()
                    print(json.dumps(dict(case=case['id'], variant=variant, error=row.get('error'),
                                          metrics=row['run']['metrics']), ensure_ascii=False), flush=True)
    finally:
        service.executor.shutdown()


if __name__ == '__main__':
    main()
