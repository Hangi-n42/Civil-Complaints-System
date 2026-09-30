"""The optional K3 metadata response preserves the existing string contract."""
import asyncio
import json

import httpx

from app.generation.service import GenerationService


def test_call_ollama_string_and_metadata_with_non_thinking_payload(monkeypatch):
    payloads = []
    timeouts = []
    def respond(request):
        timeouts.append(request.extensions['timeout']['read'])
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={
            'response': ' {"ok":true} ', 'done': True, 'done_reason': 'stop',
            'prompt_eval_count': 21, 'eval_count': 8, 'total_duration': 1000})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original_client(
        transport=httpx.MockTransport(respond), **kwargs))
    service = GenerationService()
    plain = asyncio.run(service.call_ollama('plain'))
    detailed = asyncio.run(service.call_ollama(
        'review', response_schema={'type': 'object'}, model='qwen3.5:4b',
        num_predict=2048, num_ctx=16384, think=False, timeout=360, return_metadata=True))
    assert plain == '{"ok":true}'
    assert detailed == {'text': plain, 'done': True, 'done_reason': 'stop',
                        'prompt_eval_count': 21, 'eval_count': 8, 'total_duration': 1000}
    assert payloads[0]['think'] is False
    assert payloads[1]['think'] is False
    assert payloads[1]['model'] == 'qwen3.5:4b'
    assert payloads[1]['format'] == {'type': 'object'}
    assert payloads[1]['options']['num_predict'] == 2048
    assert payloads[1]['options']['num_ctx'] == 16384
    assert asyncio.run(service.call_ollama('legacy explicit omission', think=None)) == plain
    assert 'think' not in payloads[2]
    assert timeouts == [service.timeout, 360, service.timeout]


def test_discovery_local_call_disables_proxy_and_redirect(monkeypatch):
    import pytest
    from app.core.exceptions import GenerationError
    options, hosts = [], []
    def redirect(request):
        hosts.append(request.url.host)
        return httpx.Response(302, headers={'location': 'https://example.org/model'})
    original = httpx.AsyncClient
    def client(**kwargs):
        options.append(kwargs)
        return original(transport=httpx.MockTransport(redirect), **kwargs)
    monkeypatch.setattr(httpx, 'AsyncClient', client)
    monkeypatch.setenv('HTTP_PROXY', 'http://example.org:8080')
    service = GenerationService()
    service.ollama_url = 'http://localhost:11434'
    with pytest.raises(GenerationError):
        asyncio.run(service.call_ollama('local', local_only=True))
    assert hosts == ['127.0.0.1']
    assert options[0]['trust_env'] is False and options[0]['follow_redirects'] is False
