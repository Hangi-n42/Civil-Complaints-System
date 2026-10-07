import asyncio
import json

import httpx
import pytest

from app.generation.model_client import ModelClient, ModelRequest


def test_local_identity_and_truncated_usage_are_preserved():
    def handler(request):
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models': [{'name': 'local', 'digest': 'frozen'}]})
        if request.url.path == '/api/show':
            return httpx.Response(200, json={'model_info': {'gemma.context_length': 32768}})
        body = json.loads(request.content)
        assert body['messages'] == [{'role': 'user', 'content': 'source'}]
        return httpx.Response(200, json={'done': True, 'done_reason': 'length', 'message': {'content': ''},
                                        'prompt_eval_count': 70, 'eval_count': 256})
    client = ModelClient({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434'},
                         transport=httpx.MockTransport(handler))
    assert client.identities({'draft': 'local'}, {'draft': 8192})['draft']['digest'] == 'frozen'
    result = asyncio.run(client.generate(ModelRequest('extract', 'local', [{'role': 'user', 'content': 'source'}])))
    assert result['failure_kind'] == 'truncated' and result['text'] == ''
    assert result['eval_count'] == 256 and result['usage_source'] == 'provider_reported'


def test_external_contract_no_ollama_probe_or_secret_in_record(monkeypatch):
    monkeypatch.setenv('TEST_KNOWLEDGE_KEY', 'mock-secret')
    def handler(request):
        assert request.url.path == '/v1/chat/completions'
        assert request.headers['Authorization'] == 'Bearer mock-secret'
        body = json.loads(request.content)
        assert 'options' not in body and 'think' not in body
        assert body['response_format']['json_schema']['schema'] == {'type': 'object'}
        return httpx.Response(200, json={'model': 'provider-revision', 'choices': [
            {'message': {'content': '{"ok":true}'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 12, 'completion_tokens': 7}})
    client = ModelClient({'provider': 'openai_chat', 'endpoint': 'https://mock.invalid/v1',
                          'auth_env': 'TEST_KNOWLEDGE_KEY', 'context_length': 49152},
                         transport=httpx.MockTransport(handler))
    assert client.identities({'draft': 'model'}, {'draft': 8192})['draft']['digest'] is None
    result = asyncio.run(client.generate(ModelRequest('draft', 'model', [{'role': 'user', 'content': 'example'}],
                                                     schema={'type': 'object'})))
    assert result['parsed'] == {'ok': True} and result['failure_kind'] is None
    assert result['prompt_eval_count'] == 12 and 'mock-secret' not in json.dumps(result)
    with pytest.raises(ValueError, match='think'):
        asyncio.run(client.generate(ModelRequest('draft', 'model', [], think=True)))


def test_cancel_before_request_never_calls_transport():
    def forbidden(_):
        pytest.fail('cancelled request reached transport')
    client = ModelClient({'provider': 'ollama', 'endpoint': 'http://127.0.0.1:11434'},
                         transport=httpx.MockTransport(forbidden))
    result = asyncio.run(client.generate(ModelRequest('draft', 'model', []), lambda: True))
    assert result['failure_kind'] == 'cancelled' and result['eval_count'] is None
