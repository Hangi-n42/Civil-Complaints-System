import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routers import knowledge
from app.knowledge.service import KnowledgeService


def test_feature_gate_registration_and_raw(tmp_path, monkeypatch):
    service = KnowledgeService(tmp_path / 'knowledge.db')
    app = FastAPI()
    app.include_router(knowledge.router, prefix='/api/v1')
    app.dependency_overrides[knowledge.get_knowledge_service] = lambda: service
    metadata = json.dumps(dict(title='단지', publisher='LH', namespace='LH', external_id='one'))
    try:
        with TestClient(app) as client:
            monkeypatch.setattr(knowledge.settings, 'KNOWLEDGE_ENABLED', False)
            response = client.get('/api/v1/knowledge/sources')
            assert response.status_code == 503
            assert response.json()['error']['code'] == 'KNOWLEDGE_DISABLED'
            monkeypatch.setattr(knowledge.settings, 'KNOWLEDGE_ENABLED', True)
            response = client.post('/api/v1/knowledge/sources', files={'file': ('a.csv', b'code\n1')}, data={'metadata': metadata})
            assert response.status_code == 200
            data = response.json()['data']
            url = f'/api/v1/knowledge/sources/{data["source_id"]}/versions/{data["source_version_id"]}'
            assert client.get(url + '/raw').content == b'code\n1'
            assert client.get(url).json()['data']['version']['processing_status'] == 'registered'
            assert client.get(url + '/blocks').json()['data']['items'] == []
            assert client.post('/api/v1/knowledge/runs', json={'kind': 'extract'}).status_code == 422
            assert client.get('/api/v1/knowledge/evidence/missing').status_code == 404
            assert client.post('/api/v1/knowledge/sources', files={'file': ('a.csv', b'x')}, data={'metadata': '{}'}).status_code == 422
    finally:
        service.shutdown()
