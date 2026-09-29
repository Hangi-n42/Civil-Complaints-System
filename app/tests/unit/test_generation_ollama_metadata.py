"""The optional K3 metadata response preserves the existing string contract."""
import asyncio
import json

import httpx

from app.generation.service import GenerationService


def test_call_ollama_string_and_metadata_with_non_thinking_payload(monkeypatch):
    payloads = []
    def respond(request):
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
        num_predict=2048, num_ctx=16384, think=False, return_metadata=True))
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
