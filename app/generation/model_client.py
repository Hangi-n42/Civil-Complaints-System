"""Knowledge generation contract: explicit provider, no fallback or implicit retries."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from time import monotonic
from typing import Callable
from uuid import uuid4

import httpx


@dataclass(frozen=True)
class ModelRequest:
    stage: str
    model: str
    messages: list[dict[str, str]]
    schema: dict | None = None
    max_tokens: int = 4096
    context_tokens: int = 49152
    temperature: float = 0
    think: bool | None = False
    timeout: float = 1800
    request_id: str = field(default_factory=lambda: uuid4().hex)


def configuration():
    from app.core.config import settings
    provider = settings.KNOWLEDGE_GENERATION_PROVIDER
    return dict(provider=provider,
                endpoint=settings.OLLAMA_BASE_URL if provider == 'ollama' else settings.KNOWLEDGE_GENERATION_ENDPOINT,
                auth_env=settings.KNOWLEDGE_GENERATION_AUTH_ENV,
                context_length=settings.KNOWLEDGE_GENERATION_CONTEXT_LENGTH)


class ModelClient:
    """The two supported transports share records, not provider-specific options."""
    def __init__(self, config=None, *, transport=None):
        self.config = dict(config or configuration())
        self.provider = self.config['provider']
        if self.provider not in {'ollama', 'openai_chat'}:
            raise ValueError('Unsupported generation adapter')
        self.endpoint = self.config['endpoint'].rstrip('/')
        if self.provider == 'ollama':
            from .service import local_ollama_url
            self.endpoint = local_ollama_url(self.endpoint)
        elif not self.endpoint.startswith(('http://', 'https://')):
            raise ValueError('An HTTP(S) API endpoint is required')
        self.transport = transport

    def identities(self, models, required_context):
        if self.provider == 'openai_chat':
            # This is configured identity, not a claimed remote model digest.
            length = self.config.get('context_length')
            if not length or any(required_context[r] > length for r in models):
                raise ValueError('External adapter requires an adequate declared context length')
            return {r: dict(name=n, digest=None, provider=self.provider,
                            context_length=length, identity_source='configured') for r, n in models.items()}
        with httpx.Client(timeout=15, trust_env=False, follow_redirects=False, transport=self.transport) as client:
            response = client.get(self.endpoint + '/api/tags')
            response.raise_for_status()
            installed = {m['name']: m for m in response.json()['models']}
            result = {}
            for role, name in models.items():
                if name not in installed:
                    raise ValueError('설치된 로컬 모델이 없습니다: ' + name)
                response = client.post(self.endpoint + '/api/show', json={'model': name})
                response.raise_for_status()
                lengths = [int(v) for k, v in response.json().get('model_info', {}).items()
                           if k.endswith('.context_length')]
                if not lengths or min(lengths) < required_context[role]:
                    raise ValueError('모델의 선언 컨텍스트가 실행 설정보다 작거나 확인 불가합니다.')
                result[role] = dict(name=name, digest=installed[name]['digest'], context_length=min(lengths))
            return result

    async def generate(self, request: ModelRequest, cancelled: Callable[[], bool] | None = None):
        if request.max_tokens <= 0 or request.context_tokens <= request.max_tokens or request.timeout <= 0:
            raise ValueError('Invalid generation limits')
        headers = {}
        if self.provider == 'ollama':
            payload = dict(model=request.model, messages=request.messages, stream=False,
                           options=dict(temperature=request.temperature, num_predict=request.max_tokens,
                                        num_ctx=request.context_tokens))
            if request.schema is not None:
                payload['format'] = request.schema
            if request.think is not None:
                payload['think'] = request.think
            url = self.endpoint + '/api/chat'
        else:
            if request.think not in {None, False}:
                raise ValueError('openai_chat adapter does not support the Ollama think option')
            if request.context_tokens > self.config.get('context_length', 0):
                raise ValueError('Requested context exceeds the configured external context')
            payload = dict(model=request.model, messages=request.messages, stream=False,
                           temperature=request.temperature, max_tokens=request.max_tokens)
            if request.schema is not None:
                payload['response_format'] = dict(type='json_schema', json_schema=dict(
                    name='knowledge_response', strict=True, schema=request.schema))
            secret = os.getenv(self.config.get('auth_env', ''), '')
            if secret:
                headers['Authorization'] = 'Bearer ' + secret
            url = self.endpoint + '/chat/completions'
        started = monotonic()
        result = dict(request_id=request.request_id, stage=request.stage, provider=self.provider,
                      model=request.model, text='', parsed=None, raw_response=None, done=False,
                      done_reason=None, failure_kind=None, prompt_eval_count=None, eval_count=None,
                      usage_source='unavailable', elapsed_s=0, input_chars=sum(len(m['content']) for m in request.messages))
        try:
            if cancelled and cancelled():
                result['failure_kind'] = 'cancelled'
                return result
            async with httpx.AsyncClient(timeout=request.timeout, trust_env=False, follow_redirects=False,
                                         transport=self.transport) as client:
                task = asyncio.create_task(client.post(url, json=payload, headers=headers))
                try:
                    while not task.done():
                        await asyncio.wait({task}, timeout=0.2)
                        if cancelled and cancelled():
                            task.cancel()
                            result['failure_kind'] = 'cancelled'
                            return result
                    response = await task
                finally:
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                response.raise_for_status()
                data = response.json()
            result['raw_response'] = data
            if self.provider == 'ollama':
                result.update(text=data.get('message', {}).get('content', ''), done=data.get('done', False),
                              done_reason=data.get('done_reason'), prompt_eval_count=data.get('prompt_eval_count'),
                              eval_count=data.get('eval_count'), total_duration=data.get('total_duration'))
            else:
                choice = data['choices'][0]
                usage = data.get('usage') or {}
                result.update(text=choice['message'].get('content') or '', done=True,
                              done_reason=choice.get('finish_reason'), prompt_eval_count=usage.get('prompt_tokens'),
                              eval_count=usage.get('completion_tokens'), remote_model=data.get('model'))
            if result['prompt_eval_count'] is not None or result['eval_count'] is not None:
                result['usage_source'] = 'provider_reported'
            if result['done_reason'] in {'length', 'max_tokens'} or not result['done']:
                result['failure_kind'] = 'truncated'
            elif not result['text'].strip():
                result['failure_kind'] = 'empty_output'
            elif request.schema is not None:
                try:
                    result['parsed'] = json.loads(result['text'])
                except (TypeError, ValueError):
                    result['failure_kind'] = 'invalid_json'
        except httpx.TimeoutException:
            result['failure_kind'] = 'timeout'
        except httpx.HTTPStatusError as exc:
            result.update(failure_kind='http_error', http_status=exc.response.status_code)
        except httpx.HTTPError:
            result['failure_kind'] = 'transport_error'
        except (KeyError, IndexError, TypeError, ValueError):
            result['failure_kind'] = 'invalid_response'
        finally:
            result['elapsed_s'] = round(monotonic() - started, 6)
        return result


async def legacy_call(prompt, schema, stage, model, *, recipe=None, num_predict=4096,
                      num_ctx=49152, think=False, timeout=1800):
    """Retain existing knowledge callers' metadata interface and failure handling."""
    from app.core.exceptions import GenerationError
    result = await ModelClient((recipe or {}).get('generation')).generate(ModelRequest(
        stage=stage, model=model, messages=[dict(role='user', content=prompt)], schema=schema,
        max_tokens=num_predict, context_tokens=num_ctx, think=think, timeout=timeout or 1800))
    if result['failure_kind']:
        raise GenerationError('모델 호출 실패: ' + result['failure_kind'], code='PROCESSING_ERROR',
                              retryable=False, details=result)
    return result
