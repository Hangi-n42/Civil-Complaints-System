"""Actual version diff plus direct and newly relevant requirement reassessment."""
from difflib import SequenceMatcher
import json
from time import monotonic
from uuid import uuid4

from pydantic import BaseModel
from typing import Literal

from app.core.config import settings
from app.generation.model_client import configuration, ModelClient
from . import business_run
from .service import KnowledgeConflict, encode, utcnow


class Impact(BaseModel):
    requirement_id: str
    status: Literal['affected', 'unaffected', 'unknown']
    reason: str
    change_ids: list[str]
    new_relevance: bool


class Impacts(BaseModel):
    items: list[Impact]


def differences(before, after, key_fields):
    changes, unchanged = [], []
    if key_fields:
        def indexed(blocks):
            result = {}
            for b in blocks:
                fields = b['locator'].get('fields', {})
                if any(k not in fields for k in key_fields):
                    raise ValueError('변경 비교의 키 열이 없습니다.')
                key = tuple(str(fields[k]) for k in key_fields)
                if key in result:
                    raise ValueError('변경 비교 키가 중복됩니다.')
                result[key] = b
            return result
        old, new = indexed(before), indexed(after)
        for key in sorted(set(old) | set(new)):
            a, b = old.get(key), new.get(key)
            av, bv = a['locator']['fields'] if a else {}, b['locator']['fields'] if b else {}
            fields = [dict(field=k, before=av.get(k), after=bv.get(k)) for k in sorted(set(av) | set(bv)) if av.get(k) != bv.get(k)]
            item = dict(key=list(key), before_block_id=a['id'] if a else None, after_block_id=b['id'] if b else None,
                        before=av, after=bv, fields=fields)
            if fields:
                changes.append(dict(item, id=uuid4().hex, kind='added' if not a else 'removed' if not b else 'modified'))
            else:
                unchanged.append(item)
    else:
        matcher = SequenceMatcher(a=[b['text'] for b in before], b=[b['text'] for b in after], autojunk=False)
        for kind, i, j, p, q in matcher.get_opcodes():
            if kind == 'equal':
                unchanged.extend(dict(before_block_id=a['id'], after_block_id=b['id'], text=a['text']) for a, b in zip(before[i:j], after[p:q]))
            else:
                changes.append(dict(id=uuid4().hex, kind=kind, before=before[i:j], after=after[p:q],
                                    before_block_ids=[b['id'] for b in before[i:j]], after_block_ids=[b['id'] for b in after[p:q]]))
    return dict(changes=changes, unchanged=unchanged, comparison='exact_row_values' if key_fields else 'ordered_source_text')


def review_impacts(service, run, requirements, diff, versions, direct):
    result = business_run.json_call(service, run, 'change_impact',
        '원문 또는 근거 해석·후보 전후의 실제 변경과 각 업무 요구의 범위/조건을 대조한다. 기존 연결은 영향 후보이며 영향 확정이 아니다. '
        '기존 연결이 없어도 새 조건·예외·대상으로 관련되는 요구를 affected/new_relevance로 찾는다. '
        '각 요구를 빠짐없이 판정하고 실제 변경 id와 이유를 기록한다. 미변경 행/다른 대상은 유지한다. '
        '자료없는 보행·수요·안전·인과 효과는 추정하지 않는다. 결정 불가하면 unknown이다.',
        dict(requirements=requirements, direct_dependency_ids=direct, diff=diff, versions=versions), Impacts)
    valid = bool(result and len(result['items']) == len(requirements)
        and {r['requirement_id'] for r in result['items']} == {r['id'] for r in requirements})
    if valid and any(not set(r['change_ids']) <= {c['id'] for c in diff['changes']} for r in result['items']):
        valid = False
    if not valid:
        result = dict(items=[dict(requirement_id=r['id'], status='unknown', reason='불완전 변경 검수',
                                  change_ids=[], new_relevance=False) for r in requirements])
    return result, valid


def analyze(service, request):
    started = monotonic()
    config = configuration()
    models = dict(draft=settings.STRUCTURING_MODEL, review=settings.KNOWLEDGE_REVIEW_MODEL)
    identity = ModelClient(config).identities(models, {r:49152 for r in models})
    with service.lock, service.repository.connect() as db:
        if service.closed or any(json.loads(r['payload'])['status'] in {'queued', 'running', 'cancel_requested'}
                                 for r in db.execute('SELECT payload FROM runs')):
            raise KnowledgeConflict('다른 실행이 종료된 뒤 변경 영향을 확인하세요.')
        versions = [service.repository.get(db, 'versions', identifier) for identifier in (request.before_version_id, request.after_version_id)]
        if versions[0]['source_id'] != versions[1]['source_id']:
            raise ValueError('같은 출처의 전후 버전이 필요합니다.')
        if any(v['processing_status'] != 'parsed' for v in versions):
            raise ValueError('전후 원문의 파싱이 필요합니다.')
        blocks = [service.parse_blocks(db, v['latest_parse_run_id'], v['id']) for v in versions]
        requirements = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM requirements')]
        if request.requirement_ids:
            if not set(request.requirement_ids) <= {r['id'] for r in requirements}:
                raise ValueError('알 수 없는 업무 요구')
            requirements = [r for r in requirements if r['id'] in request.requirement_ids]
        if not requirements:
            raise ValueError('영향을 확인할 업무 요구가 없습니다.')
        diff = differences(*blocks, request.key_fields)
        direct = []
        for requirement in requirements:
            current = requirement.get('current_assessment')
            if current and request.before_version_id in current['source_version_ids']:
                direct.append(requirement['id'])
        recipe = dict(generation=config, models=models, options=dict(review_tokens=4096, extraction_tokens=4096,
                     concept_tokens=512, context_tokens=49152, timeout=1800, think=False))
        run = dict(id=uuid4().hex, kind='business_change', status='running', units=[], input_version_ids=[v['id'] for v in versions],
                   recipe=recipe, started_at=utcnow(), finished_at=None, metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0),
                   diff=diff, direct_dependency_ids=direct, requirements=requirements, request=request.model_dump(),
                   model_identity=identity)
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
    # ponytail: inspect all selected requirements, including unlinked ones. Add a
    # measured candidate index only when the requirement inventory outgrows this.
    result, valid = review_impacts(service, run, requirements, diff, versions, direct)
    with service.lock, service.repository.connect() as db:
        for impact in result['items']:
            current = service.repository.get(db, 'requirements', impact['requirement_id'])
            old = next(r for r in requirements if r['id'] == current['id'])
            if current['revision'] != old['revision']:
                impact.update(status='unknown', reason='판정 중 요구 버전 변경')
            current.setdefault('change_history', []).append(dict(run_id=run['id'], impact=impact, recorded_at=utcnow()))
            if impact['status'] != 'unaffected':
                current['status'] = 'needs_review'
            service.repository.save(db, 'requirements', current)
        run.update(status='cancelled' if run['status'] == 'cancel_requested' else 'succeeded' if valid else 'partial', impacts=result['items'], finished_at=utcnow())
        run['metrics']['elapsed_s'] = monotonic() - started
        service.repository.save(db, 'runs', run)
    return run
