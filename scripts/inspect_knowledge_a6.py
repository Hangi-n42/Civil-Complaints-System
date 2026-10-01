"""Capture existing A1/A3 API queries and explicit AI-operator decisions after A6 generation."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from time import monotonic
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routers import knowledge
from app.core.config import settings
from app.knowledge.service import KnowledgeService
from scripts.run_knowledge_a6 import check_freeze

QUERIES = {'C1':'공공건설임대주택', 'C2':'남은 주택', 'X1':'위탁',
           'H1':'통합공공임대주택', 'H2':'매입계획'}


def inspect(study, case, output, decisions=None, additions=None):
    frozen = check_freeze()
    if json.loads((study/'study.json').read_text(encoding='utf-8'))['freeze'] != frozen:
        raise ValueError('다른 동결 조건의 평가 원장입니다.')
    if output.exists():
        raise ValueError('이전 조회·결정 기록을 덮어쓰지 않습니다.')
    if decisions and additions:
        raise ValueError('추가와 결정은 각각 최신 revision으로 기록하세요.')
    db_path = study / 'knowledge.db'
    # Do not let service startup recover an evaluation that is still running.
    with sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro', uri=True) as db:
        if any(json.loads(row[0])['status'] in {'queued','running','cancel_requested'}
               for row in db.execute('SELECT payload FROM runs')):
            raise ValueError('현재 실행이 끝난 후 조회하세요.')
    result = json.loads((study / (case+'.json')).read_text(encoding='utf-8'))
    run = result['run']; input_run = result['input_run']
    # Reserve a writable record before any service recovery or decision mutation.
    with output.open('x', encoding='utf-8') as stream:
        json.dump(dict(case=case, status='started', human_participants=0), stream)
        stream.flush()
        service = KnowledgeService(db_path)
        app = FastAPI(); app.include_router(knowledge.router, prefix='/api/v1')
        app.dependency_overrides[knowledge.get_knowledge_service] = lambda: service
        log = []; started = monotonic()
        try:
            with patch.object(settings, 'KNOWLEDGE_ENABLED', True), TestClient(app) as client:
                def request(method, path, **kwargs):
                    response = client.request(method, '/api/v1/knowledge'+path, **kwargs)
                    body = response.json()
                    log.append(dict(method=method, path=path, request=kwargs, status=response.status_code, response=body))
                    if response.status_code != 200:
                        raise ValueError(json.dumps(body, ensure_ascii=False))
                    return body['data']
                before_sources = request('GET', '/sources')
                cid = run.get('changeset_id')
                if run['kind']=='discovery':
                    cid = request('POST', '/runs/'+run['id']+'/ontology-changes')['changeset_id']
                before = request('GET','/candidates',params={'changeset_id':cid}) if cid else None
                if decisions or additions:
                    if not cid: raise ValueError('결정할 변경안이 없습니다.')
                    body = json.loads((decisions or additions).read_text(encoding='utf-8'))
                    if body.get('actor') != 'a6-ai-operator':
                        raise ValueError('AI 대리 조작과 사람 검수를 구분하는 actor를 사용하세요.')
                    request('POST', '/changes/'+cid+('/decisions' if decisions else '/ontology-candidates'), json=body)
                after = request('GET','/candidates',params={'changeset_id':cid}) if cid else None
                if cid and run['kind']=='discovery':
                    request('GET', '/changes/'+cid+'/schema-preview')
                for item in input_run['frozen_input']['files']:
                    request('GET','/discovery/read',params=dict(run_id=input_run['id'],file_id=item['file_id'],limit=100))
                # Retrieval presence is not scored as an answer: assess the returned conditions and evidence separately.
                for cq in result['case']['cq_ids']:
                    request('GET','/discovery/search',params=dict(run_id=input_run['id'],q=QUERIES[cq],limit=20))
                for block in result['input_blocks']:
                    request('GET','/evidence/'+block['evidence_id'],params=dict(run_id=input_run['id']))
                after_sources = request('GET', '/sources')
                if before_sources != after_sources:
                    raise AssertionError('조회/검수 중 원문 원장 변경')
                record = dict(case=case, generation_run_id=run['id'], changeset_id=cid,
                              before=before, after=after, sources_unchanged=True,
                              actor='a6-ai-operator', human_participants=0)
        except Exception as exc:
            record = dict(case=case, error=str(exc), human_participants=0)
        finally:
            service.shutdown()
        record.update(api_log=log, ai_tool_elapsed_s=round(monotonic()-started, 3))
        stream.seek(0)
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.truncate()
        print(json.dumps(dict(case=case, error=record.get('error'), changeset_id=record.get('changeset_id'),
                              api_requests=len(log)), ensure_ascii=False))



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--case', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--decisions', type=Path)
    parser.add_argument('--additions', type=Path)
    args = parser.parse_args()
    inspect(args.study, args.case, args.output, args.decisions, args.additions)


if __name__ == '__main__':
    main()
